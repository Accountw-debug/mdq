"""Kommandozeile der Engine.

Die Befehle sind in Sprint 1 als Geruest angelegt; Inhalt folgt Aufgabe fuer Aufgabe
laut ``docs/specs/SPRINT-1.md``. Noch nicht implementierte Befehle brechen mit einem
Exit-Code ungleich 0 ab, damit nichts stumm ins Leere laeuft.
"""

import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import duckdb
import typer
from rich import box
from rich.console import Console
from rich.table import Table

from mdq import CANONICAL_SCHEMA, EXPECTED_FINDINGS, RULES_DIR, __version__
from mdq.canonical import SIDES, CanonicalError, Scope, build_canonical
from mdq.decisions import (
    DecisionError,
    DecisionMemory,
    find_decisions,
    load_decisions,
    store_decisions,
)
from mdq.demo import DEFAULT_SEED
from mdq.demo.defects import write_expected
from mdq.demo.generate import build_client
from mdq.demo.generate import generate as generate_demo
from mdq.demo.mini import MINI_COMPANY_CODE, MINI_CURRENCY, MINI_SEED
from mdq.demo.mini import generate as generate_mini
from mdq.dictionaries import DictionaryError
from mdq.executor import ExecutionError
from mdq.findings import (
    FindingFileError,
    duplicate_finding_ids,
    iter_finding_files,
    load_finding_file,
    validate_finding,
)
from mdq.formats import NOTATIONS
from mdq.loader import LoaderError, check_table_names, load_table
from mdq.mapping import MappingError, load_mapping
from mdq.pack import PackError
from mdq.relevance import RelevanceError, build_relevance
from mdq.report import DecisionSummary, RunReport, collect_rejects, render
from mdq.rules import RuleError, load_rules
from mdq.run import (
    EXIT_ABORTED,
    FINDINGS_FILE,
    REPORT_FILE,
    RUN_FILE,
    RunError,
    RunOptions,
    execute_run,
    parse_created_at,
)
from mdq.staging import StagingError, stage_all

#: Profile von ``mdq demo generate``: der volle Demo-Mandant und der CHF-Mini-Mandant
PROFILE_DEMO = "demo"
PROFILE_CHF = "chf"
PROFILES = (PROFILE_DEMO, PROFILE_CHF)

#: Mindestens ein Finding ist ungueltig
EXIT_INVALID = 1
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
    company_codes: Annotated[
        str | None,
        typer.Option(
            "--company-codes",
            help="Buchungskreise des Laufs, durch Komma getrennt. Ohne Angabe: alle.",
        ),
    ] = None,
    side: Annotated[
        str,
        typer.Option("--side", help="Seite des Laufs: ar, ap oder both."),
    ] = "both",
    data_as_of: Annotated[
        str | None,
        typer.Option(
            "--data-as-of",
            help=(
                "Datenstand als JJJJ-MM-TT. Ohne Angabe: spaetestes Buchungs- oder "
                "Ausgleichsdatum der Posten; der Report nennt den verwendeten Wert."
            ),
        ),
    ] = None,
    decisions: Annotated[
        Path | None,
        typer.Option(
            "--decisions",
            help=(
                "YAML mit getroffenen Entscheidungen. Ohne Angabe wird "
                "<input>/decisions.yaml verwendet, falls vorhanden."
            ),
        ),
    ] = None,
) -> None:
    """Liest Exporte ein, typisiert sie und baut das kanonische Modell.

    Zwischenstand: die Regelausfuehrung und ``runs/<id>/`` folgen mit ``mdq run``
    (Sprint 3, Aufgabe 4).
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

    as_of = _as_date(data_as_of, "--data-as-of") if data_as_of is not None else None

    if side not in SIDES:
        err_console.print(
            f"[bold red]Fehler:[/] --side {side!r} ist unbekannt; erlaubt sind {sorted(SIDES)}."
        )
        raise typer.Exit(code=EXIT_INVALID)

    scope = Scope(
        company_codes=tuple(
            code.strip() for code in (company_codes or "").split(",") if code.strip()
        ),
        side=side,
    )

    files = sorted(
        path for path in input_dir.iterdir() if path.is_file() and path.suffix in EXPORT_SUFFIXES
    )
    if not files:
        err_console.print(f"[bold red]Fehler:[/] keine Exportdateien unter {input_dir} gefunden.")
        raise typer.Exit(code=EXIT_NO_INPUT)

    try:
        # Vor dem ersten Import, wie in `mdq run`: zwei Dateien mit demselben
        # Tabellennamen wuerden einander stillschweigend ueberschreiben (Regel 4).
        check_table_names(files)
    except LoaderError as exc:
        err_console.print(f"[bold red]Fehler:[/] {exc}")
        raise typer.Exit(code=EXIT_INVALID) from exc

    con = duckdb.connect(":memory:")
    con.execute(CANONICAL_SCHEMA.read_text(encoding="utf-8"))

    report = RunReport(
        run_id=LOAD_RUN_ID,
        engine_version=__version__,
        note=(
            "Zwischenstand: Dateien werden eingelesen, typisiert und kanonisch abgebildet. "
            "Die Regelausführung folgt mit `mdq run` (Sprint 3, Aufgabe 4)."
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
        report.add_canonical(build_canonical(con, mapping, LOAD_RUN_ID, scope))
        report.add_relevance(build_relevance(con, as_of))
        memory = _load_memory(input_dir, decisions)
        store_decisions(con, memory)
        # Regeln laufen in dieser Zwischenstufe nicht; "verwaist" waere hier ohne Aussage.
        report.add_decisions(DecisionSummary.of(memory, rules_executed=False))
    except (
        LoaderError,
        MappingError,
        StagingError,
        CanonicalError,
        RelevanceError,
        DecisionError,
    ) as exc:
        err_console.print(f"[bold red]Fehler:[/] {exc}")
        raise typer.Exit(code=EXIT_INVALID) from exc

    report.rejects = collect_rejects(con, LOAD_RUN_ID)
    render(report, console)


def _as_date(value: str, option: str) -> date:
    """``JJJJ-MM-TT`` aus einem Schalter; ein Tippfehler ist ein Fehler mit Namen."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()  # noqa: DTZ007
    except ValueError:
        err_console.print(
            f"[bold red]Fehler:[/] {option} {value!r} ist kein Datum im Format JJJJ-MM-TT."
        )
        raise typer.Exit(code=EXIT_INVALID) from None


def _load_memory(input_dir: Path, given: Path | None) -> DecisionMemory:
    """Das Entscheidungsgedaechtnis des Laufs; ohne Datei ein leeres."""
    path = find_decisions(input_dir, given)
    return load_decisions(path) if path is not None else DecisionMemory()


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
    profile: Annotated[
        str,
        typer.Option(
            "--profile",
            help="demo = der volle Mandant (EUR, zwei Buchungskreise); "
            "chf = Mini-Mandant in Fremdwaehrung (ein Buchungskreis, CHF, 20 BPs).",
        ),
    ] = PROFILE_DEMO,
) -> None:
    """Erzeugt den synthetischen Demo-Mandanten (16 Dateien und manifest.json)."""
    if profile not in PROFILES:
        err_console.print(
            f"[bold red]Fehler:[/] --profile {profile!r} ist unbekannt; "
            f"erlaubt sind {sorted(PROFILES)}."
        )
        raise typer.Exit(code=EXIT_INVALID)
    if profile == PROFILE_CHF:
        if not defects:
            err_console.print(
                "[bold red]Fehler:[/] --no-defects gilt nur fuer --profile demo; der "
                "CHF-Mandant hat keine Defektschicht."
            )
            raise typer.Exit(code=EXIT_INVALID)
        manifest = generate_mini(out, seed if seed != DEFAULT_SEED else MINI_SEED)
    else:
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
    if profile == PROFILE_CHF:
        console.print(
            f"[yellow]Profil chf:[/] Mini-Mandant, Buchungskreis {MINI_COMPANY_CODE}, "
            f"Hauswaehrung {MINI_CURRENCY}, ohne Defekte."
        )
    elif not defects:
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
        typer.Option("--out", help="Zielverzeichnis fuer den Lauf (z. B. runs/)."),
    ],
    company_codes: Annotated[
        str | None,
        typer.Option(
            "--company-codes",
            help="Buchungskreise des Laufs, durch Komma getrennt. Ohne Angabe: alle.",
        ),
    ] = None,
    side: Annotated[
        str,
        typer.Option("--side", help="Seite des Laufs: ar, ap oder both."),
    ] = "both",
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
    data_as_of: Annotated[
        str | None,
        typer.Option(
            "--data-as-of",
            help=(
                "Datenstand als JJJJ-MM-TT. Ohne Angabe: spaetestes Buchungs- oder "
                "Ausgleichsdatum der Posten; der Report nennt den verwendeten Wert."
            ),
        ),
    ] = None,
    decisions: Annotated[
        Path | None,
        typer.Option(
            "--decisions",
            help=(
                "YAML mit getroffenen Entscheidungen. Ohne Angabe wird "
                "<input>/decisions.yaml verwendet, falls vorhanden."
            ),
        ),
    ] = None,
    created_at: Annotated[
        str | None,
        typer.Option(
            "--created-at",
            help=(
                "Zeitpunkt des Laufs (JJJJ-MM-TTTHH:MM:SSZ, UTC). Ohne Angabe die Uhr; "
                "festgesetzt werden zwei Laeufe byte-identisch."
            ),
        ),
    ] = None,
) -> None:
    """Fuehrt einen vollstaendigen Lauf aus: raw -> staged -> canonical -> findings.

    Schreibt ``runs/<run_id>/`` mit ``findings.json``, ``run.json`` und ``report.txt``.
    Exit-Codes: 0 sauber, 1 Auffaelligkeiten im Lauf (Rejects, uebersprungene oder
    fehlgeschlagene Regeln), 2 Abbruch (D-097).
    """
    if decimal_notation is not None and decimal_notation not in NOTATIONS:
        err_console.print(
            f"[bold red]Fehler:[/] --decimal-notation {decimal_notation!r} ist unbekannt; "
            f"erlaubt sind {list(NOTATIONS)}."
        )
        raise typer.Exit(code=EXIT_ABORTED)
    if side not in SIDES:
        err_console.print(
            f"[bold red]Fehler:[/] --side {side!r} ist unbekannt; erlaubt sind {sorted(SIDES)}."
        )
        raise typer.Exit(code=EXIT_ABORTED)

    try:
        stamp = parse_created_at(created_at) if created_at is not None else None
        options = RunOptions(
            input_dir=input_dir,
            out_dir=out_dir,
            scope=Scope(
                company_codes=tuple(
                    code.strip() for code in (company_codes or "").split(",") if code.strip()
                ),
                side=side,
            ),
            decimal_notation=decimal_notation,
            data_as_of=_as_date(data_as_of, "--data-as-of") if data_as_of else None,
            decisions_path=decisions,
            created_at=stamp,
        )
        started = time.perf_counter()
        result = execute_run(options)
    except (
        RunError,
        LoaderError,
        MappingError,
        StagingError,
        CanonicalError,
        RelevanceError,
        DecisionError,
        DictionaryError,
        PackError,
        RuleError,
        ExecutionError,
        FindingFileError,
    ) as exc:
        err_console.print(f"[bold red]Fehler:[/] {exc}")
        raise typer.Exit(code=EXIT_ABORTED) from exc

    seconds = time.perf_counter() - started
    render(result.report, console)
    if result.recovered:
        console.print(f"\n[yellow]HINWEIS[/] {result.recovered}")
    if result.replaced:
        console.print(f"\n[yellow]HINWEIS[/] {result.replaced}")
    console.print(
        f"\n{len(result.findings)} Findings in {result.directory} "
        f"({FINDINGS_FILE}, {RUN_FILE}, {REPORT_FILE})."
    )
    # Der Zeitpunkt steht ausdruecklich da: er landet in jedem Finding, und mit
    # --created-at sind zwei Laeufe byte-identisch (D-092). Die Dauer wird nur gesagt,
    # nie geschrieben – sonst waere keine Datei je zweimal gleich.
    console.print(f"Zeitpunkt (created_at): {result.report.created_at}   Dauer: {seconds:.1f} s")
    raise typer.Exit(code=result.exit_code)


if __name__ == "__main__":  # pragma: no cover
    app()
