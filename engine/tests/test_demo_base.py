"""Der Basis-Mandant ist sauber: keine Regel aus dem Katalog darf hier greifen.

Ohne diese Tests wäre der Demo-Mandant wertlos. In Aufgabe 2 wird jeder Defekt genau
einem erwarteten Finding zugeordnet; jeder Zufallstreffer aus dem Basis-Mandanten wäre
ein Finding ohne Defekt – und die Regression würde entweder rot oder falsch grün.

Die Prüfungen hier messen die Daten: sie rechnen nach, was eine Regel später sähe. Am
Ende der Datei steht die andere Richtung – ein vollständiger `mdq run` über denselben
Mandanten, der die gebauten Regeln wirklich laufen lässt (SPRINT-3, Aufgabe 9). Beides
wird gebraucht: die Datenprüfung deckt auch Regeln ab, die es noch nicht gibt, der Lauf
deckt ab, was eine gebaute Regel über die Absicht hinaus meldet.

Die Tests nennen nur Schlüssel und Regel-IDs, nie Namen, IBAN oder Adressen (Regel 8).
"""

import json
import re
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from itertools import pairwise

import pytest
import yaml
from schwifty import IBAN
from stdnum.de import vat as de_vat
from typer.testing import CliRunner

from mdq import LOGIC_DIR
from mdq.cli import app
from mdq.demo import DATA_AS_OF, PAYMENT_TERMS, SKONTO_LOSS_LIMIT, WINDOW_END, WINDOW_START
from mdq.demo.names import LEGAL_FORMS_BY_COUNTRY, normalize_core
from mdq.formats import parse_amount, parse_date
from mdq.report import STATUS_EXECUTED
from mdq.run import EXIT_CLEAN, RunOptions, execute_run

from .conftest import demo_rows

runner = CliRunner()

#: Meldegrenze von AP-LEA-002 – der Basis-Mandant bleibt darunter
SKONTO_FINDING_LIMIT = Decimal("1000.00")

#: Abstand, ab dem AP-LEA-001 zwei gleich hohe Rechnungen als Paar betrachtet
DOUBLE_PAYMENT_WINDOW_DAYS = 60

#: Platzhalter, auf die AR-VAL-005 anspringt
PLACEHOLDERS = ("test", "unbekannt", "xxx", "???", "dummy", "muster")

_LEGAL_FORMS = tuple(
    sorted(
        {form for forms in LEGAL_FORMS_BY_COUNTRY.values() for _, form in forms},
        key=len,
        reverse=True,
    )
)


def _core_name(name: str) -> str:
    """Kernname ohne Rechtsform – so vergleicht AR-DUP-001 später."""
    for form in _LEGAL_FORMS:
        if name.endswith(form):
            name = name[: -len(form)]
            break
    return normalize_core(name)


@pytest.fixture(scope="module")
def demo_client(demo_base_client):
    """Dieses Modul prueft ausschliesslich den defektfreien Basis-Mandanten (D-045).

    Die Defekt-Schicht verletzt fast jede Invariante hier mit Absicht – eine Dublette ist
    ein doppelter Kernname, ein Loeschkandidat ein Konto ohne Posten. Deshalb zeigt
    `demo_client` in diesem Modul auf den Mandanten *ohne* Defekte.
    """
    return demo_base_client


@pytest.fixture(scope="module")
def masters(demo_client):
    """Debitoren- und Kreditorenstamm als Zeilenlisten."""
    out, _ = demo_client
    return demo_rows(out, "KNA1"), demo_rows(out, "LFA1")


# --- Stammdaten ----------------------------------------------------------------------


def test_core_names_are_unique(masters) -> None:
    """AR-DUP-001/AP-DUP-001: keine Dublette ohne Defekt."""
    customers, vendors = masters
    cores = [_core_name(row["NAME1"]) for row in customers + vendors]
    assert len(set(cores)) == len(cores)


def test_no_placeholder_names(masters) -> None:
    """AR-VAL-005."""
    for rows in masters:
        for row in rows:
            lowered = f"{row['NAME1']} {row['ORT01']}".lower()
            assert not any(marker in lowered for marker in PLACEHOLDERS)


def test_no_deletion_flag_or_block(demo_client, masters) -> None:
    """AR-CON-002: Löschvormerkung und Sperre bleiben leer."""
    out, _ = demo_client
    for rows in masters:
        assert all(row["LOEVM"] == "" and row["SPERR"] == "" for row in rows)
    for table in ("KNB1", "LFB1"):
        assert all(row["LOEVM"] == "" and row["SPERR"] == "" for row in demo_rows(out, table))


def test_vat_ids_are_unique_and_match_their_country(masters) -> None:
    """AR-VAL-001/002: richtiges Präfix, gültiges Format, keine geteilte USt-ID."""
    patterns = yaml.safe_load(
        (LOGIC_DIR / "dictionaries" / "vat_id_patterns.yaml").read_text(encoding="utf-8")
    )
    all_patterns = {**patterns["patterns"], **patterns["non_eu_patterns"]}
    seen: set[str] = set()
    for rows in masters:
        for row in rows:
            vat_id = row["STCEG"]
            if not vat_id:
                continue
            assert vat_id not in seen
            seen.add(vat_id)
            assert vat_id.startswith(row["LAND1"]), row["LAND1"]
            assert re.match(all_patterns[row["LAND1"]], vat_id), row["LAND1"]


def test_german_vat_ids_have_a_valid_check_digit(masters) -> None:
    """SPRINT-2.md: die DE-Prüfziffer wird über python-stdnum gerechnet."""
    for rows in masters:
        for row in rows:
            if row["LAND1"] == "DE" and row["STCEG"]:
                assert de_vat.is_valid(row["STCEG"])


def test_ibans_are_valid_and_unique(demo_client) -> None:
    """AR-VAL-003/AP-VAL-003 und AP-CON-001: gültige Prüfziffer, keine geteilte IBAN."""
    out, _ = demo_client
    ibans = [row["IBAN"] for row in demo_rows(out, "TIBAN")]
    assert len(set(ibans)) == len(ibans)
    for iban in ibans:
        assert IBAN(iban).is_valid


def test_bank_country_matches_the_partner_country(demo_client, masters) -> None:
    """AR-CON-003/AP-CON-002: IBAN-Land und Sitzland stimmen überein."""
    out, _ = demo_client
    customers, vendors = masters
    countries = {row["KUNNR"]: row["LAND1"] for row in customers}
    countries.update({row["LIFNR"]: row["LAND1"] for row in vendors})
    for table, key in (("KNBK", "KUNNR"), ("LFBK", "LIFNR")):
        for row in demo_rows(out, table):
            assert row["BANKS"] == countries[row[key]]


def test_every_bank_row_has_an_iban(demo_client) -> None:
    """Ohne TIBAN-Zeile wäre die Bankverbindung im kanonischen Modell ohne IBAN."""
    out, _ = demo_client
    known = {
        (row["BANKS"], row["BANKL"], row["BANKN"], row["BKONT"])
        for row in demo_rows(out, "TIBAN")
    }
    for table in ("KNBK", "LFBK"):
        for row in demo_rows(out, table):
            assert (row["BANKS"], row["BANKL"], row["BANKN"], row["BKONT"]) in known


def test_payment_method_needs_a_bank_account(demo_client) -> None:
    """AR-COM-003/AP-COM-002: kein Lastschrift- oder Überweisungs-Zahlweg ohne Bank."""
    out, _ = demo_client
    with_bank = {row["KUNNR"] for row in demo_rows(out, "KNBK")}
    for row in demo_rows(out, "KNB1"):
        if "E" in row["ZWELS"]:
            assert row["KUNNR"] in with_bank
    with_bank = {row["LIFNR"] for row in demo_rows(out, "LFBK")}
    for row in demo_rows(out, "LFB1"):
        if "U" in row["ZWELS"]:
            assert row["LIFNR"] in with_bank


def test_company_code_master_is_complete(demo_client) -> None:
    """AR-COM-002 (ZTERM leer), AR-COM-004 (Mahnverfahren), AP-COM-003 (REPRF)."""
    out, _ = demo_client
    for row in demo_rows(out, "KNB1"):
        assert row["ZTERM"] != ""
        assert row["MAHNA"] != ""
    for row in demo_rows(out, "LFB1"):
        assert row["ZTERM"] != ""
        assert row["REPRF"] == "X"


def test_payment_terms_match_the_decision(demo_client) -> None:
    """ZB02 ist 14 Tage 2 % – so bleibt das Beispiel-Finding F-005 wahr (Regel 1)."""
    out, _ = demo_client
    terms = {row["ZTERM"]: row for row in demo_rows(out, "T052")}
    assert terms["ZB02"]["ZTAG1"] == "14"
    assert Decimal(terms["ZB02"]["ZPRZ1"].replace(",", ".")) == Decimal("2.000")
    assert terms["ZB01"]["ZTAG1"] == "10"
    assert {row["ZTERM"] for row in demo_rows(out, "T052U")} == {t[0] for t in PAYMENT_TERMS}


# --- Posten --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def items(demo_client):
    """Alle Posten, getrennt nach Seite."""
    out, _ = demo_client
    customer = demo_rows(out, "BSID") + demo_rows(out, "BSAD")
    vendor = demo_rows(out, "BSIK") + demo_rows(out, "BSAK")
    return customer, vendor


def test_items_reference_existing_master_records(demo_client, masters, items) -> None:
    out, _ = demo_client
    customers, vendors = masters
    customer_items, vendor_items = items

    known_customers = {row["KUNNR"] for row in customers}
    known_vendors = {row["LIFNR"] for row in vendors}
    company = {(row["KUNNR"], row["BUKRS"]) for row in demo_rows(out, "KNB1")}
    company |= {(row["LIFNR"], row["BUKRS"]) for row in demo_rows(out, "LFB1")}

    for row in customer_items:
        assert row["KUNNR"] in known_customers
        assert (row["KUNNR"], row["BUKRS"]) in company
    for row in vendor_items:
        assert row["LIFNR"] in known_vendors
        assert (row["LIFNR"], row["BUKRS"]) in company


def test_every_partner_has_postings(masters, items) -> None:
    """AR-HYG-001/AP-HYG-001 und AR-HYG-002 verlangen 'kein Posten' – hier hat jeder welche."""
    customers, vendors = masters
    customer_items, vendor_items = items
    assert {row["KUNNR"] for row in customer_items} == {row["KUNNR"] for row in customers}
    assert {row["LIFNR"] for row in vendor_items} == {row["LIFNR"] for row in vendors}


def test_postings_stay_inside_the_window(items) -> None:
    """Kein Beleg nach dem Datenstand – ein Export kann ihn nicht enthalten."""
    for rows in items:
        for row in rows:
            posting_date = parse_date(row["BUDAT"])
            assert WINDOW_START <= posting_date <= WINDOW_END
            assert posting_date <= DATA_AS_OF


def test_payment_equals_invoice_minus_discount(demo_client) -> None:
    """Ausgeglichene Belege gehen auf: Zahlung = Rechnung − Skonto."""
    out, _ = demo_client
    for table, key, invoice_type in (("BSAD", "KUNNR", "DR"), ("BSAK", "LIFNR", "KR")):
        by_clearing: dict[str, dict[str, dict]] = defaultdict(dict)
        for row in demo_rows(out, table):
            role = "invoice" if row["BLART"] == invoice_type else "payment"
            by_clearing[row["AUGBL"]].setdefault(role, row)
        assert by_clearing
        for clearing_doc, pair in by_clearing.items():
            invoice, payment = pair.get("invoice"), pair.get("payment")
            assert invoice is not None and payment is not None, clearing_doc
            expected = parse_amount(invoice["DMBTR"]) - parse_amount(invoice["SKNTO"])
            assert parse_amount(payment["DMBTR"]) == expected, clearing_doc
            assert invoice[key] == payment[key]


def test_no_double_payment_pattern(items) -> None:
    """AP-LEA-001: keine zwei gleich hohen Rechnungen eines Partners binnen 60 Tagen."""
    for rows, key, invoice_type in ((items[0], "KUNNR", "DR"), (items[1], "LIFNR", "KR")):
        by_partner: dict[tuple[str, Decimal], list] = defaultdict(list)
        for row in rows:
            if row["BLART"] != invoice_type:
                continue
            by_partner[(row[key], parse_amount(row["DMBTR"]))].append(parse_date(row["BLDAT"]))
        for (partner, _), dates in by_partner.items():
            dates.sort()
            for first, second in pairwise(dates):
                assert (second - first).days > DOUBLE_PAYMENT_WINDOW_DAYS, partner


def test_discount_loss_stays_below_the_finding_limit(items) -> None:
    """AP-LEA-002: entgangenes Skonto je Kreditor in 12 Monaten unter der Meldegrenze."""
    _, vendor_items = items
    since = DATA_AS_OF - timedelta(days=365)
    loss: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for row in vendor_items:
        if row["BLART"] != "KR" or row["AUGBL"] == "":
            continue
        base = parse_amount(row["SKFBT"])
        taken = parse_amount(row["SKNTO"])
        if base == 0 or taken > 0 or parse_date(row["BLDAT"]) < since:
            continue
        percent = Decimal(row["ZBD1P"].replace(",", "."))
        loss[row["LIFNR"]] += (base * percent / 100).quantize(Decimal("0.01"))
    assert loss, "kein Kreditor mit Skontobedingung – der Testfall liefe ins Leere"
    worst = max(loss.values())
    assert worst <= SKONTO_LOSS_LIMIT, worst
    assert worst < SKONTO_FINDING_LIMIT


def test_open_items_have_no_clearing_document(demo_client) -> None:
    out, _ = demo_client
    for table in ("BSID", "BSIK"):
        assert all(row["AUGBL"] == "" for row in demo_rows(out, table))


def test_cleared_share_is_about_two_thirds(items) -> None:
    """SPRINT-2.md: rund 65 % der Rechnungen sind ausgeglichen."""
    for rows, invoice_type in ((items[0], "DR"), (items[1], "KR")):
        invoices = [row for row in rows if row["BLART"] == invoice_type]
        cleared = [row for row in invoices if row["AUGBL"] != ""]
        share = len(cleared) / len(invoices)
        assert 0.55 <= share <= 0.75, share

# --- Die andere Richtung: der Lauf ueber den defektfreien Mandanten --------------------


@pytest.fixture(scope="module")
def base_run(demo_client, tmp_path_factory):
    """Ein vollstaendiger `mdq run` ueber den Mandanten, den `--no-defects` schreibt.

    Fester `created_at`, damit zwei Laeufe vergleichbar bleiben (D-092).
    """
    out, _ = demo_client
    return execute_run(
        RunOptions(
            input_dir=out,
            out_dir=tmp_path_factory.mktemp("base_run"),
            created_at="2026-08-31T08:00:00Z",
        )
    )


def test_no_rule_fires_on_the_defect_free_client(base_run) -> None:
    """Der Nachweis zu `--no-defects`: kein Finding, wenn kein Defekt gesetzt ist (D-045).

    Bis hierher war die Invariante nur ueber die Daten geprueft – jede Regel einzeln
    nachgerechnet. Dieser Test laesst die gebauten Regeln wirklich laufen. Schlaegt er
    an, ist das ein Fund und keine Testschwaeche: entweder traegt der Basis-Generator
    einen Defekt, den niemand gesetzt hat, oder eine Regel trennt schlechter als ihr
    Klartext behauptet. Gemeldet wird er dann, nicht angepasst (Regel 1).
    """
    by_rule = Counter(finding["rule_id"] for finding in base_run.findings)
    assert base_run.findings == [], f"Findings ohne Defekt: {dict(by_rule)}"


def test_the_run_over_the_defect_free_client_is_clean(base_run) -> None:
    """Keine Rejects, keine uebersprungene Regel, Exit 0 – der Lauf selbst ist unauffaellig."""
    assert base_run.report.rejects == []
    assert [rule.rule_id for rule in base_run.report.rules if rule.status != STATUS_EXECUTED] == []
    assert base_run.exit_code == EXIT_CLEAN


def test_the_cli_flag_writes_exactly_this_client(demo_client, tmp_path) -> None:
    """`--no-defects` und die Fixture sind derselbe Mandant.

    Ohne diese Klammer pruefte alles oben einen Mandanten, den der Schalter so gar nicht
    schreibt – der Nachweis haette dann ein Loch genau an der Stelle, um die es geht.
    """
    _, fixture_manifest = demo_client
    result = runner.invoke(
        app,
        ["demo", "generate", "--out", str(tmp_path / "ohne"), "--no-defects"],
    )
    assert result.exit_code == 0, result.stderr
    written = json.loads((tmp_path / "ohne" / "manifest.json").read_text(encoding="utf-8"))
    assert written == fixture_manifest
