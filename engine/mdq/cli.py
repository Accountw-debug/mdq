"""Kommandozeile der Prototyp-Engine.

Die Befehle sind in Sprint 1 als Geruest angelegt; Inhalt folgt Aufgabe fuer Aufgabe
laut ``docs/specs/SPRINT-1.md``. Noch nicht implementierte Befehle brechen mit einem
Exit-Code ungleich 0 ab, damit nichts stumm ins Leere laeuft.
"""

from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from mdq import RULES_DIR, __version__
from mdq.findings import (
    FindingFileError,
    duplicate_finding_ids,
    iter_finding_files,
    load_finding_file,
    validate_finding,
)
from mdq.rules import RuleError, load_rules

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
    help="MDQ – Finance Master Data & Leakage Check (Prototyp-Engine).",
    no_args_is_help=True,
    add_completion=False,
)

rules_app = typer.Typer(help="Regeln aus logic/rules/ inspizieren.", no_args_is_help=True)
app.add_typer(rules_app, name="rules")


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

    warned = [rule for rule in rules if rule.warnings]
    for rule in warned:
        for message in rule.warnings:
            console.print(f"[yellow]HINWEIS[/] {rule.id}: {message}")

    console.print(f"\n{len(rules)} Regeln, {len(warned)} mit Hinweis.")


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
