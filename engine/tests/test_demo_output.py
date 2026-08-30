"""Ausgabe des Generators: Determinismus, SE16N-Format, Manifest, `mdq load`."""

import json
from decimal import Decimal

import duckdb
import pytest
import yaml
from typer.testing import CliRunner

from mdq import CANONICAL_SCHEMA
from mdq.cli import app
from mdq.demo import DATA_AS_OF, DEFAULT_SEED, MANDT, TABLES
from mdq.demo.defects import DefectError
from mdq.demo.generate import generate
from mdq.demo.writers import DATE_INITIAL, columns_for
from mdq.formats import parse_amount, parse_date
from mdq.loader import load_table

from .conftest import demo_rows

runner = CliRunner()

#: Spalten mit Geldbeträgen – Prozentsätze stehen bewusst nicht hier, sie tragen drei
#: Nachkommastellen (SAP-Format der Felder ZPRZ*/ZBD1P) und sind damit auf Wert-Ebene
#: mehrdeutig im Sinne von D-035.
AMOUNT_COLUMNS = ("WRBTR", "DMBTR", "SKFBT", "SKNTO")
DATE_COLUMNS = ("BUDAT", "BLDAT", "CPUDT", "ZFBDT", "AUGDT", "ERDAT", "MADAT", "VALID_FROM")

#: Obergrenze aus SPRINT-2.md (Victor, 2026-08-30: 20 MB statt 15)
SIZE_LIMIT_BYTES = 20 * 1024 * 1024


def test_all_tables_are_written(demo_client) -> None:
    """16 Dateien seit Sprint 3: T001 kam als Traeger der Hauswaehrung dazu (D-030)."""
    out, manifest = demo_client
    assert [entry["table"] for entry in manifest["tables"]] == list(TABLES)
    assert len(TABLES) == 16
    assert "T001" in TABLES
    assert sorted(path.name for path in out.glob("*.txt")) == sorted(f"{t}.txt" for t in TABLES)


def test_same_seed_gives_identical_files(tmp_path) -> None:
    """Determinismus (Regel 9): gleicher Seed, identische Bytes – nicht nur gleiche Zeilen."""
    first = generate(tmp_path / "a", DEFAULT_SEED)
    second = generate(tmp_path / "b", DEFAULT_SEED)
    assert [entry["sha256"] for entry in first["tables"]] == [
        entry["sha256"] for entry in second["tables"]
    ]
    for table in TABLES:
        assert (tmp_path / "a" / f"{table}.txt").read_bytes() == (
            tmp_path / "b" / f"{table}.txt"
        ).read_bytes()


def test_other_seed_gives_other_data(tmp_path) -> None:
    """Ohne diesen Test wäre ein Generator, der den Seed ignoriert, ebenfalls 'deterministisch'.

    Verglichen wird der Basis-Mandant: die Defektliste nennt konkrete Kontonummern und
    gilt nur für den Vorgabe-Seed.
    """
    first = generate(tmp_path / "a", DEFAULT_SEED, ())
    second = generate(tmp_path / "b", DEFAULT_SEED + 1, ())
    assert first["tables"][0]["sha256"] != second["tables"][0]["sha256"]


def test_defects_are_bound_to_their_seed(tmp_path) -> None:
    """Ein anderer Seed bricht mit klarer Meldung ab, statt in Folgefehler zu laufen."""
    with pytest.raises(DefectError, match="Seed"):
        generate(tmp_path / "x", DEFAULT_SEED + 1)


def test_manifest_matches_files(demo_client) -> None:
    out, manifest = demo_client
    stored = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert stored == manifest
    assert stored["seed"] == DEFAULT_SEED
    assert stored["data_as_of"] == DATA_AS_OF.isoformat()
    assert stored["client"] == MANDT
    for entry in stored["tables"]:
        lines = (out / entry["file"]).read_text(encoding="utf-8").splitlines()
        assert len(lines) - 1 == entry["rows"], entry["table"]


def test_columns_come_from_the_mapping(demo_client) -> None:
    """Keine Spalte, die das Mapping nicht kennt – sonst bricht der Loader in Sprint 3."""
    out, _ = demo_client
    for table in TABLES:
        header = (out / f"{table}.txt").read_text(encoding="utf-8").splitlines()[0]
        assert tuple(header.split("\t")) == columns_for(table), table


def test_keys_keep_leading_zeros(demo_client) -> None:
    out, _ = demo_client
    assert all(len(row["KUNNR"]) == 10 for row in demo_rows(out, "KNA1"))
    assert all(len(row["LIFNR"]) == 10 for row in demo_rows(out, "LFA1"))
    for row in demo_rows(out, "BSAD"):
        assert len(row["BELNR"]) == 10
        assert len(row["BUZEI"]) == 3


def test_document_key_is_unique_across_all_item_tables(demo_client) -> None:
    """(BUKRS, GJAHR, BELNR, BUZEI) ist der Belegschluessel – er darf sich nie wiederholen.

    Der Stolperdraht zu D-080: Gutschriften liegen 5 bis 45 Tage nach ihrer Rechnung und
    koennen im Folgejahr landen. Zieht ihre Nummer aus dem Nummernkreis des Rechnungsjahrs,
    treffen ueber den Jahreswechsel zwei Kreise im selben Geschaeftsjahr aufeinander und
    `fi_item.item_key` ist nicht mehr eindeutig – 37 Paare waren es, bis die Nummer aus dem
    Kreis des eigenen Geschaeftsjahrs kam.
    """
    out, _ = demo_client
    seen: dict[tuple[str, str, str, str], str] = {}
    for table in ("BSID", "BSAD", "BSIK", "BSAK"):
        for row in demo_rows(out, table):
            key = (row["BUKRS"], row["GJAHR"], row["BELNR"], row["BUZEI"])
            assert key not in seen, f"{key} steht in {table} und in {seen[key]}"
            seen[key] = table


def test_amounts_parse_as_decimal_with_two_places(demo_client) -> None:
    """Regel 2: Beträge sind Decimal mit zwei Nachkommastellen, nie float."""
    out, _ = demo_client
    for table in ("BSID", "BSAD", "BSIK", "BSAK"):
        for row in demo_rows(out, table):
            for column in AMOUNT_COLUMNS:
                value = parse_amount(row[column])
                assert isinstance(value, Decimal)
                assert value >= 0
                assert -value.as_tuple().exponent == 2, (table, column)


def test_dates_parse_and_initial_values_are_written(demo_client) -> None:
    """Offene Posten tragen im Ausgleichsdatum den SAP-Initialwert, nicht Leerzeichen."""
    out, _ = demo_client
    for table in ("BSID", "BSAD", "BSIK", "BSAK", "KNA1", "KNB5", "TIBAN"):
        for row in demo_rows(out, table):
            for column in DATE_COLUMNS:
                if column in row:
                    parse_date(row[column])
    assert all(row["AUGDT"] == DATE_INITIAL for row in demo_rows(out, "BSID"))
    assert all(row["AUGDT"] != DATE_INITIAL for row in demo_rows(out, "BSAD"))


def test_load_reads_every_table_without_rejects(demo_client) -> None:
    """Akzeptanz aus SPRINT-2.md: alle Tabellen, 0 Rejects, Zeilen laut Manifest.

    Seit Sprint 3 sind es 16 statt 15: T001 liefert die Hauswaehrung (D-030).
    """
    out, manifest = demo_client
    con = duckdb.connect(":memory:")
    con.execute(CANONICAL_SCHEMA.read_text(encoding="utf-8"))
    results = [load_table(con, out / f"{table}.txt") for table in TABLES]

    assert [result.table for result in results] == list(TABLES)
    assert all(result.encoding == "UTF-8" for result in results)
    assert all(result.delimiter == "Tab" for result in results)
    assert all(result.warnings == () for result in results)
    assert [result.rows for result in results] == [e["rows"] for e in manifest["tables"]]
    assert con.execute("SELECT count(*) FROM reject").fetchone()[0] == 0


def test_files_stay_under_the_size_limit(demo_client) -> None:
    out, _ = demo_client
    total = sum(path.stat().st_size for path in out.glob("*.txt"))
    assert total < SIZE_LIMIT_BYTES, f"{total} Bytes"


def test_cli_generates_into_the_target_directory(tmp_path) -> None:
    result = runner.invoke(
        app, ["demo", "generate", "--out", str(tmp_path / "m"), "--seed", "1", "--no-defects"]
    )
    assert result.exit_code == 0
    assert (tmp_path / "m" / "manifest.json").is_file()


def test_cli_expected_writes_the_expected_findings(tmp_path) -> None:
    """`mdq demo expected` erzeugt die Erwartung aus defects.yaml (D-010)."""
    target = tmp_path / "expected_findings.yaml"
    result = runner.invoke(app, ["demo", "expected", "--out", str(target)])
    assert result.exit_code == 0
    document = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert document["findings"], "die erzeugte Erwartung darf nicht leer sein"
    assert "GENERIERT" in target.read_text(encoding="utf-8")


def test_repo_copy_matches_the_generator(demo_client, repo_root) -> None:
    """Der eingecheckte Demo-Mandant ist genau das, was der Generator heute liefert.

    Ohne diesen Test könnte die Fixture im Repo veralten, während die Tests gegen eine
    frisch erzeugte Fassung grün bleiben – die Regression ab Sprint 3 liefe dann gegen
    andere Daten als die Regeln im Repo sehen.
    """
    _, manifest = demo_client
    stored = json.loads(
        (repo_root / "testdata" / "demo_mandant" / "manifest.json").read_text(encoding="utf-8")
    )
    assert stored == manifest
