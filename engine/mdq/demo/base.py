"""Sauberer Basis-Mandant: Stammdaten ohne einen einzigen Defekt.

Jede Entscheidung hier hat ein Ziel: **keine Regel aus `logic/rules/CATALOG.md` darf auf
diesen Daten greifen.** Die Defekte kommen in Aufgabe 2 aus `defects.yaml` obendrauf.
Wo eine Regel sonst zufällig auslösen würde, steht der Grund als Kommentar an der Stelle
und wird in `engine/tests/test_demo_base.py` geprüft.

Alle Werte sind erfunden (D-008): Bankleitzahlen aus einem in Deutschland nicht
vergebenen Bereich, IBAN-Prüfziffern gültig über schwifty, DE-USt-IdNr. mit gültiger
Prüfziffer über python-stdnum, alle übrigen USt-IdNr. formatgültig laut
`logic/dictionaries/vat_id_patterns.yaml`.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from schwifty import IBAN
from stdnum.de import vat as de_vat

from mdq.demo import (
    COMPANY_CODE_SPLIT,
    CREATED_FROM,
    CUSTOMER_ACCOUNT_GROUPS,
    CUSTOMER_BANK_SHARE,
    CUSTOMER_TERMS_WEIGHTS,
    ONE_TIME_SHARE,
    PAYER_PROFILES,
    RECON_ACCOUNT_CUSTOMER,
    RECON_ACCOUNT_VENDOR,
    SAP_USERS,
    VENDOR_ACCOUNT_GROUPS,
    VENDOR_BANK_SHARE,
    VENDOR_TERMS_WEIGHTS,
    WINDOW_START,
)
from mdq.demo.geo import Place, places_by_country
from mdq.demo.names import NameFactory

#: Sitzländer der Geschäftspartner mit ihrem Gewicht (~75 % Deutschland)
COUNTRY_WEIGHTS = {"DE": 75, "AT": 5, "NL": 4, "FR": 4, "IT": 4, "PL": 3, "CH": 3, "US": 2}

#: Sprachenschlüssel je Land (SAP SPRAS)
LANGUAGE_BY_COUNTRY = {
    "DE": "D", "AT": "D", "CH": "D", "NL": "E", "PL": "E", "US": "E", "FR": "F", "IT": "I",
}

#: Größenklasse des Partners: (Name, Gewicht) – steuert Rechnungsanzahl und -höhe
SIZE_CLASSES = (("klein", 60), ("mittel", 30), ("gross", 10))

#: Bankleitzahlen werden aus diesem Bereich gezogen. In Deutschland ist er nicht
#: vergeben – die Bank hinter der IBAN existiert also nicht (SPRINT-2.md).
INVENTED_BANK_KEY_RANGE = (90000000, 99999999)

#: Aufbau der Bankverbindung je Land: (Länge Bankschlüssel, Länge Kontonummer, Ziffern?)
_BANK_LAYOUT = {
    "DE": (8, 10, True),
    "AT": (5, 11, True),
    "CH": (5, 12, True),
    "NL": (4, 10, False),
    "FR": (10, 11, True),
    "IT": (10, 12, True),
    "PL": (8, 16, True),
}

#: Länder ohne IBAN im Demo-Mandanten – US-Partner werden per Scheck bezahlt
COUNTRIES_WITHOUT_IBAN = ("US",)


@dataclass(frozen=True)
class BankAccount:
    """Bankverbindung; die IBAN steht in SAP in TIBAN, nicht in KNBK/LFBK."""

    bank_country: str
    bank_key: str
    account_number: str
    bank_control_key: str
    iban: str
    valid_from: date


@dataclass(frozen=True)
class CompanyCodeData:
    """Buchungskreis-Sicht eines Partners (KNB1 bzw. LFB1)."""

    company_code: str
    payment_terms: str
    recon_account: str
    payment_methods: str
    created_on: date
    created_by: str


@dataclass(frozen=True)
class Partner:
    """Ein Geschäftspartner mit allem, was Stammdaten und Posten brauchen."""

    role: str
    number: str
    country: str
    name1: str
    search_term: str
    place: Place
    street: str
    po_box: str
    po_box_postal_code: str
    address_id: str
    account_group: str
    is_one_time: bool
    vat_id: str
    tax_number: str
    language: str
    phone: str
    created_on: date
    created_by: str
    bank: BankAccount | None
    company_codes: tuple[CompanyCodeData, ...]
    payer_profile: str
    size_class: str

    @property
    def bp_key(self) -> str:
        """Kanonischer Schlüssel wie im Finding: ``C:``/``V:`` plus Kontonummer."""
        return f"{'C' if self.role == 'CUSTOMER' else 'V'}:{self.number}"


def _weighted(rng, weights: dict[str, int] | tuple) -> str:
    """Zieht einen Schlüssel nach Gewichten – Reihenfolge fest, also deterministisch."""
    items = tuple(weights.items()) if isinstance(weights, dict) else weights
    keys = [key for key, _ in items]
    return rng.choices(keys, weights=[weight for _, weight in items], k=1)[0]


def german_vat_id(rng, used: set[str]) -> str:
    """DE-USt-IdNr. mit gültiger Prüfziffer (python-stdnum)."""
    while True:
        body = "".join(str(rng.randint(0, 9)) for _ in range(8))
        for check in range(10):
            candidate = f"DE{body}{check}"
            if de_vat.is_valid(candidate) and candidate not in used:
                used.add(candidate)
                return candidate


def foreign_vat_id(rng, country: str, used: set[str]) -> str:
    """USt-IdNr. für die übrigen Länder – formatgültig laut vat_id_patterns.yaml.

    Nur die deutsche Prüfziffer wird gerechnet (SPRINT-2.md); für die anderen Länder
    prüft V1 ohnehin nur das Format (AR-VAL-002/AP-VAL-002).
    """
    def digits(count: int) -> str:
        return "".join(str(rng.randint(0, 9)) for _ in range(count))

    while True:
        if country == "AT":
            candidate = f"ATU{digits(8)}"
        elif country == "NL":
            candidate = f"NL{digits(9)}B{digits(2)}"
        elif country == "FR":
            candidate = f"FR{digits(2)}{digits(9)}"
        elif country == "IT":
            candidate = f"IT{digits(11)}"
        elif country == "PL":
            candidate = f"PL{digits(10)}"
        elif country == "CH":
            candidate = f"CHE{digits(9)}MWST"
        else:
            return ""
        if candidate not in used:
            used.add(candidate)
            return candidate


def _bank_account(rng, country: str, used_accounts: set[tuple[str, str]], created_on: date):
    """Erfundene Bankverbindung mit gültiger IBAN-Prüfziffer."""
    key_length, account_length, numeric_key = _BANK_LAYOUT[country]
    while True:
        if country == "DE":
            bank_key = str(rng.randint(*INVENTED_BANK_KEY_RANGE))
        elif numeric_key:
            bank_key = "".join(str(rng.randint(0, 9)) for _ in range(key_length))
        else:
            bank_key = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(key_length))
        account = "".join(str(rng.randint(0, 9)) for _ in range(account_length))
        if (bank_key, account) in used_accounts:
            continue
        try:
            if country == "FR":
                iban = IBAN.generate(country, bank_code=bank_key[:5], branch_code=bank_key[5:],
                                     account_code=account)
            else:
                iban = IBAN.generate(country, bank_code=bank_key, account_code=account)
        except ValueError:  # pragma: no cover – Layout ist je Land fest
            continue
        used_accounts.add((bank_key, account))
        return BankAccount(
            bank_country=country,
            bank_key=bank_key,
            account_number=account,
            bank_control_key="",
            iban=str(iban),
            valid_from=created_on,
        )


def _address_parts(rng, place: Place, names: NameFactory) -> tuple[str, str, str]:
    """Straße und – bei jedem zwanzigsten Partner zusätzlich – ein Postfach."""
    street = names.street()
    if rng.random() < 0.05:
        po_box = str(rng.randint(1000, 99999))
        return street, po_box, place.postal_code
    return street, "", ""


def _company_codes(rng, role: str, created_on: date, created_by: str) -> tuple[CompanyCodeData, ...]:
    """Buchungskreis-Sichten eines Partners.

    Die Zahlungsbedingung ist immer gesetzt – eine leere ZTERM wäre AR-COM-002, und die
    20 Fälle dafür setzt Aufgabe 2.
    """
    codes = _weighted(rng, tuple((entry, int(share * 100)) for entry, share in COMPANY_CODE_SPLIT))
    weights = CUSTOMER_TERMS_WEIGHTS if role == "CUSTOMER" else VENDOR_TERMS_WEIGHTS
    recon = RECON_ACCOUNT_CUSTOMER if role == "CUSTOMER" else RECON_ACCOUNT_VENDOR
    return tuple(
        CompanyCodeData(
            company_code=code,
            payment_terms=_weighted(rng, weights),
            recon_account=recon,
            payment_methods="",
            created_on=created_on,
            created_by=created_by,
        )
        for code in codes
    )


def _payment_methods(role: str, has_bank: bool) -> str:
    """Zahlweg.

    Ohne Bankverbindung nie Lastschrift (AR-COM-003) und nie Überweisung (AP-COM-002) –
    sonst meldeten diese beiden Regeln Treffer, die kein Defekt gesetzt hat.
    """
    if role == "CUSTOMER":
        return "E" if has_bank else ""
    return "U" if has_bank else "S"


def build_partners(rng, role: str, numbers: list[str], names: NameFactory) -> list[Partner]:
    """Erzeugt die Stammsätze einer Seite in der Reihenfolge der Kontonummern."""
    used_vat: set[str] = set()
    used_accounts: set[tuple[str, str]] = set()
    partners: list[Partner] = []
    groups = CUSTOMER_ACCOUNT_GROUPS if role == "CUSTOMER" else VENDOR_ACCOUNT_GROUPS
    bank_share = CUSTOMER_BANK_SHARE if role == "CUSTOMER" else VENDOR_BANK_SHARE

    for index, number in enumerate(numbers):
        country = _weighted(rng, COUNTRY_WEIGHTS)
        place = rng.choice(places_by_country(country))
        company = names.company(country)
        is_one_time = rng.random() < ONE_TIME_SHARE
        created_on = CREATED_FROM + timedelta(days=rng.randint(0, (WINDOW_START - CREATED_FROM).days))
        created_by = rng.choice(SAP_USERS)
        street, po_box, po_box_postal = _address_parts(rng, place, names)

        has_bank = country not in COUNTRIES_WITHOUT_IBAN and rng.random() < bank_share
        bank = _bank_account(rng, country, used_accounts, created_on) if has_bank else None

        vat_id = german_vat_id(rng, used_vat) if country == "DE" else foreign_vat_id(rng, country, used_vat)
        tax_number = (
            f"{rng.randint(100, 999)}/{rng.randint(100, 999)}/{rng.randint(10000, 99999)}"
            if country == "DE"
            else ""
        )

        company_codes = _company_codes(rng, role, created_on, created_by)
        methods = _payment_methods(role, has_bank)
        company_codes = tuple(
            CompanyCodeData(
                company_code=entry.company_code,
                payment_terms=entry.payment_terms,
                recon_account=entry.recon_account,
                payment_methods=methods,
                created_on=entry.created_on,
                created_by=entry.created_by,
            )
            for entry in company_codes
        )

        partners.append(
            Partner(
                role=role,
                number=number,
                country=country,
                name1=company.name1,
                search_term=company.search_term,
                place=place,
                street=street,
                po_box=po_box,
                po_box_postal_code=po_box_postal,
                # Adressnummer aus einem eigenen Nummernkreis, nicht aus der Kontonummer
                address_id=str(500000000 + index).rjust(10, "0"),
                account_group=groups[1] if is_one_time else groups[0],
                is_one_time=is_one_time,
                vat_id=vat_id,
                tax_number=tax_number,
                language=LANGUAGE_BY_COUNTRY[country],
                phone=f"0{rng.randint(200, 999)} {rng.randint(100000, 9999999)}",
                created_on=created_on,
                created_by=created_by,
                bank=bank,
                company_codes=company_codes,
                payer_profile=_weighted(rng, tuple((name, int(share * 100)) for name, share, _, _ in PAYER_PROFILES)),
                size_class=_weighted(rng, SIZE_CLASSES),
            )
        )
    return partners


def account_numbers(rng, role_range: tuple[int, int], count: int, anchors: tuple[str, ...]) -> list[str]:
    """Kontonummern mit Lücken; die Ankerkonten sind immer dabei.

    Zehnstellig mit führenden Nullen (D-009) – die Nullen sind der häufigste Grund,
    warum SAP-Schlüssel bei der Verarbeitung kaputtgehen.
    """
    reserved = {int(anchor) for anchor in anchors}
    pool = [number for number in range(role_range[0], role_range[1] + 1) if number not in reserved]
    chosen = set(rng.sample(pool, count - len(reserved))) | reserved
    return [str(number).rjust(10, "0") for number in sorted(chosen)]
