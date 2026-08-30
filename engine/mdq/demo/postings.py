"""Posten des Basis-Mandanten: Rechnungen, Zahlungen, Gutschriften.

Eine Rechnung ist entweder am Datenstand noch offen (BSID/BSIK) oder durch genau eine
Zahlung ausgeglichen (BSAD/BSAK). Die Zahlung ist ein eigener Beleg und steht als eigene
Zeile in den ausgeglichenen Posten – so sieht ein FI-Export aus.

Geld ist durchgehend ``Decimal`` und wird in Cent gezogen (Regel 2, D-009): ein float
wäre hier der kürzeste Weg zu einer Zahlung, die nicht zur Rechnung passt.

Zwei Invarianten halten den Basis-Mandanten frei von Zufallstreffern:

* **Kein Belegpaar wie AP-LEA-001.** Zwei Rechnungen desselben Partners mit gleichem
  Betrag innerhalb von 60 Tagen wären zusammen mit ähnlicher Referenz eine mögliche
  Doppelzahlung. Deshalb wird ein Betrag neu gezogen, wenn er beim selben Partner schon
  innerhalb von 60 Tagen vorkommt.
* **Kein Skontoverlust über der Meldegrenze.** AP-LEA-002 meldet ab 1.000,00 in zwölf
  Monaten. Würde ein Zahler diese Grenze reißen, zieht er das Skonto ausnahmsweise doch.
"""

from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal

from mdq.demo import (
    CREDIT_MEMO_SHARE,
    DATA_AS_OF,
    DOC_TYPES,
    INVOICE_AMOUNT_CENTS,
    INVOICE_COUNTS,
    LOCAL_CURRENCY,
    OPEN_PROBABILITY_BY_AGE,
    PAYER_PROFILES,
    PAYMENT_TERMS,
    SKONTO_LOSS_LIMIT,
    WINDOW_END,
    WINDOW_START,
)
from mdq.demo.base import Partner

#: Buchungsschlüssel je Belegart und Seite
POSTING_KEYS = {
    "customer_invoice": "01",
    "customer_payment": "15",
    "customer_credit": "11",
    "vendor_invoice": "31",
    "vendor_payment": "25",
    "vendor_credit": "21",
}

#: Soll-/Haben-Kennzeichen je Belegart
DEBIT_CREDIT = {
    "customer_invoice": "S",
    "customer_payment": "H",
    "customer_credit": "H",
    "vendor_invoice": "H",
    "vendor_payment": "S",
    "vendor_credit": "S",
}

#: Abstand gleicher Beträge beim selben Partner, unterhalb dessen neu gezogen wird
SAME_AMOUNT_WINDOW_DAYS = 60

_TERMS_BY_KEY = {entry[0]: entry for entry in PAYMENT_TERMS}
_PROFILE_BY_NAME = {entry[0]: entry for entry in PAYER_PROFILES}


@dataclass(frozen=True)
class FiItem:
    """Eine Einzelpostenzeile auf einem Personenkonto (BSID/BSAD/BSIK/BSAK)."""

    role: str
    bp_number: str
    company_code: str
    fiscal_year: str
    document_no: str
    line_item: str
    posting_date: date
    document_date: date
    doc_type: str
    posting_key: str
    debit_credit: str
    amount: Decimal
    reference: str
    assignment: str
    item_text: str
    baseline_date: date
    payment_terms: str
    disc_days1: int
    disc_pct1: Decimal
    disc_base: Decimal
    disc_taken: Decimal
    payment_method: str
    gl_account: str
    clearing_date: date | None
    clearing_doc: str
    is_open: bool


@dataclass
class _Invoice:
    """Zwischenstand einer Rechnung, bevor Belegnummern vergeben sind."""

    partner: Partner
    company_code: str
    payment_terms: str
    document_date: date
    posting_date: date
    amount: Decimal
    payment_method: str
    reference: str
    disc_taken: Decimal
    payment_date: date | None
    document_no: str = ""
    payment_no: str = ""


class _DocumentNumbers:
    """Belegnummernkreise je Präfix, Buchungskreis und Geschäftsjahr."""

    def __init__(self) -> None:
        self._counters: dict[tuple[str, str, str], int] = {}

    def next(self, prefix: str, company_code: str, fiscal_year: str) -> str:
        key = (prefix, company_code, fiscal_year)
        value = self._counters.get(key, 0) + 1
        self._counters[key] = value
        return f"{prefix}{value:08d}"


def _workday(value: date) -> date:
    """Nächster Werktag – Belege werden nicht am Wochenende gebucht."""
    while value.weekday() >= 5:
        value += timedelta(days=1)
    return value


def _open_probability(document_date: date) -> float:
    """Wahrscheinlichkeit, dass eine Rechnung dieses Alters noch offen ist."""
    age = (DATA_AS_OF - document_date).days
    for limit, probability in OPEN_PROBABILITY_BY_AGE:
        if age <= limit:
            return probability
    return OPEN_PROBABILITY_BY_AGE[-1][1]  # pragma: no cover – letzte Schwelle fängt alles


def _payment_date(rng, profile: str, baseline: date, disc_days: int, net_days: int,
                  take_discount: bool) -> date:
    """Zahltag aus dem Zahlerprofil des Partners."""
    if take_discount:
        earliest = max(1, disc_days - 3)
        return _workday(baseline + timedelta(days=rng.randint(earliest, max(earliest, disc_days))))
    _, _, mean_delay, spread = _PROFILE_BY_NAME[profile]
    delay = round(rng.gauss(mean_delay, spread))
    due = baseline + timedelta(days=net_days)
    return _workday(max(due + timedelta(days=delay), baseline + timedelta(days=1)))


def _draw_amount(rng, partner: Partner, document_date: date,
                 seen: dict[Decimal, list[date]]) -> Decimal:
    """Rechnungsbetrag; gleiche Beträge beim selben Partner halten 60 Tage Abstand."""
    low, high = INVOICE_AMOUNT_CENTS[partner.size_class]
    while True:
        amount = (Decimal(rng.randint(low, high)) / 100).quantize(Decimal("0.01"))
        dates = seen.get(amount, ())
        if all(abs((document_date - other).days) > SAME_AMOUNT_WINDOW_DAYS for other in dates):
            seen.setdefault(amount, []).append(document_date)
            return amount


def _build_invoices(rng, partner: Partner, references) -> list[_Invoice]:
    """Alle Rechnungen eines Partners samt Zahlungsentscheidung."""
    count_low, count_high = INVOICE_COUNTS[partner.role][partner.size_class]
    invoices: list[_Invoice] = []
    seen_amounts: dict[Decimal, list[date]] = {}
    # Skontoverlust je rollierendem Jahr, damit AP-LEA-002 im Basis-Mandanten schweigt
    skonto_loss = Decimal("0.00")
    span = (WINDOW_END - WINDOW_START).days

    for _ in range(rng.randint(count_low, count_high)):
        company = rng.choice(partner.company_codes)
        document_date = _workday(WINDOW_START + timedelta(days=rng.randint(0, span)))
        if document_date > WINDOW_END:
            continue
        posting_date = _workday(document_date + timedelta(days=rng.randint(0, 3)))
        if posting_date > WINDOW_END:
            posting_date = document_date
        amount = _draw_amount(rng, partner, document_date, seen_amounts)

        _, disc_days, disc_pct, net_days, _ = _TERMS_BY_KEY[company.payment_terms]
        has_discount = disc_days > 0 and disc_pct > 0
        take_discount = has_discount and partner.payer_profile == "skontotreu"

        is_open = rng.random() < _open_probability(document_date)
        payment_date = None
        disc_taken = Decimal("0.00")

        if not is_open:
            payment_date = _payment_date(
                rng, partner.payer_profile, document_date, disc_days, net_days, take_discount
            )
            missed = has_discount and payment_date > document_date + timedelta(days=disc_days)
            if missed and partner.role == "VENDOR":
                loss = (amount * disc_pct / 100).quantize(Decimal("0.01"))
                if skonto_loss + loss > SKONTO_LOSS_LIMIT:
                    # Grenze erreicht: dieser Zahler zieht das Skonto doch
                    payment_date = _payment_date(
                        rng, partner.payer_profile, document_date, disc_days, net_days, True
                    )
                    missed = False
                else:
                    skonto_loss += loss
            if has_discount and not missed:
                disc_taken = (amount * disc_pct / 100).quantize(Decimal("0.01"))
            if payment_date > WINDOW_END:
                # Nach dem Datenstand kann nicht gezahlt worden sein – Posten bleibt offen
                payment_date = None
                disc_taken = Decimal("0.00")

        invoices.append(
            _Invoice(
                partner=partner,
                company_code=company.company_code,
                payment_terms=company.payment_terms,
                document_date=document_date,
                posting_date=posting_date,
                amount=amount,
                payment_method=company.payment_methods,
                reference=next(references),
                disc_taken=disc_taken,
                payment_date=payment_date,
            )
        )
    return invoices


def _reference_stream(prefix: str):
    """Fortlaufende, mandantenweit eindeutige Belegreferenzen (XBLNR)."""
    counter = 100000
    while True:
        counter += 1
        yield f"{prefix}-{counter}"


def _item_from_invoice(invoice: _Invoice, kind: str) -> FiItem:
    """Rechnungszeile; ausgeglichen genau dann, wenn eine Zahlung existiert."""
    partner = invoice.partner
    _, disc_days, disc_pct, _, _ = _TERMS_BY_KEY[invoice.payment_terms]
    has_discount = disc_days > 0 and disc_pct > 0
    return FiItem(
        role=partner.role,
        bp_number=partner.number,
        company_code=invoice.company_code,
        fiscal_year=f"{invoice.posting_date.year}",
        document_no=invoice.document_no,
        line_item="001",
        posting_date=invoice.posting_date,
        document_date=invoice.document_date,
        doc_type=DOC_TYPES[kind][0],
        posting_key=POSTING_KEYS[kind],
        debit_credit=DEBIT_CREDIT[kind],
        amount=invoice.amount,
        reference=invoice.reference,
        assignment=invoice.document_date.strftime("%Y%m%d"),
        item_text="Rechnung",
        baseline_date=invoice.document_date,
        payment_terms=invoice.payment_terms,
        disc_days1=disc_days,
        disc_pct1=disc_pct,
        disc_base=invoice.amount if has_discount else Decimal("0.00"),
        disc_taken=invoice.disc_taken,
        payment_method=invoice.payment_method,
        gl_account="",
        clearing_date=invoice.payment_date,
        clearing_doc=invoice.payment_no,
        is_open=invoice.payment_date is None,
    )


def _item_from_payment(invoice: _Invoice, kind: str) -> FiItem:
    """Zahlungszeile: Rechnungsbetrag minus gezogenes Skonto."""
    partner = invoice.partner
    return FiItem(
        role=partner.role,
        bp_number=partner.number,
        company_code=invoice.company_code,
        fiscal_year=f"{invoice.payment_date.year}",
        document_no=invoice.payment_no,
        line_item="001",
        posting_date=invoice.payment_date,
        document_date=invoice.payment_date,
        doc_type=DOC_TYPES[kind][0],
        posting_key=POSTING_KEYS[kind],
        debit_credit=DEBIT_CREDIT[kind],
        amount=invoice.amount - invoice.disc_taken,
        reference="",
        assignment=invoice.document_no,
        item_text="Zahlung",
        baseline_date=invoice.payment_date,
        payment_terms="",
        disc_days1=0,
        disc_pct1=Decimal("0.000"),
        disc_base=Decimal("0.00"),
        disc_taken=Decimal("0.00"),
        payment_method=invoice.payment_method,
        gl_account="",
        clearing_date=invoice.payment_date,
        clearing_doc=invoice.payment_no,
        is_open=False,
    )


def _credit_memo(rng, invoice: _Invoice, kind: str, document_no: str) -> FiItem:
    """Offene Gutschrift, aus einer Rechnung abgeleitet."""
    partner = invoice.partner
    share = Decimal(rng.randint(5, 20)) / 100
    amount = (invoice.amount * share).quantize(Decimal("0.01"))
    document_date = _workday(min(invoice.document_date + timedelta(days=rng.randint(5, 45)),
                                 WINDOW_END))
    return FiItem(
        role=partner.role,
        bp_number=partner.number,
        company_code=invoice.company_code,
        fiscal_year=f"{document_date.year}",
        document_no=document_no,
        line_item="001",
        posting_date=document_date,
        document_date=document_date,
        doc_type=DOC_TYPES[kind][0],
        posting_key=POSTING_KEYS[kind],
        debit_credit=DEBIT_CREDIT[kind],
        amount=amount,
        reference=f"GS-{invoice.reference}",
        assignment=invoice.document_no,
        item_text="Gutschrift",
        baseline_date=document_date,
        payment_terms=invoice.payment_terms,
        disc_days1=0,
        disc_pct1=Decimal("0.000"),
        disc_base=Decimal("0.00"),
        disc_taken=Decimal("0.00"),
        payment_method=invoice.payment_method,
        gl_account="",
        clearing_date=None,
        clearing_doc="",
        is_open=True,
    )


def build_items(rng, partners: list[Partner], role: str) -> list[FiItem]:
    """Alle Posten einer Seite, mit Belegnummern in Buchungsreihenfolge."""
    side = "customer" if role == "CUSTOMER" else "vendor"
    references = _reference_stream("RG" if role == "CUSTOMER" else "RE")
    numbers = _DocumentNumbers()

    invoices: list[_Invoice] = []
    for partner in partners:
        invoices.extend(_build_invoices(rng, partner, references))

    # Belegnummern in Buchungsreihenfolge vergeben, wie SAP sie zieht
    invoices.sort(key=lambda inv: (inv.posting_date, inv.partner.number, inv.reference))
    invoice_prefix = DOC_TYPES[f"{side}_invoice"][1]
    for index, invoice in enumerate(invoices):
        invoices[index] = replace(
            invoice,
            document_no=numbers.next(
                invoice_prefix, invoice.company_code, f"{invoice.posting_date.year}"
            ),
        )

    paid = sorted(
        (invoice for invoice in invoices if invoice.payment_date is not None),
        key=lambda inv: (inv.payment_date, inv.partner.number, inv.document_no),
    )
    payment_prefix = DOC_TYPES[f"{side}_payment"][1]
    for invoice in paid:
        invoice.payment_no = numbers.next(
            payment_prefix, invoice.company_code, f"{invoice.payment_date.year}"
        )

    items: list[FiItem] = []
    for invoice in invoices:
        items.append(_item_from_invoice(invoice, f"{side}_invoice"))
        if invoice.payment_date is not None:
            items.append(_item_from_payment(invoice, f"{side}_payment"))

    credit_prefix = DOC_TYPES[f"{side}_credit"][1]
    for invoice in invoices:
        if rng.random() < CREDIT_MEMO_SHARE:
            document_date = invoice.document_date
            number = numbers.next(credit_prefix, invoice.company_code, f"{document_date.year}")
            items.append(_credit_memo(rng, invoice, f"{side}_credit", number))

    items.sort(key=lambda item: (item.company_code, item.fiscal_year, item.document_no))
    return items


def currency() -> str:
    """Hauswährung des Mandanten – V1 kennt genau eine (D-030)."""
    return LOCAL_CURRENCY
