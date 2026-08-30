"""Entscheidungsgedaechtnis: gepflegte Entscheidungen wirken ueber Laeufe hinweg.

Ein Kunde entscheidet einmal, dass zwei Konten bewusst getrennt bleiben oder ein Wert
richtig ist – und will das im naechsten Lauf nicht wieder als offenen Punkt sehen. Die
Entscheidungen stehen dafuer in einer gepflegten YAML-Datei (``--decisions``, ersatzweise
``<input>/decisions.yaml``) und nicht im ``findings.json`` eines Vorlaufs: das koppelte
Laeufe aneinander, und der Vergleich zweier Laeufe ist ausdruecklich nicht Sprint 3/4
(D-088). Spaeter schreibt die UI diese Datei.

Was das Gedaechtnis **nicht** tut: Findings unterdruecken. Das Finding entsteht wie
sonst auch und traegt den gespeicherten Status statt ``open`` – eine Whitelist wirkt,
aber nichts verschwindet stumm (Regel 4). Auffaellt der Unterschied im Report: geladene,
angewandte und verwaiste Eintraege stehen dort mit Zahl.

Geprueft wird streng, weil ein Gedaechtnis mit falschen Schluesseln schlimmer ist als
keines: ``rule_id`` und ``bp_key`` stehen redundant neben der ``finding_id`` und muessen
zum erzeugten Finding passen (sonst ist der Eintrag nach einer Regelaenderung veraltet),
ein unbekannter ``reason_code`` ist ein Fehler mit Zeilennummer, ein Eintrag ohne
passendes Finding ein Hinweis.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import duckdb
import yaml

#: Vorgabename im Eingabeverzeichnis, wenn ``--decisions`` fehlt
DEFAULT_FILENAME = "decisions.yaml"

#: Gruende, aus denen ein Fall entschieden sein kann, und der Status, den das Finding
#: danach traegt. Beide Werte stehen so in ``logic/finding.schema.json`` – hier wird
#: kein neuer Statuswert erfunden (D-089).
REASON_STATUS = {
    "intentionally_separate": "rejected",
    "data_correct": "rejected",
    "not_relevant": "rejected",
    "accepted_risk": "accepted_risk",
}

#: Pflichtfelder eines Eintrags. ``reason`` gehoert dazu, weil das Finding-Schema den
#: Grund verlangt und eine Entscheidung ohne Begruendung im naechsten Jahr niemandem hilft.
REQUIRED_FIELDS = (
    "finding_id", "rule_id", "bp_key", "decided_by", "decided_at", "reason_code", "reason",
)

#: Erlaubte Felder eines Eintrags
ALLOWED_FIELDS = REQUIRED_FIELDS

#: Abschnitte auf oberster Ebene
TOP_LEVEL_KEYS = ("version", "decisions")


class DecisionError(ValueError):
    """Die Datei mit den Entscheidungen ist unvollstaendig oder widerspruechlich."""


@dataclass(frozen=True)
class Decision:
    """Eine getroffene Entscheidung zu genau einem Finding."""

    finding_id: str
    rule_id: str
    bp_key: str
    decided_by: str
    decided_at: datetime
    reason_code: str
    reason: str

    @property
    def status(self) -> str:
        """Der Status, den das Finding statt ``open`` traegt."""
        return REASON_STATUS[self.reason_code]

    def as_finding_decision(self) -> dict[str, Any]:
        """Der ``decision``-Block des Findings – Feldnamen nach Schema."""
        return {
            "by": self.decided_by,
            "at": self.decided_at.isoformat(),
            "reason": self.reason,
            "reason_code": self.reason_code,
        }


@dataclass
class DecisionMemory:
    """Die geladenen Entscheidungen und was der Lauf mit ihnen gemacht hat.

    Nicht eingefroren, weil der Lauf mitschreibt, welcher Eintrag getroffen hat: die
    uebrigen sind verwaist und gehoeren als Hinweis in den Report.
    """

    entries: dict[str, Decision] = field(default_factory=dict)
    path: Path | None = None
    applied: set[str] = field(default_factory=set)

    def __len__(self) -> int:
        return len(self.entries)

    def get(self, finding_id: str) -> Decision | None:
        return self.entries.get(finding_id)

    def mark_applied(self, finding_id: str) -> None:
        self.applied.add(finding_id)

    @property
    def orphans(self) -> list[Decision]:
        """Eintraege, zu denen der Lauf kein Finding erzeugt hat – nach ID sortiert."""
        return [
            decision
            for finding_id, decision in sorted(self.entries.items())
            if finding_id not in self.applied
        ]


def apply_decision(finding: dict[str, Any], memory: DecisionMemory | None) -> dict[str, Any]:
    """Setzt Status und ``decision`` eines Findings aus dem Gedaechtnis.

    Passt ``rule_id`` oder ``bp_key`` des Eintrags nicht zum Finding, ist das ein Fehler:
    dieselbe ``finding_id`` bei anderer Regel oder anderem Konto heisst, dass der Eintrag
    nach einer Regelaenderung veraltet ist – ihn stillschweigend anzuwenden hiesse, eine
    Entscheidung auf einen fremden Fall zu uebertragen.
    """
    if memory is None:
        return finding
    decision = memory.get(finding["finding_id"])
    if decision is None:
        return finding

    entity_key = finding.get("entity", {}).get("bp_key")
    if decision.rule_id != finding["rule_id"] or decision.bp_key != entity_key:
        raise DecisionError(
            f"{finding['finding_id']}: der Eintrag im Entscheidungsgedaechtnis nennt "
            f"{decision.rule_id} / {decision.bp_key}, das Finding gehoert zu "
            f"{finding['rule_id']} / {entity_key}. Eintrag veraltet – Regel geaendert? "
            "Eintrag pruefen und neu setzen, nicht raten."
        )

    finding["status"] = decision.status
    finding["decision"] = decision.as_finding_decision()
    memory.mark_applied(finding["finding_id"])
    return finding


class _LineLoader(yaml.SafeLoader):
    """YAML-Loader, der jedem Objekt seine Zeilennummer mitgibt.

    Ohne sie nennte eine Meldung nur den Fehler, nicht die Stelle – bei einer von Hand
    gepflegten Datei ist die Zeile die halbe Auskunft.
    """


def _construct_mapping(loader: _LineLoader, node: yaml.Node) -> dict[str, Any]:
    mapping = yaml.SafeLoader.construct_mapping(loader, node, deep=True)
    mapping["__line__"] = node.start_mark.line + 1
    return mapping


_LineLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _as_datetime(value: Any) -> datetime | None:
    """``decided_at`` als Zeitpunkt; ein Datum ohne Uhrzeit gilt als Mitternacht."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def parse_decisions(document: Any, path: Path) -> DecisionMemory:
    """Prueft ein geladenes Dokument und meldet alle Probleme gemeinsam."""
    if not isinstance(document, dict):
        raise DecisionError(f"{path.name}: enthaelt kein Objekt")

    errors: list[str] = []
    unknown = sorted(set(document) - set(TOP_LEVEL_KEYS) - {"__line__"})
    if unknown:
        errors.append(f"unbekannte Abschnitte: {unknown}")

    raw = document.get("decisions")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        errors.append("decisions: muss eine Liste von Eintraegen sein")
        raw = []

    entries: dict[str, Decision] = {}
    for position, entry in enumerate(raw, start=1):
        if not isinstance(entry, dict):
            errors.append(f"decisions[{position}]: muss ein Objekt sein")
            continue
        line = entry.get("__line__", "?")
        where = f"Zeile {line}"

        unknown_fields = sorted(set(entry) - set(ALLOWED_FIELDS) - {"__line__"})
        if unknown_fields:
            errors.append(f"{where}: unbekannte Felder {unknown_fields}")
        missing = [name for name in REQUIRED_FIELDS if not entry.get(name)]
        if missing:
            errors.append(f"{where}: Pflichtfelder fehlen: {missing}")
            continue

        reason_code = entry["reason_code"]
        if reason_code not in REASON_STATUS:
            errors.append(
                f"{where}: reason_code {reason_code!r} ist unbekannt; erlaubt sind "
                f"{sorted(REASON_STATUS)}"
            )
            continue

        decided_at = _as_datetime(entry["decided_at"])
        if decided_at is None:
            errors.append(f"{where}: decided_at ist kein Zeitpunkt (JJJJ-MM-TT[THH:MM:SS])")
            continue

        reason = entry["reason"]
        if not isinstance(reason, str):
            errors.append(f"{where}: reason muss ein Text sein")
            continue

        finding_id = str(entry["finding_id"])
        if finding_id in entries:
            errors.append(f"{where}: finding_id {finding_id} steht mehrfach in der Datei")
            continue
        entries[finding_id] = Decision(
            finding_id=finding_id,
            rule_id=str(entry["rule_id"]),
            bp_key=str(entry["bp_key"]),
            decided_by=str(entry["decided_by"]),
            decided_at=decided_at,
            reason_code=reason_code,
            reason=reason,
        )

    if errors:
        joined = "\n    ".join(errors)
        raise DecisionError(f"{path.name}:\n    {joined}")
    return DecisionMemory(entries=entries, path=path)


def load_decisions(path: Path) -> DecisionMemory:
    """Liest und prueft eine Datei mit Entscheidungen."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DecisionError(f"{path.name}: nicht als UTF-8 lesbar ({type(exc).__name__})") from exc
    try:
        document = yaml.load(text, Loader=_LineLoader)
    except yaml.YAMLError as exc:
        raise DecisionError(f"{path.name}: kein gueltiges YAML ({type(exc).__name__})") from exc
    return parse_decisions(document, path)


def find_decisions(input_dir: Path, given: Path | None = None) -> Path | None:
    """Der Pfad zur Datei: ``--decisions`` gewinnt, sonst ``<input>/decisions.yaml``.

    Eine ausdruecklich genannte Datei, die es nicht gibt, ist ein Fehler – der Anwender
    haette sonst ein stillschweigend leeres Gedaechtnis (Regel 4). Die Vorgabedatei darf
    fehlen; dann gibt es kein Gedaechtnis.
    """
    if given is not None:
        if not given.is_file():
            raise DecisionError(f"Datei mit Entscheidungen existiert nicht: {given}")
        return given
    candidate = input_dir / DEFAULT_FILENAME
    return candidate if candidate.is_file() else None


def store_decisions(con: duckdb.DuckDBPyConnection, memory: DecisionMemory) -> int:
    """Schreibt das Gedaechtnis in die kanonische Tabelle ``decision_memory``.

    Der Lauf haelt damit fest, mit welchem Gedaechtnis er gearbeitet hat. Eine ``run_id``
    fuehrt die Tabelle bewusst nicht: die Entscheidungen gelten ueber Laeufe hinweg.
    """
    con.execute("DELETE FROM decision_memory")
    for finding_id, decision in sorted(memory.entries.items()):
        con.execute(
            "INSERT INTO decision_memory "
            "(finding_id, rule_id, bp_key, decided_by, decided_at, reason_code, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                finding_id,
                decision.rule_id,
                decision.bp_key,
                decision.decided_by,
                decision.decided_at,
                decision.reason_code,
                decision.reason,
            ],
        )
    return len(memory.entries)
