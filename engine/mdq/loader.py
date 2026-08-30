"""Einlesen von SE16N-Exporten in DuckDB – nur Encoding und Format, kein Mapping.

Encoding wird erkannt, nicht angenommen (docs/CONCEPT.md, Abschnitt 10). Alle Spalten
landen als TEXT in ``raw_<TABELLE>``: führende Nullen in Schlüsseln müssen erhalten
bleiben (Regel 2, D-009), und Typ-Inferenz ist genau das, was sie frisst.

Die Rohdatei wird nie verändert (Regel 3). Nicht-UTF-8-Dateien werden für den Import in
eine temporäre UTF-8-Fassung übersetzt; der ``sha256`` bezieht sich immer auf die
Originalbytes, sonst wäre er kein Beleg für die Eingabedatei.

Jede Rohtabelle trägt zusätzlich ``_row_no``: die Nummer der Datenzeile in der Datei.
Ohne sie könnte ein Reject aus einer späteren Stufe nicht sagen, welche Zeile gemeint
ist (Regel 4), und eine im Nachhinein vergebene Nummer wäre nicht die der Datei.
"""

import csv
import hashlib
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

#: Trenner in der Reihenfolge ihrer Bevorzugung
DELIMITERS = (("\t", "Tab"), (";", "Semikolon"))

#: Höchstlänge des Rohauszugs in ``reject`` – die einzige Stelle für Rohdaten
RAW_EXCERPT_LIMIT = 200

#: Zeilennummer der Datenzeile in der Datei, 1-basiert ohne Kopfzeile
ROW_NO_COLUMN = "_row_no"

_BOMS = (
    (b"\xef\xbb\xbf", "UTF-8-BOM", "utf-8-sig"),
    (b"\xff\xfe", "UTF-16-LE", "utf-16"),
    (b"\xfe\xff", "UTF-16-BE", "utf-16"),
)


class LoaderError(ValueError):
    """Die Datei konnte nicht eingelesen werden."""


@dataclass(frozen=True)
class LoadResult:
    """Ergebnis eines Datei-Imports – Grundlage für den Run-Report (Aufgabe 6)."""

    table: str
    path: Path
    rows: int
    encoding: str
    delimiter: str
    sha256: str
    columns: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def sha256_of(path: Path) -> str:
    """Hash über die Originalbytes der Datei."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_encoding(raw: bytes, path: Path) -> tuple[str, str, tuple[str, ...]]:
    """Erkennt das Encoding: (Anzeigename, Python-Codec, Warnungen).

    Reihenfolge: BOM ist eindeutig; ohne BOM wird UTF-8 strikt versucht; erst wenn das
    scheitert, greift CP1252. Der Fallback ist die einzige Stelle, an der geraten wird –
    deshalb wird er als Warnung ausgewiesen und im Run-Report gezeigt.

    Bewusst ohne Ratebibliothek (chardet): statistische Erkennung ist nicht
    deterministisch (Regel 9).
    """
    for prefix, label, codec in _BOMS:
        if raw.startswith(prefix):
            return label, codec, ()
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return (
            "CP1252",
            "cp1252",
            (
                (
                    f"{path.name}: kein BOM und kein gültiges UTF-8 – als CP1252 gelesen. "
                    "Das ist die einzige geratene Annahme; Umlaute im Ergebnis prüfen."
                ),
            ),
        )
    return "UTF-8", "utf-8", ()


def detect_delimiter(header_line: str, path: Path) -> tuple[str, str]:
    """Erkennt den Spaltentrenner an der Kopfzeile: (Zeichen, Anzeigename)."""
    counts = {char: header_line.count(char) for char, _ in DELIMITERS}
    for char, label in DELIMITERS:
        if counts[char] > 0:
            return char, label
    raise LoaderError(
        f"{path.name}: kein Spaltentrenner in der Kopfzeile gefunden "
        f"(erwartet {' oder '.join(label for _, label in DELIMITERS)})."
    )


def default_table_name(path: Path) -> str:
    """Tabellenname aus dem Dateinamen: ``KNA1_utf8_tab.txt`` -> ``KNA1``."""
    stem = path.stem.split("_", 1)[0].strip().upper()
    if not stem:
        raise LoaderError(f"{path.name}: aus dem Dateinamen lässt sich kein Tabellenname ableiten.")
    return stem


def header_columns(header_line: str, delimiter: str) -> list[str]:
    """Spaltennamen der Kopfzeile, Anführungszeichen entfernt."""
    return next(csv.reader([header_line], delimiter=delimiter, quotechar='"'), [])


def _check_columns(columns: list[str], path: Path) -> None:
    """Leere oder doppelte Spaltennamen sind ein Fehler, keine stille Umbenennung.

    Geprueft wird die Kopfzeile der Datei, nicht das Ergebnis von DuckDB: DuckDB haengt
    an doppelte Namen still ein ``_1`` an – das waere ein stumm verworfener Unterschied
    (Regel 4).
    """
    if not columns:
        raise LoaderError(f"{path.name}: Kopfzeile enthaelt keine Spalten.")
    blank = [index for index, name in enumerate(columns) if not name.strip()]
    if blank:
        raise LoaderError(f"{path.name}: leere Spaltennamen an Position {blank}.")
    duplicates = sorted({name for name in columns if columns.count(name) > 1})
    if duplicates:
        raise LoaderError(f"{path.name}: doppelte Spaltennamen {duplicates}.")


def load_table(
    con: duckdb.DuckDBPyConnection, path: Path, table: str | None = None
) -> LoadResult:
    """Liest eine Exportdatei in ``raw_<TABELLE>``; alle Spalten der Datei als TEXT.

    Dazu kommt ``_row_no`` als erste Spalte. ``LoadResult.columns`` bleibt die Kopfzeile
    der Datei – sie beschreibt den Export, nicht die Tabelle.
    """
    if not path.is_file():
        raise LoaderError(f"Datei existiert nicht: {path}")

    raw = path.read_bytes()
    if not raw.strip():
        raise LoaderError(f"{path.name}: Datei ist leer.")

    encoding, codec, warnings = detect_encoding(raw, path)
    try:
        text = raw.decode(codec)
    except UnicodeDecodeError as exc:  # pragma: no cover – cp1252 ist total
        raise LoaderError(f"{path.name}: Dekodieren als {encoding} fehlgeschlagen ({exc.reason}).")

    header_line = text.splitlines()[0] if text.splitlines() else ""
    delimiter, delimiter_label = detect_delimiter(header_line, path)

    _check_columns(header_columns(header_line, delimiter), path)

    table_name = (table or default_table_name(path)).upper()
    target = f"raw_{table_name}"

    # Einheitlich über eine UTF-8-Zwischenfassung importieren: DuckDB liest CP1252 und
    # UTF-16 nicht, und ein Weg für alle Encodings garantiert identische Ergebnisse.
    with tempfile.TemporaryDirectory(prefix="mdq-load-") as tmp:
        staged = Path(tmp) / f"{table_name}.csv"
        staged.write_text(text, encoding="utf-8", newline="")
        try:
            # parallel=False: die Zeilennummer muss die der Datei sein, nicht die eines
            # Scans, der die Blöcke in beliebiger Reihenfolge zusammenführt (Regel 9).
            relation = con.read_csv(
                str(staged),
                delimiter=delimiter,
                header=True,
                all_varchar=True,
                quotechar='"',
                parallel=False,
            )
            columns = list(relation.columns)
            con.execute(
                f'CREATE OR REPLACE TABLE "{target}" AS '
                f'SELECT row_number() OVER () AS "{ROW_NO_COLUMN}", * FROM relation'
            )
        except duckdb.Error as exc:
            raise LoaderError(f"{path.name}: CSV nicht lesbar ({type(exc).__name__}).") from exc

    rows = con.execute(f'SELECT count(*) FROM "{target}"').fetchone()[0]
    return LoadResult(
        table=table_name,
        path=path,
        rows=rows,
        encoding=encoding,
        delimiter=delimiter_label,
        sha256=sha256_of(path),
        columns=tuple(columns),
        warnings=warnings,
    )


def record_reject(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    stage: str,
    source_table: str,
    row_no: int | None,
    reason: str,
    raw_excerpt: str | None = None,
) -> None:
    """Schreibt eine nicht verarbeitbare Zeile mit Grund in ``reject`` (Regel 4).

    ``raw_excerpt`` ist laut kanonischem Schema die einzige Stelle, an der Rohdaten stehen
    dürfen; er wird auf ``RAW_EXCERPT_LIMIT`` Zeichen gekürzt und gehört nie in eine
    Logmeldung oder Exception (Regel 8).
    """
    excerpt = None if raw_excerpt is None else raw_excerpt[:RAW_EXCERPT_LIMIT]
    con.execute(
        "INSERT INTO reject (run_id, stage, source_table, row_no, reason, raw_excerpt) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [run_id, stage, source_table, row_no, reason, excerpt],
    )
