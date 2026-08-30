"""SAP-Wertformate. Die Fälle stammen aus testdata/encoding_samples/BSID_formats.txt."""

from datetime import date
from decimal import Decimal

import pytest

from mdq.formats import ParseError, parse_amount, parse_date

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
