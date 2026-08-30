"""SAP-Wertformate: Text -> Decimal / date.

Beträge sind immer ``Decimal``, nie ``float`` (CLAUDE.md, Regel 2). Nicht parsebare Werte
werfen ``ParseError``; der Aufrufer schreibt daraus eine Zeile in ``reject`` – nichts wird
still zu NULL (Regel 4).

Fehlermeldungen beschreiben die **Form** des Wertes, nie den Wert selbst: ein Betrag oder
Datum kann zu einem Geschäftspartner gehören und darf nicht in Logs stehen (Regel 8).
Der Rohwert gehört ausschließlich in ``reject.raw_excerpt``.
"""

import re
from collections.abc import Iterable
from datetime import date
from decimal import Decimal, InvalidOperation

#: SAP-Initialwerte für Datumsfelder – fachlich "kein Datum", kein Reject
DATE_INITIALS = frozenset({"00000000", "00.00.0000", "0000-00-00"})

#: Dezimalnotationen: "de" = 1.234,56 · "iso" = 1234.56 (D-035)
NOTATIONS = ("de", "iso")

#: Welche Notation ein eindeutiger Dezimaltrenner belegt
_NOTATION_BY_DECIMAL = {",": "de", ".": "iso"}

#: SAP schreibt "X" für gesetzt; leer heisst nicht gesetzt
FLAG_TRUE = "X"

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


def _single_separator(body: str) -> tuple[str, int] | None:
    """Der einzige vorkommende Trenner und die Zahl der ihm folgenden Ziffern.

    ``None``, sobald beide Trenner vorkommen, keiner vorkommt oder einer mehrfach steht –
    dann ist die Lesart schon aus dem Wert heraus entschieden.
    """
    has_dot, has_comma = "." in body, "," in body
    if has_dot == has_comma:
        return None
    separator = "." if has_dot else ","
    if body.count(separator) > 1:
        return None
    return separator, len(body) - body.rfind(separator) - 1


def _decimal_separator(body: str, notation: str | None = None) -> str | None:
    """Bestimmt den Dezimaltrenner. None = keiner, der Wert ist ganzzahlig.

    Regeln: kommen Punkt und Komma vor, ist der **letzte** der Dezimaltrenner. Kommt nur
    eines von beiden mehrfach vor, ist es der Tausendertrenner. Kommt es genau einmal vor,
    entscheidet die Zahl der folgenden Ziffern – bei genau drei ist der Wert mehrdeutig
    (``1.234`` ist deutsch 1234, ISO 1,234).

    Für den mehrdeutigen Fall entscheidet ``notation``, die Notation der Datei (D-035).
    Ohne sie bleibt es beim ``ParseError``: geraten wird nicht.
    """
    has_dot, has_comma = "." in body, "," in body
    if has_dot and has_comma:
        return "." if body.rfind(".") > body.rfind(",") else ","

    single = _single_separator(body)
    if single is None:
        return None
    separator, following = single
    if following != 3:
        return separator
    if notation is None:
        raise ParseError(
            "mehrdeutiges Betragsformat: ein einzelner Trenner mit genau drei folgenden "
            "Ziffern kann Tausender- oder Dezimaltrenner sein"
        )
    # In der Notation der Datei ist genau ein Zeichen der Dezimaltrenner; ist es ein
    # anderes, steht hier ein Tausendertrenner und der Wert ist ganzzahlig.
    return separator if _NOTATION_BY_DECIMAL[separator] == notation else None


def detect_notation(values: Iterable[str | None]) -> str | None:
    """Notation aus den **eindeutigen** Werten einer Spalte: ``"de"``, ``"iso"`` oder None.

    Eindeutig ist ein Wert, der beide Trenner enthält, einen Trenner mehrfach führt oder
    genau einen Trenner mit ein bis zwei folgenden Ziffern hat. Alles andere (``1.234``,
    ``0``, leer) sagt nichts und wird übergangen. Widersprechen sich zwei Werte derselben
    Spalte, gewinnt keiner: die Spalte gilt als stumm, und der Widerspruch fällt beim
    Vergleich der Spalten auf (Aufgabe 1, R-1).

    Deterministisch: das Ergebnis hängt nicht von der Reihenfolge der Werte ab (Regel 9).
    """
    seen: set[str] = set()
    for text in values:
        if text is None:
            continue
        body = text.strip()
        if not body:
            continue
        body, _ = _strip_sign(body)
        if not _AMOUNT_ALLOWED.match(body):
            continue
        body = body.replace(" ", "")

        has_dot, has_comma = "." in body, "," in body
        if has_dot and has_comma:
            last = "." if body.rfind(".") > body.rfind(",") else ","
            seen.add(_NOTATION_BY_DECIMAL[last])
            continue
        single = _single_separator(body)
        if single is None:
            # Ein Trenner mehrfach: er ist der Tausendertrenner, der andere der Dezimaltrenner.
            if has_dot or has_comma:
                thousands = "." if has_dot else ","
                seen.add("de" if thousands == "." else "iso")
            continue
        separator, following = single
        if 1 <= following <= 2:
            seen.add(_NOTATION_BY_DECIMAL[separator])

    return seen.pop() if len(seen) == 1 else None


def parse_amount(text: str | None, notation: str | None = None) -> Decimal | None:
    """Liest einen SAP-Betrag als ``Decimal``.

    Leerer Wert -> ``None`` (SAP-Initialwert, kein Reject). ``"0,00"`` ist dagegen ein
    echter Betrag und ergibt ``Decimal("0.00")``.

    Erkannt werden deutsche (``1.234,56``) und ISO-Schreibweise (``1234.56``), Leerzeichen
    als Tausendertrenner sowie vorangestelltes und nachgestelltes Vorzeichen.

    ``notation`` ist die Notation der Datei (``"de"`` / ``"iso"``, D-035) und wird nur für
    mehrdeutige Werte wie ``1.234`` gebraucht; ohne sie bleiben die abgelehnt.
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
    separator = _decimal_separator(body, notation)
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


def parse_percent(text: str | None) -> Decimal | None:
    """Liest einen SAP-Prozentsatz (``2,000``) als ``Decimal``.

    Prozentfelder tragen drei Nachkommastellen und nie einen Tausendertrenner: ein
    einzelner Trenner ist deshalb immer der Dezimaltrenner, unabhängig von der Notation
    der Datei (D-048). ``ZPRZ1``/``ZBD1P`` sind Prozentsätze mit festem SAP-Format, keine
    Beträge – die Notationserkennung gilt für sie nicht.
    """
    if text is None:
        return None
    body = text.strip()
    if not body:
        return None

    body, sign = _strip_sign(body)
    if not body:
        raise ParseError("Prozentsatz besteht nur aus einem Vorzeichen")
    if not _AMOUNT_ALLOWED.match(body):
        raise ParseError("Prozentsatz enthält unerlaubte Zeichen (erlaubt: Ziffern, Punkt, Komma)")

    body = body.replace(" ", "")
    if "." in body and "," in body:
        raise ParseError("Prozentsatz hat zwei Trenner – erwartet wird genau ein Dezimaltrenner")
    single = _single_separator(body)
    if single is None and ("." in body or "," in body):
        raise ParseError("Prozentsatz hat denselben Trenner mehrfach")

    digits, fraction = (body, "") if single is None else body.split(single[0])
    if not _DIGITS_ONLY.match(digits or "0") or (fraction and not _DIGITS_ONLY.match(fraction)):
        raise ParseError("Prozentsatz hat kein gültiges Ziffernmuster")

    literal = f"{digits or '0'}.{fraction}" if fraction else (digits or "0")
    try:
        return Decimal(literal) * sign
    except InvalidOperation as exc:  # pragma: no cover – vom Muster oben abgedeckt
        raise ParseError("Prozentsatz ist keine gültige Dezimalzahl") from exc


def parse_integer(text: str | None) -> int | None:
    """Liest ein SAP-Ganzzahlfeld (``ZTAG1``, ``MAHNS``); führende Nullen sind erlaubt.

    Leerer Wert -> ``None``. Ein Trenner ist hier ein Fehler: ein Zahlungsziel in Tagen
    hat keine Nachkommastelle, und stillschweigend zu runden wäre ein verworfener
    Unterschied (Regel 4).
    """
    if text is None:
        return None
    body = text.strip()
    if not body:
        return None

    body, sign = _strip_sign(body)
    if not _DIGITS_ONLY.match(body):
        raise ParseError("Ganzzahl enthält andere Zeichen als Ziffern")
    return int(body) * sign


def parse_flag(text: str | None) -> bool | None:
    """Liest ein SAP-Kennzeichen: ``"X"`` -> ``True``, leer -> ``None``.

    Leer wird ``None`` und nicht ``False``: ``staged`` spiegelt die Quelle, die
    ``NOT NULL DEFAULT FALSE``-Vorgaben des kanonischen Schemas setzt das Mapping
    (Aufgabe 2). Jeder andere Wert ist ein Fehler statt einer stillen Annahme.
    """
    if text is None:
        return None
    body = text.strip()
    if not body:
        return None
    if body.upper() == FLAG_TRUE:
        return True
    raise ParseError(f'Kennzeichen ist weder leer noch "{FLAG_TRUE}"')
