"""Defekt-Schicht: die bewusst eingebauten Fehler des Demo-Mandanten.

Grundidee des Sprints (`docs/specs/SPRINT-2.md`): **Fehler sind Daten, nicht Code.** Der
Basis-Mandant ist regelfrei (D-045); diese Schicht wendet die Liste aus
`testdata/demo_mandant/defects.yaml` darauf an und liefert zugleich die Findings, die
daraus entstehen müssen. Aus dieser Liste wird `testdata/expected/expected_findings.yaml`
erzeugt – sie wird nie von Hand gepflegt (Regel 1, D-010).

Jeder Defekttyp ist eine kleine Funktion mit :func:`defect_type`-Registrierung und einem
Docstring, der den Defekt in einem Satz erklärt. Ein unbekannter Typ ist ein Fehler und
kein übersprungener Eintrag (Regel 4).

Determinismus (Regel 9, D-047): jeder Defekt zieht seinen eigenen Zufallsstrom über
``random_for(seed, "defect:<id>")``. Ein neuer Defekt verschiebt damit keinen bestehenden.

Belegungsplan: ein Konto trägt höchstens einen Defekt. Wo zwei Defekte dasselbe Konto
brauchen – etwa eine Dublette, die zugleich Soll-Quelle für ein falsches USt-ID-Präfix
ist – meldet der zweite das mit ``overlaps`` an. Alles andere ist ein Fehler, damit kein
Finding entsteht, das kein Defekt erklärt.
"""

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import yaml
from schwifty import IBAN

from mdq.demo import (
    CUSTOMER_ACCOUNT_GROUPS,
    DATA_AS_OF,
    DOC_TYPES,
    PAYMENT_TERMS,
    VENDOR_ACCOUNT_GROUPS,
    WINDOW_END,
    WINDOW_START,
    random_for,
)
from mdq.demo.base import (
    LANGUAGE_BY_COUNTRY,
    BankAccount,
    CompanyCodeData,
    Partner,
    foreign_vat_id,
)
from mdq.demo.geo import Place
from mdq.demo.postings import DEBIT_CREDIT, POSTING_KEYS, FiItem, workday

#: Cent-Quantisierung – jeder Betrag im Generator ist Decimal (Regel 2)
CENT = Decimal("0.01")

#: Zwölf-Monats-Fenster der Relevanz (D-051). Untergrenze ist der Tag nach dem
#: Stichtag vor einem Jahr, damit "in den letzten 12 Monaten" ein geschlossener
#: Zeitraum ist.
WINDOW_12M_START = DATA_AS_OF - timedelta(days=364)

#: Kleinster Einzelbetrag, in den ein Gesamtvolumen zerlegt wird
MIN_INVOICE_AMOUNT = Decimal("100.00")

#: Versuche, ein Volumen in lauter verschiedene Beträge zu zerlegen
_SPLIT_ATTEMPTS = 50

_TERMS_BY_KEY = {entry[0]: entry for entry in PAYMENT_TERMS}

#: Länder, deren Präfix ein Defekt vom Typ ``vat_prefix`` vergibt. Alle fünf sind im
#: Wörterbuch `vat_id_patterns.yaml` beschrieben, die erzeugte Nummer ist also im Format
#: ihres Landes gültig – der Fehler ist allein das Präfix (D-053).
_FOREIGN_VAT_COUNTRIES = ("AT", "NL", "FR", "IT", "PL")

#: Umschrift für die Dubletten-Variante "Umlaut/Transliteration"
_TRANSLITERATION = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
}

#: Zweitschreibweise je Rechtsform für die Dubletten-Variante "Rechtsform-Schreibweise"
_LEGAL_FORM_VARIANTS = {
    "GmbH": "G.m.b.H.",
    "GmbH & Co. KG": "GmbH & Co KG",
    "AG": "Aktiengesellschaft",
    "KG": "Kommanditgesellschaft",
    "OHG": "oHG",
    "e.K.": "eK",
    "UG (haftungsbeschränkt)": "UG haftungsbeschraenkt",
    "SE": "S.E.",
    "eG": "e.G.",
    "KGaA": "KG a.A.",
    "B.V.": "BV",
    "N.V.": "NV",
    "S.A.R.L.": "SARL",
    "S.A.S.": "SAS",
    "S.A.": "SA",
    "S.r.l.": "Srl",
    "S.p.A.": "SpA",
    "Sp. z o.o.": "Sp. z o. o.",
    "Inc.": "Inc",
    "LLC": "L.L.C.",
    "Corp.": "Corp",
}


class DefectError(ValueError):
    """Ein Defekt ist nicht anwendbar: unbekannter Typ, unbekanntes Konto, unmögliche Werte."""


@dataclass(frozen=True)
class Hit:
    """Ein Treffer, den ein Defekt erzeugt – Konto, optional Buchungskreis und Beleg."""

    bp_key: str
    company_code: str | None = None
    document_no: str | None = None
    finding_key: str | None = None


@dataclass(frozen=True)
class ExpectedFinding:
    """Ein Finding, das der Lauf auf dem Demo-Mandanten liefern muss."""

    rule_id: str
    bp_key: str
    defect_id: str
    company_code: str | None = None
    document_no: str | None = None
    finding_key: str | None = None
    #: Regelversion, ab der dieses Finding Pflicht ist; davor bekannt-offen (D-054)
    from_rule_version: str | None = None

    @property
    def sort_key(self) -> tuple[str, ...]:
        """Feste Reihenfolge der erwarteten Liste – ohne sie wäre sie nicht deterministisch."""
        return (
            self.rule_id,
            self.bp_key,
            self.company_code or "",
            self.document_no or "",
            self.finding_key or "",
        )

    def to_dict(self) -> dict[str, str]:
        """Eintrag für `expected_findings.yaml`; leere Felder bleiben weg."""
        data = {"rule_id": self.rule_id, "bp_key": self.bp_key}
        for name in ("company_code", "document_no", "finding_key", "from_rule_version"):
            value = getattr(self, name)
            if value is not None:
                data[name] = value
        data["defect"] = self.defect_id
        return data


@dataclass(frozen=True)
class Defect:
    """Ein Eintrag aus `defects.yaml`."""

    id: str
    type: str
    note: str
    params: dict
    expected: tuple[dict, ...]
    overlaps: tuple[str, ...]


#: Erlaubte Schlüssel eines Defekt-Eintrags und eines erwarteten Findings
_DEFECT_FIELDS = frozenset({"id", "type", "note", "params", "expected", "overlaps"})
_EXPECTED_FIELDS = frozenset(
    {"rule_id", "bp_key", "company_code", "document_no", "finding_key", "from_rule_version"}
)


def load_defects(path: Path, seed: int | None = None) -> tuple[Defect, ...]:
    """Liest `defects.yaml` und prüft jeden Eintrag, bevor irgendetwas angewendet wird.

    Unbekannte Felder sind ein Fehler und keine stille Auslassung (Regel 4). Alle Probleme
    einer Datei werden gemeinsam gemeldet, damit sie in einem Durchgang zu beheben sind
    (gleiche Linie wie D-023 beim Regel-Loader).

    Die Datei nennt konkrete Kontonummern und gilt damit für genau den Seed, unter dem sie
    entstanden ist. Wird mit einem anderen Seed erzeugt, bricht der Lauf hier ab – sonst
    liefe er in unverständliche Folgefehler ("Konto gibt es nicht").
    """
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict) or "defects" not in document:
        raise DefectError(f"{path.name}: erwartet einen Schlüssel 'defects'.")
    if seed is not None and document.get("seed") != seed:
        raise DefectError(
            f"{path.name} ist auf Seed {document.get('seed')} ausgelegt, erzeugt wird mit "
            f"Seed {seed}. Die Defekte nennen konkrete Kontonummern; für einen anderen "
            "Seed den Mandanten mit --no-defects erzeugen."
        )

    problems: list[str] = []
    defects: list[Defect] = []
    seen: set[str] = set()

    for position, entry in enumerate(document["defects"] or (), start=1):
        where = f"{path.name}, Eintrag {position}"
        if not isinstance(entry, dict):
            problems.append(f"{where}: kein Objekt.")
            continue

        unknown = sorted(set(entry) - _DEFECT_FIELDS)
        if unknown:
            problems.append(f"{where}: unbekannte Felder: {', '.join(unknown)}.")

        identifier = entry.get("id")
        if not isinstance(identifier, str) or not identifier:
            problems.append(f"{where}: 'id' fehlt oder ist leer.")
            continue
        where = f"{path.name}, Defekt {identifier}"
        if identifier in seen:
            problems.append(f"{where}: doppelte id.")
        seen.add(identifier)

        kind = entry.get("type")
        if kind not in _HANDLERS:
            known = ", ".join(defect_types())
            problems.append(f"{where}: unbekannter Defekttyp {kind!r}. Bekannt: {known}.")

        note = entry.get("note")
        if not isinstance(note, str) or not note.strip():
            problems.append(f"{where}: 'note' fehlt – jeder Defekt braucht einen fachlichen Satz.")

        params = entry.get("params", {})
        if not isinstance(params, dict):
            problems.append(f"{where}: 'params' ist kein Objekt.")
            params = {}

        expected = entry.get("expected")
        if expected is None:
            problems.append(f"{where}: 'expected' fehlt – Negativfälle tragen ausdrücklich [].")
            expected = []
        for spec in expected:
            if not isinstance(spec, dict) or "rule_id" not in spec:
                problems.append(f"{where}: erwartetes Finding ohne 'rule_id'.")
                continue
            extra = sorted(set(spec) - _EXPECTED_FIELDS)
            if extra:
                problems.append(f"{where}: erwartetes Finding mit unbekannten Feldern: {extra}.")

        overlaps = tuple(entry.get("overlaps", ()))
        for other in overlaps:
            if other not in seen:
                problems.append(f"{where}: overlaps verweist auf unbekannten Defekt {other}.")

        defects.append(
            Defect(
                id=identifier,
                type=kind,
                note=note if isinstance(note, str) else "",
                params=params,
                expected=tuple(expected),
                overlaps=overlaps,
            )
        )

    if problems:
        raise DefectError("\n".join(problems))
    return tuple(defects)


class _Numbering:
    """Belegnummern für neue Belege – setzt je Nummernkreis hinter dem Basis-Mandanten auf.

    Der Basis-Mandant vergibt je (Präfix, Buchungskreis, Geschäftsjahr) fortlaufend; die
    Defekt-Schicht macht dort weiter und überspringt Nummern, die ein Ankerfall fest
    belegt hat. Eine doppelt vergebene Belegnummer wäre ein Fehler und kein Zufall.
    """

    def __init__(self, items: Iterable[FiItem]) -> None:
        self._counters: dict[tuple[str, str, str], int] = {}
        self._used: set[tuple[str, str, str]] = set()
        for item in items:
            prefix = item.document_no[:2]
            key = (prefix, item.company_code, item.fiscal_year)
            self._counters[key] = max(self._counters.get(key, 0), int(item.document_no[2:]))
            self._used.add((item.company_code, item.fiscal_year, item.document_no))

    def next(self, prefix: str, company_code: str, fiscal_year: str) -> str:
        """Nächste freie Nummer im Kreis."""
        key = (prefix, company_code, fiscal_year)
        counter = self._counters.get(key, 0)
        while True:
            counter += 1
            number = f"{prefix}{counter:08d}"
            if (company_code, fiscal_year, number) not in self._used:
                break
        self._counters[key] = counter
        self._used.add((company_code, fiscal_year, number))
        return number

    def reserve(self, number: str, company_code: str, fiscal_year: str) -> str:
        """Belegt eine fest vorgegebene Nummer (Ankerfälle) und meldet Kollisionen."""
        key = (company_code, fiscal_year, number)
        if key in self._used:
            raise DefectError(
                f"Belegnummer {number} ist in {company_code}/{fiscal_year} schon vergeben."
            )
        self._used.add(key)
        return number


class _References:
    """Belegreferenzen (XBLNR) hinter dem Basis-Mandanten, mandantenweit eindeutig."""

    def __init__(self, items: Iterable[FiItem]) -> None:
        self._counter = 0
        for item in items:
            match = re.fullmatch(r"(?:RG|RE)-(\d+)", item.reference)
            if match:
                self._counter = max(self._counter, int(match.group(1)))

    def next(self, role: str) -> str:
        self._counter += 1
        return f"{'RG' if role == 'CUSTOMER' else 'RE'}-{self._counter}"


class DemoModel:
    """Der Mandant zwischen Basis und Export: Stammsätze und Posten, änderbar.

    Der Basis-Mandant liefert unveränderliche ``Partner``- und ``FiItem``-Objekte; hier
    werden sie über ``dataclasses.replace`` ersetzt, nie in place verändert. Rohdaten
    werden nicht angefasst – der Export entsteht danach wie zuvor aus dem Modell.
    """

    def __init__(
        self,
        customers: Sequence[Partner],
        vendors: Sequence[Partner],
        customer_items: Sequence[FiItem],
        vendor_items: Sequence[FiItem],
    ) -> None:
        self._partners: dict[str, Partner] = {p.bp_key: p for p in (*customers, *vendors)}
        self._items: list[FiItem] = [*customer_items, *vendor_items]
        self.numbering = _Numbering(self._items)
        self.references = _References(self._items)
        self._claims: dict[str, str] = {}

    # --- Stammsätze ------------------------------------------------------------------

    def partner(self, bp_key: str) -> Partner:
        """Partner zum kanonischen Schlüssel; unbekannt ist ein Fehler."""
        try:
            return self._partners[bp_key]
        except KeyError:
            raise DefectError(f"Konto {bp_key} gibt es im Basis-Mandanten nicht.") from None

    def update(self, bp_key: str, **changes) -> Partner:
        """Ersetzt Felder eines Stammsatzes."""
        updated = replace(self.partner(bp_key), **changes)
        self._partners[bp_key] = updated
        return updated

    def company_of(self, bp_key: str, company_code: str) -> CompanyCodeData:
        """Buchungskreis-Sicht eines Partners; nicht vorhanden ist ein Fehler."""
        for entry in self.partner(bp_key).company_codes:
            if entry.company_code == company_code:
                return entry
        raise DefectError(f"Konto {bp_key} ist nicht im Buchungskreis {company_code} geführt.")

    def update_company(self, bp_key: str, company_code: str, **changes) -> None:
        """Ersetzt Felder einer Buchungskreis-Sicht."""
        partner = self.partner(bp_key)
        self.company_of(bp_key, company_code)
        self._partners[bp_key] = replace(
            partner,
            company_codes=tuple(
                replace(entry, **changes) if entry.company_code == company_code else entry
                for entry in partner.company_codes
            ),
        )

    # --- Posten ----------------------------------------------------------------------

    def items_of(self, bp_key: str) -> list[FiItem]:
        """Alle Posten eines Kontos in Modellreihenfolge."""
        partner = self.partner(bp_key)
        return [
            item
            for item in self._items
            if item.bp_number == partner.number and item.role == partner.role
        ]

    def drop_items(self, bp_key: str, keep: Callable[[FiItem], bool] | None = None) -> int:
        """Entfernt Posten eines Kontos und liefert die Anzahl der entfernten Zeilen."""
        partner = self.partner(bp_key)

        def mine(item: FiItem) -> bool:
            return item.bp_number == partner.number and item.role == partner.role

        before = len(self._items)
        self._items = [
            item for item in self._items if not mine(item) or (keep is not None and keep(item))
        ]
        return before - len(self._items)

    def add_items(self, items: Iterable[FiItem]) -> None:
        """Nimmt neue Posten auf."""
        self._items.extend(items)

    def replace_item(self, old: FiItem, new: FiItem) -> None:
        """Tauscht einen Posten an Ort und Stelle."""
        self._items[self._items.index(old)] = new

    # --- Belegungsplan ---------------------------------------------------------------

    def claim(self, defect: Defect, *bp_keys: str) -> None:
        """Trägt Konten in den Belegungsplan ein; Doppelbelegung muss angemeldet sein."""
        for bp_key in bp_keys:
            self.partner(bp_key)
            owner = self._claims.get(bp_key)
            if owner is not None and owner not in defect.overlaps:
                raise DefectError(
                    f"{defect.id}: Konto {bp_key} trägt bereits Defekt {owner}. "
                    f"Gewollte Doppelbelegung mit 'overlaps: [{owner}]' anmelden."
                )
            self._claims.setdefault(bp_key, defect.id)

    def claims(self) -> dict[str, str]:
        """Belegungsplan: Konto -> Defekt, der es zuerst beansprucht hat."""
        return dict(self._claims)

    # --- Ergebnis --------------------------------------------------------------------

    def customers(self) -> list[Partner]:
        return sorted(
            (p for p in self._partners.values() if p.role == "CUSTOMER"), key=lambda p: p.number
        )

    def vendors(self) -> list[Partner]:
        return sorted(
            (p for p in self._partners.values() if p.role == "VENDOR"), key=lambda p: p.number
        )

    def items(self, role: str) -> list[FiItem]:
        """Posten einer Seite, sortiert wie im Basis-Mandanten."""
        return sorted(
            (item for item in self._items if item.role == role),
            key=lambda item: (item.company_code, item.fiscal_year, item.document_no),
        )


# --- Bausteine für Posten -------------------------------------------------------------


def _terms(key: str) -> tuple:
    """Zahlungsbedingung; unbekannt ist ein Fehler und kein stiller Default."""
    try:
        return _TERMS_BY_KEY[key]
    except KeyError:
        raise DefectError(f"Zahlungsbedingung {key} gibt es in T052 nicht.") from None


def _split_amount(
    rng, total: Decimal, count: int, minimum: Decimal = MIN_INVOICE_AMOUNT
) -> list[Decimal]:
    """Zerlegt ein Volumen in ``count`` **verschiedene** Einzelbeträge.

    Verschieden, weil zwei gleiche Beträge desselben Kreditors innerhalb von 60 Tagen das
    Muster von AP-LEA-001 wären – ein Treffer, den kein Defekt gesetzt hat (D-045).
    """
    if count <= 0:
        return []
    cents = int((total * 100).to_integral_value())
    floor = int((minimum * 100).to_integral_value())
    if cents < floor * count:
        raise DefectError(f"{total} lässt sich nicht in {count} Beträge ab {minimum} zerlegen.")
    free = cents - floor * count
    for _ in range(_SPLIT_ATTEMPTS):
        cuts = sorted(rng.randint(0, free) for _ in range(count - 1))
        parts: list[int] = []
        previous = 0
        for cut in (*cuts, free):
            parts.append(floor + cut - previous)
            previous = cut
        if len(set(parts)) == count:
            return [(Decimal(part) / 100).quantize(CENT) for part in parts]
    raise DefectError(f"{total} liess sich nicht in {count} verschiedene Beträge zerlegen.")


def _workdays(start: date, end: date) -> list[date]:
    """Alle Werktage im Zeitraum – Belege werden nicht am Wochenende gebucht."""
    days = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    return [day for day in days if day.weekday() < 5]


def _pick_dates(rng, count: int, start: date, end: date) -> list[date]:
    """``count`` verschiedene Werktage im Zeitraum, aufsteigend."""
    if count <= 0:
        return []
    candidates = _workdays(start, end)
    if len(candidates) < count:
        raise DefectError(f"Im Zeitraum {start}..{end} liegen keine {count} Werktage.")
    return sorted(rng.sample(candidates, count))


def _delay(rng, terms_key: str, late: bool) -> int:
    """Tage zwischen Belegdatum und Zahlung, abhängig von der Zahlungsbedingung."""
    _, disc_days, disc_pct, net_days, _ = _terms(terms_key)
    if disc_days > 0 and disc_pct > 0:
        return disc_days + rng.randint(3, 14) if late else rng.randint(max(1, disc_days - 4), disc_days)
    return max(1, net_days + rng.randint(-3, 8))


def _max_delay(terms_key: str, late: bool) -> int:
    """Obergrenze von :func:`_delay` – legt fest, wie früh eine Rechnung liegen muss."""
    _, disc_days, disc_pct, net_days, _ = _terms(terms_key)
    if disc_days > 0 and disc_pct > 0:
        return disc_days + 14 if late else disc_days
    return net_days + 8


def _invoice(
    model: DemoModel,
    partner: Partner,
    *,
    company_code: str,
    terms: str,
    document_date: date,
    amount: Decimal,
    reference: str,
    posting_date: date | None = None,
    payment_date: date | None = None,
    take_discount: bool = False,
    document_no: str | None = None,
    payment_no: str | None = None,
) -> list[FiItem]:
    """Eine Rechnung und – falls bezahlt – die zugehörige Zahlung, wie im Basis-Mandanten.

    Zahlung = Rechnung minus gezogenem Skonto; beides ``Decimal`` (Regel 2).
    """
    side = "customer" if partner.role == "CUSTOMER" else "vendor"
    posting_date = posting_date or document_date
    year = f"{posting_date.year}"
    prefix = DOC_TYPES[f"{side}_invoice"][1]
    number = (
        model.numbering.reserve(document_no, company_code, year)
        if document_no is not None
        else model.numbering.next(prefix, company_code, year)
    )

    _, disc_days, disc_pct, _, _ = _terms(terms)
    has_discount = disc_days > 0 and disc_pct > 0
    disc_taken = (
        (amount * disc_pct / 100).quantize(CENT)
        if has_discount and take_discount and payment_date is not None
        else Decimal("0.00")
    )

    method = model.company_of(partner.bp_key, company_code).payment_methods
    payment_number = ""
    if payment_date is not None:
        pay_year = f"{payment_date.year}"
        pay_prefix = DOC_TYPES[f"{side}_payment"][1]
        payment_number = (
            model.numbering.reserve(payment_no, company_code, pay_year)
            if payment_no is not None
            else model.numbering.next(pay_prefix, company_code, pay_year)
        )

    invoice = FiItem(
        role=partner.role,
        bp_number=partner.number,
        company_code=company_code,
        fiscal_year=year,
        document_no=number,
        line_item="001",
        posting_date=posting_date,
        document_date=document_date,
        doc_type=DOC_TYPES[f"{side}_invoice"][0],
        posting_key=POSTING_KEYS[f"{side}_invoice"],
        debit_credit=DEBIT_CREDIT[f"{side}_invoice"],
        amount=amount,
        reference=reference,
        assignment=document_date.strftime("%Y%m%d"),
        item_text="Rechnung",
        baseline_date=document_date,
        payment_terms=terms,
        disc_days1=disc_days,
        disc_pct1=disc_pct,
        disc_base=amount if has_discount else Decimal("0.00"),
        disc_taken=disc_taken,
        payment_method=method,
        gl_account="",
        clearing_date=payment_date,
        clearing_doc=payment_number,
        is_open=payment_date is None,
    )
    if payment_date is None:
        return [invoice]

    payment = FiItem(
        role=partner.role,
        bp_number=partner.number,
        company_code=company_code,
        fiscal_year=f"{payment_date.year}",
        document_no=payment_number,
        line_item="001",
        posting_date=payment_date,
        document_date=payment_date,
        doc_type=DOC_TYPES[f"{side}_payment"][0],
        posting_key=POSTING_KEYS[f"{side}_payment"],
        debit_credit=DEBIT_CREDIT[f"{side}_payment"],
        amount=amount - disc_taken,
        reference="",
        assignment=number,
        item_text="Zahlung",
        baseline_date=payment_date,
        payment_terms="",
        disc_days1=0,
        disc_pct1=Decimal("0.000"),
        disc_base=Decimal("0.00"),
        disc_taken=Decimal("0.00"),
        payment_method=method,
        gl_account="",
        clearing_date=payment_date,
        clearing_doc=payment_number,
        is_open=False,
    )
    return [invoice, payment]


def _credit_memo(
    model: DemoModel, partner: Partner, *, company_code: str, document_date: date,
    amount: Decimal, reference: str,
) -> FiItem:
    """Offene Gutschrift – nettet im Sinne von AP-LEA-001 eine Doppelzahlung."""
    side = "customer" if partner.role == "CUSTOMER" else "vendor"
    year = f"{document_date.year}"
    number = model.numbering.next(DOC_TYPES[f"{side}_credit"][1], company_code, year)
    return FiItem(
        role=partner.role,
        bp_number=partner.number,
        company_code=company_code,
        fiscal_year=year,
        document_no=number,
        line_item="001",
        posting_date=document_date,
        document_date=document_date,
        doc_type=DOC_TYPES[f"{side}_credit"][0],
        posting_key=POSTING_KEYS[f"{side}_credit"],
        debit_credit=DEBIT_CREDIT[f"{side}_credit"],
        amount=amount,
        reference=reference,
        assignment=document_date.strftime("%Y%m%d"),
        item_text="Gutschrift",
        baseline_date=document_date,
        payment_terms="",
        disc_days1=0,
        disc_pct1=Decimal("0.000"),
        disc_base=Decimal("0.00"),
        disc_taken=Decimal("0.00"),
        payment_method=model.company_of(partner.bp_key, company_code).payment_methods,
        gl_account="",
        clearing_date=None,
        clearing_doc="",
        is_open=True,
    )


def _as_date(value) -> date:
    """Datum aus YAML – PyYAML liefert je nach Schreibweise ``date`` oder Text."""
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _as_money(value) -> Decimal:
    """Betrag aus YAML; immer über Text, nie über float (Regel 2)."""
    return Decimal(str(value)).quantize(CENT)


def _bank_from_iban(iban: str, valid_from: date) -> BankAccount:
    """Bankverbindung aus einer vorgegebenen IBAN (Ankerfall mit fester IBAN)."""
    return BankAccount(
        bank_country=iban[:2],
        bank_key=iban[4:12],
        account_number=iban[12:],
        bank_control_key="",
        iban=iban,
        valid_from=valid_from,
    )


def _rebuild_postings(model: DemoModel, rng, bp_key: str, spec: dict) -> None:
    """Ersetzt die Posten eines Kontos durch eine Menge, die vorgegebene Kennzahlen trifft.

    Das ist der Kern der Ankerfälle: `SPRINT-2.md` gibt Volumen 12M, offene Posten und
    Zahlungsanzahl vor, und die Beispiel-Findings nennen dieselben Zahlen. Am Ende prüft
    die Funktion nach, dass die gebauten Posten die Vorgabe treffen – ein Rundungsfehler
    hier wäre ein falsches erwartetes Ergebnis (Regel 1).
    """
    partner = model.partner(bp_key)
    company_code = spec["company_code"]
    terms = spec.get("payment_terms") or model.company_of(bp_key, company_code).payment_terms
    late = bool(spec.get("late", False))
    model.drop_items(bp_key)

    items: list[FiItem] = []
    explicit = tuple(spec.get("documents", ()))
    explicit_total = Decimal("0.00")
    for entry in explicit:
        amount = _as_money(entry["amount"])
        explicit_total += amount
        items.extend(
            _invoice(
                model,
                partner,
                company_code=company_code,
                terms=terms,
                document_date=_as_date(entry["document_date"]),
                posting_date=_as_date(entry.get("posting_date", entry["document_date"])),
                amount=amount,
                reference=entry["reference"],
                payment_date=_as_date(entry["payment_date"]) if entry.get("payment_date") else None,
                document_no=entry.get("document_no"),
                payment_no=entry.get("payment_no"),
            )
        )

    open_total = _as_money(spec.get("open_items", "0.00"))
    if "open_amounts" in spec:
        open_amounts = [_as_money(value) for value in spec["open_amounts"]]
        if sum(open_amounts) != open_total:
            raise DefectError(f"{bp_key}: open_amounts ergeben nicht {open_total}.")
    else:
        open_amounts = _split_amount(rng, open_total, int(spec.get("open_count", 0)))

    volume = _as_money(spec["volume_12m"])
    paid_count = int(spec.get("payments", 0)) - len(explicit)
    paid_total = volume - open_total - explicit_total
    if paid_count < 0 or (paid_count == 0 and paid_total != 0):
        raise DefectError(f"{bp_key}: {paid_total} lässt sich nicht auf {paid_count} Zahlungen verteilen.")

    last_payment = _as_date(spec["last_payment_on"]) if spec.get("last_payment_on") else None
    horizon = (last_payment or WINDOW_END) - timedelta(days=_max_delay(terms, late) + 1)
    schedule = list(
        zip(
            _pick_dates(rng, paid_count, WINDOW_12M_START, horizon),
            _split_amount(rng, paid_total, paid_count),
            strict=True,
        )
    )
    paid = [
        (document_date, amount, min(document_date + timedelta(days=_delay(rng, terms, late)), WINDOW_END))
        for document_date, amount in schedule
    ]
    if last_payment is not None and paid:
        latest = max(range(len(paid)), key=lambda index: paid[index][2])
        document_date, amount, _ = paid[latest]
        paid[latest] = (document_date, amount, last_payment)

    for document_date, amount, payment_date in paid:
        items.extend(
            _invoice(
                model,
                partner,
                company_code=company_code,
                terms=terms,
                document_date=document_date,
                amount=amount,
                reference=model.references.next(partner.role),
                payment_date=payment_date,
                take_discount=not late,
            )
        )

    # Die letzte Aktivität ist das späteste Beleg- oder Ausgleichsdatum (D-062). Gibt der
    # Defekt sie über `last_payment_on` vor, darf keine offene Rechnung danach liegen.
    open_dates = (
        [_as_date(value) for value in spec["open_dates"]]
        if "open_dates" in spec
        else _pick_dates(rng, len(open_amounts), WINDOW_12M_START, last_payment or WINDOW_END)
    )
    for document_date, amount in zip(open_dates, open_amounts, strict=True):
        items.extend(
            _invoice(
                model,
                partner,
                company_code=company_code,
                terms=terms,
                document_date=document_date,
                amount=amount,
                reference=model.references.next(partner.role),
            )
        )

    invoices = [item for item in items if item.item_text == "Rechnung"]
    built_volume = sum(
        (item.amount for item in invoices if WINDOW_12M_START <= item.posting_date <= WINDOW_END),
        Decimal("0.00"),
    )
    built_open = sum((item.amount for item in invoices if item.is_open), Decimal("0.00"))
    if built_volume != volume or built_open != open_total:
        raise DefectError(
            f"{bp_key}: gebaut wurden Volumen {built_volume} und OP {built_open}, "
            f"vorgegeben sind {volume} und {open_total}."
        )
    model.add_items(items)


# --- Registrierung der Defekttypen ----------------------------------------------------

_HANDLERS: dict[str, Callable[[DemoModel, Defect, object], list[Hit]]] = {}


def defect_type(name: str):
    """Registriert eine Funktion als Defekttyp; doppelte Namen sind ein Fehler."""

    def register(function):
        if name in _HANDLERS:
            raise DefectError(f"Defekttyp {name} ist doppelt registriert.")
        _HANDLERS[name] = function
        return function

    return register


def defect_types() -> tuple[str, ...]:
    """Alle bekannten Defekttypen, alphabetisch."""
    return tuple(sorted(_HANDLERS))


# --- Namensvarianten für Dubletten ----------------------------------------------------


def _transliterate(text: str) -> str:
    """Umlaute und ß ausgeschrieben – die häufigste Dublettenvariante in SAP-Stammdaten."""
    for source, target in _TRANSLITERATION.items():
        text = text.replace(source, target)
    return text


def _legal_form_variant(name: str) -> str:
    """Zweitschreibweise der Rechtsform am Ende des Namens."""
    for form, variant in sorted(_LEGAL_FORM_VARIANTS.items(), key=lambda item: -len(item[0])):
        if name.endswith(f" {form}"):
            return f"{name[: -len(form)]}{variant}"
    raise DefectError(f"Zu {name!r} ist keine zweite Schreibweise der Rechtsform bekannt.")


def _street_variant(street: str) -> str:
    """"Lindenstraße 14" wird zu "Lindenstr. 14" und umgekehrt."""
    if "straße" in street:
        return street.replace("straße", "str.")
    if "str." in street:
        return street.replace("str.", "straße")
    return street.replace(" ", "-", 1)


def _typo(rng, name: str) -> str:
    """Ein Buchstabe im Kernnamen vertauscht – Levenshtein-Abstand 1."""
    stem, _, rest = name.partition(" ")
    if len(stem) < 4:
        raise DefectError(f"{name!r}: Kernname zu kurz für einen Tippfehler.")
    position = rng.randrange(1, len(stem) - 1)
    alternatives = [c for c in "abcdefghijklmnopqrstuvwxyz" if c != stem[position].lower()]
    letter = alternatives[rng.randrange(len(alternatives))]
    return f"{stem[:position]}{letter}{stem[position + 1:]} {rest}".strip()


def _duplicate_fields(rng, leader: Partner, variant: str) -> dict:
    """Stammdatenfelder des zweiten Kontos eines Dubletten-Clusters."""
    common = {
        "place": leader.place,
        "country": leader.country,
        "language": leader.language,
        "search_term": leader.search_term,
        "street": leader.street,
        "po_box": "",
        "po_box_postal_code": "",
        "name1": leader.name1,
        "name2": "",
        "is_one_time": False,
    }
    if variant == "transliteration":
        return {**common, "name1": _transliterate(leader.name1),
                "street": _transliterate(leader.street)}
    if variant == "legal_form":
        return {**common, "name1": _legal_form_variant(leader.name1)}
    if variant == "street_spelling":
        return {**common, "street": _street_variant(leader.street)}
    if variant == "po_box":
        # Ohne Adress-Normalisierung wird dieses Paar nicht gefunden (Victor, 2026-08-30)
        return {**common, "street": "", "po_box": str(1000 + rng.randrange(9000)),
                "po_box_postal_code": leader.place.postal_code}
    if variant == "name2":
        head, _, tail = leader.name1.rpartition(" ")
        return {**common, "name1": head, "name2": tail}
    if variant == "typo":
        return {**common, "name1": _typo(rng, leader.name1)}
    raise DefectError(f"Unbekannte Dubletten-Variante {variant!r}.")


def _used_vat_ids(model: DemoModel) -> set[str]:
    """Alle vergebenen USt-IdNr. – ein Defekt darf keine zweite Dublette nebenbei erzeugen."""
    return {
        partner.vat_id
        for partner in (*model.customers(), *model.vendors())
        if partner.vat_id
    }


def _break_checksum(iban: str) -> str:
    """Dreht die Prüfziffer einer IBAN, bis die Mod-97-Prüfung fehlschlägt."""
    current = int(iban[2:4])
    for offset in range(1, 100):
        candidate = f"{iban[:2]}{(current + offset) % 100:02d}{iban[4:]}"
        try:
            IBAN(candidate)
        except ValueError:
            return candidate
    raise DefectError(f"Zu {iban[:4]}… liess sich keine ungültige Prüfziffer bilden.")


# --- Defekttypen ----------------------------------------------------------------------


@defect_type("anchor")
def _anchor(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """Setzt einen der sechs Ankerfälle auf exakt die Werte aus SPRINT-2.md."""
    params = defect.params
    bp_key = params["bp_key"]
    model.claim(defect, bp_key)
    partner = model.partner(bp_key)
    country = params.get("country", partner.country)

    changes: dict = {
        "country": country,
        "language": LANGUAGE_BY_COUNTRY[country],
        "is_one_time": False,
        "account_group": (
            CUSTOMER_ACCOUNT_GROUPS[0] if partner.role == "CUSTOMER" else VENDOR_ACCOUNT_GROUPS[0]
        ),
    }
    for field in ("name1", "name2", "search_term", "street", "vat_id", "tax_number",
                  "deletion_flag", "posting_block"):
        if field in params:
            changes[field] = params[field]
    if "city" in params:
        changes["place"] = Place(
            city=params["city"],
            postal_code=params["postal_code"],
            region=params["region"],
            country=country,
        )

    if "iban" in params:
        changes["bank"] = _bank_from_iban(params["iban"], partner.created_on)
    elif partner.bank is not None and partner.bank.bank_country != country:
        # Sonst wäre die IBAN plötzlich aus einem anderen Land als der Sitz (AR/AP-CON-002/003)
        changes["bank"] = None

    postings = params["postings"]
    company_code = postings["company_code"]
    template = next(
        (entry for entry in partner.company_codes if entry.company_code == company_code),
        partner.company_codes[0],
    )
    # Zahlweg wie im Basis-Mandanten: ohne Bankverbindung nie Lastschrift oder Ueberweisung
    has_bank = changes.get("bank", partner.bank) is not None
    if partner.role == "CUSTOMER":
        method = "E" if has_bank else ""
    else:
        method = "U" if has_bank else "S"
    changes["company_codes"] = (
        replace(
            template,
            company_code=company_code,
            payment_terms=postings.get("payment_terms", template.payment_terms),
            payment_methods=method,
        ),
    )
    model.update(bp_key, **changes)
    _rebuild_postings(model, rng, bp_key, postings)
    # Die erwarteten Findings eines Ankers stehen wörtlich in defects.yaml – sie stammen
    # aus den Beispiel-Findings und werden nicht aus Treffern abgeleitet.
    return []


@defect_type("duplicate_cluster")
def _duplicate_cluster(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """Ein zweites Konto trägt Namen und Adresse des ersten in einer Schreibvariante."""
    leader_key = defect.params["leader"]
    twin_key = defect.params["twin"]
    model.claim(defect, leader_key, twin_key)
    leader = model.partner(leader_key)
    model.update(twin_key, **_duplicate_fields(rng, leader, defect.params["variant"]))
    return [Hit(leader_key)]


@defect_type("vat_prefix")
def _vat_prefix(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """USt-IdNr. mit dem Präfix eines fremden Landes, im Format dieses Landes gültig."""
    used = _used_vat_ids(model)
    hits = []
    for index, bp_key in enumerate(defect.params["bp_keys"]):
        model.claim(defect, bp_key)
        partner = model.partner(bp_key)
        candidates = [c for c in _FOREIGN_VAT_COUNTRIES if c != partner.country]
        foreign = candidates[index % len(candidates)]
        model.update(bp_key, vat_id=foreign_vat_id(rng, foreign, used))
        hits.append(Hit(bp_key))
    return hits


@defect_type("vat_format")
def _vat_format(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """USt-IdNr., die dem Länderformat nicht entspricht – Präfix bleibt korrekt (D-058)."""
    variant = defect.params["variant"]
    hits = []
    for bp_key in defect.params["bp_keys"]:
        model.claim(defect, bp_key)
        partner = model.partner(bp_key)
        if variant == "steuernummer":
            # Der häufigste Formatfehler in der Praxis: die Steuernummer steht im
            # Feld STCEG. Ohne Buchstabenpräfix ist das kein Präfixfehler (D-058).
            value = partner.tax_number or (
                f"{rng.randint(100, 999)}/{rng.randint(100, 999)}/{rng.randint(10000, 99999)}"
            )
        elif variant == "zu_kurz":
            value = f"{partner.country}{''.join(str(rng.randint(0, 9)) for _ in range(6))}"
        elif variant == "buchstabe_statt_ziffer":
            digits = [index for index, char in enumerate(partner.vat_id) if char.isdigit()]
            if not digits:
                raise DefectError(f"{bp_key}: USt-IdNr. ohne Ziffer, Variante nicht anwendbar.")
            position = digits[rng.randrange(len(digits))]
            value = f"{partner.vat_id[:position]}O{partner.vat_id[position + 1:]}"
        else:
            raise DefectError(f"Unbekannte Format-Variante {variant!r}.")
        model.update(bp_key, vat_id=value)
        hits.append(Hit(bp_key))
    return hits


@defect_type("iban_checksum")
def _iban_checksum(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """IBAN mit verdrehter Prüfziffer; Bankschlüssel und Kontonummer bleiben unverändert."""
    hits = []
    for bp_key in defect.params["bp_keys"]:
        model.claim(defect, bp_key)
        partner = model.partner(bp_key)
        if partner.bank is None:
            raise DefectError(f"{bp_key}: ohne Bankverbindung ist keine IBAN zu verderben.")
        model.update(bp_key, bank=replace(partner.bank, iban=_break_checksum(partner.bank.iban)))
        hits.append(Hit(bp_key))
    return hits


@defect_type("deletion_flag")
def _deletion_flag(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """Löschvormerkung oder Buchungssperre, zentral oder je Buchungskreis."""
    params = defect.params
    bp_key = params["bp_key"]
    model.claim(defect, bp_key)
    field = "deletion_flag" if params.get("flag", "deletion") == "deletion" else "posting_block"
    company_codes = tuple(params.get("company_codes", ()))
    if params.get("scope", "central") == "central":
        model.update(bp_key, **{field: "X"})
    else:
        for company_code in company_codes:
            model.update_company(bp_key, company_code, **{field: "X"})

    if not params.get("with_open_items", True):
        # Negativfall: Kennzeichen gesetzt, aber nichts mehr offen
        model.drop_items(bp_key, keep=lambda item: not item.is_open)
        return []

    hits = []
    for company_code in company_codes:
        open_items = [
            item
            for item in model.items_of(bp_key)
            if item.is_open and item.company_code == company_code
        ]
        if not open_items:
            raise DefectError(
                f"{defect.id}: {bp_key} hat in {company_code} keinen offenen Posten – "
                "AR-CON-002 verlangt einen."
            )
        hits.append(Hit(bp_key, company_code))
    return hits


@defect_type("missing_payment_terms")
def _missing_payment_terms(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """Zahlungsbedingung im Buchungskreis geleert; auf den Belegen steht sie weiter."""
    params = defect.params
    bp_key = params["bp_key"]
    company_code = params["company_code"]
    model.claim(defect, bp_key)
    model.update_company(bp_key, company_code, payment_terms="")

    if not params.get("dominant", True):
        # Ohne eindeutige Mehrheit auf den Belegen gibt es kein Soll – Stufe C statt B
        rotation = ("ZB01", "ZB02", "ZB03", "ZB04")
        invoices = [
            item
            for item in model.items_of(bp_key)
            if item.company_code == company_code and item.item_text == "Rechnung"
        ]
        for index, item in enumerate(invoices):
            key = rotation[index % len(rotation)]
            _, disc_days, disc_pct, _, _ = _terms(key)
            model.replace_item(
                item,
                replace(
                    item,
                    payment_terms=key,
                    disc_days1=disc_days,
                    disc_pct1=disc_pct,
                    disc_base=item.amount if disc_days > 0 and disc_pct > 0 else Decimal("0.00"),
                ),
            )
    return [Hit(bp_key, company_code)]


@defect_type("missing_reprf")
def _missing_reprf(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """Prüfung auf doppelte Rechnung (REPRF) im Buchungskreis nicht gesetzt."""
    hits = []
    for bp_key in defect.params["bp_keys"]:
        model.claim(defect, bp_key)
        for entry in model.partner(bp_key).company_codes:
            model.update_company(bp_key, entry.company_code, invoice_check="")
            hits.append(Hit(bp_key, entry.company_code))
    return hits


@defect_type("placeholder_name")
def _placeholder_name(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """Statt eines Firmennamens steht ein Platzhalter im Stammsatz."""
    hits = []
    for target in defect.params["targets"]:
        bp_key = target["bp_key"]
        model.claim(defect, bp_key)
        model.update(bp_key, name1=target["name"], is_one_time=False)
        hits.append(Hit(bp_key))
    return hits


@defect_type("dormant_account")
def _dormant_account(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """Konto ohne einen einzigen Posten im Postenfenster – Löschkandidat (D-049, D-056)."""
    hits = []
    for bp_key in defect.params["bp_keys"]:
        model.claim(defect, bp_key)
        partner = model.partner(bp_key)
        if partner.created_on >= WINDOW_START:
            raise DefectError(
                f"{defect.id}: {bp_key} ist erst am {partner.created_on} angelegt – "
                "AR-HYG-001 verlangt ERDAT vor Fensterbeginn."
            )
        model.drop_items(bp_key)
        hits.append(Hit(bp_key))
    return hits


@defect_type("double_payment")
def _double_payment(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """Dieselbe Rechnung zweimal erfasst und bezahlt, die Referenz in zwei Schreibweisen."""
    params = defect.params
    keys = params.get("bp_keys") or [params["bp_key"], params["bp_key"]]
    model.claim(defect, *dict.fromkeys(keys))
    company_code = params["company_code"]
    amount = _as_money(params["amount"])
    terms = params.get("payment_terms", "ZB03")

    documents = []
    for key, reference, document_date, payment_date in (
        (keys[0], params["reference_a"], _as_date(params["document_date_a"]),
         _as_date(params["payment_date_a"])),
        (keys[1], params["reference_b"], _as_date(params["document_date_b"]),
         _as_date(params["payment_date_b"])),
    ):
        partner = model.partner(key)
        items = _invoice(
            model,
            partner,
            company_code=company_code,
            terms=terms,
            document_date=document_date,
            amount=amount,
            reference=reference,
            payment_date=payment_date,
        )
        model.add_items(items)
        documents.append(items[0])

    if params.get("netting", "none") == "credit_memo":
        # Gutschrift innerhalb von 180 Tagen: die Doppelzahlung ist ausgeglichen, kein Finding
        later = max(item.document_date for item in documents)
        model.add_items([
            _credit_memo(
                model,
                model.partner(keys[1]),
                company_code=company_code,
                document_date=workday(later + timedelta(days=int(params.get("netting_days", 45)))),
                amount=amount,
                reference=f"GS-{params['reference_b']}",
            )
        ])
        return []

    return [
        Hit(
            keys[0],
            company_code,
            documents[1].document_no,
            f"{documents[0].document_no}|{documents[1].document_no}",
        )
    ]


@defect_type("discount_usage")
def _discount_usage(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """Zahlverhalten neu gesetzt: Skonto verfallen lassen (Verlust) oder korrekt ziehen."""
    params = defect.params
    bp_key = params["bp_key"]
    model.claim(defect, bp_key)
    postings = params["postings"]
    company_code = postings["company_code"]
    model.update_company(bp_key, company_code, payment_terms=postings["payment_terms"])
    # Nur dieser eine Buchungskreis bleibt, damit die Kennzahlen des Kontos eindeutig sind
    entry = model.company_of(bp_key, company_code)
    model.update(bp_key, company_codes=(entry,))
    _rebuild_postings(model, rng, bp_key, postings)
    return [Hit(bp_key, company_code)] if postings.get("late") else []


@defect_type("shared_bank_account")
def _shared_bank_account(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """Zwei Konten führen dieselbe Bankverbindung, ohne Regulierer-Bezug."""
    first, second = defect.params["bp_keys"]
    model.claim(defect, first, second)
    source = model.partner(first)
    target = model.partner(second)
    if source.bank is None:
        raise DefectError(f"{defect.id}: {first} hat keine Bankverbindung zum Teilen.")
    if source.country != target.country:
        raise DefectError(
            f"{defect.id}: {first} und {second} sitzen in verschiedenen Ländern – "
            "die geteilte IBAN wäre zugleich ein IBAN-Land-Befund."
        )
    model.update(second, bank=source.bank, payer_bp="")
    return [Hit(first)]


@defect_type("customer_is_vendor")
def _customer_is_vendor(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """Derselbe Geschäftspartner ist als Debitor und als Kreditor geführt (gleiche USt-IdNr.)."""
    customer_key = defect.params["customer"]
    vendor_key = defect.params["vendor"]
    model.claim(defect, customer_key, vendor_key)
    customer = model.partner(customer_key)
    vendor = model.partner(vendor_key)
    if customer.country != vendor.country:
        raise DefectError(
            f"{defect.id}: {customer_key} und {vendor_key} sitzen in verschiedenen Ländern – "
            "die übernommene USt-IdNr. wäre zugleich ein Präfixbefund."
        )
    model.update(vendor_key, vat_id=customer.vat_id, name1=customer.name1,
                 search_term=customer.search_term, is_one_time=False)
    model.update(customer_key, is_one_time=False)
    return [Hit(customer_key)]


@defect_type("unapplied_cash")
def _unapplied_cash(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """Zahlungseingang ohne Rechnungsbezug, älter als 30 Tage (Akonto)."""
    hits = []
    for target in defect.params["targets"]:
        bp_key = target["bp_key"]
        model.claim(defect, bp_key)
        partner = model.partner(bp_key)
        company_code = target["company_code"]
        posting_date = _as_date(target["posting_date"])
        if (DATA_AS_OF - posting_date).days <= 30:
            raise DefectError(
                f"{defect.id}: {bp_key} – eine Akontozahlung vom {posting_date} ist am "
                "Datenstand keine 30 Tage alt."
            )
        year = f"{posting_date.year}"
        number = model.numbering.next(DOC_TYPES["customer_payment"][1], company_code, year)
        model.add_items([
            FiItem(
                role=partner.role,
                bp_number=partner.number,
                company_code=company_code,
                fiscal_year=year,
                document_no=number,
                line_item="001",
                posting_date=posting_date,
                document_date=posting_date,
                doc_type=DOC_TYPES["customer_payment"][0],
                posting_key=POSTING_KEYS["customer_payment"],
                debit_credit=DEBIT_CREDIT["customer_payment"],
                amount=_as_money(target["amount"]),
                reference="",
                assignment="",
                item_text="Akontozahlung",
                baseline_date=posting_date,
                payment_terms="",
                disc_days1=0,
                disc_pct1=Decimal("0.000"),
                disc_base=Decimal("0.00"),
                disc_taken=Decimal("0.00"),
                payment_method=model.company_of(bp_key, company_code).payment_methods,
                gl_account="",
                clearing_date=None,
                clearing_doc="",
                is_open=True,
            )
        ])
        # Der finding_key ist die Belegnummer: ein Konto kann mehrere unzugeordnete
        # Zahlungen tragen, und AR-LEA-001 liefert je Beleg ein Finding (Spec
        # SPRINT-3 Aufgabe 8). Ohne ihn haette die Erwartung keinen
        # Vergleichsschluessel fuer den zweiten Beleg desselben Kontos.
        hits.append(Hit(bp_key, company_code, number, number))
    return hits


@defect_type("central_payer")
def _central_payer(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """Zentralregulierer: zwei Konten mit gleicher Bank und Adresse, verbunden über KNVP-RG."""
    payer_key = defect.params["payer"]
    member_key = defect.params["member"]
    model.claim(defect, payer_key, member_key)
    payer = model.partner(payer_key)
    member = model.partner(member_key)
    if payer.role != "CUSTOMER" or member.role != "CUSTOMER":
        raise DefectError(f"{defect.id}: KNVP kennt nur Debitoren.")
    if payer.bank is None:
        raise DefectError(f"{defect.id}: der Regulierer {payer_key} hat keine Bankverbindung.")
    if payer.country != member.country:
        raise DefectError(f"{defect.id}: Regulierer und Konto sitzen in verschiedenen Ländern.")
    model.update(
        member_key,
        bank=payer.bank,
        place=payer.place,
        street=payer.street,
        po_box=payer.po_box,
        po_box_postal_code=payer.po_box_postal_code,
        payer_bp=payer.number,
        is_one_time=False,
    )
    return []


@defect_type("one_time_lookalike")
def _one_time_lookalike(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """Zwei CpD-Konten mit fast gleichem Namen – CpD wird nie auf Dubletten geprüft."""
    first, second = defect.params["bp_keys"]
    model.claim(defect, first, second)
    leader = model.partner(first)
    if not leader.is_one_time or not model.partner(second).is_one_time:
        raise DefectError(f"{defect.id}: {first}/{second} sind keine CpD-Konten (XCPDK).")
    fields = _duplicate_fields(rng, leader, "transliteration")
    # CpD bleibt CpD: genau darum ist dieses Paar ein Negativfall
    fields["is_one_time"] = True
    model.update(second, **fields)
    return []


@defect_type("same_core_name_other_form")
def _same_core_name_other_form(model: DemoModel, defect: Defect, rng) -> list[Hit]:
    """Gleicher Kernname, andere Rechtsform, andere Adresse – höchstens ein Hinweis."""
    first, second = defect.params["bp_keys"]
    model.claim(defect, first, second)
    leader = model.partner(first)
    head, _, form = leader.name1.rpartition(" ")
    other = defect.params["legal_form"]
    if other == form:
        raise DefectError(f"{defect.id}: {other} ist dieselbe Rechtsform wie bei {first}.")
    model.update(second, name1=f"{head} {other}", search_term=leader.search_term,
                 is_one_time=False)
    return []


# --- Anwenden -------------------------------------------------------------------------


def _expected_for(defect: Defect, hits: Sequence[Hit]) -> list[ExpectedFinding]:
    """Übersetzt die ``expected``-Zeilen eines Defekts in konkrete erwartete Findings.

    Eine Zeile mit ``bp_key`` gilt wörtlich (Ankerfälle); ohne ``bp_key`` wird sie über
    alle Treffer des Defekts ausgerollt. ``expected: []`` ist die Zusage, dass der Defekt
    **kein** Finding erzeugt – meldet er trotzdem Treffer, ist das ein Fehler.
    """
    if not defect.expected:
        if hits:
            raise DefectError(
                f"{defect.id}: als Negativfall deklariert (expected: []), meldet aber "
                f"{len(hits)} Treffer."
            )
        return []

    needs_hits = any("bp_key" not in spec for spec in defect.expected)
    if needs_hits and not hits:
        raise DefectError(f"{defect.id}: erwartet Findings, hat aber keinen Treffer erzeugt.")

    entries: list[ExpectedFinding] = []
    for spec in defect.expected:
        if "bp_key" in spec:
            entries.append(ExpectedFinding(defect_id=defect.id, **spec))
            continue
        for hit in hits:
            entries.append(
                ExpectedFinding(
                    rule_id=spec["rule_id"],
                    bp_key=hit.bp_key,
                    defect_id=defect.id,
                    company_code=spec.get("company_code", hit.company_code),
                    document_no=spec.get("document_no", hit.document_no),
                    finding_key=spec.get("finding_key", hit.finding_key),
                    from_rule_version=spec.get("from_rule_version"),
                )
            )
    return entries


def apply_defects(
    model: DemoModel, defects: Sequence[Defect], seed: int
) -> list[ExpectedFinding]:
    """Wendet alle Defekte in Dateireihenfolge an und liefert die erwarteten Findings."""
    expected: list[ExpectedFinding] = []
    for defect in defects:
        handler = _HANDLERS.get(defect.type)
        if handler is None:  # pragma: no cover – load_defects meldet das schon
            raise DefectError(f"{defect.id}: unbekannter Defekttyp {defect.type!r}.")
        hits = handler(model, defect, random_for(seed, f"defect:{defect.id}"))
        expected.extend(_expected_for(defect, hits))
    return sorted(expected, key=lambda entry: entry.sort_key)


#: Kopf der erzeugten Erwartungsdatei – wer sie von Hand ändert, verliert die Änderung
EXPECTED_HEADER = """\
# Erwartete Findings des Demo-Mandanten – GENERIERT, nicht von Hand pflegen.
#
# Quelle ist `testdata/demo_mandant/defects.yaml`; neu erzeugt mit
#   uv run mdq demo expected
# Jede Zeile nennt den Defekt, aus dem sie stammt. Weicht ein Lauf ab, ist entweder der
# Generator, die Regel oder die Erwartung falsch – das wird geklärt, nicht weggetestet
# (CLAUDE.md Regel 1, D-010).
#
# `from_rule_version` heisst: dieses Finding ist erst ab der genannten Regelversion Pflicht.
# Bis dahin weist die Regression es als bekannt-offen aus, statt den Lauf rot zu färben (D-054).
"""

#: Feldreihenfolge je Zeile – Teil des Vertrags mit dem Regressionstest
_EXPECTED_ORDER = (
    "rule_id", "bp_key", "company_code", "document_no", "finding_key", "from_rule_version",
    "defect",
)


def render_expected(expected: Sequence[ExpectedFinding], version: str = "0.1") -> str:
    """Erzeugt den Text von `expected_findings.yaml` – eine Zeile je erwartetem Finding."""
    lines = [EXPECTED_HEADER, f'\nversion: "{version}"\nfindings:\n']
    for entry in sorted(expected, key=lambda item: item.sort_key):
        data = entry.to_dict()
        fields = ", ".join(
            f'{name}: "{data[name]}"' if name != "rule_id" else f"{name}: {data[name]}"
            for name in _EXPECTED_ORDER
            if name in data
        )
        lines.append(f"  - {{ {fields} }}\n")
    if not expected:
        lines[-1] = lines[-1].replace("findings:\n", "findings: []\n")
    return "".join(lines)


def write_expected(path: Path, expected: Sequence[ExpectedFinding], version: str = "0.1") -> int:
    """Schreibt die erwarteten Findings und liefert ihre Anzahl."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_expected(expected, version), encoding="utf-8")
    return len(expected)
