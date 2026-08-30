"""Kommandozeile der Engine.

Die Befehle sind in Sprint 1 als Geruest angelegt; Inhalt folgt Aufgabe fuer Aufgabe
laut ``docs/specs/SPRINT-1.md``. Noch nicht implementierte Befehle brechen mit einem
Exit-Code ungleich 0 ab, damit nichts stumm ins Leere laeuft.
"""

from collections import Counter
from pathlib import Path
from typing import Annotated, NoReturn

import duckdb
import typer
from rich import box
from rich.console import Console
from rich.table import Table

from mdq import CANONICAL_SCHEMA, EXPECTED_FINDINGS, RULES_DIR, __version__
from mdq.demo import DEFAULT_SEED
from mdq.demo.defects import write_expected
from mdq.demo.generate import build_client
from mdq.demo.generate import generate as generate_demo
from mdq.findings import (
    FindingFileError,
    duplicate_finding_ids,
    iter_finding_files,
    load_finding_file,
    validate_finding,
)
from mdq.formats import NOTATIONS
from mdq.loader import LoaderError, load_table
from mdq.mapping import MappingError, load_mapping
from mdq.report import RunReport, collect_rejects, render
from mdq.rules import RuleError, load_rules
from mdq.staging import StagingError, stage_all

#: Mindestens ein Finding ist ungueltig
EXIT_INVALID = 1
#: Exit-Code fuer Befehle, deren Umsetzung noch aussteht
EXIT_NOT_IMPLEMENTED = 2
#: Es gab nichts zu pruefen – nie stillschweigend als Erfolg melden
EXIT_NO_INPUT = 3

# soft_wrap: Pfade und Meldungen sollen nicht mitten im Wort umbrochen werden.
console = Console(soft_wrap=True)
err_console = Console(stderr=True, soft_wrap=True)

app = typer.Typer(
    name="mdq",
    help="MDQ – Finance Master Data & Leakage Check.",
    no_args_is_help=True,
    add_completion=False,
)

rules_app = typer.Typer(help="Regeln aus logic/rules/ inspizieren.", no_args_is_help=True)
app.add_typer(rules_app, name="rules")

demo_app = typer.Typer(help="Demo-Mandanten erzeugen (Sprint 2).", no_args_is_help=True)
app.add_typer(demo_app, name="demo")


def _not_implemented(what: str, task: str) -> NoReturn:
    """Bricht mit klarer Meldung ab, statt ein leeres Ergebnis vorzutaeuschen."""
    err_console.print(f"[bold red]{what} ist noch nicht implementiert.[/] Geplant in: {task}.")
    raise typer.Exit(code=EXIT_NOT_IMPLEMENTED)


@app.command()
def version() -> None:
    """Zeigt die Engine-Version."""
    console.print(f"mdq {__version__}")


@app.command()
def validate(
    path: Annotated[
        Path,
        typer.Argument(help="Datei oder Verzeichnis mit Findings (YAML/JSON)."),
    ],
) -> None:
    """Validiert Findings gegen logic/finding.schema.json."""
    try:
        files = iter_finding_files(path)
    except FindingFileError as exc:
        err_console.print(f"[bold red]Fehler:[/] {exc}")
        raise typer.Exit(code=EXIT_NO_INPUT) from exc

    if not files:
        err_console.print(f"[bold red]Fehler:[/] keine Finding-Dateien unter {path} gefunden.")
        raise typer.Exit(code=EXIT_NO_INPUT)

    documents: dict[Path, dict] = {}
    invalid_files = 0
    for file_path in files:
        try:
            finding = load_finding_file(file_path)
        except FindingFileError as exc:
            invalid_files += 1
            console.print(f"[bold red]FEHLER[/] {file_path}")
            console.print(f"    {exc}")
            continue

        errors = validate_finding(finding)
        if errors:
            invalid_files += 1
            console.print(f"[bold red]FEHLER[/] {file_path}")
            for message in errors:
                console.print(f"    {message}")
        else:
            documents[file_path] = finding
            console.print(f"[green]OK[/]     {file_path}")

    duplicates = duplicate_finding_ids(documents)
    for finding_id, paths in duplicates.items():
        console.print(f"[bold red]FEHLER[/] finding_id {finding_id} kommt mehrfach vor:")
        for duplicate_path in paths:
            console.print(f"    {duplicate_path}")

    valid = len(files) - invalid_files
    console.print(f"\n{len(files)} Dateien, {valid} valide, {invalid_files} fehlerhaft.")
    if duplicates:
        console.print(f"{len(duplicates)} doppelte finding_id, siehe oben.")
    if invalid_files or duplicates:
        raise typer.Exit(code=EXIT_INVALID)


@rules_app.command("list")
def rules_list(
    directory: Annotated[
        Path,
        typer.Option("--dir", help="Regelverzeichnis (Vorgabe: logic/rules/)."),
    ] = RULES_DIR,
) -> None:
    """Listet die Regeln mit ID, Version, Seite, Kategorie und Stufe."""
    try:
        rules = load_rules(directory)
    except RuleError as exc:
        err_console.print(f"[bold red]Fehler:[/] {exc}")
        raise typer.Exit(code=EXIT_INVALID) from exc

    if not rules:
        err_console.print(f"[bold red]Fehler:[/] keine Regeln unter {directory} gefunden.")
        raise typer.Exit(code=EXIT_NO_INPUT)

    # Ohne Titelspalte: der Titel enthaelt {params}-Platzhalter und wuerde in einer
    # Liste nur Breite kosten. Er steht im Regelkopf und spaeter im Finding.
    table = Table(box=box.SIMPLE)
    for column in ("ID", "Ver", "Seite", "Kategorie", "Stufe", "Aktion", "SK", "Tab"):
        table.add_column(column, no_wrap=True)

    for rule in rules:
        table.add_row(
            rule.id,
            rule.version,
            rule.side,
            rule.category,
            rule.default_tier,
            rule.default_action_type,
            str(rule.damage_class),
            str(len(rule.requires_tables)),
        )
    console.print(table)

    # Regeln ohne Testfaelle kommen hier nicht mehr an: der Loader lehnt sie ab (D-021).
    without_edge = [rule.id for rule in rules if not rule.tests.get("edge")]
    console.print(f"\n{len(rules)} Regeln, {len(without_edge)} ohne Grenzfall.")


#: Dateiendungen, die `mdq load` als Export ansieht
EXPORT_SUFFIXES = (".txt", ".csv")

#: Fester Lauf-Bezeichner des Zwischenstands – kein Zeitstempel, damit die Ausgabe
#: deterministisch bleibt (Regel 9).
LOAD_RUN_ID = "load-zwischenstand"


@app.command()
def load(
    input_dir: Annotated[
        Path,
        typer.Option("--input", help="Verzeichnis mit SE16N-Exporten (.txt/.csv)."),
    ],
    decimal_notation: Annotated[
        str | None,
        typer.Option(
            "--decimal-notation",
            help=(
                "Dezimalnotation der Exporte (de|iso). Greift nur, wo eine Datei selbst "
                "keinen eindeutigen Betrag enthaelt."
            ),
        ),
    ] = None,
) -> None:
    """Liest Exporte ein, typisiert sie (raw -> staged) und zeigt den Run-Report.

    Zwischenstand: Mapping auf das kanonische Schema und Regelausfuehrung folgen in den
    naechsten Aufgaben von Sprint 3.
    """
    if not input_dir.is_dir():
        err_console.print(f"[bold red]Fehler:[/] Verzeichnis existiert nicht: {input_dir}")
        raise typer.Exit(code=EXIT_NO_INPUT)

    if decimal_notation is not None and decimal_notation not in NOTATIONS:
        err_console.print(
            f"[bold red]Fehler:[/] --decimal-notation {decimal_notation!r} ist unbekannt; "
            f"erlaubt sind {list(NOTATIONS)}."
        )
        raise typer.Exit(code=EXIT_INVALID)

    files = sorted(
        path for path in input_dir.iterdir() if path.is_file() and path.suffix in EXPORT_SUFFIXES
    )
    if not files:
        err_console.print(f"[bold red]Fehler:[/] keine Exportdateien unter {input_dir} gefunden.")
        raise typer.Exit(code=EXIT_NO_INPUT)

    con = duckdb.connect(":memory:")
    con.execute(CANONICAL_SCHEMA.read_text(encoding="utf-8"))

    report = RunReport(
        run_id=LOAD_RUN_ID,
        engine_version=__version__,
        note=(
            "Zwischenstand: Dateien werden eingelesen und typisiert. "
            "Mapping SAP -> kanonisch und Regelausführung folgen in Sprint 3."
        ),
    )
    try:
        for path in files:
            report.add_load(load_table(con, path))
        mapping = load_mapping()
        for result in stage_all(
            con, mapping, [load.table for load in report.loads], LOAD_RUN_ID, decimal_notation
        ):
            report.add_stage(result)
    except (LoaderError, MappingError, StagingError) as exc:
        err_console.print(f"[bold red]Fehler:[/] {exc}")
        raise typer.Exit(code=EXIT_INVALID) from exc

    report.rejects = collect_rejects(con, LOAD_RUN_ID)
    render(report, console)


def _thousands(value: int) -> str:
    """Zahl mit Punkt als Tausendertrenner, wie im Run-Report."""
    return f"{value:,}".replace(",", ".")


@demo_app.command("generate")
def demo_generate(
    out: Annotated[
        Path,
        typer.Option("--out", help="Zielverzeichnis fuer die Exportdateien."),
    ],
    seed: Annotated[
        int,
        typer.Option("--seed", help="Zufalls-Seed; gleicher Seed gibt identische Dateien."),
    ] = DEFAULT_SEED,
    defects: Annotated[
        bool,
        typer.Option(
            "--defects/--no-defects",
            help="Eingebaute Fehler aus defects.yaml anwenden (Vorgabe) oder den reinen Basis-Mandanten schreiben.",
        ),
    ] = True,
) -> None:
    """Erzeugt den synthetischen Demo-Mandanten (15 Dateien und manifest.json)."""
    manifest = generate_demo(out, seed, None if defects else ())

    table = Table(box=box.SIMPLE)
    for column in ("Tabelle", "Zeilen", "sha256"):
        table.add_column(column, no_wrap=True)
    for entry in manifest["tables"]:
        table.add_row(entry["table"], _thousands(entry["rows"]), entry["sha256"][:8])
    console.print(table)
    console.print(
        f"\n{len(manifest['tables'])} Dateien, {_thousands(manifest['total_rows'])} Zeilen, "
        f"Seed {manifest['seed']}, Datenstand {manifest['data_as_of']} -> {out}"
    )
    if not defects:
        console.print("[yellow]Ohne Defekte:[/] reiner Basis-Mandant, auf dem keine Regel greifen darf.")


@demo_app.command("expected")
def demo_expected(
    out: Annotated[
        Path,
        typer.Option("--out", help="Zieldatei fuer die erwarteten Findings."),
    ] = EXPECTED_FINDINGS,
    seed: Annotated[
        int,
        typer.Option("--seed", help="Zufalls-Seed des Mandanten, aus dem die Erwartung entsteht."),
    ] = DEFAULT_SEED,
) -> None:
    """Erzeugt die erwarteten Findings aus defects.yaml – nie von Hand pflegen (D-010)."""
    client = build_client(seed)
    write_expected(out, client.expected)

    counts = Counter(entry.rule_id for entry in client.expected)
    table = Table(box=box.SIMPLE)
    for column in ("Regel", "Findings"):
        table.add_column(column, no_wrap=True)
    for rule_id, count in sorted(counts.items()):
        table.add_row(rule_id, str(count))
    console.print(table)

    later = sum(1 for entry in client.expected if entry.from_rule_version)
    console.print(
        f"\n{len(client.expected)} erwartete Findings aus {len(counts)} Regeln"
        + (f", davon {later} erst ab einer spaeteren Regelversion" if later else "")
        + f" -> {out}"
    )


@app.command()
def run(
    input_dir: Annotated[
        Path,
        typer.Option("--input", help="Verzeichnis mit SAP-Exports."),
    ],
    out_dir: Annotated[
        Path,
        typer.Option("--out", help="Zielverzeichnis fuer den Lauf."),
    ],
) -> None:
    """Fuehrt einen vollstaendigen Lauf aus (raw -> staged -> canonical -> findings)."""
    _not_implemented(f"run ({input_dir} -> {out_dir})", "Sprint 3")


if __name__ == "__main__":  # pragma: no cover
    app()
