"""Kommandozeile der Prototyp-Engine.

Die Befehle sind in Sprint 1 als Geruest angelegt; Inhalt folgt Aufgabe fuer Aufgabe
laut ``docs/specs/SPRINT-1.md``. Noch nicht implementierte Befehle brechen mit einem
Exit-Code ungleich 0 ab, damit nichts stumm ins Leere laeuft.
"""

from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console

from mdq import __version__

#: Exit-Code fuer Befehle, deren Umsetzung noch aussteht
EXIT_NOT_IMPLEMENTED = 2

console = Console()
err_console = Console(stderr=True)

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
    _not_implemented(f"validate ({path})", "SPRINT-1, Aufgabe 2 – Schema-Validierung")


@rules_app.command("list")
def rules_list() -> None:
    """Listet die Regeln mit ID, Version, Seite, Kategorie und Stufe."""
    _not_implemented("rules list", "SPRINT-1, Aufgabe 3 – Regel-Loader")


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
