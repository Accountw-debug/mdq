"""SAP-Wertformate: Text -> Decimal / date.

Beträge sind immer ``Decimal``, nie ``float`` (CLAUDE.md, Regel 2). Nicht parsebare Werte
werfen ``ParseError``; der Aufrufer schreibt daraus eine Zeile in ``reject`` – nichts wird
still zu NULL (Regel 4).

Fehlermeldungen beschreiben die **Form** des Wertes, nie den Wert selbst: ein Betrag oder
Datum kann zu einem Geschäftspartner gehören und darf nicht in Logs stehen (Regel 8).
Der Rohwert gehört ausschließlich in ``reject.raw_excerpt``.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

#: SAP-Initialwerte für Datumsfelder – fachlich "kein Datum", kein Reject
DATE_INITIALS = frozenset({"00000000", "00.00.0000", "0000-00-00"})

_DIGITS_ONLY = re.compile(r"\A[0-9]+\Z")
_AMOUNT_ALLOWED = re.compile(r"\A[0-9., ]+\Z")
_DATE_COMPACT = re.compile(r"\A([0-9]{4})([0-9]{2})([0-9]{2})\Z")
_DATE_GERMAN = re.compile(r"\A([0-9]{1,2})\.([0-9]{1,2})\.([0-9]{4})\Z")
_DATE_ISO = re.compile(r"\A([0-9]{4})-([0-9]{2})-([0-9]{2})\Z")


class ParseError(ValueError):
    """Der Wert konnte nicht als Betrag oder Datum gelesen werden."""


def _strip_sign(text: str) -> tuple[str, int]:
    """Trennt das Vorzeichen ab. SAP schreibt es vorangestellt oder nachgestellt."""
    sign = 1
    if text.endswith(("-", "+")):
        sign = -1 if text.endswith("-") else 1
        text = text[:-1].rstrip()
    elif text.startswith(("-", "+")):
        sign = -1 if text.startswith("-") else 1
        text = text[1:].lstrip()
    return text, sign


def _decimal_separator(body: str) -> str | None:
    """Bestimmt den Dezimaltrenner. None = keiner, der Wert ist ganzzahlig.

    Regeln: kommen Punkt und Komma vor, ist der **letzte** der Dezimaltrenner. Kommt nur
    eines von beiden mehrfach vor, ist es der Tausendertrenner. Kommt es genau einmal vor,
    entscheidet die Zahl der folgenden Ziffern – bei genau drei ist der Wert mehrdeutig
    (``1.234`` ist deutsch 1234, ISO 1,234) und wird abgelehnt statt geraten.
    """
    has_dot, has_comma = "." in body, "," in body
    if has_dot and has_comma:
        return "." if body.rfind(".") > body.rfind(",") else ","
    separator = "." if has_dot else "," if has_comma else None
    if separator is None:
        return None
    if body.count(separator) > 1:
        return None
    following = len(body) - body.rfind(separator) - 1
    if following == 3:
        raise ParseError(
            "mehrdeutiges Betragsformat: ein einzelner Trenner mit genau drei folgenden "
            "Ziffern kann Tausender- oder Dezimaltrenner sein"
        )
    return separator


def parse_amount(text: str | None) -> Decimal | None:
    """Liest einen SAP-Betrag als ``Decimal``.

    Leerer Wert -> ``None`` (SAP-Initialwert, kein Reject). ``"0,00"`` ist dagegen ein
    echter Betrag und ergibt ``Decimal("0.00")``.

    Erkannt werden deutsche (``1.234,56``) und ISO-Schreibweise (``1234.56``), Leerzeichen
    als Tausendertrenner sowie vorangestelltes und nachgestelltes Vorzeichen.
    """
    if text is None:
        return None
    body = text.strip()
    if not body:
        return None

    body, sign = _strip_sign(body)
    if not body:
        raise ParseError("Betrag besteht nur aus einem Vorzeichen")
    if not _AMOUNT_ALLOWED.match(body):
        raise ParseError("Betrag enthält unerlaubte Zeichen (erlaubt: Ziffern, Punkt, Komma)")

    body = body.replace(" ", "")
    separator = _decimal_separator(body)
    if separator is None:
        digits, fraction = body.replace(".", "").replace(",", ""), ""
    else:
        thousands = "," if separator == "." else "."
        digits, _, fraction = body.replace(thousands, "").partition(separator)

    if not _DIGITS_ONLY.match(digits or "0") or (fraction and not _DIGITS_ONLY.match(fraction)):
        raise ParseError("Betrag hat kein gültiges Ziffernmuster")

    literal = f"{digits or '0'}.{fraction}" if fraction else (digits or "0")
    try:
        value = Decimal(literal)
    except InvalidOperation as exc:  # pragma: no cover – vom Muster oben abgedeckt
        raise ParseError("Betrag ist keine gültige Dezimalzahl") from exc
    return value * sign


def parse_date(text: str | None) -> date | None:
    """Liest ein SAP-Datum.

    Leerer Wert und Initialwerte (``00000000``) -> ``None``, kein Reject.
    Erkannt: ``20260830``, ``30.08.2026``, ``2026-08-30``.
    """
    if text is None:
        return None
    body = text.strip()
    if not body or body in DATE_INITIALS:
        return None

    for pattern, order in (
        (_DATE_COMPACT, (0, 1, 2)),
        (_DATE_ISO, (0, 1, 2)),
        (_DATE_GERMAN, (2, 1, 0)),
    ):
        match = pattern.match(body)
        if not match:
            continue
        parts = match.groups()
        year, month, day = (int(parts[index]) for index in order)
        try:
            return date(year, month, day)
        except ValueError as exc:
            raise ParseError(f"Datum ist kein gültiger Kalendertag ({exc})") from exc

    raise ParseError("Datum passt zu keinem bekannten Format (YYYYMMDD, TT.MM.JJJJ, YYYY-MM-DD)")
