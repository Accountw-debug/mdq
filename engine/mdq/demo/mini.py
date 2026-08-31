"""Mini-Mandant in Fremdwährung: ein Buchungskreis, CHF, 20 Geschäftspartner.

Er hat zwei Aufgaben (SPRINT-3.md, Aufgabe 9):

* Er belegt, dass ein Lauf auf einem **Nicht-EUR-Mandanten** vollständig durchläuft und
  die Hauswährung überall neben dem Betrag steht (Regel 2) – nicht nur im Kopf des
  Laufs, sondern in `bp_relevance` und in jedem Finding.
* Er liefert die **zweite Hauswährung** für den Abbruchtest nach D-030. Der Test führt
  die T001 beider Mandanten in einem Temp-Verzeichnis zusammen; beide Zeilen sind echte
  Generatorausgabe, es wird kein Datensatz erfunden.

Eigener Bauer statt eines parametrierten Demo-Generators (D-199): der Demo-Generator
trägt die erwarteten Findings des Regressionsmandanten, und ihn für einen Mandanten
anzufassen, der nie eine Erwartung trägt, wäre das falsche Risiko. Gemeinsam benutzt
werden nur die Zeilenbauer aus :mod:`mdq.demo.generate` und die Schreiber aus
:mod:`mdq.demo.writers` – die Spaltenlisten kommen damit weiterhin allein aus
`logic/mappings/sap_ecc.yaml`, es gibt keine zweite Feldliste.

Die Kontonummernkreise liegen **neben** denen des Demo-Mandanten (103xxx statt 100–102xxx,
202xxx statt 200–201xxx). Nur so lassen sich beide Mandanten in einem Verzeichnis
zusammenführen, ohne dass ein Konto zweimal vorkommt.

Die Geschäftspartner selbst kommen aus demselben Basisbauer wie beim Demo-Mandanten und
sitzen deshalb überwiegend in Deutschland: Sitzland des Partners und Hauswährung des
Buchungskreises sind zwei verschiedene Dinge, und ein Schweizer Buchungskreis mit
deutschen Kunden ist der Normalfall, nicht die Ausnahme.
"""

from dataclasses import replace
from pathlib import Path
from typing import Any

from mdq.demo import TABLES, random_for
from mdq.demo.base import Partner, account_numbers, build_partners
from mdq.demo.generate import (
    DemoClient,
    bank_rows,
    company_code_rows,
    customer_company_rows,
    customer_master_rows,
    dunning_rows,
    iban_rows,
    item_rows,
    partner_function_rows,
    payment_terms_rows,
    payment_terms_text_rows,
    vendor_company_rows,
    vendor_master_rows,
)
from mdq.demo.names import NameFactory
from mdq.demo.postings import build_items
from mdq.demo.writers import write_manifest, write_table

#: Eigener Seed. Er ist nicht der des Demo-Mandanten: die beiden Mandanten haben nichts
#: miteinander zu tun, und ein gemeinsamer Seed legte das Gegenteil nahe.
MINI_SEED = 20260831

#: Der eine Buchungskreis mit Name und Sitzland – Vorgabe Victors zu Aufgabe 9
MINI_COMPANY_CODE = "3000"
MINI_COMPANY_CODE_NAMES = {MINI_COMPANY_CODE: ("MDQ Demo Suisse AG", "CH")}

#: Hauswährung des Mandanten. Sie ist der Punkt des Ganzen (D-030, D-083).
MINI_CURRENCY = "CHF"

MINI_CUSTOMER_COUNT = 12
MINI_VENDOR_COUNT = 8

#: Nummernkreise neben denen des Demo-Mandanten, damit beide zusammen ein Verzeichnis
#: ergeben können (Demo: 100000–102999 bzw. 200000–201999)
MINI_CUSTOMER_RANGE = (103000, 103999)
MINI_VENDOR_RANGE = (202000, 202999)


def _in_one_company_code(partner: Partner) -> Partner:
    """Setzt den Partner auf den einen Buchungskreis des Mini-Mandanten.

    Der Basisbauer verteilt die Partner nach ``COMPANY_CODE_SPLIT`` auf 1000 und 2000;
    hier gibt es nur einen Kreis. Übernommen wird die erste Buchungskreis-Sicht mit
    allem, was daran hängt (Zahlungsbedingung, Abstimmkonto, Zahlweg, Anlagedaten) –
    geändert wird ausschließlich die Nummer.
    """
    first = partner.company_codes[0]
    return replace(
        partner,
        company_codes=(replace(first, company_code=MINI_COMPANY_CODE),),
    )


def build_client(seed: int = MINI_SEED) -> DemoClient:
    """Baut den Mini-Mandanten: Stammsätze, Posten, die 16 Tabellen als Zeilenlisten.

    Ohne Defektschicht und ohne erwartete Findings: der Mandant belegt den Lauf, nicht
    die Regeln. ``DemoClient.expected`` bleibt deshalb leer.
    """
    names = NameFactory(random_for(seed, "mini-names"))

    customer_numbers = account_numbers(
        random_for(seed, "mini-customer-numbers"),
        MINI_CUSTOMER_RANGE,
        MINI_CUSTOMER_COUNT,
        (),
    )
    vendor_numbers = account_numbers(
        random_for(seed, "mini-vendor-numbers"), MINI_VENDOR_RANGE, MINI_VENDOR_COUNT, ()
    )

    customers = [
        _in_one_company_code(partner)
        for partner in build_partners(
            random_for(seed, "mini-customers"), "CUSTOMER", customer_numbers, names
        )
    ]
    vendors = [
        _in_one_company_code(partner)
        for partner in build_partners(
            random_for(seed, "mini-vendors"), "VENDOR", vendor_numbers, names
        )
    ]

    # Erst umhängen, dann buchen: die Posten ziehen ihren Buchungskreis aus dem Partner.
    customer_items = build_items(random_for(seed, "mini-customer-items"), customers, "CUSTOMER")
    vendor_items = build_items(random_for(seed, "mini-vendor-items"), vendors, "VENDOR")

    open_customer = [item for item in customer_items if item.is_open]
    cleared_customer = [item for item in customer_items if not item.is_open]
    open_vendor = [item for item in vendor_items if item.is_open]
    cleared_vendor = [item for item in vendor_items if not item.is_open]

    tables = {
        "KNA1": customer_master_rows(customers),
        "KNB1": customer_company_rows(customers),
        "KNBK": bank_rows(customers, "KUNNR"),
        "KNVP": partner_function_rows(customers),
        "KNB5": dunning_rows(customer_items),
        "LFA1": vendor_master_rows(vendors),
        "LFB1": vendor_company_rows(vendors),
        "LFBK": bank_rows(vendors, "LIFNR"),
        "TIBAN": iban_rows(customers, vendors),
        "BSID": item_rows(open_customer, "KUNNR", with_po=False, currency=MINI_CURRENCY),
        "BSAD": item_rows(cleared_customer, "KUNNR", with_po=False, currency=MINI_CURRENCY),
        "BSIK": item_rows(open_vendor, "LIFNR", with_po=True, currency=MINI_CURRENCY),
        "BSAK": item_rows(cleared_vendor, "LIFNR", with_po=True, currency=MINI_CURRENCY),
        "T001": company_code_rows(MINI_COMPANY_CODE_NAMES, MINI_CURRENCY),
        "T052": payment_terms_rows(),
        "T052U": payment_terms_text_rows(),
    }
    return DemoClient(tables=tables, expected=())


def build_tables(seed: int = MINI_SEED) -> dict[str, list[dict[str, str]]]:
    """Nur die 16 Tabellen – für Tests, die keine Dateien brauchen."""
    return build_client(seed).tables


def generate(out_dir: Path, seed: int = MINI_SEED) -> dict[str, Any]:
    """Schreibt den Mini-Mandanten nach ``out_dir`` und liefert das Manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    client = build_client(seed)
    entries = [write_table(out_dir, table, client.tables[table]) for table in TABLES]
    return write_manifest(out_dir, seed, entries)
