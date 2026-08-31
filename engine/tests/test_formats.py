"""SAP-Wertformate. Die Fälle stammen aus testdata/encoding_samples/BSID_formats.txt."""

from datetime import date
from decimal import Decimal

import duckdb
import pytest

from mdq import RULE_MACROS
from mdq.formats import (
    ParseError,
    detect_notation,
    format_amount,
    format_date,
    parse_amount,
    parse_date,
    parse_flag,
    parse_integer,
    parse_percent,
)

# --- Beträge -------------------------------------------------------------------------

AMOUNTS = [
    # aus SPRINT-1.md
    ("1.234,56-", Decimal("-1234.56")),
    ("1234.56", Decimal("1234.56")),
    # aus BSID_formats.txt
    ("1.234,56", Decimal("1234.56")),
    ("8.930,00", Decimal("8930.00")),
    # führendes Minus (Freigabe Victor)
    ("-1234.56", Decimal("-1234.56")),
    ("-1.234,56", Decimal("-1234.56")),
    ("+1.234,56", Decimal("1234.56")),
    ("1.234,56+", Decimal("1234.56")),
    # Null ist ein echter Wert, kein Initialwert
    ("0,00", Decimal("0.00")),
    ("0.00", Decimal("0.00")),
    # Tausendertrenner mehrfach, ganzzahlig
    ("1.234.567", Decimal(1234567)),
    ("1,234,567", Decimal(1234567)),
    ("1 234 567,89", Decimal("1234567.89")),
    ("1234", Decimal(1234)),
    # gemischt: der letzte Trenner entscheidet
    ("1,234.56", Decimal("1234.56")),
]


@pytest.mark.parametrize(("text", "expected"), AMOUNTS, ids=[a[0] for a in AMOUNTS])
def test_parse_amount(text, expected) -> None:
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text", ["", "   ", None])
def test_empty_amount_is_none(text) -> None:
    """Leere Zelle -> NULL, kein Reject."""
    assert parse_amount(text) is None


def test_amount_is_never_float() -> None:
    """Regel 2: Beträge sind Decimal, nie float."""
    value = parse_amount("1.234,56")
    assert isinstance(value, Decimal)
    assert not isinstance(value, float)


def test_amount_is_exact_not_rounded() -> None:
    assert parse_amount("0,10") + parse_amount("0,20") == Decimal("0.30")


def test_amount_keeps_two_decimals() -> None:
    assert str(parse_amount("8.930,00")) == "8930.00"


@pytest.mark.parametrize("text", ["1.234", "1,234", "12.345"])
def test_ambiguous_grouping_is_rejected(text) -> None:
    """Ein einzelner Trenner mit drei folgenden Ziffern ist mehrdeutig – nicht raten."""
    with pytest.raises(ParseError) as excinfo:
        parse_amount(text)
    assert "mehrdeutig" in str(excinfo.value)


@pytest.mark.parametrize("text", ["abc", "12x34", "1.2.3,4,5", "-", "EUR 12"])
def test_unparsable_amount_raises(text) -> None:
    """Regel 4: kein stilles NULL, kein Ersatzwert."""
    with pytest.raises(ParseError):
        parse_amount(text)


# --- Datum ---------------------------------------------------------------------------

DATES = [
    ("20260830", date(2026, 8, 30)),
    ("30.08.2026", date(2026, 8, 30)),
    ("2026-08-30", date(2026, 8, 30)),
    ("20260501", date(2026, 5, 1)),
    ("30.05.2026", date(2026, 5, 30)),
    ("1.1.2026", date(2026, 1, 1)),
]


@pytest.mark.parametrize(("text", "expected"), DATES, ids=[d[0] for d in DATES])
def test_parse_date(text, expected) -> None:
    assert parse_date(text) == expected


@pytest.mark.parametrize("text", ["", "   ", None, "00000000", "00.00.0000", "0000-00-00"])
def test_initial_date_is_none(text) -> None:
    """SAP-Initialwert -> NULL, kein Reject."""
    assert parse_date(text) is None


@pytest.mark.parametrize("text", ["20261301", "32.01.2026", "20260230"])
def test_invalid_calendar_day_raises(text) -> None:
    with pytest.raises(ParseError) as excinfo:
        parse_date(text)
    assert "Kalendertag" in str(excinfo.value)


@pytest.mark.parametrize("text", ["30/08/2026", "Aug 30 2026", "260830", "20260830X"])
def test_unknown_date_format_raises(text) -> None:
    with pytest.raises(ParseError):
        parse_date(text)


# --- Regel 8: keine Werte in Meldungen ----------------------------------------------


@pytest.mark.parametrize("text", ["1.234", "12x34", "30/08/2026", "20261301", "1.2.3,4,5"])
def test_messages_never_quote_the_value(text) -> None:
    """Ein Betrag oder Datum kann zu einem Geschäftspartner gehören – nicht in Logs.

    Der Rohwert gehört ausschließlich in ``reject.raw_excerpt`` (Regel 8).
    """
    raised = False
    for parser in (parse_amount, parse_date):
        try:
            parser(text)
        except ParseError as exc:
            raised = True
            assert text not in str(exc), f"{parser.__name__} nennt den Wert in der Meldung"
    assert raised, "Testfall loest keinen ParseError aus"


# --- Notation je Datei (D-035) --------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "notation", "expected"),
    [
        # der Trenner ist Tausendertrenner: 1234
        ("1.234", "de", Decimal(1234)),
        ("1,234", "iso", Decimal(1234)),
        # der Trenner ist Dezimaltrenner
        ("1,234", "de", Decimal("1.234")),
        ("1.234", "iso", Decimal("1.234")),
        # eindeutige Werte bleiben unabhaengig von der Notation, was sie sind
        ("1.234,56", "de", Decimal("1234.56")),
        ("1.234,56", "iso", Decimal("1234.56")),
        ("1234.56", "de", Decimal("1234.56")),
    ],
)
def test_notation_decides_only_the_ambiguous_case(text, notation, expected) -> None:
    assert parse_amount(text, notation) == expected


def test_ambiguous_amount_without_notation_stays_a_reject() -> None:
    """Grenzfall: ohne Notation wird nicht geraten (D-035)."""
    with pytest.raises(ParseError, match="mehrdeutig"):
        parse_amount("1.234")


NOTATIONS = [
    # eindeutig deutsch
    (["1.234,56"], "de"),
    (["0,00"], "de"),
    (["1.234.567"], "de"),
    (["8.930,00", "1.234"], "de"),
    # eindeutig ISO
    (["1234.56"], "iso"),
    (["1,234.56"], "iso"),
    (["1,234,567"], "iso"),
    # sagt nichts: nur mehrdeutige, leere oder trennerlose Werte
    (["1.234"], None),
    (["1234", "", "0"], None),
    ([None, "   "], None),
    # widersprechen sich zwei Werte, gewinnt keiner
    (["1.234,56", "1,234.56"], None),
]


@pytest.mark.parametrize(("values", "expected"), NOTATIONS, ids=range(len(NOTATIONS)))
def test_detect_notation(values, expected) -> None:
    assert detect_notation(values) == expected


def test_detect_notation_ignores_order() -> None:
    """Determinismus: dieselben Werte ergeben dieselbe Notation, egal in welcher Folge."""
    values = ["1.234", "0,00", "", "8.930,00"]
    assert detect_notation(values) == detect_notation(list(reversed(values))) == "de"


def test_detect_notation_skips_unparsable_values() -> None:
    """Ein kaputter Wert entscheidet die Notation der Datei nicht mit."""
    assert detect_notation(["12x34", "1.234,56"]) == "de"


# --- Prozentsaetze (D-048) ------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2,000", Decimal("2.000")),
        ("2.000", Decimal("2.000")),
        ("0,000", Decimal("0.000")),
        ("100,000", Decimal("100.000")),
        ("3", Decimal(3)),
    ],
)
def test_parse_percent(text, expected) -> None:
    """Ein einzelner Trenner ist im Prozentfeld immer der Dezimaltrenner."""
    assert parse_percent(text) == expected


@pytest.mark.parametrize("text", ["", "   ", None])
def test_empty_percent_is_none(text) -> None:
    assert parse_percent(text) is None


@pytest.mark.parametrize("text", ["1.234,56", "2,0,0", "2x"])
def test_bad_percent_raises(text) -> None:
    with pytest.raises(ParseError):
        parse_percent(text)


def test_percent_ignores_the_file_notation() -> None:
    """`2.000` ist ein Prozentsatz von 2, kein Tausender – auch in einer de-Datei."""
    assert parse_percent("2.000") == parse_percent("2,000") == Decimal("2.000")


# --- Ganzzahlen und Kennzeichen -------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [("30", 30), ("00", 0), ("0", 0), ("007", 7), ("-5", -5), ("", None), (None, None)],
)
def test_parse_integer(text, expected) -> None:
    assert parse_integer(text) == expected


@pytest.mark.parametrize("text", ["2,5", "2.5", "x"])
def test_integer_with_separator_raises(text) -> None:
    """Grenzfall: ein Zahlungsziel hat keine Nachkommastelle – nicht stillschweigend runden."""
    with pytest.raises(ParseError):
        parse_integer(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("X", True), ("x", True), (" X ", True), ("", None), ("   ", None), (None, None)],
)
def test_parse_flag(text, expected) -> None:
    assert parse_flag(text) is expected


@pytest.mark.parametrize("text", ["Y", "0", "1", "XX"])
def test_unknown_flag_raises(text) -> None:
    """Trifft nicht: alles ausser leer und X ist ein Fehler, keine stille Annahme."""
    with pytest.raises(ParseError):
        parse_flag(text)


def test_new_parsers_never_quote_the_value() -> None:
    """Regel 8 gilt auch fuer die neuen Parser."""
    for parser, text in ((parse_percent, "1.234,56"), (parse_integer, "2,5"), (parse_flag, "Y")):
        with pytest.raises(ParseError) as excinfo:
            parser(text)
        assert text not in str(excinfo.value), parser.__name__


# --- Betragsformatierer fuer Freitext (D-187) ----------------------------------------


@pytest.mark.parametrize(
    ("wert", "waehrung", "erwartet"),
    [
        ("42100.00", "EUR", "42.100,00 EUR"),
        ("0.00", "EUR", "0,00 EUR"),
        ("999.99", "EUR", "999,99 EUR"),
        ("1000.00", "EUR", "1.000,00 EUR"),
        ("1234567.89", "CHF", "1.234.567,89 CHF"),
        ("-1092.32", "EUR", "-1.092,32 EUR"),
        ("9999999999999.99", "EUR", "9.999.999.999.999,99 EUR"),
        ("42100.00", None, "42.100,00"),
        ("7", "EUR", "7,00 EUR"),
        (None, "EUR", None),
    ],
)
def test_format_amount(wert, waehrung, erwartet) -> None:
    assert format_amount(wert, waehrung) == erwartet


def test_format_amount_nimmt_decimal() -> None:
    assert format_amount(Decimal("42100.00"), "EUR") == "42.100,00 EUR"
    assert format_amount(Decimal("-0.05"), "EUR") == "-0,05 EUR"


def test_format_amount_lehnt_float_ab() -> None:
    """Regel 2 endet nicht an der Darstellung."""
    with pytest.raises(TypeError):
        format_amount(42100.0, "EUR")


def test_format_amount_rundet_nicht() -> None:
    """Runden gehoert in die Regel, nicht in die Darstellung."""
    with pytest.raises(ValueError, match="Nachkommastellen"):
        format_amount("1.005", "EUR")


def test_format_amount_lehnt_unsinn_ab() -> None:
    with pytest.raises(ValueError, match="kein Betrag"):
        format_amount("42.100,00", "EUR")


def test_makro_und_python_sind_gleich() -> None:
    """`mdq_money` im SQL und `format_amount` in Python schreiben denselben Text.

    Sonst stuende im Titel eines Findings eine andere Schreibweise als im Run-Report –
    derselbe Betrag, zwei Bilder.
    """
    werte = [
        "0.00", "0.01", "0.99", "1.00", "9.99", "10.00", "99.99", "100.00", "999.99",
        "1000.00", "1000.01", "9999.99", "10000.00", "123456.78", "1234567.89",
        "999999999.99", "9999999999999.99", "-0.01", "-1092.32", "-1234567.89",
    ]
    con = duckdb.connect(":memory:")
    try:
        con.execute(RULE_MACROS.read_text(encoding="utf-8"))
        for wert in werte:
            aus_sql = con.execute(
                "SELECT mdq_money(CAST(? AS DECIMAL(15,2)), 'EUR')", [wert]
            ).fetchone()[0]
            assert aus_sql == format_amount(wert, "EUR"), wert
    finally:
        con.close()


# --- Datum als Freitext (D-201) --------------------------------------------------------


@pytest.mark.parametrize(
    ("wert", "erwartet"),
    [
        ("2026-03-17", "17.03.2026"),
        ("2024-09-01", "01.09.2024"),
        ("2026-12-31", "31.12.2026"),
        ("2024-02-29", "29.02.2024"),
        ("1999-01-01", "01.01.1999"),
        (None, None),
    ],
)
def test_format_date(wert, erwartet) -> None:
    assert format_date(wert) == erwartet


def test_format_date_nimmt_date() -> None:
    assert format_date(date(2026, 3, 17)) == "17.03.2026"
    assert format_date(date(2024, 9, 1)) == "01.09.2024"


def test_format_date_lehnt_alles_andere_ab() -> None:
    """Ein halb geparstes Datum waere schlimmer als keines."""
    for unsinn in ("17.03.2026", "20260317", "2026-3-17", "2026-03-17T08:00:00Z", ""):
        with pytest.raises(ValueError, match="kein ISO-Datum"):
            format_date(unsinn)


def test_datums_makro_und_python_sind_gleich() -> None:
    """`mdq_date` im SQL und `format_date` in Python schreiben denselben Text.

    Dieselbe Klammer wie bei `mdq_money`: sonst stuende im Ist-Text eines Findings eine
    andere Schreibweise als im Run-Report – dasselbe Datum, zwei Bilder.
    """
    werte = [
        "2024-01-01", "2024-02-29", "2024-09-01", "2024-09-06", "2024-12-31",
        "2025-01-31", "2025-08-28", "2026-03-17", "2026-08-28", "2026-12-31",
        "1999-12-31", "2000-01-01", "2019-01-02", "2100-01-01",
    ]
    con = duckdb.connect(":memory:")
    try:
        con.execute(RULE_MACROS.read_text(encoding="utf-8"))
        for wert in werte:
            aus_sql = con.execute("SELECT mdq_date(CAST(? AS DATE))", [wert]).fetchone()[0]
            assert aus_sql == format_date(wert), wert
    finally:
        con.close()
