"""Schreiben der Exportdateien im SE16N-Format und des Manifests.

Format wie ein SE16N-Export mit technischen Spaltennamen: Tabulator als Trenner, UTF-8
ohne BOM, Datum ``YYYYMMDD``, Beträge in deutscher Schreibweise (``1.234,56``), Vorzeichen
über ``SHKZG`` statt am Betrag, Schlüssel unkonvertiert mit führenden Nullen (D-009).

Die Spaltenliste je Tabelle kommt aus `logic/mappings/sap_ecc.yaml` – es gibt keine
zweite Feldliste im Code. Fehlt eine Spalte in einer Zeile, ist das ein Fehler und kein
leeres Feld: der Generator soll jede Spalte bewusst füllen (CLAUDE.md Regel 4).
"""

import hashlib
import json
from decimal import Decimal
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

import yaml

from mdq import LOGIC_DIR
from mdq.demo import DATA_AS_OF, GENERATOR_VERSION, MANDT, TABLES

#: SAP-Initialwert eines leeren Datumsfeldes; der Loader macht daraus NULL (D-035)
DATE_INITIAL = "00000000"

#: Trenner und Zeilenende des Exports
DELIMITER = "\t"
LINE_END = "\n"


class WriterError(ValueError):
    """Eine Zeile passt nicht zur Spaltenliste der Tabelle."""


@lru_cache(maxsize=1)
def _mapping() -> dict[str, Any]:
    text = (LOGIC_DIR / "mappings" / "sap_ecc.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(text)


@cache
def columns_for(table: str) -> tuple[str, ...]:
    """Spalten der Exportdatei: ``MANDT`` und die Felder aus dem Mapping, in Mapping-Reihenfolge."""
    tables = _mapping()["tables"]
    if table not in tables:
        raise WriterError(f"{table}: im Mapping logic/mappings/sap_ecc.yaml nicht beschrieben.")
    fields = tables[table].get("fields")
    if not fields:
        raise WriterError(f"{table}: im Mapping ohne Feldliste.")
    return ("MANDT", *fields)


def fmt_text(value: str | None) -> str:
    """Text; ``None`` wird zur leeren Zelle."""
    return "" if value is None else str(value)


def fmt_key(value: str | int, width: int) -> str:
    """Schlüssel mit führenden Nullen, zum Beispiel ``0000100234``."""
    return str(value).rjust(width, "0")


def fmt_flag(value: bool) -> str:
    """SAP-Kennzeichen: ``X`` oder leer."""
    return "X" if value else ""


def fmt_date(value) -> str:
    """Datum als ``YYYYMMDD``; ``None`` wird zum Initialwert ``00000000``."""
    return DATE_INITIAL if value is None else f"{value:%Y%m%d}"


def fmt_amount(value: Decimal) -> str:
    """Betrag in deutscher Schreibweise mit zwei Nachkommastellen, ohne Vorzeichen.

    Das Vorzeichen steht in SAP im Soll-/Haben-Kennzeichen ``SHKZG``; ein negativer Betrag
    wäre hier ein Fehler im Generator und kein Format-Sonderfall.
    """
    if value < 0:
        raise WriterError("negativer Betrag – das Vorzeichen gehört in SHKZG")
    quantized = value.quantize(Decimal("0.01"))
    return f"{quantized:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def fmt_percent(value: Decimal) -> str:
    """Prozentsatz mit drei Nachkommastellen, wie SAP die Felder ZPRZ1/ZBD1P führt."""
    return f"{value.quantize(Decimal('0.001')):.3f}".replace(".", ",")


def fmt_int(value: int) -> str:
    """Ganzzahl ohne führende Nullen (Tage, Zähler)."""
    return str(value)


def write_table(out_dir: Path, table: str, rows: list[dict[str, str]]) -> dict[str, Any]:
    """Schreibt ``<TABELLE>.txt`` und liefert den Manifest-Eintrag."""
    columns = columns_for(table)
    lines = [DELIMITER.join(columns)]
    for index, row in enumerate(rows):
        missing = [column for column in columns if column not in row]
        if missing:
            raise WriterError(f"{table}, Zeile {index + 1}: Spalten fehlen: {missing}")
        unknown = sorted(set(row) - set(columns))
        if unknown:
            raise WriterError(f"{table}, Zeile {index + 1}: unbekannte Spalten: {unknown}")
        values = [row[column] for column in columns]
        broken = [
            columns[position]
            for position, value in enumerate(values)
            if not isinstance(value, str) or DELIMITER in value or "\n" in value
        ]
        if broken:
            raise WriterError(f"{table}, Zeile {index + 1}: Werte mit Trenner oder Umbruch: {broken}")
        lines.append(DELIMITER.join(values))

    path = out_dir / f"{table}.txt"
    payload = (LINE_END.join(lines) + LINE_END).encode("utf-8")
    path.write_bytes(payload)
    return {
        "table": table,
        "file": path.name,
        "rows": len(rows),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def write_manifest(out_dir: Path, seed: int, entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Schreibt ``manifest.json``: Seed, Version, Datenstand, Zeilen und Hash je Datei."""
    manifest = {
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "client": MANDT,
        "data_as_of": DATA_AS_OF.isoformat(),
        "tables": entries,
        "total_rows": sum(entry["rows"] for entry in entries),
    }
    text = json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    (out_dir / "manifest.json").write_text(text, encoding="utf-8")
    return manifest


def expected_tables() -> tuple[str, ...]:
    """Die 16 Tabellen des Demo-Mandanten in Schreibreihenfolge."""
    return TABLES
