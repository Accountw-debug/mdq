"""Staging raw -> staged: Typisierung, Notation, Rejects, Kontrollsummen.

Der wichtigste Teil ist der Äquivalenztest: die SQL-Makros aus `logic/schema/staging.sql`
und die Referenz-Implementierung in `engine/mdq/formats.py` müssen Wert für Wert dasselbe
liefern – auf einem festen Grenzfallsatz **und** auf jedem Wert des Demo-Mandanten. Ohne
diesen Test wäre die Entscheidung, im SQL zu rechnen (D-071), eine Wette.
"""

from datetime import date
from decimal import Decimal

import duckdb
import pytest

from mdq import CANONICAL_SCHEMA
from mdq.formats import (
    INT_MAX,
    INT_MIN,
    ParseError,
    fits_decimal,
    parse_amount,
    parse_date,
    parse_flag,
    parse_integer,
    parse_percent,
)
from mdq.loader import load_table
from mdq.mapping import load_mapping
from mdq.staging import (
    DECIMAL_PRECISION,
    StagingError,
    detect_table_notation,
    install_macros,
    parse_values,
    stage_all,
    stage_table,
)


def reference(value: str | None, type_class: str, notation: str | None = None):
    """Was eine getypte Spalte enthalten muss – ausschliesslich aus `formats.py`.

    Bis D-204 ergaenzte diese Funktion zwei Grenzen still selbst: den INTEGER-Bereich und
    die Breite der Zielspalte. Damit prueft ein Aequivalenztest nicht mehr die Zusage aus
    D-071, sondern seine eigene Nachbildung. Beide Grenzen stehen jetzt in der Referenz –
    `parse_integer` meldet den Bereich, `formats.fits_decimal` ist das benannte
    Gegenstueck zu `mdq_fits`. Hier wird nur noch uebersetzt, was das Staging ohnehin tut:
    ein nicht lesbarer Wert wird im SQL NULL und danach ein Reject.
    """
    try:
        if type_class == "date":
            return parse_date(value)
        if type_class == "flag":
            return parse_flag(value)
        if type_class == "integer":
            return parse_integer(value)
        parsed = parse_amount(value, notation) if type_class == "amount" else parse_percent(value)
    except ParseError:
        return None
    return parsed if fits_decimal(parsed, *DECIMAL_PRECISION[type_class]) else None


@pytest.fixture
def macros(canonical_db):
    """Verbindung mit kanonischem Schema und den Staging-Makros."""
    install_macros(canonical_db)
    return canonical_db


@pytest.fixture(scope="module")
def staged(tmp_path_factory):
    """Der ausgelieferte Demo-Mandant, geladen und gestagt – einmal je Testlauf."""
    from mdq.demo import DEFAULT_SEED
    from mdq.demo.generate import generate as generate_demo

    out = tmp_path_factory.mktemp("staging_demo")
    manifest = generate_demo(out, DEFAULT_SEED)
    con = duckdb.connect(":memory:")
    con.execute(CANONICAL_SCHEMA.read_text(encoding="utf-8"))
    mapping = load_mapping()
    tables = [load_table(con, out / entry["file"]).table for entry in manifest["tables"]]
    results = stage_all(con, mapping, tables, "test-run")
    return con, mapping, {result.table: result for result in results}


# --- Äquivalenz (a): fester Grenzfallsatz ----------------------------------------------

AMBIGUOUS = "1.234"

AMOUNT_CASES = [
    # beide Notationen, eindeutig
    "1.234,56", "1234.56", "1,234.56", "1.234.567", "1,234,567", "1 234 567,89",
    # der mehrdeutige Fall (D-035)
    AMBIGUOUS, "1,234", "12.345", "0.000",
    # Vorzeichen, vorangestellt und nachgestellt
    "1.234,56-", "-1.234,56", "+1.234,56", "1.234,56+", "-0,00", "0,00-",
    # SAP-Initialwerte und Randformen
    "", "   ", None, "0,00", "0", "1.", ",56",
    # nur Trennzeichen, auch mit Vorzeichen: kein Betrag von null, sondern kein Betrag
    ".", ",", "...", " . ", "-.", "+.", ".-",
    # nicht lesbar
    "x", "12x34", "1.2.3,4,5", "-", "+", "1,2.3,4",
    # zu breit oder zu genau fuer DECIMAL(15,2)
    "1,2345", "99999999999999,99", "1234567890123,45",
]

PERCENT_CASES = [
    "2,000", "2.000", "0,000", "3", "2,5", "99,999",
    # ueber die SAP-Domaene PRZ23 hinaus: DECIMAL(5,3) faellt bei 100,000
    "100,000", "1.234,56", "2,0,0", "2x", "", None, "0",
    # nur Trennzeichen und blosse Vorzeichen – dieselbe Linie wie beim Betrag
    ".", ",", "...", " . ", "-", "+", "-.", "+.",
]

DATE_CASES = [
    "20260830", "2026-08-30", "30.08.2026", "1.2.2026", "01.02.2026",
    # SAP-Initialwerte -> NULL, kein Reject
    "00000000", "00.00.0000", "0000-00-00", "", "   ", None,
    # unmoegliche Kalendertage und unbekannte Formate
    "20261301", "20260230", "30/08/2026", "2026-13-01", "x",
]

INTEGER_CASES = ["30", "00", "0", "007", "-5", "+7", "", None, "2,5", "2.5", "x",
                 # die Grenzen der INTEGER-Spalte, je einen Schritt davor und dahinter
                 "2147483647", "2147483648", "-2147483648", "-2147483649"]

FLAG_CASES = ["X", "x", " X ", "", "   ", None, "Y", "0", "1", "XX"]


@pytest.mark.parametrize("notation", [None, "de", "iso"])
def test_amount_macro_matches_python(macros, notation) -> None:
    """Grenzfallsatz: SQL-Makro und `formats.parse_amount` liefern dasselbe."""
    got = parse_values(macros, AMOUNT_CASES, "amount", notation)
    expected = [reference(value, "amount", notation) for value in AMOUNT_CASES]
    assert got == expected


def test_ambiguous_amount_needs_the_file_notation(macros) -> None:
    """`1.234` ist ohne Notation ein Reject, mit Notation ein bestimmter Wert (D-035)."""
    assert parse_values(macros, [AMBIGUOUS], "amount", None) == [None]
    assert parse_values(macros, [AMBIGUOUS], "amount", "de") == [Decimal(1234)]
    # ISO gelesen waeren es 1,234 – drei Nachkommastellen passen nicht in DECIMAL(15,2)
    assert parse_values(macros, [AMBIGUOUS], "amount", "iso") == [None]


def test_percent_macro_matches_python(macros) -> None:
    """Prozentfelder werden nach Feldtyp gelesen, ohne Notation der Datei (D-048)."""
    got = parse_values(macros, PERCENT_CASES, "percent")
    assert got == [reference(value, "percent") for value in PERCENT_CASES]


def test_percent_beyond_the_sap_domain_is_a_reject(macros) -> None:
    """`100,000` passt nicht in DECIMAL(5,3) – SAP-Domäne PRZ23 lässt höchstens 99,999."""
    assert parse_values(macros, ["99,999", "100,000"], "percent") == [Decimal("99.999"), None]


@pytest.mark.parametrize(
    ("cases", "type_class"),
    [(DATE_CASES, "date"), (INTEGER_CASES, "integer"), (FLAG_CASES, "flag")],
    ids=["date", "integer", "flag"],
)
def test_macro_matches_python(macros, cases, type_class) -> None:
    got = parse_values(macros, cases, type_class)
    assert got == [reference(value, type_class) for value in cases]


def test_amount_with_three_decimals_is_not_rounded(macros) -> None:
    """Runden waere ein stumm verworfener Unterschied (Regel 4)."""
    assert parse_values(macros, ["1,234"], "amount", "de") == [None]
    assert reference("1,234", "amount", "de") is None


@pytest.mark.parametrize("wert", [".", ",", "...", " . ", "-.", "+.", ".-"])
def test_nur_trennzeichen_ist_kein_nullbetrag(macros, wert) -> None:
    """Beide Seiten lehnen ab – und zwar ab, nicht auf null (D-204).

    Der Aequivalenztest allein wuerde diesen Fall nicht sichern: er verlangt nur, dass
    Makro und Python **dasselbe** sagen, und bis hierher sagten beide einstimmig 0,00.
    Deshalb steht hier ausdruecklich, was herauskommen muss.
    """
    assert parse_values(macros, [wert], "amount") == [None]
    with pytest.raises(ParseError):
        parse_amount(wert)
    assert parse_values(macros, [wert], "percent") == [None]
    with pytest.raises(ParseError):
        parse_percent(wert)


def test_leerer_wert_bleibt_ein_initialwert(macros) -> None:
    """Gegenprobe zur Schaerfung: leer ist weiterhin NULL und kein Reject (D-035)."""
    assert parse_values(macros, ["", "   ", None], "amount") == [None, None, None]
    assert [parse_amount(wert) for wert in ("", "   ", None)] == [None, None, None]
    # Und der fehlende Vorkommateil bleibt erlaubt: ",56" ist 0,56, nicht "keine Ziffer".
    assert parse_values(macros, [",56"], "amount") == [Decimal("0.56")]
    assert parse_amount(",56") == Decimal("0.56")


@pytest.mark.parametrize(
    ("wert", "erwartet"),
    [
        (str(INT_MAX), INT_MAX),
        (str(INT_MAX + 1), None),
        (str(INT_MIN), INT_MIN),
        (str(INT_MIN - 1), None),
    ],
)
def test_ganzzahl_haelt_die_grenzen_der_zielspalte(macros, wert, erwartet) -> None:
    """Was nicht in die INTEGER-Spalte passt, ist ein Reject – auf beiden Seiten (D-204).

    Bis hierher kappte nur das Makro; `parse_integer` lieferte die Zahl unbegrenzt weiter,
    und der Test glich das still aus.
    """
    assert parse_values(macros, [wert], "integer") == [erwartet]
    assert reference(wert, "integer") == erwartet
    if erwartet is None:
        with pytest.raises(ParseError, match="INTEGER"):
            parse_integer(wert)


def test_fits_decimal_ist_das_gegenstueck_zu_mdq_fits(macros) -> None:
    """Die Breite der Zielspalte gehoert zur Referenz, nicht in den Testcode (D-204)."""
    fuer_spalte = [
        (Decimal("1.234"), False),   # drei Nachkommastellen passen nicht in DECIMAL(15,2)
        (Decimal("1.23"), True),
        (Decimal("9999999999999.99"), True),
        (Decimal("99999999999999.99"), False),  # 14 Vorkommastellen sind zu viel
    ]
    for wert, erwartet in fuer_spalte:
        assert fits_decimal(wert, 15, 2) is erwartet, wert
        aus_sql = macros.execute(f"SELECT mdq_fits('{wert}', 15, 2)").fetchone()[0]
        assert bool(aus_sql) is erwartet, wert

    # Der fehlende Wert ist der eine Fall, in dem die beiden verschieden **aussehen** und
    # dasselbe **tun**: `mdq_fits` prueft das Literal und sagt zu NULL FALSE, weil da
    # nichts zu passen ist; `fits_decimal` prueft den geparsten Wert und sagt True, weil
    # nichts da ist, das scheitern koennte. In der Spalte steht danach beide Male NULL.
    assert fits_decimal(None, 15, 2) is True
    assert macros.execute("SELECT mdq_fits(NULL, 15, 2)").fetchone()[0] is False
    assert parse_values(macros, [None], "amount") == [None]
    assert reference(None, "amount") is None


# --- Äquivalenz (b): jeder Wert des Demo-Mandanten -------------------------------------


def test_macros_match_python_on_every_demo_value(staged) -> None:
    """Zelle fuer Zelle: jeder eindeutige Wert jeder getypten Spalte, alle 16 Tabellen."""
    con, mapping, results = staged
    install_macros(con)
    geprueft = 0
    for table_name in sorted(results):
        table = mapping.table(table_name)
        notation = detect_table_notation(con, table, mapping)
        for column in table.columns:
            type_class = mapping.type_of(column)
            if type_class == "text":
                continue
            values = [
                value
                for (value,) in con.execute(
                    f'SELECT DISTINCT "{column}" FROM "raw_{table_name}" ORDER BY 1'
                ).fetchall()
            ]
            got = parse_values(con, values, type_class, notation)
            expected = [reference(value, type_class, notation) for value in values]
            assert got == expected, f"{table_name}.{column}"
            geprueft += len(values)
    assert geprueft > 10000, "der Abgleich deckt zu wenige Werte ab, um etwas zu sichern"


# --- Der Demo-Mandant: die fachlichen Zahlen -------------------------------------------


def test_demo_client_stages_without_rejects(staged) -> None:
    """0 Rejects ueber alle 16 Tabellen, keine Zeile verloren."""
    con, _, results = staged
    assert len(results) == 16  # 16 seit T001 (D-030)
    for result in results.values():
        assert result.rejected == 0, result.table
        assert result.rows_staged == result.rows_raw, result.table
    assert con.execute("SELECT count(*) FROM reject").fetchone()[0] == 0


def test_control_total_bsid(staged) -> None:
    """Kontrollsumme je Tabelle, Buchungskreis und Waehrung – die Waehrung steht daneben."""
    _, _, results = staged
    totals = {
        (total.company_code, total.currency): total.amount
        for total in results["BSID"].totals
    }
    assert totals[("1000", "EUR")] == "123605141.17"
    assert totals[("2000", "EUR")] == "34685341.29"


def test_notation_comes_from_the_posting_files(staged) -> None:
    """Die vier Postentabellen belegen ihre Notation selbst; Stammdaten schweigen."""
    _, _, results = staged
    for table in ("BSID", "BSAD", "BSIK", "BSAK"):
        assert results[table].notation == "de"
        assert results[table].notation_source == "Datei"
    assert results["KNA1"].notation is None
    assert results["KNA1"].notation_source == "unbestimmt"


def test_amount_signed_local_follows_shkzg(staged) -> None:
    """S ist positiv, H negativ – das Vorzeichen wird genau einmal gesetzt (D-009)."""
    con, _, _ = staged
    credit = con.execute(
        'SELECT "DMBTR", "amount_signed_local" FROM "staged_BSID" '
        "WHERE \"SHKZG\" = 'H' ORDER BY \"_row_no\" LIMIT 1"
    ).fetchone()
    assert credit == (Decimal("1092.32"), Decimal("-1092.32"))
    debit = con.execute(
        'SELECT "DMBTR", "amount_signed_local" FROM "staged_BSID" '
        "WHERE \"SHKZG\" = 'S' ORDER BY \"_row_no\" LIMIT 1"
    ).fetchone()
    assert debit == (Decimal("917.50"), Decimal("917.50"))


def test_reference_norm_is_upper_case(staged) -> None:
    """D-065: die Normalisierung passiert hier, nicht in der Regel."""
    con, _, _ = staged
    row = con.execute(
        'SELECT "reference_norm" FROM "staged_BSID" WHERE "XBLNR" = \'GS-RG-122417\''
    ).fetchone()
    assert row == ("GSRG122417",)


def test_staged_columns_have_the_expected_types(staged) -> None:
    con, _, _ = staged
    types = dict(
        con.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'staged_BSID'"
        ).fetchall()
    )
    assert types["BUDAT"] == "DATE"
    assert types["DMBTR"] == "DECIMAL(15,2)"
    assert types["amount_signed_local"] == "DECIMAL(15,2)"
    assert types["ZBD1P"] == "DECIMAL(5,3)"
    assert types["ZBD1T"] == "INTEGER"
    # Schluessel bleiben Text, sonst gehen fuehrende Nullen verloren (Regel 2)
    assert types["BELNR"] == "VARCHAR"
    assert types["KUNNR"] == "VARCHAR"


def test_leading_zeros_survive_the_staging(staged) -> None:
    con, _, _ = staged
    keys = con.execute('SELECT DISTINCT "KUNNR" FROM "staged_BSID" LIMIT 5').fetchall()
    assert all(key.startswith("0000") for (key,) in keys)


def test_flags_are_boolean_and_empty_stays_null(staged) -> None:
    """Leer wird NULL, nicht FALSE: das kanonische DEFAULT setzt erst Aufgabe 2."""
    con, _, _ = staged
    gesetzt, leer = con.execute(
        'SELECT count(*) FILTER (WHERE "LOEVM"), count(*) FILTER (WHERE "LOEVM" IS NULL) '
        'FROM "staged_KNA1"'
    ).fetchone()
    assert gesetzt > 0 and leer > 0


def test_staging_is_deterministic(staged) -> None:
    """Zweimal stagen ergibt dieselben Kontrollsummen (Regel 9)."""
    con, mapping, results = staged
    again = stage_table(con, mapping, "BSID", "test-run-2")
    assert [total.to_dict() for total in again.totals] == [
        total.to_dict() for total in results["BSID"].totals
    ]
    assert again.rows_staged == results["BSID"].rows_staged


# --- Rejects: kleine, gebaute Exporte ---------------------------------------------------


@pytest.fixture
def mapping():
    return load_mapping()


def _export(tmp_path, mapping, table_name: str, rows: list[dict]):
    """Schreibt einen kleinen Export mit den gemappten Spalten der Tabelle."""
    table = mapping.table(table_name)
    columns = list(table.fields)
    lines = ["\t".join(columns)]
    lines += ["\t".join(str(row.get(column, "")) for column in columns) for row in rows]
    path = tmp_path / f"{table_name}.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


BSID_ROW = {
    "KUNNR": "0000100001", "BUKRS": "1000", "GJAHR": "2026", "BELNR": "1800000001",
    "BUZEI": "001", "BUDAT": "20260801", "BLDAT": "20260801", "CPUDT": "20260801",
    "BLART": "DR", "BSCHL": "01", "SHKZG": "S", "WAERS": "EUR",
    "WRBTR": "100,00", "DMBTR": "100,00", "XBLNR": "RE-1", "ZFBDT": "20260801",
    "ZTERM": "ZB01", "ZBD1T": "10", "ZBD1P": "3,000", "SKFBT": "100,00", "SKNTO": "0,00",
    "HKONT": "140000", "AUGDT": "00000000",
}


def _stage_rows(con, mapping, tmp_path, table_name, rows, notation=None):
    load_table(con, _export(tmp_path, mapping, table_name, rows))
    install_macros(con)
    return stage_table(con, mapping, table_name, "test-run", notation)


def _rejects(con):
    return con.execute(
        "SELECT row_no, reason, raw_excerpt FROM reject ORDER BY row_no"
    ).fetchall()


def test_unreadable_date_rejects_only_that_row(canonical_db, mapping, tmp_path) -> None:
    """Trifft: eine kaputte Zeile geht nach `reject`, die uebrigen werden gestagt."""
    rows = [BSID_ROW, {**BSID_ROW, "BELNR": "1800000002", "BUDAT": "30/08/2026"}, BSID_ROW]
    result = _stage_rows(canonical_db, mapping, tmp_path, "BSID", rows)
    assert (result.rows_raw, result.rows_staged, result.rejected) == (3, 2, 1)
    rejects = _rejects(canonical_db)
    assert len(rejects) == 1
    row_no, reason, excerpt = rejects[0]
    assert row_no == 2
    assert reason.startswith("BUDAT: ")
    assert "Datum" in reason
    assert "1800000002" in excerpt


def test_reject_reason_names_the_first_faulty_field(canonical_db, mapping, tmp_path) -> None:
    """R-2: verworfen wird die ganze Zeile, benannt wird das erste fehlerhafte Feld."""
    broken = {**BSID_ROW, "BUDAT": "30/08/2026", "DMBTR": "x"}
    _stage_rows(canonical_db, mapping, tmp_path, "BSID", [broken])
    (_, reason, _), = _rejects(canonical_db)
    # BUDAT steht im Mapping vor DMBTR
    assert reason.startswith("BUDAT: ")


def test_reject_reason_never_quotes_the_value(canonical_db, mapping, tmp_path) -> None:
    """Regel 8: der Rohwert steht nur in `raw_excerpt`."""
    _stage_rows(canonical_db, mapping, tmp_path, "BSID", [{**BSID_ROW, "DMBTR": "12x34"}])
    (_, reason, excerpt), = _rejects(canonical_db)
    assert "12x34" not in reason
    assert "12x34" in excerpt


def test_amount_with_three_decimals_is_rejected(canonical_db, mapping, tmp_path) -> None:
    """Grenzfall: `1,234` ist in einer DECIMAL(15,2)-Spalte kein Betrag."""
    result = _stage_rows(canonical_db, mapping, tmp_path, "BSID", [{**BSID_ROW, "DMBTR": "1,234"}])
    assert result.rejected == 1
    (_, reason, _), = _rejects(canonical_db)
    assert reason.startswith("DMBTR: ")


def test_percent_over_the_domain_is_rejected(canonical_db, mapping, tmp_path) -> None:
    """`100,000` in ZBD1P heisst kaputter Export, nicht 100 Prozent Skonto."""
    result = _stage_rows(canonical_db, mapping, tmp_path, "BSID", [{**BSID_ROW, "ZBD1P": "100,000"}])
    assert result.rejected == 1
    (_, reason, _), = _rejects(canonical_db)
    assert reason.startswith("ZBD1P: ")


def test_unknown_debit_credit_is_rejected(canonical_db, mapping, tmp_path) -> None:
    """Ohne S oder H ist das Vorzeichen von amount_signed_local eine Vermutung."""
    result = _stage_rows(canonical_db, mapping, tmp_path, "BSID", [{**BSID_ROW, "SHKZG": "Q"}])
    assert result.rejected == 1
    (_, reason, _), = _rejects(canonical_db)
    assert reason.startswith("SHKZG: ")


def test_sap_initial_values_are_not_rejects(canonical_db, mapping, tmp_path) -> None:
    """Trifft nicht: leere Zelle und `00000000` sind fachlich `kein Wert` (D-035)."""
    row = {**BSID_ROW, "AUGDT": "00000000", "SKNTO": "", "ZBD1P": "", "UMSKZ": ""}
    result = _stage_rows(canonical_db, mapping, tmp_path, "BSID", [row])
    assert result.rejected == 0
    assert canonical_db.execute(
        'SELECT "AUGDT", "SKNTO", "ZBD1P" FROM "staged_BSID"'
    ).fetchone() == (None, None, None)


def test_dates_are_parsed(canonical_db, mapping, tmp_path) -> None:
    result = _stage_rows(canonical_db, mapping, tmp_path, "BSID", [BSID_ROW])
    assert result.rejected == 0
    assert canonical_db.execute('SELECT "BUDAT" FROM "staged_BSID"').fetchone() == (
        date(2026, 8, 1),
    )


# --- Notation je Datei ------------------------------------------------------------------


def test_notation_parameter_fills_in_when_the_file_is_silent(
    canonical_db, mapping, tmp_path
) -> None:
    """R-3: der Laufparameter greift nur, wo die Datei nichts belegt."""
    rows = [{**BSID_ROW, "WRBTR": "1.234", "DMBTR": "1.234", "SKFBT": "", "SKNTO": ""}]
    result = _stage_rows(canonical_db, mapping, tmp_path, "BSID", rows, notation="de")
    assert result.notation_source == "Parameter"
    assert result.rejected == 0
    assert canonical_db.execute('SELECT "DMBTR" FROM "staged_BSID"').fetchone() == (
        Decimal(1234),
    )


def test_ambiguous_without_notation_becomes_a_reject(canonical_db, mapping, tmp_path) -> None:
    rows = [{**BSID_ROW, "WRBTR": "1.234", "DMBTR": "1.234", "SKFBT": "", "SKNTO": ""}]
    result = _stage_rows(canonical_db, mapping, tmp_path, "BSID", rows)
    assert result.notation_source == "unbestimmt"
    assert result.rejected == 1


def test_file_notation_beats_the_parameter(canonical_db, mapping, tmp_path) -> None:
    """Die Datei belegt ihre Notation selbst; der Parameter wird als Hinweis ausgewiesen."""
    result = _stage_rows(canonical_db, mapping, tmp_path, "BSID", [BSID_ROW], notation="iso")
    assert result.notation == "de"
    assert result.notation_source == "Datei"
    assert any("iso" in warning for warning in result.warnings)


def test_conflicting_notation_names_both_columns(canonical_db, mapping, tmp_path) -> None:
    """R-1: Abbruch, und die Meldung nennt die beiden Spalten – keine Werte (Regel 8)."""
    rows = [{**BSID_ROW, "WRBTR": "1.234,56", "DMBTR": "1,234.56"}]
    load_table(canonical_db, _export(tmp_path, mapping, "BSID", rows))
    install_macros(canonical_db)
    with pytest.raises(StagingError) as excinfo:
        stage_table(canonical_db, mapping, "BSID", "test-run")
    message = str(excinfo.value)
    assert "WRBTR" in message and "DMBTR" in message
    assert "1.234,56" not in message and "1,234.56" not in message


def test_unknown_notation_parameter_is_refused(canonical_db, mapping, tmp_path) -> None:
    load_table(canonical_db, _export(tmp_path, mapping, "BSID", [BSID_ROW]))
    install_macros(canonical_db)
    with pytest.raises(StagingError, match="Dezimalnotation"):
        stage_table(canonical_db, mapping, "BSID", "test-run", notation="deutsch")


# --- Spaltenabgleich --------------------------------------------------------------------


def test_unknown_column_stops_the_table(canonical_db, mapping, tmp_path) -> None:
    """Regel 4: eine unbekannte Spalte wird mit Namen gemeldet, nicht uebergangen."""
    path = _export(tmp_path, mapping, "BSID", [BSID_ROW])
    text = path.read_text(encoding="utf-8").splitlines()
    text[0] += "\tZZBONUS"
    text[1] += "\t42"
    path.write_text("\n".join(text) + "\n", encoding="utf-8")
    load_table(canonical_db, path)
    install_macros(canonical_db)
    with pytest.raises(StagingError, match="ZZBONUS"):
        stage_table(canonical_db, mapping, "BSID", "test-run")


def test_missing_column_is_a_hint_not_a_stop(canonical_db, mapping, tmp_path) -> None:
    """Ein unvollstaendiger Export wird gestagt, die Luecke aber benannt.

    `testdata/encoding_samples/` liefert bewusst nur einen Ausschnitt der Spalten; ob ein
    fehlendes Feld den Lauf kosten muss, entscheidet erst das kanonische Modell (Aufgabe 2).
    """
    path = _export(tmp_path, mapping, "BSID", [BSID_ROW])
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    keep = [index for index, name in enumerate(header) if name != "SGTXT"]
    path.write_text(
        "\n".join("\t".join(line.split("\t")[index] for index in keep) for line in lines) + "\n",
        encoding="utf-8",
    )
    load_table(canonical_db, path)
    install_macros(canonical_db)
    result = stage_table(canonical_db, mapping, "BSID", "test-run")
    assert result.rows_staged == 1
    assert any("SGTXT" in warning for warning in result.warnings)
    columns = {
        name
        for (name,) in canonical_db.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'staged_BSID'"
        ).fetchall()
    }
    assert "SGTXT" not in columns
    assert "BUDAT" in columns


def test_missing_total_column_is_named(canonical_db, mapping, tmp_path) -> None:
    """Ohne BUKRS oder WAERS gibt es keine Kontrollsumme – und einen Fehler mit Namen.

    Frueher lief die Abfrage ungeprueft und endete in einem nackten DuckDB-Fehler ohne
    Tabellen- oder Spaltennamen; die Waehrung neben dem Betrag ist aber Regel 2, und ihr
    Fehlen gehoert benannt (Regel 4).
    """
    path = _export(tmp_path, mapping, "BSID", [BSID_ROW])
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    keep = [index for index, name in enumerate(header) if name != "WAERS"]
    path.write_text(
        "\n".join("\t".join(line.split("\t")[index] for index in keep) for line in lines) + "\n",
        encoding="utf-8",
    )
    load_table(canonical_db, path)
    install_macros(canonical_db)
    with pytest.raises(StagingError) as excinfo:
        stage_table(canonical_db, mapping, "BSID", "test-run")
    message = str(excinfo.value)
    assert "BSID" in message and "WAERS" in message


def test_totals_still_come_with_both_columns(canonical_db, mapping, tmp_path) -> None:
    """Gegenprobe: mit beiden Spalten steht die Summe wie bisher neben ihrer Waehrung."""
    result = _stage_rows(canonical_db, mapping, tmp_path, "BSID", [BSID_ROW])
    assert [total.to_dict() for total in result.totals] == [
        {"company_code": "1000", "currency": "EUR", "amount": "100.00"}
    ]


def test_missing_raw_table_is_named(canonical_db, mapping) -> None:
    install_macros(canonical_db)
    with pytest.raises(StagingError, match="raw_BSID"):
        stage_table(canonical_db, mapping, "BSID", "test-run")
