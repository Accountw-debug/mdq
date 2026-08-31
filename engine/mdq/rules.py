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
    "title",
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

#: Felder, die im Kopf stehen duerfen, aber nicht muessen. `title` ist seit der
#: Schema-Aenderung Pflicht, weil jedes Finding einen Titel tragen muss.
OPTIONAL_KEYS = ("parameters",)

#: Name eines Regelparameters: `${params.<name>}` im SQL, `parameters.<name>` im Kopf
_PARAMETER_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

#: Eine Schwelle, die ein Betrag ist, steht als ausgeschriebene Dezimalzahl im Kopf –
#: nie als float (Regel 2). Mehr als das kommt als Zeichenkette nicht ins SQL.
_DECIMAL_LITERAL_RE = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")

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

#: Schluessel, die `remediation` haben darf – gleich dem Finding-Schema, damit ein
#: falscher Schluessel den Regelautor trifft und nicht erst den Lauf.
REMEDIATION_KEYS = ("sap_transaction", "path", "field", "mass_change_eligible", "steps")

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
    #: Benannte Schwellen der Regel, als `${params.<name>}` ins SQL eingesetzt (D-107).
    #: Leer, wenn die Regel keine hat.
    parameters: dict[str, int | float | str]
    title: str
    sql: str
    path: Path


def _check_enum(errors: list[str], head: dict, key: str, allowed: tuple) -> None:
    value = head.get(key)
    if value not in allowed:
        errors.append(f"{key}: erlaubt sind {list(allowed)}")


def _check_text(errors: list[str], head: dict, key: str) -> None:
    value = head.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{key}: muss ein nicht-leerer Text sein")


#: Testlisten, die belegt sein muessen. `edge` bleibt optional: nicht jede Regel hat einen
#: Grenzfall, und ein erfundener waere schlechter als keiner (D-021, D-066).
REQUIRED_TEST_KEYS = ("hits", "no_hits")


def _check_tests(errors: list[str], head: dict) -> dict[str, tuple[str, ...]]:
    """Prueft `tests`. Leere `hits`/`no_hits` sind seit dem Demo-Mandanten ein Fehler (D-021)."""
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
        if key in REQUIRED_TEST_KEYS and not entries:
            errors.append(
                f"tests.{key}: leer – jede Regel braucht einen Testfall aus "
                "testdata/demo_mandant/defects.yaml (D-021, D-066)"
            )
            continue
        result[key] = tuple(entries)
    return result


def _check_parameters(errors: list[str], head: dict) -> dict[str, int | float | str]:
    """Prueft den optionalen Block `parameters` – benannte Schwellen der Regel (D-107).

    Zahlen werden unveraendert als Literal ins SQL gesetzt. Dazu ist **eine** Sorte
    Zeichenkette erlaubt: eine ausgeschriebene Dezimalzahl (`"1000.00"`). Der Grund ist
    Regel 2 – eine Schwelle, die ein Betrag ist, darf nicht durch ein `float`. YAML liest
    `1000.00` als `float`; der Vergleich in DuckDB zoege den DECIMAL-Betrag auf die
    Fliesskommaseite, und eine Schwelle wie `1000.05` waere binaer gar nicht darstellbar.
    Als Zeichenkette bleibt sie exakt und wird im SQL nach DECIMAL gecastet
    (`${params.min_loss}::DECIMAL(15,2)`); `repr()` setzt die Anfuehrungszeichen. Das
    Muster laesst nur Ziffern, ein Vorzeichen und einen Punkt zu – kein anderer Text
    kommt so ins SQL.
    """
    parameters = head.get("parameters")
    if parameters is None:
        return {}
    if not isinstance(parameters, dict) or not parameters:
        errors.append("parameters: muss ein nicht-leeres Objekt sein")
        return {}
    checked: dict[str, int | float | str] = {}
    for name, value in parameters.items():
        if not isinstance(name, str) or not _PARAMETER_NAME_RE.match(name):
            errors.append(f"parameters: '{name}' ist kein gueltiger Name ([a-z][a-z0-9_]*)")
            continue
        if isinstance(value, str):
            if not _DECIMAL_LITERAL_RE.match(value):
                errors.append(
                    f"parameters.{name}: als Zeichenkette ist nur eine ausgeschriebene "
                    f"Dezimalzahl erlaubt (etwa \"1000.00\"), nicht {value!r}"
                )
                continue
            checked[name] = value
            continue
        if isinstance(value, bool) or not isinstance(value, int | float):
            errors.append(
                f"parameters.{name}: erwartet eine Zahl oder eine ausgeschriebene "
                f"Dezimalzahl als Zeichenkette, nicht {type(value).__name__}"
            )
            continue
        checked[name] = value
    return checked


def _check_remediation(errors: list[str], head: dict) -> dict[str, Any]:
    remediation = head.get("remediation")
    if not isinstance(remediation, dict):
        errors.append("remediation: muss ein Objekt mit sap_transaction sein")
        return {}
    if not isinstance(remediation.get("sap_transaction"), str):
        errors.append("remediation.sap_transaction: fehlt oder ist kein Text")
    if not isinstance(remediation.get("mass_change_eligible"), bool):
        errors.append("remediation.mass_change_eligible: fehlt oder ist kein Wahrheitswert")
    unknown = sorted(set(remediation) - set(REMEDIATION_KEYS))
    if unknown:
        errors.append(
            f"remediation: unbekannte Schluessel {unknown}, erlaubt sind {list(REMEDIATION_KEYS)}"
        )
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

    for key in ("title", "plain_logic", "why", "if_wrong"):
        _check_text(errors, head, key)

    plain_logic = head.get("plain_logic")
    if isinstance(plain_logic, str) and _TEMPLATE_PLAIN_LOGIC_MARKER in plain_logic:
        errors.append("plain_logic: enthaelt noch den Platzhaltertext aus _TEMPLATE.rule.sql")

    remediation = _check_remediation(errors, head)
    parameters = _check_parameters(errors, head)
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
        parameters=parameters,
        title=head["title"].strip(),
        sql=sql,
        path=path,
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
