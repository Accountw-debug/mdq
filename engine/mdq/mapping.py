"""Laden und Pruefen von ``logic/mappings/sap_ecc.yaml``.

Das Mapping ist die Quelle der Wahrheit fuer Feldlisten: welche Spalte eines SE16N-Exports
in welches kanonische Feld laeuft, welche Spalte bewusst ignoriert wird und welche Typklasse
ein Feld beim Staging bekommt. Wie beim Regelloader wird die Datei vollstaendig geprueft,
bevor eine Zeile Daten fliesst – ein Fehler im Mapping soll den Autor treffen, nicht erst
den Lauf beim Kunden.

Eine Spalte, die weder unter ``fields`` noch unter ``ignore`` steht, ist ein Fehler mit
Spaltenname (CLAUDE.md, Regel 4). Ein gemapptes Feld ohne Eintrag in ``field_types`` ebenso:
stillschweigend TEXT waere genau die Annahme, die fuehrende Nullen rettet und Datumsfelder
verliert.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from mdq import SAP_MAPPING

#: Typklassen, die ``field_types`` kennt – Reihenfolge = Reihenfolge der Meldungen
TYPE_CLASSES = ("amount", "percent", "date", "integer", "flag", "text")

#: Typklasse -> Spaltentyp der Staging-Tabelle (DuckDB-Dialekt).
#: Beträge sind DECIMAL, nie float (Regel 2, D-009); Schlüssel bleiben TEXT.
COLUMN_TYPE = {
    "amount": "DECIMAL(15,2)",
    "percent": "DECIMAL(5,3)",
    "date": "DATE",
    "integer": "INTEGER",
    "flag": "BOOLEAN",
    "text": "TEXT",
}

#: Schluessel, die eine Tabelle im Mapping tragen darf
TABLE_KEYS = (
    "target",
    "role",
    "key",
    "fields",
    "ignore",
    "join",
    "status",
    "is_open",
    "filter",
    "fields_of_interest",
)

#: Schluessel auf oberster Ebene
TOP_LEVEL_KEYS = ("version", "detect", "tables", "derivations", "field_types")

#: Tabellen mit diesem Status sind angemeldet, aber noch nicht Teil der Pipeline
STATUS_LATER = "later"


class MappingError(ValueError):
    """Das Mapping ist unvollstaendig, widerspruechlich oder nicht lesbar."""


@dataclass(frozen=True)
class TableMapping:
    """Eine Quelltabelle des Mappings (``KNA1``, ``BSID``, …)."""

    name: str
    target: str | None
    role: str | None
    key: tuple[str, ...]
    #: SAP-Feld -> kanonisches Feld, in der Reihenfolge des Mappings
    fields: dict[str, str]
    ignore: tuple[str, ...]
    is_open: bool | None
    join: dict[str, tuple[str, ...]]
    status: str | None

    @property
    def columns(self) -> tuple[str, ...]:
        """Die gemappten Spalten in Mapping-Reihenfolge."""
        return tuple(self.fields)

    @property
    def is_staged(self) -> bool:
        """Wahr, wenn die Tabelle in dieser Ausbaustufe gestagt wird."""
        return self.status != STATUS_LATER and self.target is not None and bool(self.fields)


@dataclass(frozen=True)
class Mapping:
    """Das gepruefte Mapping einer Quelle (hier: SAP ECC)."""

    version: str
    tables: dict[str, TableMapping]
    field_types: dict[str, str]
    detect: dict[str, tuple[str, ...]]
    path: Path

    @property
    def staged_tables(self) -> list[TableMapping]:
        """Tabellen, die das Staging fuellt – nach Namen sortiert (Regel 9)."""
        return sorted(
            (table for table in self.tables.values() if table.is_staged),
            key=lambda table: table.name,
        )

    def table(self, name: str) -> TableMapping:
        """Die Tabelle zum Namen; unbekannt ist ein Fehler mit Namen, kein stilles Nichts."""
        try:
            return self.tables[name.upper()]
        except KeyError:
            raise MappingError(
                f"{name}: im Mapping {self.path.name} nicht beschrieben. "
                f"Bekannt sind: {', '.join(sorted(self.tables))}."
            ) from None

    def type_of(self, field: str) -> str:
        """Typklasse eines SAP-Feldes."""
        try:
            return self.field_types[field]
        except KeyError:
            raise MappingError(
                f"{field}: keine Typklasse in field_types – "
                f"erlaubt sind {list(TYPE_CLASSES)}."
            ) from None


def _as_str_list(value: Any) -> list[str] | None:
    """Liste von Texten oder None, wenn der Wert keine ist."""
    if value is None:
        return []
    if isinstance(value, list) and all(isinstance(entry, str) for entry in value):
        return value
    return None


def _check_table(errors: list[str], name: str, spec: Any) -> TableMapping | None:
    """Prueft eine Tabelle des Mappings und baut sie; None, wenn sie unbrauchbar ist."""
    if not isinstance(spec, dict):
        errors.append(f"tables.{name}: muss ein Objekt sein")
        return None

    unknown = sorted(set(spec) - set(TABLE_KEYS))
    if unknown:
        errors.append(f"tables.{name}: unbekannte Schluessel {unknown}")

    fields = spec.get("fields") or {}
    if not isinstance(fields, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in fields.items()
    ):
        errors.append(f"tables.{name}.fields: muss SAP-Feld -> kanonisches Feld abbilden")
        fields = {}

    ignore = _as_str_list(spec.get("ignore"))
    if ignore is None:
        errors.append(f"tables.{name}.ignore: muss eine Liste von Spaltennamen sein")
        ignore = []
    duplicates = sorted({entry for entry in ignore if ignore.count(entry) > 1})
    if duplicates:
        errors.append(f"tables.{name}.ignore: doppelte Eintraege {duplicates}")

    both = sorted(set(fields) & set(ignore))
    if both:
        errors.append(
            f"tables.{name}: {both} stehen zugleich unter fields und ignore – "
            "eine Spalte wird entweder gemappt oder bewusst ignoriert"
        )

    status = spec.get("status")
    if status is not None and status != STATUS_LATER:
        errors.append(f'tables.{name}.status: erlaubt ist nur "{STATUS_LATER}"')

    target = spec.get("target")
    if target is not None and not isinstance(target, str):
        errors.append(f"tables.{name}.target: muss ein Text oder null sein")
        target = None

    is_open = spec.get("is_open")
    if is_open is not None and not isinstance(is_open, bool):
        errors.append(f"tables.{name}.is_open: muss ein Wahrheitswert sein")
        is_open = None

    key = spec.get("key")
    key_list = [key] if isinstance(key, str) else _as_str_list(key)
    if key_list is None:
        errors.append(f"tables.{name}.key: muss ein Spaltenname oder eine Liste davon sein")
        key_list = []
    unknown_key = sorted(set(key_list) - set(fields))
    if unknown_key and fields:
        errors.append(f"tables.{name}.key: {unknown_key} stehen nicht unter fields")

    join: dict[str, tuple[str, ...]] = {}
    raw_join = spec.get("join") or {}
    if not isinstance(raw_join, dict):
        errors.append(f"tables.{name}.join: muss Zieltabelle -> Spaltenliste abbilden")
    else:
        for other, columns in raw_join.items():
            column_list = _as_str_list(columns)
            if column_list is None:
                errors.append(f"tables.{name}.join.{other}: muss eine Liste von Spalten sein")
                continue
            join[other] = tuple(column_list)

    return TableMapping(
        name=name,
        target=target,
        role=spec.get("role"),
        key=tuple(key_list),
        fields=dict(fields),
        ignore=tuple(ignore),
        is_open=is_open,
        join=join,
        status=status,
    )


def _check_field_types(errors: list[str], raw: Any, mapped: set[str]) -> dict[str, str]:
    """Prueft ``field_types`` gegen die tatsaechlich gemappten Felder."""
    if not isinstance(raw, dict):
        errors.append("field_types: muss Typklasse -> Feldliste abbilden")
        return {}

    unknown = sorted(set(raw) - set(TYPE_CLASSES))
    if unknown:
        errors.append(f"field_types: unbekannte Typklassen {unknown}, erlaubt {list(TYPE_CLASSES)}")

    result: dict[str, str] = {}
    twice: list[str] = []
    for type_class in TYPE_CLASSES:
        entries = _as_str_list(raw.get(type_class))
        if entries is None:
            errors.append(f"field_types.{type_class}: muss eine Liste von Feldnamen sein")
            continue
        for field in entries:
            if field in result:
                twice.append(field)
                continue
            result[field] = type_class
    if twice:
        errors.append(f"field_types: {sorted(set(twice))} stehen in mehr als einer Typklasse")

    without_type = sorted(mapped - set(result))
    if without_type:
        errors.append(
            f"field_types: gemappte Felder ohne Typklasse {without_type} – "
            "ohne Eintrag wuerde stillschweigend TEXT angenommen (Regel 4)"
        )
    unused = sorted(set(result) - mapped)
    if unused:
        errors.append(
            f"field_types: {unused} werden von keiner Tabelle gemappt – "
            "Eintrag entfernen oder Feld ergaenzen"
        )
    return result


def parse_mapping(document: Any, path: Path) -> Mapping:
    """Prueft ein geladenes Mapping-Dokument und meldet alle Probleme gemeinsam."""
    if not isinstance(document, dict):
        raise MappingError(f"{path.name}: enthaelt kein Objekt")

    errors: list[str] = []
    missing = [key for key in TOP_LEVEL_KEYS if key not in document]
    if missing:
        errors.append(f"Pflichtabschnitte fehlen: {missing}")
    unknown = sorted(set(document) - set(TOP_LEVEL_KEYS))
    if unknown:
        errors.append(f"unbekannte Abschnitte: {unknown}")

    version = document.get("version")
    if not isinstance(version, str) or not version.strip():
        errors.append("version: muss ein nicht-leerer Text sein")
        version = ""

    raw_tables = document.get("tables")
    tables: dict[str, TableMapping] = {}
    if not isinstance(raw_tables, dict) or not raw_tables:
        errors.append("tables: muss ein nicht-leeres Objekt sein")
    else:
        for name, spec in raw_tables.items():
            table = _check_table(errors, name, spec)
            if table is not None:
                tables[name] = table

    mapped = {field for table in tables.values() for field in table.fields}
    field_types = _check_field_types(errors, document.get("field_types"), mapped)

    detect: dict[str, tuple[str, ...]] = {}
    raw_detect = document.get("detect")
    if not isinstance(raw_detect, dict):
        errors.append("detect: muss Tabelle -> Spaltenliste abbilden")
    else:
        for name, columns in raw_detect.items():
            column_list = _as_str_list(columns)
            if column_list is None:
                errors.append(f"detect.{name}: muss eine Liste von Spaltennamen sein")
                continue
            if name not in tables:
                errors.append(f"detect.{name}: unter tables nicht beschrieben")
            detect[name] = tuple(column_list)

    if errors:
        joined = "\n    ".join(errors)
        raise MappingError(f"{path.name}:\n    {joined}")

    return Mapping(
        version=version,
        tables=tables,
        field_types=field_types,
        detect=detect,
        path=path,
    )


def load_mapping(path: Path = SAP_MAPPING) -> Mapping:
    """Liest und prueft das Mapping."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise MappingError(f"{path.name}: nicht als UTF-8 lesbar ({type(exc).__name__})") from exc
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise MappingError(f"{path.name}: kein gueltiges YAML ({type(exc).__name__})") from exc
    return parse_mapping(document, path)


def unknown_columns(table: TableMapping, columns: list[str]) -> list[str]:
    """Spalten des Exports, die das Mapping weder abbildet noch ignoriert."""
    known = set(table.fields) | set(table.ignore)
    return [name for name in columns if name not in known]


def missing_columns(table: TableMapping, columns: list[str]) -> list[str]:
    """Gemappte Felder, die der Export nicht liefert."""
    return [name for name in table.fields if name not in columns]


def check_export_columns(table: TableMapping, columns: list[str]) -> list[str]:
    """Vergleicht die Kopfzeile eines Exports mit dem Mapping.

    Zwei getrennte Meldungen, weil es zwei verschiedene Ursachen sind: eine unbekannte
    Spalte ist ein Mapping, das nachgezogen werden muss (Regel 4); eine fehlende Spalte
    ist ein unvollstaendiger Export.
    """
    errors: list[str] = []
    unknown = unknown_columns(table, columns)
    if unknown:
        errors.append(
            f"{table.name}: unbekannte Spalten {unknown} – im Mapping unter fields "
            "aufnehmen oder unter ignore eintragen"
        )
    absent = missing_columns(table, columns)
    if absent:
        errors.append(f"{table.name}: im Export fehlen gemappte Spalten {absent}")
    return errors
