"""Validierung von Findings gegen ``logic/finding.schema.json``.

Jedes Finding wird gegen das Schema geprueft; ein ungueltiges Finding laesst den Lauf
fehlschlagen (CLAUDE.md, Regel 6). Die Fehlermeldungen zitieren bewusst **nie** den
beanstandeten Wert, sondern nur Pfad und verletzte Bedingung – ein Wert koennte ein Name,
eine IBAN oder eine Adresse sein, und die gehoeren nicht in Logs (Regel 8).
"""

import json
from collections.abc import Iterable
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from mdq import FINDING_SCHEMA

#: Dateiendungen, die als Finding gelesen werden. YAML fuer die fachlichen Beispiele,
#: JSON, weil das der Vertrag zur UI ist (D-007).
FINDING_SUFFIXES = (".yaml", ".yml", ".json")

_TIMESTAMP_TAG = "tag:yaml.org,2002:timestamp"


class FindingYamlLoader(yaml.SafeLoader):
    """SafeLoader ohne Timestamp-Resolver.

    PyYAML macht aus ``data_as_of: 2026-08-28`` sonst ein ``datetime.date``-Objekt. Dann
    scheitert die Schema-Pruefung mit "ist kein String", statt das Format zu pruefen.
    Ohne den Resolver kommt der Wert als Text an und ``format: date`` greift.
    """


FindingYamlLoader.yaml_implicit_resolvers = {
    first_char: [(tag, regexp) for tag, regexp in resolvers if tag != _TIMESTAMP_TAG]
    for first_char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


class FindingFileError(ValueError):
    """Die Datei konnte nicht als Finding gelesen werden."""


format_checker = FormatChecker()


@format_checker.checks("date-time", raises=ValueError)
def _check_date_time(value: object) -> bool:
    """Prueft ``format: date-time``.

    Der mitgelieferte FormatChecker kennt ``date-time`` nur mit dem Zusatzpaket
    ``rfc3339-validator``; ohne das Paket wuerde das Format still ungeprueft bleiben
    (D-018). ``fromisoformat`` versteht ab Python 3.11 auch das Suffix ``Z``.
    """
    if not isinstance(value, str):
        return True
    datetime.fromisoformat(value)
    return True


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Laedt ``logic/finding.schema.json`` (einmalig, danach aus dem Cache)."""
    return json.loads(FINDING_SCHEMA.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(load_schema(), format_checker=format_checker)


def _path_label(path: Iterable[Any]) -> str:
    """JSON-Pfad als lesbaren Text, z. B. ``entity.bp_key`` oder ``evidence[0].agrees``."""
    label = ""
    for part in path:
        if isinstance(part, int):
            label += f"[{part}]"
        elif label:
            label += f".{part}"
        else:
            label = str(part)
    return label or "(Wurzel)"


def _invariant_note(error: Any) -> str:
    """Klartext der verletzten Invariante, falls der Fehler aus einem ``allOf``-Zweig kommt.

    Die drei Invarianten des Schemas (Klasse 1 nie Stufe A, Stufe A/B braucht ein Soll,
    mass_change nur bei Stufe A) tragen dort eine ``description``. Ohne sie waere die
    Meldung technisch korrekt, aber fachlich stumm.
    """
    schema_path = list(error.absolute_schema_path)
    if len(schema_path) >= 2 and schema_path[0] == "allOf":
        branch = load_schema()["allOf"][schema_path[1]]
        description = branch.get("description")
        if description:
            return f" – {description}"
    return ""


def _describe(error: Any) -> str:
    """Baut eine Meldung aus Pfad und Bedingung, ohne den beanstandeten Wert (D-015)."""
    label = _path_label(error.absolute_path)
    if error.validator in ("required", "additionalProperties"):
        # Diese Meldungen nennen nur Feldnamen, keine Werte.
        detail = error.message
    else:
        detail = f"verletzt {error.validator}: {json.dumps(error.validator_value, ensure_ascii=False)}"
    return f"{label}: {detail}{_invariant_note(error)}"


def validate_finding(finding: dict[str, Any]) -> list[str]:
    """Validiert ein Finding. Leere Liste = valide.

    Die Reihenfolge ist deterministisch nach Pfad und Validator sortiert (D-016), damit
    gleicher Input immer dieselbe Ausgabe liefert.
    """
    errors = _validator().iter_errors(finding)
    ordered = sorted(errors, key=lambda e: ([str(p) for p in e.absolute_path], str(e.validator)))
    return [_describe(error) for error in ordered]


def load_finding_file(path: Path) -> dict[str, Any]:
    """Liest ein Finding aus YAML oder JSON.

    Wirft ``FindingFileError`` mit Grund – nicht lesbare Dateien werden nie stumm
    uebersprungen (Regel 4).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise FindingFileError(f"nicht als UTF-8 lesbar: {exc.__class__.__name__}") from exc

    try:
        if path.suffix == ".json":
            document = json.loads(text)
        else:
            document = yaml.load(text, Loader=FindingYamlLoader)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise FindingFileError(f"nicht parsebar: {exc.__class__.__name__}") from exc

    if not isinstance(document, dict):
        raise FindingFileError(f"enthaelt kein Objekt, sondern {type(document).__name__}")
    return document


def iter_finding_files(path: Path) -> list[Path]:
    """Findet Finding-Dateien: eine Datei oder alle passenden in einem Verzeichnis.

    Sortiert, damit die Ausgabe reproduzierbar ist (Regel 9).
    """
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(p for p in path.rglob("*") if p.is_file() and p.suffix in FINDING_SUFFIXES)
    raise FindingFileError(f"Pfad existiert nicht: {path}")


def duplicate_finding_ids(findings_by_file: dict[Path, dict[str, Any]]) -> dict[str, list[Path]]:
    """Findet finding_ids, die in mehreren Dateien vorkommen.

    Die finding_id ist ein Hash ueber Regel und Ist-Zustand; doppelte IDs bedeuten
    entweder eine Kopie oder eine falsch gebildete ID. Beides muss auffallen.
    """
    by_id: dict[str, list[Path]] = {}
    for file_path, finding in sorted(findings_by_file.items()):
        finding_id = finding.get("finding_id")
        if isinstance(finding_id, str):
            by_id.setdefault(finding_id, []).append(file_path)
    return {fid: paths for fid, paths in sorted(by_id.items()) if len(paths) > 1}
