"""Erzeugt den Demo-Mandanten: Stammdaten, Posten, 15 Exportdateien, Manifest.

Ablauf: Kontonummern ziehen → Stammsätze bauen → Posten buchen → Mahndaten aus den
offenen Posten ableiten → Dateien schreiben. Jede Phase hat ihren eigenen Zufallsstrom
(:func:`mdq.demo.random_for`), damit eine spätere Phase die früheren nicht verschiebt.

Determinismus (Regel 9): gleicher Seed → byte-identische Dateien. Es gibt keine Uhr im
Generator; der Datenstand kommt als Konstante aus :mod:`mdq.demo`.
"""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from mdq.demo import (
    ANCHOR_CUSTOMERS,
    ANCHOR_VENDORS,
    CUSTOMER_COUNT,
    CUSTOMER_RANGE,
    DATA_AS_OF,
    LOCAL_CURRENCY,
    MANDT,
    PAYMENT_TERMS,
    TABLES,
    VENDOR_COUNT,
    VENDOR_RANGE,
    random_for,
)
from mdq.demo.base import BankAccount, Partner, account_numbers, build_partners
from mdq.demo.names import NameFactory
from mdq.demo.postings import FiItem, build_items
from mdq.demo.writers import (
    fmt_amount,
    fmt_date,
    fmt_flag,
    fmt_int,
    fmt_percent,
    fmt_text,
    write_manifest,
    write_table,
)

#: Verkaufsorganisation, Vertriebsweg und Sparte für die Partnerrollen (KNVP)
DIST_CHANNEL = "10"
DIVISION = "00"

#: Bankverbindungstyp in KNBK/LFBK
PARTNER_BANK_TYPE = "0001"

#: Mahnverfahren – bei jedem Debitor gesetzt, sonst meldete AR-COM-004 den ganzen Mandanten
DUNNING_PROCEDURE = "0001"

#: Mahnbereich; leer ist in SAP der Standardbereich
DUNNING_AREA = ""

#: Mahnstufe nach Alter des ältesten offenen Postens in Tagen
DUNNING_LEVELS = ((90, "3"), (60, "2"), (30, "1"))


def _master_row(partner: Partner) -> dict[str, str]:
    """Gemeinsame Felder von KNA1 und LFA1 – die Tabellen sind bis auf drei Spalten gleich."""
    return {
        "MANDT": MANDT,
        "LAND1": partner.country,
        "NAME1": partner.name1,
        "NAME2": "",
        "NAME3": "",
        "NAME4": "",
        "SORTL": partner.search_term,
        "ORT01": partner.place.city,
        "PSTLZ": partner.place.postal_code,
        "REGIO": partner.place.region,
        "STRAS": partner.street,
        "PFACH": partner.po_box,
        "PSTL2": partner.po_box_postal_code,
        "ADRNR": partner.address_id,
        "XCPDK": fmt_flag(partner.is_one_time),
        # Keine Löschvormerkung, keine Sperre: das wäre AR-CON-002 (Aufgabe 2)
        "LOEVM": "",
        "SPERR": "",
        "KONZS": "",
        "SPRAS": partner.language,
        "ERDAT": fmt_date(partner.created_on),
        "ERNAM": partner.created_by,
        "TELF1": partner.phone,
        "STCD1": partner.tax_number,
        "STCD2": "",
        "STCEG": partner.vat_id,
    }


def customer_master_rows(partners: list[Partner]) -> list[dict[str, str]]:
    """KNA1."""
    rows = []
    for partner in partners:
        row = _master_row(partner)
        row.update({"KUNNR": partner.number, "KTOKD": partner.account_group, "KNRZA": ""})
        rows.append(row)
    return rows


def vendor_master_rows(partners: list[Partner]) -> list[dict[str, str]]:
    """LFA1."""
    rows = []
    for partner in partners:
        row = _master_row(partner)
        row.update({"LIFNR": partner.number, "KTOKK": partner.account_group, "LNRZA": ""})
        rows.append(row)
    return rows


def customer_company_rows(partners: list[Partner]) -> list[dict[str, str]]:
    """KNB1 – Zahlungsbedingung und Mahnverfahren sind immer gesetzt."""
    rows = []
    for partner in partners:
        for company in partner.company_codes:
            rows.append({
                "MANDT": MANDT,
                "KUNNR": partner.number,
                "BUKRS": company.company_code,
                "AKONT": company.recon_account,
                "ZTERM": company.payment_terms,
                "MAHNA": DUNNING_PROCEDURE,
                "SPERR": "",
                "LOEVM": "",
                "ZWELS": company.payment_methods,
                "ZAHLS": "",
                "KNRZB": "",
                "TOGRU": "",
                "ZUAWA": "001",
                "ERDAT": fmt_date(company.created_on),
                "ERNAM": company.created_by,
            })
    return rows


def vendor_company_rows(partners: list[Partner]) -> list[dict[str, str]]:
    """LFB1 – REPRF (Prüfung doppelte Rechnung) ist gesetzt, sonst wäre das AP-COM-003."""
    rows = []
    for partner in partners:
        for company in partner.company_codes:
            rows.append({
                "MANDT": MANDT,
                "LIFNR": partner.number,
                "BUKRS": company.company_code,
                "AKONT": company.recon_account,
                "ZTERM": company.payment_terms,
                "SPERR": "",
                "LOEVM": "",
                "ZWELS": company.payment_methods,
                "ZAHLS": "",
                "LNRZB": "",
                "TOGRU": "",
                "REPRF": "X",
                "ZUAWA": "001",
                "ERDAT": fmt_date(company.created_on),
                "ERNAM": company.created_by,
            })
    return rows


def bank_rows(partners: list[Partner], key_column: str) -> list[dict[str, str]]:
    """KNBK bzw. LFBK – die IBAN steht nicht hier, sondern in TIBAN."""
    rows = []
    for partner in partners:
        if partner.bank is None:
            continue
        rows.append({
            "MANDT": MANDT,
            key_column: partner.number,
            "BANKS": partner.bank.bank_country,
            "BANKL": partner.bank.bank_key,
            "BANKN": partner.bank.account_number,
            "BKONT": partner.bank.bank_control_key,
            "BVTYP": PARTNER_BANK_TYPE,
            "KOINH": partner.name1[:60],
            "XEZER": "",
        })
    return rows


def iban_rows(*partner_lists: list[Partner]) -> list[dict[str, str]]:
    """TIBAN – eine Zeile je Bankverbindung, sortiert wie der Schlüssel."""
    accounts: dict[tuple[str, str, str, str], BankAccount] = {}
    for partners in partner_lists:
        for partner in partners:
            if partner.bank is None:
                continue
            bank = partner.bank
            accounts[(bank.bank_country, bank.bank_key, bank.account_number,
                      bank.bank_control_key)] = bank
    return [
        {
            "MANDT": MANDT,
            "BANKS": bank.bank_country,
            "BANKL": bank.bank_key,
            "BANKN": bank.account_number,
            "BKONT": bank.bank_control_key,
            "IBAN": bank.iban,
            "VALID_FROM": fmt_date(bank.valid_from),
        }
        for _, bank in sorted(accounts.items())
    ]


def partner_function_rows(partners: list[Partner]) -> list[dict[str, str]]:
    """KNVP – Auftraggeber zeigt auf das eigene Konto.

    Regulierer-Konstellationen (PARVW = RG auf ein anderes Konto) sind Negativfälle für
    die Dublettenprüfung und kommen als Defekt in Aufgabe 2.
    """
    rows = []
    for partner in partners:
        for company in partner.company_codes:
            rows.append({
                "MANDT": MANDT,
                "KUNNR": partner.number,
                "VKORG": company.company_code,
                "VTWEG": DIST_CHANNEL,
                "SPART": DIVISION,
                "PARVW": "AG",
                "KUNN2": partner.number,
                "PARZA": "000",
            })
    return rows


def dunning_rows(items: list[FiItem]) -> list[dict[str, str]]:
    """KNB5 – Mahnstufe je Debitor und Buchungskreis aus dem ältesten offenen Posten."""
    oldest: dict[tuple[str, str], FiItem] = {}
    for item in items:
        if not item.is_open or item.debit_credit != "S":
            continue
        key = (item.bp_number, item.company_code)
        current = oldest.get(key)
        if current is None or item.document_date < current.document_date:
            oldest[key] = item

    rows = []
    for (number, company_code), item in sorted(oldest.items()):
        age = (DATA_AS_OF - item.document_date).days
        level = next((value for limit, value in DUNNING_LEVELS if age >= limit), None)
        if level is None:
            continue
        rows.append({
            "MANDT": MANDT,
            "KUNNR": number,
            "BUKRS": company_code,
            "MABER": DUNNING_AREA,
            "MAHNS": level,
            "MADAT": fmt_date(min(item.document_date + timedelta(days=30 * int(level)),
                                  DATA_AS_OF)),
            "MANSP": "",
            "KNRMA": "",
        })
    return rows


def payment_terms_rows() -> list[dict[str, str]]:
    """T052 – Skontotage und -prozent je Zahlungsbedingung."""
    return [
        {
            "MANDT": MANDT,
            "ZTERM": key,
            "ZTAGG": "00",
            "ZTAG1": fmt_int(disc_days),
            "ZPRZ1": fmt_percent(disc_pct),
            "ZTAG2": "0",
            "ZPRZ2": fmt_percent(Decimal("0.000")),
            "ZTAG3": fmt_int(net_days),
        }
        for key, disc_days, disc_pct, net_days, _ in PAYMENT_TERMS
    ]


def payment_terms_text_rows() -> list[dict[str, str]]:
    """T052U – deutsche Texte zu den Zahlungsbedingungen."""
    return [
        {"MANDT": MANDT, "ZTERM": key, "SPRAS": "D", "TEXT1": text}
        for key, _, _, _, text in PAYMENT_TERMS
    ]


def item_rows(items: list[FiItem], key_column: str, with_po: bool) -> list[dict[str, str]]:
    """BSID/BSAD bzw. BSIK/BSAK – eine Zeile je Personenkontenposten."""
    rows = []
    for item in items:
        row = {
            "MANDT": MANDT,
            key_column: item.bp_number,
            "BUKRS": item.company_code,
            "GJAHR": item.fiscal_year,
            "BELNR": item.document_no,
            "BUZEI": item.line_item,
            "BUDAT": fmt_date(item.posting_date),
            "BLDAT": fmt_date(item.document_date),
            "CPUDT": fmt_date(item.posting_date),
            "BLART": item.doc_type,
            "BSCHL": item.posting_key,
            "SHKZG": item.debit_credit,
            "UMSKZ": "",
            "WAERS": LOCAL_CURRENCY,
            # Beleg- und Hauswährung sind gleich: V1 kennt eine Währung (D-030)
            "WRBTR": fmt_amount(item.amount),
            "DMBTR": fmt_amount(item.amount),
            "XBLNR": item.reference,
            "ZUONR": item.assignment,
            "SGTXT": item.item_text,
            "ZFBDT": fmt_date(item.baseline_date),
            "ZTERM": item.payment_terms,
            "ZBD1T": fmt_int(item.disc_days1),
            "ZBD1P": fmt_percent(item.disc_pct1),
            "SKFBT": fmt_amount(item.disc_base),
            "SKNTO": fmt_amount(item.disc_taken),
            "ZLSCH": item.payment_method,
            "ZLSPR": "",
            "REBZG": "",
            "HKONT": fmt_text(item.gl_account),
            "AUGDT": fmt_date(item.clearing_date),
            "AUGBL": item.clearing_doc,
        }
        if with_po:
            row["EBELN"] = ""
        rows.append(row)
    return rows


def build_tables(seed: int) -> dict[str, list[dict[str, str]]]:
    """Baut alle 15 Tabellen als Zeilenlisten – ohne Datei-Ein-/Ausgabe."""
    names = NameFactory(random_for(seed, "names"))

    customer_numbers = account_numbers(
        random_for(seed, "customer-numbers"), CUSTOMER_RANGE, CUSTOMER_COUNT, ANCHOR_CUSTOMERS
    )
    vendor_numbers = account_numbers(
        random_for(seed, "vendor-numbers"), VENDOR_RANGE, VENDOR_COUNT, ANCHOR_VENDORS
    )

    customers = build_partners(random_for(seed, "customers"), "CUSTOMER", customer_numbers, names)
    vendors = build_partners(random_for(seed, "vendors"), "VENDOR", vendor_numbers, names)

    customer_items = build_items(random_for(seed, "customer-items"), customers, "CUSTOMER")
    vendor_items = build_items(random_for(seed, "vendor-items"), vendors, "VENDOR")

    open_customer = [item for item in customer_items if item.is_open]
    cleared_customer = [item for item in customer_items if not item.is_open]
    open_vendor = [item for item in vendor_items if item.is_open]
    cleared_vendor = [item for item in vendor_items if not item.is_open]

    return {
        "KNA1": customer_master_rows(customers),
        "KNB1": customer_company_rows(customers),
        "KNBK": bank_rows(customers, "KUNNR"),
        "KNVP": partner_function_rows(customers),
        "KNB5": dunning_rows(customer_items),
        "LFA1": vendor_master_rows(vendors),
        "LFB1": vendor_company_rows(vendors),
        "LFBK": bank_rows(vendors, "LIFNR"),
        "TIBAN": iban_rows(customers, vendors),
        "BSID": item_rows(open_customer, "KUNNR", with_po=False),
        "BSAD": item_rows(cleared_customer, "KUNNR", with_po=False),
        "BSIK": item_rows(open_vendor, "LIFNR", with_po=True),
        "BSAK": item_rows(cleared_vendor, "LIFNR", with_po=True),
        "T052": payment_terms_rows(),
        "T052U": payment_terms_text_rows(),
    }


def generate(out_dir: Path, seed: int) -> dict[str, Any]:
    """Schreibt den Demo-Mandanten nach ``out_dir`` und liefert das Manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = build_tables(seed)
    entries = [write_table(out_dir, table, tables[table]) for table in TABLES]
    return write_manifest(out_dir, seed, entries)
