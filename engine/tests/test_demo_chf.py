"""Der Mini-Mandant in Fremdwährung und der Abbruch nach D-030.

Zwei Dinge werden hier belegt, die vorher nur behauptet waren:

* Ein Lauf auf einem **Nicht-EUR-Mandanten** geht vollständig durch, und die Hauswährung
  steht überall neben dem Betrag – im Laufkopf, in `bp_relevance` und in jedem Betrag,
  den der Bericht zeigt (Regel 2).
* Zwei Hauswährungen im Scope brechen den Lauf mit Exit 2 ab (D-030), und der in der
  Meldung genannte Ausweg über `--company-codes` funktioniert.

Die zweite Währung ist keine erfundene Zeile: der Abbruchtest führt die **echten** T001
beider Mandanten in einem Temp-Verzeichnis zusammen. Beide Zeilen stammen aus dem
jeweiligen Generator und liegen so im Repo (D-199).
"""

import json
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from mdq import DEMO_MANDANT_CHF_DIR, DEMO_MANDANT_DIR
from mdq.cli import app
from mdq.demo import TABLES
from mdq.demo.mini import (
    MINI_COMPANY_CODE,
    MINI_CURRENCY,
    MINI_CUSTOMER_COUNT,
    MINI_SEED,
    MINI_VENDOR_COUNT,
    build_tables,
)
from mdq.demo.mini import generate as generate_mini
from mdq.report import STATUS_EXECUTED
from mdq.run import EXIT_ABORTED, EXIT_CLEAN, RunOptions, execute_run
from tests.conftest import demo_rows

runner = CliRunner()

#: Fester Laufzeitpunkt – ohne ihn wäre kein Lauf mit einem anderen vergleichbar (D-092)
CREATED_AT = "2026-08-31T08:00:00Z"


@pytest.fixture(scope="module")
def chf_run(tmp_path_factory):
    """Ein Lauf auf dem eingecheckten CHF-Mandanten.

    Wie bei der Regression bewusst der eingecheckte Ordner und nicht die neu erzeugte
    Fassung: das sind die Dateien, die im Repo liegen.
    """
    return execute_run(
        RunOptions(
            input_dir=DEMO_MANDANT_CHF_DIR,
            out_dir=tmp_path_factory.mktemp("chf_run"),
            created_at=CREATED_AT,
        )
    )


# --- Der Mandant selbst ----------------------------------------------------------------


def test_repo_copy_matches_the_generator(tmp_path) -> None:
    """Der eingecheckte CHF-Mandant ist genau das, was der Bauer heute liefert.

    Dieselbe Absicherung wie beim Demo-Mandanten: ohne sie könnte die Fixture im Repo
    veralten, während die Tests gegen eine frisch erzeugte Fassung grün bleiben.
    """
    manifest = generate_mini(tmp_path / "chf")
    stored = json.loads((DEMO_MANDANT_CHF_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert stored == manifest


def test_two_runs_are_byte_identical(tmp_path) -> None:
    """Gleicher Seed, gleiche Bytes (Regel 9)."""
    generate_mini(tmp_path / "a")
    generate_mini(tmp_path / "b")
    for table in TABLES:
        assert (tmp_path / "a" / f"{table}.txt").read_bytes() == (
            tmp_path / "b" / f"{table}.txt"
        ).read_bytes(), table


def test_one_company_code_in_chf() -> None:
    """Ein Buchungskreis, CHF, Sitzland CH – die Vorgabe zu Aufgabe 9."""
    rows = demo_rows(DEMO_MANDANT_CHF_DIR, "T001")
    assert [(row["BUKRS"], row["WAERS"], row["LAND1"]) for row in rows] == [
        (MINI_COMPANY_CODE, MINI_CURRENCY, "CH")
    ]


def test_twenty_business_partners_in_that_company_code() -> None:
    """20 Geschäftspartner, jeder genau einmal im einen Buchungskreis geführt."""
    customers = demo_rows(DEMO_MANDANT_CHF_DIR, "KNA1")
    vendors = demo_rows(DEMO_MANDANT_CHF_DIR, "LFA1")
    assert len(customers) == MINI_CUSTOMER_COUNT
    assert len(vendors) == MINI_VENDOR_COUNT
    assert len(customers) + len(vendors) == 20

    company_rows = demo_rows(DEMO_MANDANT_CHF_DIR, "KNB1") + demo_rows(
        DEMO_MANDANT_CHF_DIR, "LFB1"
    )
    assert len(company_rows) == 20
    assert {row["BUKRS"] for row in company_rows} == {MINI_COMPANY_CODE}


def test_account_numbers_do_not_collide_with_the_demo_client() -> None:
    """Die Nummernkreise liegen nebeneinander – sonst liesse sich nichts zusammenführen."""
    chf_customers = {row["KUNNR"] for row in demo_rows(DEMO_MANDANT_CHF_DIR, "KNA1")}
    chf_vendors = {row["LIFNR"] for row in demo_rows(DEMO_MANDANT_CHF_DIR, "LFA1")}
    demo_customers = {row["KUNNR"] for row in demo_rows(DEMO_MANDANT_DIR, "KNA1")}
    demo_vendors = {row["LIFNR"] for row in demo_rows(DEMO_MANDANT_DIR, "LFA1")}

    assert not chf_customers & demo_customers
    assert not chf_vendors & demo_vendors


def test_items_carry_the_house_currency() -> None:
    """Beleg- und Hauswährung sind gleich: der Mandant bucht in CHF, nicht in EUR."""
    for table in ("BSID", "BSAD", "BSIK", "BSAK"):
        currencies = {row["WAERS"] for row in demo_rows(DEMO_MANDANT_CHF_DIR, table)}
        assert currencies == {MINI_CURRENCY}, table


def test_the_generator_writes_every_table() -> None:
    """Alle 16 Tabellen – eine fehlende fiele sonst erst beim Schreiben auf."""
    assert set(build_tables()) == set(TABLES)


# --- Der Lauf auf dem Nicht-EUR-Mandanten ---------------------------------------------


def test_the_run_goes_through_cleanly(chf_run) -> None:
    """Exit 0, keine Rejects, jede Regel ausgeführt – ein Nicht-EUR-Mandant läuft durch."""
    assert chf_run.exit_code == EXIT_CLEAN
    assert chf_run.report.rejects == []
    assert [rule.rule_id for rule in chf_run.report.rules if rule.status != STATUS_EXECUTED] == []


def test_the_house_currency_is_chf_everywhere(chf_run) -> None:
    """Die Währung steht neben dem Betrag – im Kopf des Laufs und in jeder Relevanzzeile."""
    document = json.loads((chf_run.directory / "run.json").read_text(encoding="utf-8"))
    assert document["house_currency"] == MINI_CURRENCY
    assert chf_run.report.relevance.house_currency == MINI_CURRENCY
    assert MINI_CURRENCY in (chf_run.directory / "report.txt").read_text(encoding="utf-8")


def test_the_relevance_carries_real_amounts(chf_run) -> None:
    """Ohne Beträge wäre die Hauswährung behauptet statt belegt."""
    relevance = chf_run.report.relevance
    assert relevance.partners == 20
    assert Decimal(relevance.open_items_total) > 0
    assert Decimal(relevance.volume_12m_total) > 0


def test_no_finding_on_the_mini_client(chf_run) -> None:
    """Der Mandant hat keine Defektschicht; ein Finding wäre ein Fund, kein Rauschen."""
    assert chf_run.findings == []


# --- D-030: zwei Hauswaehrungen -------------------------------------------------------


def merged_input(target, seed: int = MINI_SEED):
    """Beide Mandanten in einem Verzeichnis: CHF-Dateien, T001 aus **beiden**.

    Zusammengeführt wird genau die Tabelle, die die Hauswährung trägt. Die Kopfzeile
    steht einmal, darunter die echten Zeilen beider Generatorausgaben – kein erfundener
    Datensatz. Die Konten des EUR-Mandanten fehlen bewusst: für die Frage, wie viele
    Hauswährungen im Scope liegen, zählt allein `company_code` (D-083).
    """
    generate_mini(target, seed)
    demo = (DEMO_MANDANT_DIR / "T001.txt").read_text(encoding="utf-8").splitlines()
    chf = (target / "T001.txt").read_text(encoding="utf-8").splitlines()
    assert demo[0] == chf[0], "beide Exporte müssen dieselbe Kopfzeile haben"
    (target / "T001.txt").write_text(
        "\n".join([demo[0], *demo[1:], *chf[1:]]) + "\n", encoding="utf-8"
    )
    return target


def test_two_house_currencies_abort_the_run(tmp_path) -> None:
    """D-030: V1 rechnet nicht um – zwei Währungen wären unvergleichbare Beträge."""
    result = runner.invoke(
        app,
        [
            "run",
            "--input",
            str(merged_input(tmp_path / "beide")),
            "--out",
            str(tmp_path / "runs"),
            "--created-at",
            CREATED_AT,
        ],
    )
    assert result.exit_code == EXIT_ABORTED
    # Die Abbruchmeldung geht nach stderr – sie ist ein Fehler, keine Ausgabe.
    message = result.stderr
    assert "CHF" in message and "EUR" in message
    assert "--company-codes" in message


def test_the_way_out_named_in_the_message_works(tmp_path) -> None:
    """Grenzfall: der Scope auf den CHF-Kreis macht denselben Input wieder lauffähig."""
    result = runner.invoke(
        app,
        [
            "run",
            "--input",
            str(merged_input(tmp_path / "beide")),
            "--out",
            str(tmp_path / "runs"),
            "--company-codes",
            MINI_COMPANY_CODE,
            "--created-at",
            CREATED_AT,
        ],
    )
    assert result.exit_code == EXIT_CLEAN, result.stderr
    runs = sorted((tmp_path / "runs").iterdir())
    document = json.loads((runs[0] / "run.json").read_text(encoding="utf-8"))
    assert document["house_currency"] == MINI_CURRENCY
