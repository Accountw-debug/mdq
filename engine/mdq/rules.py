"""Laden und Pruefen der Regeln aus ``logic/rules/``.

Eine Regel = eine Datei ``<ID>.rule.sql`` mit YAML-Kopf zwischen ``/* ---`` und ``--- */``
(CLAUDE.md, Regel 5). Der Loader prueft den Kopf vollstaendig, bevor das SQL je ausgefuehrt
wird: ein Fehler im Kopf soll den Regelautor treffen, nicht erst den Lauf beim Kunden.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from mdq import RULES_DIR

#: Pflichtfelder im Regelkopf (Reihenfolge = Reihenfolge der Meldungen)
REQUIRED_KEYS = (
    "id",
    "version",
    "side",
    "category",
    "severity",
    "damage_class",
    "default_tier",
    "default_action_type",
    "requires_tables",
    "plain_logic",
    "why",
    "if_wrong",
    "remediation",
    "tests",
)

#: Felder, die im Kopf stehen duerfen, aber nicht muessen. `title` ist auch im
#: Finding-Schema optional.
OPTIONAL_KEYS = ("title",)

SIDES = ("AR", "AP", "CROSS")
SEVERITIES = ("low", "medium", "high", "critical")
DAMAGE_CLASSES = (1, 2, 3)
TIERS = ("A", "B", "C", "decision")
ACTION_TYPES = ("mass_change", "review", "decision", "process")

#: Kuerzel in der Regel-ID -> Kategorie im Glossar
CATEGORY_BY_CODE = {
    "COM": "completeness",
    "VAL": "validity",
    "CON": "consistency",
    "HYG": "hygiene",
    "RSK": "risk",
    "DUP": "duplicate",
    "LEA": "leakage",
}

TEST_KEYS = ("hits", "no_hits", "edge")

_HEADER_RE = re.compile(r"\A/\* ---\n(?P<head>.*?)\n--- \*/\n(?P<sql>.*)\Z", re.DOTALL)
_ID_RE = re.compile(r"\A(AR|AP|CROSS)-(COM|VAL|CON|HYG|RSK|DUP|LEA)-([0-9]{3})\Z")
_VERSION_RE = re.compile(r"\A[0-9]+\.[0-9]+\Z")

#: Dateien mit diesem Praefix sind Vorlagen, keine Regeln (z. B. `_TEMPLATE.rule.sql`)
TEMPLATE_PREFIX = "_"
RULE_SUFFIX = ".rule.sql"

#: Platzhaltertext aus `_TEMPLATE.rule.sql` – im Klartext einer echten Regel ein Fehler
_TEMPLATE_PLAIN_LOGIC_MARKER = "In einem Satz:"


class RuleError(ValueError):
    """Der Regelkopf ist unvollstaendig, widerspruechlich oder nicht lesbar."""


@dataclass(frozen=True)
class Rule:
    """Eine geladene Regel: geprueft Kopf, unveraendertes SQL."""

    id: str
    version: str
    side: str
    category: str
    severity: str
    damage_class: int
    default_tier: str
    default_action_type: str
    requires_tables: tuple[str, ...]
    plain_logic: str
    why: str
    if_wrong: str
    remediation: dict[str, Any]
    tests: dict[str, tuple[str, ...]]
    sql: str
    path: Path
    title: str | None = None

    @property
    def warnings(self) -> list[str]:
        """Nicht blockierende Hinweise.

        Testfaelle koennen erst mit dem Demo-Mandanten (Sprint 2) gefuellt werden; bis
        dahin sind leere Listen eine Warnung, danach ein Fehler (D-021).
        """
        messages = []
        for key in ("hits", "no_hits"):
            if not self.tests.get(key):
                messages.append(f"tests.{key} ist leer – Testfall fehlt (ab Sprint 2 ein Fehler)")
        return messages


def _check_enum(errors: list[str], head: dict, key: str, allowed: tuple) -> None:
    value = head.get(key)
    if value not in allowed:
        errors.append(f"{key}: erlaubt sind {list(allowed)}")


def _check_text(errors: list[str], head: dict, key: str) -> None:
    value = head.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{key}: muss ein nicht-leerer Text sein")


def _check_tests(errors: list[str], head: dict) -> dict[str, tuple[str, ...]]:
    """Prueft die Struktur von `tests`. Leere Listen sind hier bewusst kein Fehler."""
    tests = head.get("tests")
    if not isinstance(tests, dict):
        errors.append("tests: muss ein Objekt mit hits, no_hits und edge sein")
        return {}

    unknown = sorted(set(tests) - set(TEST_KEYS))
    if unknown:
        errors.append(f"tests: unbekannte Schluessel {unknown}, erlaubt sind {list(TEST_KEYS)}")

    result: dict[str, tuple[str, ...]] = {}
    for key in TEST_KEYS:
        if key not in tests:
            errors.append(f"tests.{key}: fehlt")
            continue
        entries = tests[key] or []
        if not isinstance(entries, list) or not all(isinstance(e, str) for e in entries):
            errors.append(f"tests.{key}: muss eine Liste von bp_key-Texten sein")
            continue
        result[key] = tuple(entries)
    return result


def _check_remediation(errors: list[str], head: dict) -> dict[str, Any]:
    remediation = head.get("remediation")
    if not isinstance(remediation, dict):
        errors.append("remediation: muss ein Objekt mit sap_transaction sein")
        return {}
    if not isinstance(remediation.get("sap_transaction"), str):
        errors.append("remediation.sap_transaction: fehlt oder ist kein Text")
    if not isinstance(remediation.get("mass_change_eligible"), bool):
        errors.append("remediation.mass_change_eligible: fehlt oder ist kein Wahrheitswert")
    return remediation


def _check_invariants(errors: list[str], head: dict, remediation: dict) -> None:
    """Fachliche Invarianten – sie fangen Fehler beim Regelautor statt erst im Lauf."""
    damage_class = head.get("damage_class")
    tier = head.get("default_tier")
    action_type = head.get("default_action_type")

    if damage_class == 1:
        if tier == "A":
            errors.append(
                "default_tier: Schadensklasse 1 (Bankdaten) wird nie Stufe A "
                "(CLAUDE.md Regel 11, D-005)"
            )
        if remediation.get("mass_change_eligible") is True:
            errors.append(
                "remediation.mass_change_eligible: Schadensklasse 1 ist nie massenaenderbar"
            )
    if action_type == "mass_change" and tier != "A":
        errors.append("default_action_type: mass_change setzt default_tier 'A' voraus")


def _check_id(errors: list[str], head: dict, path: Path) -> None:
    rule_id = head.get("id")
    if not isinstance(rule_id, str):
        errors.append("id: fehlt oder ist kein Text")
        return

    match = _ID_RE.match(rule_id)
    if not match:
        errors.append("id: erwartet <AR|AP|CROSS>-<COM|VAL|CON|HYG|RSK|DUP|LEA>-<NNN>")
        return

    side_code, category_code, _ = match.groups()
    if head.get("side") in SIDES and head["side"] != side_code:
        errors.append(f"side: widerspricht der id ({rule_id} erwartet side {side_code})")
    expected_category = CATEGORY_BY_CODE[category_code]
    if head.get("category") is not None and head["category"] != expected_category:
        errors.append(f"category: widerspricht der id ({rule_id} erwartet {expected_category})")

    expected_name = f"{rule_id}{RULE_SUFFIX}"
    if path.name != expected_name:
        errors.append(f"id: passt nicht zum Dateinamen (erwartet {expected_name})")


def parse_rule(text: str, path: Path) -> Rule:
    """Parst eine Regeldatei. Sammelt alle Probleme und meldet sie gemeinsam."""
    match = _HEADER_RE.match(text)
    if not match:
        raise RuleError(f"{path.name}: kein YAML-Kopf zwischen '/* ---' und '--- */' gefunden")

    try:
        head = yaml.safe_load(match.group("head"))
    except yaml.YAMLError as exc:
        raise RuleError(f"{path.name}: Kopf ist kein gueltiges YAML ({type(exc).__name__})") from exc

    if not isinstance(head, dict):
        raise RuleError(f"{path.name}: Kopf enthaelt kein Objekt")

    sql = match.group("sql").strip()
    errors: list[str] = []

    missing = [key for key in REQUIRED_KEYS if key not in head]
    if missing:
        errors.append(f"Pflichtfelder fehlen: {missing}")

    unknown = sorted(set(head) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    if unknown:
        errors.append(f"unbekannte Kopf-Felder: {unknown}")

    _check_id(errors, head, path)

    version = head.get("version")
    if not isinstance(version, str) or not _VERSION_RE.match(version):
        errors.append('version: erwartet Text im Format "1.0"')

    _check_enum(errors, head, "side", SIDES)
    _check_enum(errors, head, "category", tuple(CATEGORY_BY_CODE.values()))
    _check_enum(errors, head, "severity", SEVERITIES)
    _check_enum(errors, head, "damage_class", DAMAGE_CLASSES)
    _check_enum(errors, head, "default_tier", TIERS)
    _check_enum(errors, head, "default_action_type", ACTION_TYPES)

    tables = head.get("requires_tables")
    if not isinstance(tables, list) or not tables or not all(isinstance(t, str) for t in tables):
        errors.append("requires_tables: muss eine nicht-leere Liste von Tabellennamen sein")
        tables = []

    for key in ("plain_logic", "why", "if_wrong"):
        _check_text(errors, head, key)

    plain_logic = head.get("plain_logic")
    if isinstance(plain_logic, str) and _TEMPLATE_PLAIN_LOGIC_MARKER in plain_logic:
        errors.append("plain_logic: enthaelt noch den Platzhaltertext aus _TEMPLATE.rule.sql")

    remediation = _check_remediation(errors, head)
    tests = _check_tests(errors, head)
    _check_invariants(errors, head, remediation)

    if not sql:
        errors.append("SQL-Rumpf ist leer")

    if errors:
        joined = "\n    ".join(errors)
        raise RuleError(f"{path.name}:\n    {joined}")

    return Rule(
        id=head["id"],
        version=head["version"],
        side=head["side"],
        category=head["category"],
        severity=head["severity"],
        damage_class=head["damage_class"],
        default_tier=head["default_tier"],
        default_action_type=head["default_action_type"],
        requires_tables=tuple(tables),
        plain_logic=plain_logic.strip(),
        why=head["why"].strip(),
        if_wrong=head["if_wrong"].strip(),
        remediation=remediation,
        tests=tests,
        sql=sql,
        path=path,
        title=head.get("title"),
    )


def load_rule_file(path: Path) -> Rule:
    """Liest und prueft eine einzelne Regeldatei."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RuleError(f"{path.name}: nicht als UTF-8 lesbar ({type(exc).__name__})") from exc
    return parse_rule(text, path)


def iter_rule_files(directory: Path = RULES_DIR) -> list[Path]:
    """Regeldateien im Verzeichnis, sortiert; Vorlagen (`_*`) uebersprungen."""
    if not directory.is_dir():
        raise RuleError(f"Regelverzeichnis existiert nicht: {directory}")
    return sorted(
        path
        for path in directory.glob(f"*{RULE_SUFFIX}")
        if not path.name.startswith(TEMPLATE_PREFIX)
    )


def load_rules(directory: Path = RULES_DIR) -> list[Rule]:
    """Laedt alle Regeln eines Verzeichnisses, nach ID sortiert (Determinismus, Regel 9)."""
    rules = [load_rule_file(path) for path in iter_rule_files(directory)]
    return sorted(rules, key=lambda rule: rule.id)
