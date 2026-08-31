"""Der ganze Lauf: ``load → stage → map → relevance → Regeln → Findings → Dateien``.

Dieses Modul ist die Engine von ``mdq run``; es kennt kein Typer und keine Konsole, damit
der Regressionsvergleich (Aufgabe 5) und spaeter ein Dienst denselben Lauf ohne CLI
ausfuehren koennen.

Ergebnis eines Laufs sind drei Dateien in ``runs/<run_id>/``:

* ``findings.json`` – Array, nach ``finding_id`` sortiert, jedes Finding schema-valide.
* ``run.json`` – der Vertrag, den die UI laedt: ``RunReport.to_dict()`` samt Scope und
  Versionen, dazu die sechs Felder, die die UI als Lauf-Kopf erwartet (D-094).
* ``report.txt`` – derselbe Report als Text, feste Breite, ohne Farben.

Der ``run_id`` ist eine Funktion der Daten und der Frage, nicht des Codes (D-093):
``<data_as_of>-<kurzhash>`` ueber die Input-Hashes, den Scope, den Datenstand und den
Inhalt der Entscheidungsdatei. Zwei Laeufe mit gleichem ``--created-at`` schreiben
byte-identische Dateien; ohne den Schalter unterscheiden sie sich in genau einem Feld,
``created_at`` (D-092).

Geschrieben wird atomar: erst in ein temporaeres Verzeichnis, dann getauscht. Ein
Abbruch laesst einen vorhandenen Lauf unberuehrt, und es gibt nie ein halb ersetztes
Verzeichnis (D-093).
"""

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb

from mdq import CANONICAL_SCHEMA, RULES_DIR, __version__
from mdq.canonical import Scope, build_canonical
from mdq.decisions import DecisionMemory, find_decisions, load_decisions, store_decisions
from mdq.executor import (
    ExecutionError,
    InvalidFindingError,
    RunContext,
    execute_rule_rows,
    missing_tables,
)
from mdq.findings import schema_version
from mdq.loader import load_table
from mdq.mapping import load_mapping
from mdq.pack import load_pack
from mdq.relevance import build_relevance
from mdq.report import (
    DecisionSummary,
    RuleOutcome,
    RunReport,
    collect_rejects,
    render_to_text,
)
from mdq.rules import load_rules
from mdq.staging import stage_all

#: Dateiendungen, die als Export gelten
EXPORT_SUFFIXES = (".txt", ".csv")

#: Laenge des Kurzhashs im ``run_id``
RUN_ID_HASH_LENGTH = 8

#: Platzhalter-Laufnummer, solange der echte ``run_id`` noch nicht gebildet werden kann:
#: er enthaelt den Datenstand, und der steht erst nach der Relevanzstufe fest. Die
#: Rejects der frueheren Stufen werden am Ende umgeschrieben – zwei Laufnummern in einer
#: Datenbank waeren eine stille Ungereimtheit (Regel 4).
PENDING_RUN_ID = "pending"

#: Die drei Dateien eines Laufs
FINDINGS_FILE = "findings.json"
RUN_FILE = "run.json"
REPORT_FILE = "report.txt"

#: Exit-Codes nach SPRINT-3.md, Aufgabe 4 (D-097)
EXIT_CLEAN = 0
EXIT_PROBLEMS = 1
EXIT_ABORTED = 2


class RunError(ValueError):
    """Der Lauf kann nicht ausgefuehrt oder nicht geschrieben werden – Abbruch."""


@dataclass(frozen=True)
class RunOptions:
    """Was einen Lauf beschreibt. Alles, was den ``run_id`` beeinflusst, steht hier."""

    input_dir: Path
    out_dir: Path
    scope: Scope = field(default_factory=Scope)
    decimal_notation: str | None = None
    data_as_of: date | None = None
    decisions_path: Path | None = None
    #: Zeitpunkt des Laufs als ISO-8601 in UTC (``…Z``); ``None`` = Uhr (D-092)
    created_at: str | None = None
    #: Regelverzeichnis. Gehoert zum Paket und wird nicht ueber die CLI gesetzt; der
    #: Parameter besteht, damit ein Test einen eigenen Regelsatz einsetzen kann.
    rules_dir: Path = RULES_DIR


@dataclass(frozen=True)
class RunResult:
    """Ergebnis eines Laufs: Report, Findings, Verzeichnis, Exit-Code."""

    report: RunReport
    findings: list[dict[str, Any]]
    directory: Path
    exit_code: int
    #: Vermerk, wenn ein vorhandener Lauf ersetzt wurde. Steht **nicht** in den Dateien:
    #: sonst waere der zweite Lauf nicht mehr byte-identisch mit dem ersten (D-092).
    replaced: str | None = None
    #: ``finding_id -> finding_key`` der Regel, die das Finding erzeugt hat (D-099).
    #: Nicht Teil von ``findings.json``: der Schluessel gehoert nicht ins Finding-Schema,
    #: sondern ist der Vergleichsschluessel der Regression (D-068).
    finding_keys: dict[str, str | None] = field(default_factory=dict)

    @property
    def finding_rows(self) -> list[tuple[dict[str, Any], str | None]]:
        """Findings mit ihrem ``finding_key`` – die Form, die ``regression`` erwartet."""
        return [(finding, self.finding_keys[finding["finding_id"]]) for finding in self.findings]


def now_utc() -> str:
    """Jetzt als ISO-8601 in UTC, auf Sekunden genau, mit ``Z``."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_created_at(value: str) -> str:
    """Prueft ``--created-at`` und normalisiert auf ``…Z`` (D-092)."""
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        raise RunError(
            f"--created-at {value!r} ist kein Zeitpunkt nach ISO 8601 "
            "(erwartet JJJJ-MM-TTTHH:MM:SSZ)."
        ) from None
    if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
        raise RunError(
            f"--created-at {value!r} ist nicht UTC. Der Zeitpunkt gehoert zum Lauf, nicht "
            "zum Betrachter – erwartet wird JJJJ-MM-TTTHH:MM:SSZ."
        )
    return stamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def input_files(input_dir: Path) -> list[Path]:
    """Die Exportdateien eines Verzeichnisses, nach Namen sortiert (Regel 9)."""
    if not input_dir.is_dir():
        raise RunError(f"Eingabeverzeichnis existiert nicht: {input_dir}")
    files = sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix in EXPORT_SUFFIXES
    )
    if not files:
        raise RunError(
            f"Keine Exportdateien ({', '.join(EXPORT_SUFFIXES)}) unter {input_dir} gefunden."
        )
    return files


def _sha256_of_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_id_for(
    file_hashes: list[tuple[str, str]],
    scope: Scope,
    data_as_of: date,
    decimal_notation: str | None,
    decisions_hash: str | None,
) -> str:
    """``<data_as_of>-<kurzhash>`` – die Kennung eines Laufs (D-093).

    Im Hash stehen die Daten und die Frage: Input-Hashes, Scope, Datenstand und der
    Inhalt der Entscheidungsdatei. **Nicht** im Hash stehen Engine- und Paketversion:
    derselbe Datenstand mit derselben Frage ist derselbe Lauf, auch nach einem
    Engine-Update – die Versionen stehen dafuer in ``run.json``.
    """
    lines = [f"{table}\t{digest}" for table, digest in sorted(file_hashes)]
    codes = ",".join(sorted(scope.company_codes))
    window = f"{scope.item_window_from or ''}|{scope.item_window_to or ''}"
    lines.append(f"scope\t{codes}|{scope.side}|{window}|{decimal_notation or ''}")
    lines.append(f"data_as_of\t{data_as_of.isoformat()}")
    lines.append(f"decisions\t{decisions_hash or '-'}")
    digest = hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()
    return f"{data_as_of.isoformat()}-{digest[:RUN_ID_HASH_LENGTH]}"


def _memory(input_dir: Path, given: Path | None) -> tuple[DecisionMemory, str | None]:
    """Das Entscheidungsgedaechtnis und der Inhaltshash seiner Datei."""
    path = find_decisions(input_dir, given)
    if path is None:
        return DecisionMemory(), None
    return load_decisions(path), _sha256_of_file(path)


def _write_run_meta(
    con: duckdb.DuckDBPyConnection, report: RunReport, created_at: str, pack_hash: str
) -> None:
    """Der Lauf beschreibt sich selbst in ``run_meta``.

    ``started_at`` und ``finished_at`` tragen beide den Zeitpunkt des Laufs: eine
    gemessene Dauer waere der einzige Wert der ganzen Pipeline, der sich bei gleichem
    Input aendert (Regel 9). Wie lange es gedauert hat, sagt die Konsole (D-092).
    """
    con.execute("DELETE FROM run_meta WHERE run_id = ?", [report.run_id])
    con.execute(
        "INSERT INTO run_meta (run_id, engine_version, pack_version, dict_version, "
        "pack_hash, data_as_of, started_at, finished_at, input_files, scope) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            report.run_id,
            report.engine_version,
            report.pack_version,
            (report.versions or {}).get("dict"),
            pack_hash,
            report.data_as_of,
            created_at,
            created_at,
            json.dumps(
                [
                    {
                        "name": result.path.name,
                        "sha256": result.sha256,
                        "rows": result.rows,
                        "encoding": result.encoding,
                        "delimiter": result.delimiter,
                    }
                    for result in report.sorted_loads
                ],
                ensure_ascii=False,
            ),
            json.dumps(report.scope, ensure_ascii=False),
        ],
    )


def _execute_rules(
    con: duckdb.DuckDBPyConnection,
    ctx: RunContext,
    report: RunReport,
    rules_dir: Path = RULES_DIR,
) -> tuple[list[dict[str, Any]], dict[str, str | None]]:
    """Fuehrt alle Regeln aus ``logic/rules/`` aus, in fester Reihenfolge (Regel 9).

    Eine Regel, deren Tabellen fehlen, wird uebersprungen und im Report genannt; eine
    Regel, deren SQL oder Ausgabe-Vertrag bricht, gilt als fehlgeschlagen und haelt die
    uebrigen nicht auf – beides fuehrt zu Exit 1 (D-097). Ein **ungueltiges Finding**
    dagegen bricht den Lauf ab: ein Lauf, der schema-ungueltige Findings ausliefert, ist
    schlimmer als keiner (CLAUDE.md Regel 6).

    Geliefert werden die sortierten Findings **und** ihre ``finding_key``s: aus dem
    fertigen Finding ist der Schluessel nicht mehr herauszulesen, die Regression braucht
    ihn aber (D-068, D-099).
    """
    findings: list[dict[str, Any]] = []
    keys: dict[str, str | None] = {}
    origin: dict[str, str] = {}
    for rule in load_rules(rules_dir):
        absent = missing_tables(con, rule)
        if absent:
            report.add_rule(RuleOutcome.skipped(rule, absent))
            continue
        try:
            produced = execute_rule_rows(con, rule, ctx)
        except InvalidFindingError:
            raise
        except ExecutionError as exc:
            report.add_rule(RuleOutcome.failed(rule, str(exc)))
            continue
        for finding, finding_key in produced:
            finding_id = finding["finding_id"]
            if finding_id in origin:
                raise RunError(
                    f"finding_id {finding_id} kommt aus {origin[finding_id]} und "
                    f"{rule.id}. Zwei Regeln duerfen kein Finding teilen – eine von "
                    "beiden braucht eine eigene finding_key-Spalte."
                )
            origin[finding_id] = rule.id
            keys[finding_id] = finding_key
            findings.append(finding)
        report.add_rule(RuleOutcome.executed(rule, len(produced)))
    return sorted(findings, key=lambda finding: finding["finding_id"]), keys


def _dump(payload: Any) -> str:
    """JSON, wie es in ein Laufverzeichnis gehoert: lesbar, deterministisch, ohne float.

    ``default`` schlaegt bewusst fehl statt zu runden: ein ``Decimal``, das bis hierher
    kommt, ist ein Fehler in der Regel oder im Report, kein Formatierungsfall (Regel 2).
    """
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def _replacement_note(target: Path, versions: dict[str, str]) -> str:
    """Vermerk, wenn ein vorhandener Lauf ersetzt wird (D-093).

    Weil die Versionen nicht im ``run_id`` stehen, kann ein neues Regelpaket einen alten
    Lauf unter derselben Kennung ersetzen. Dann nennt der Vermerk beide Staende – sonst
    verschwaende der alte Lauf still.
    """
    before = ""
    try:
        old = json.loads((target / RUN_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        old = None
    if isinstance(old, dict):
        old_versions = old.get("versions") or {}
        before = (
            f"vorher engine {old.get('engine_version')}/pack {old.get('pack_version')}"
            f", Paket-Hash {str(old_versions.get('pack_hash', '?'))[:8]}"
        )
    now = (
        f"jetzt engine {versions.get('engine')}/pack {versions.get('pack')}"
        f", Paket-Hash {versions.get('pack_hash', '?')[:8]}"
    )
    inner = f"{before}; {now}" if before else f"kein lesbares run.json vorhanden; {now}"
    return f"Lauf {target.name} ersetzt ({inner})."


def _write_atomically(target: Path, files: dict[str, str]) -> str | None:
    """Schreibt die Dateien in ein temporaeres Verzeichnis und tauscht dann (D-093)."""
    out_dir = target.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    staging = out_dir / f".tmp-{target.name}"
    backup = out_dir / f".replaced-{target.name}"
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)
    staging.mkdir()
    for name, content in files.items():
        (staging / name).write_text(content, encoding="utf-8")

    replaced = target.exists()
    if replaced:
        target.rename(backup)
    try:
        staging.rename(target)
    except OSError:
        if replaced:
            backup.rename(target)
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(backup, ignore_errors=True)
    return target.name if replaced else None


def execute_run(options: RunOptions) -> RunResult:
    """Fuehrt einen vollstaendigen Lauf aus und schreibt ``runs/<run_id>/``."""
    created_at = options.created_at or now_utc()
    files = input_files(options.input_dir)
    pack = load_pack()
    mapping = load_mapping()
    versions = {
        "engine": __version__,
        **pack.to_dict(),
        "mapping": mapping.version,
        "finding_schema": schema_version(),
    }

    con = duckdb.connect(":memory:")
    try:
        con.execute(CANONICAL_SCHEMA.read_text(encoding="utf-8"))
        report = RunReport(
            run_id=PENDING_RUN_ID,
            engine_version=__version__,
            pack_version=pack.pack_version,
            created_at=created_at,
        )

        for path in files:
            report.add_load(load_table(con, path))
        for result in stage_all(
            con,
            mapping,
            [load.table for load in report.loads],
            PENDING_RUN_ID,
            options.decimal_notation,
        ):
            report.add_stage(result)
        report.add_canonical(build_canonical(con, mapping, PENDING_RUN_ID, options.scope))

        relevance = build_relevance(con, options.data_as_of)
        report.add_relevance(relevance)

        memory, decisions_hash = _memory(options.input_dir, options.decisions_path)
        store_decisions(con, memory)

        run_id = run_id_for(
            [(load.table, load.sha256) for load in report.loads],
            options.scope,
            relevance.data_as_of,
            options.decimal_notation,
            decisions_hash,
        )
        report.run_id = run_id
        con.execute(
            "UPDATE reject SET run_id = ? WHERE run_id = ?", [run_id, PENDING_RUN_ID]
        )

        report.versions = versions
        report.scope = {
            **options.scope.to_dict(),
            "decimal_notation": options.decimal_notation,
            "data_as_of_source": relevance.data_as_of_source,
            "decisions_file": str(memory.path) if memory.path else None,
        }
        report.company_codes = tuple(
            row[0]
            for row in con.execute(
                "SELECT company_code FROM company_code ORDER BY company_code"
            ).fetchall()
        )

        ctx = RunContext(
            run_id=run_id,
            engine_version=__version__,
            pack_version=pack.pack_version,
            data_as_of=relevance.data_as_of.isoformat(),
            created_at=created_at,
            decisions=memory,
        )
        findings, finding_keys = _execute_rules(con, ctx, report, options.rules_dir)
        report.add_decisions(DecisionSummary.of(memory, rules_executed=True))
        report.rejects = collect_rejects(con, run_id)
        report.exit_code = EXIT_PROBLEMS if report.has_problems else EXIT_CLEAN
        _write_run_meta(con, report, created_at, pack.pack_hash)
    finally:
        con.close()

    target = options.out_dir / report.run_id
    replaced = None
    if target.exists():
        replaced = _replacement_note(target, versions)
    payload = {
        FINDINGS_FILE: _dump(findings),
        RUN_FILE: _dump(report.to_dict()),
        REPORT_FILE: render_to_text(report),
    }
    _write_atomically(target, payload)
    return RunResult(
        report=report,
        findings=findings,
        directory=target,
        exit_code=report.exit_code,
        replaced=replaced,
        finding_keys=finding_keys,
    )
