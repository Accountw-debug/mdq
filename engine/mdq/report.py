"""Run-Report: was wurde geladen, was verworfen, was geprüft – und was nicht.

Der Report ist ein Datenobjekt; die Darstellung ist davon getrennt (D-037). Sprint 3
braucht dieselben Zahlen als JSON neben dem Lauf, und die UI liest ausschließlich JSON
(D-007) – sie darf sich nie auf geparsten Terminaltext stützen.

Der Report zeigt ``raw_excerpt`` nie an: Rohtext gehört in die Tabelle ``reject``, nicht
in eine Ausgabe, die jemand in ein Ticket kopiert (Regel 8, D-036).
"""

from dataclasses import dataclass, field
from typing import Any

import duckdb
from rich import box
from rich.console import Console
from rich.table import Table

from mdq.loader import LoadResult
from mdq.rules import Rule
from mdq.staging import StageResult

#: Reihenfolge der Pipeline-Stufen im Report
STAGES = ("raw", "staged", "canonical")

#: Höchstzahl der je Stufe einzeln genannten Reject-Gründe
MAX_REASONS_PER_STAGE = 5

#: Kürzung des sha256 in der Anzeige – die volle Summe steht im LoadResult und in to_dict()
SHA_DISPLAY_LENGTH = 8

STATUS_EXECUTED = "executed"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"

_STATUS_LABEL = {
    STATUS_EXECUTED: "ausgeführt",
    STATUS_SKIPPED: "übersprungen",
    STATUS_FAILED: "fehlgeschlagen",
}


@dataclass(frozen=True)
class RuleOutcome:
    """Ergebnis einer Regel im Lauf."""

    rule_id: str
    status: str
    findings: int = 0
    reason: str | None = None

    @classmethod
    def executed(cls, rule: Rule | str, findings: int) -> "RuleOutcome":
        return cls(_rule_id(rule), STATUS_EXECUTED, findings=findings)

    @classmethod
    def skipped(cls, rule: Rule | str, missing_tables: list[str]) -> "RuleOutcome":
        return cls(
            _rule_id(rule),
            STATUS_SKIPPED,
            reason=f"benötigte Tabellen fehlen: {', '.join(missing_tables)}",
        )

    @classmethod
    def failed(cls, rule: Rule | str, reason: str) -> "RuleOutcome":
        return cls(_rule_id(rule), STATUS_FAILED, reason=reason)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "status": self.status,
            "findings": self.findings,
            "reason": self.reason,
        }


def _rule_id(rule: Rule | str) -> str:
    return rule if isinstance(rule, str) else rule.id


@dataclass(frozen=True)
class RejectSummary:
    """Rejects einer Pipeline-Stufe, zusammengefasst nach Grund – ohne Rohtext."""

    stage: str
    count: int
    reasons: tuple[tuple[str, int], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "count": self.count,
            "reasons": [{"reason": reason, "count": count} for reason, count in self.reasons],
        }


@dataclass
class RunReport:
    """Sammelt die Kennzahlen eines Laufs."""

    run_id: str
    engine_version: str | None = None
    pack_version: str | None = None
    data_as_of: str | None = None
    house_currency: str | None = None
    note: str | None = None
    loads: list[LoadResult] = field(default_factory=list)
    stages: list[StageResult] = field(default_factory=list)
    rules: list[RuleOutcome] = field(default_factory=list)
    rejects: list[RejectSummary] = field(default_factory=list)

    def add_load(self, result: LoadResult) -> None:
        self.loads.append(result)

    def add_stage(self, result: StageResult) -> None:
        self.stages.append(result)

    def add_rule(self, outcome: RuleOutcome) -> None:
        self.rules.append(outcome)

    @property
    def sorted_rules(self) -> list[RuleOutcome]:
        """Nach Regel-ID sortiert – über Läufe vergleichbar (Regel 9)."""
        return sorted(self.rules, key=lambda outcome: outcome.rule_id)

    @property
    def sorted_loads(self) -> list[LoadResult]:
        return sorted(self.loads, key=lambda result: (result.table, result.path.name))

    @property
    def sorted_stages(self) -> list[StageResult]:
        return sorted(self.stages, key=lambda result: result.table)

    @property
    def rows_staged(self) -> int:
        return sum(result.rows_staged for result in self.stages)

    @property
    def findings_total(self) -> int:
        return sum(outcome.findings for outcome in self.rules)

    @property
    def rejects_total(self) -> int:
        return sum(summary.count for summary in self.rejects)

    @property
    def skipped_rules(self) -> list[RuleOutcome]:
        return [o for o in self.sorted_rules if o.status == STATUS_SKIPPED]

    @property
    def failed_rules(self) -> list[RuleOutcome]:
        return [o for o in self.sorted_rules if o.status == STATUS_FAILED]

    @property
    def warnings(self) -> list[str]:
        return [
            warning
            for results in (self.sorted_loads, self.sorted_stages)
            for result in results
            for warning in result.warnings
        ]

    @property
    def has_problems(self) -> bool:
        """Wahr, sobald etwas nicht glatt lief.

        Ein Lauf mit Rejects, übersprungenen oder fehlgeschlagenen Regeln ist kein
        stiller Erfolg (D-038). Ob daraus ein Exit-Code wird, entscheidet Sprint 3.
        """
        return bool(
            self.rejects_total or self.skipped_rules or self.failed_rules or self.warnings
        )

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisierbare Fassung – gleiche Zahlen wie die Textausgabe."""
        return {
            "run_id": self.run_id,
            "engine_version": self.engine_version,
            "pack_version": self.pack_version,
            "data_as_of": self.data_as_of,
            "house_currency": self.house_currency,
            "note": self.note,
            "files": [
                {
                    "table": result.table,
                    "file": result.path.name,
                    "rows": result.rows,
                    "encoding": result.encoding,
                    "delimiter": result.delimiter,
                    "sha256": result.sha256,
                    "columns": list(result.columns),
                    "warnings": list(result.warnings),
                }
                for result in self.sorted_loads
            ],
            "stages": [result.to_dict() for result in self.sorted_stages],
            "rejects": [summary.to_dict() for summary in self.rejects],
            "rules": [outcome.to_dict() for outcome in self.sorted_rules],
            "totals": {
                "files": len(self.loads),
                "rows": sum(result.rows for result in self.loads),
                "rows_staged": self.rows_staged,
                "rejects": self.rejects_total,
                "findings": self.findings_total,
                "rules_executed": len([o for o in self.rules if o.status == STATUS_EXECUTED]),
                "rules_skipped": len(self.skipped_rules),
                "rules_failed": len(self.failed_rules),
            },
            "has_problems": self.has_problems,
        }


def collect_rejects(con: duckdb.DuckDBPyConnection, run_id: str) -> list[RejectSummary]:
    """Fasst die Tabelle ``reject`` je Stufe zusammen – ohne ``raw_excerpt``."""
    rows = con.execute(
        "SELECT stage, reason, count(*) AS anzahl FROM reject WHERE run_id = ? "
        "GROUP BY stage, reason ORDER BY stage, anzahl DESC, reason",
        [run_id],
    ).fetchall()

    by_stage: dict[str, list[tuple[str, int]]] = {}
    for stage, reason, count in rows:
        by_stage.setdefault(stage, []).append((reason, count))

    known = [stage for stage in STAGES if stage in by_stage]
    extra = sorted(stage for stage in by_stage if stage not in STAGES)
    return [
        RejectSummary(
            stage=stage,
            count=sum(count for _, count in by_stage[stage]),
            reasons=tuple(by_stage[stage]),
        )
        for stage in known + extra
    ]


def _render_header(console: Console, report: RunReport) -> None:
    console.print(f"[bold]Lauf {report.run_id}[/]")
    parts = [
        ("Engine", report.engine_version),
        ("Regelpaket", report.pack_version),
        ("Datenstand", report.data_as_of),
        ("Hauswährung", report.house_currency),
    ]
    console.print("  " + "   ".join(f"{label}: {value or '–'}" for label, value in parts))
    if report.note:
        console.print(f"  [yellow]{report.note}[/]")


def _render_files(console: Console, report: RunReport) -> None:
    console.print("\n[bold]Geladene Dateien[/]")
    if not report.loads:
        console.print("  keine Dateien geladen.")
        return

    # Technische Werte nie kürzen: min_width haelt sie, wird es eng, weicht der
    # Dateiname als Einziger. Ohne min_width schrumpft rich alle Spalten gleichmaessig.
    table = Table(box=box.SIMPLE)
    table.add_column("Tabelle", no_wrap=True, min_width=7)
    table.add_column("Datei", no_wrap=True, overflow="ellipsis")
    table.add_column("Zeilen", no_wrap=True, min_width=6, justify="right")
    table.add_column("Encoding", no_wrap=True, min_width=9)
    table.add_column("Trenner", no_wrap=True, min_width=9)
    table.add_column("sha256", no_wrap=True, min_width=SHA_DISPLAY_LENGTH)
    for result in report.sorted_loads:
        table.add_row(
            result.table,
            result.path.name,
            str(result.rows),
            result.encoding,
            result.delimiter,
            result.sha256[:SHA_DISPLAY_LENGTH],
        )
    console.print(table)
    console.print(
        f"  {len(report.loads)} Dateien, "
        f"{sum(result.rows for result in report.loads)} Zeilen."
    )
    # Warnungen bewusst als eigene Zeilen: in einer Spalte gingen sie unter.
    for warning in report.warnings:
        console.print(f"  [yellow]HINWEIS[/] {warning}")


def _render_stages(console: Console, report: RunReport) -> None:
    """Kontrollsummen der Stufe `staged`: Zeilen raw gegen staged, Summen je Buchungskreis.

    Die Summe steht immer neben ihrer Währung (Regel 2): ohne sie wäre die Zahl eines
    Mandanten mit zwei Hauswährungen falsch etikettiert.
    """
    if not report.stages:
        return

    console.print("\n[bold]Staging (raw -> staged)[/]")
    table = Table(box=box.SIMPLE)
    table.add_column("Tabelle", no_wrap=True, min_width=7)
    for column in ("Zeilen raw", "Zeilen staged", "Rejects"):
        table.add_column(column, no_wrap=True, justify="right")
    table.add_column("Notation", no_wrap=True)
    for result in report.sorted_stages:
        rejected = str(result.rejected) if result.rejected else "–"
        notation = f"{result.notation} ({result.notation_source})" if result.notation else "–"
        table.add_row(
            result.table,
            str(result.rows_raw),
            str(result.rows_staged),
            rejected,
            notation,
        )
    console.print(table)

    totals = [(result.table, total) for result in report.sorted_stages for total in result.totals]
    if totals:
        console.print("  [bold]Summe amount_signed_local[/]")
        sums = Table(box=box.SIMPLE)
        for column in ("Tabelle", "Buchungskreis", "Währung"):
            sums.add_column(column, no_wrap=True)
        sums.add_column("Summe", no_wrap=True, justify="right")
        for table_name, total in totals:
            sums.add_row(
                table_name,
                total.company_code or "–",
                total.currency or "–",
                total.amount,
            )
        console.print(sums)


def _render_rejects(console: Console, report: RunReport) -> None:
    console.print("\n[bold]Rejects[/]")
    if not report.rejects:
        console.print("  keine Rejects.")
        return

    for summary in report.rejects:
        console.print(f"  [red]{summary.stage}[/]: {summary.count}")
        for reason, count in summary.reasons[:MAX_REASONS_PER_STAGE]:
            console.print(f"      {count}x {reason}")
        remaining = len(summary.reasons) - MAX_REASONS_PER_STAGE
        if remaining > 0:
            console.print(f"      … und {remaining} weitere Gründe")
    console.print(f"  {report.rejects_total} Zeilen insgesamt nicht verarbeitet.")


def _render_rules(console: Console, report: RunReport) -> None:
    console.print("\n[bold]Regeln[/]")
    if not report.rules:
        console.print("  keine Regeln ausgeführt.")
        return

    table = Table(box=box.SIMPLE)
    for column in ("Regel", "Status", "Findings"):
        table.add_column(column, no_wrap=True)
    table.add_column("Grund", overflow="fold")
    for outcome in report.sorted_rules:
        findings = str(outcome.findings) if outcome.status == STATUS_EXECUTED else "–"
        table.add_row(
            outcome.rule_id,
            _STATUS_LABEL.get(outcome.status, outcome.status),
            findings,
            outcome.reason or "",
        )
    console.print(table)

    executed = len([o for o in report.rules if o.status == STATUS_EXECUTED])
    console.print(f"  {executed} Regeln ausgeführt, {report.findings_total} Findings.")
    # "Nicht geprüft" wird ausgewiesen, nicht weggelassen (docs/CONCEPT.md, Block 3).
    if report.skipped_rules:
        console.print(f"  [yellow]{len(report.skipped_rules)} Regeln nicht geprüft.[/]")
    if report.failed_rules:
        console.print(f"  [red]{len(report.failed_rules)} Regeln fehlgeschlagen.[/]")


def render(report: RunReport, console: Console | None = None) -> None:
    """Schreibt den Report als Text. Reihenfolge und Inhalt sind deterministisch."""
    out = console or Console(soft_wrap=True)
    _render_header(out, report)
    _render_files(out, report)
    _render_stages(out, report)
    _render_rejects(out, report)
    _render_rules(out, report)
    if report.has_problems:
        out.print("\n[yellow]Der Lauf hatte Auffälligkeiten – siehe oben.[/]")
