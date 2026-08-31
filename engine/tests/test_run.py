"""`mdq run` Ende-zu-Ende: die drei Dateien, der Vertrag zur UI, Determinismus, Exit-Codes.

Der Lauf ist die Stelle, an der alle Stufen zusammenkommen; entsprechend prueft diese
Datei nicht nur, dass etwas herauskommt, sondern **was genau**: dass `run.json` die sechs
Felder traegt, die die UI als Lauf-Kopf liest, dass zwei Laeufe mit festem `--created-at`
byte-identisch sind, dass ein Abbruch nichts Halbes hinterlaesst und dass in den
Artefakten keine Geschaeftspartnerdaten stehen (Regel 8).

Der Demo-Mandant wird einmal je Modul gelaufen; die kleinen Faelle arbeiten auf
erfundenen Exporten.
"""

import json
import time
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mdq import DEMO_MANDANT_DIR, __version__
from mdq.canonical import Scope
from mdq.cli import app
from mdq.relevance import RelevanceError
from mdq.run import (
    EXIT_ABORTED,
    EXIT_CLEAN,
    EXIT_PROBLEMS,
    FINDINGS_FILE,
    REPORT_FILE,
    RUN_FILE,
    RunError,
    RunOptions,
    execute_run,
    parse_created_at,
    run_id_for,
)

runner = CliRunner()

#: Fester Zeitpunkt – die Uhr hat in einem Test nichts verloren (Regel 9)
CREATED_AT = "2026-08-31T08:00:00Z"

#: Ein winziger, vollstaendiger Mandant: ein Buchungskreis, ein Debitor, ein Posten
T001 = "BUKRS\tBUTXT\tWAERS\tLAND1\n1000\tDemo Industrie AG\tEUR\tDE\n"
KNA1 = "KUNNR\tLAND1\tNAME1\tORT01\tERDAT\n0000100001\tDE\tAlpha AG\tAugsburg\t20200101\n"
KNB1 = "KUNNR\tBUKRS\tAKONT\n0000100001\t1000\t140000\n"
BSID = (
    "KUNNR\tBUKRS\tGJAHR\tBELNR\tBUZEI\tBUDAT\tBLART\tSHKZG\tWAERS\tWRBTR\tDMBTR\n"
    "0000100001\t1000\t2026\t0100000001\t001\t20260115\tDR\tS\tEUR\t1.000,00\t1.000,00\n"
)
KLEIN = {"T001": T001, "KNA1": KNA1, "KNB1": KNB1, "BSID": BSID}


def schreibe(directory: Path, files: dict[str, str]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (directory / f"{name}.txt").write_text(content, encoding="utf-8")
    return directory


def lauf(tmp_path: Path, files: dict[str, str] | None = None, **kwargs) -> object:
    """Kleiner Lauf auf erfundenen Exporten."""
    quelle = schreibe(tmp_path / "input", files if files is not None else KLEIN)
    kwargs.setdefault("created_at", CREATED_AT)
    return execute_run(RunOptions(input_dir=quelle, out_dir=tmp_path / "runs", **kwargs))


def gelesen(directory: Path, name: str):
    return json.loads((directory / name).read_text(encoding="utf-8"))


# --- Der Demo-Mandant, einmal gelaufen -------------------------------------------------


@pytest.fixture(scope="module")
def demo_run(demo_client, tmp_path_factory):
    out = tmp_path_factory.mktemp("runs")
    directory, _manifest = demo_client
    return execute_run(
        RunOptions(input_dir=directory, out_dir=out, created_at=CREATED_AT)
    )


def test_lauf_schreibt_drei_dateien(demo_run):
    """Akzeptanz aus SPRINT-3.md, Aufgabe 4."""
    assert sorted(path.name for path in demo_run.directory.iterdir()) == [
        FINDINGS_FILE,
        REPORT_FILE,
        RUN_FILE,
    ]
    assert demo_run.exit_code == EXIT_CLEAN
    assert demo_run.directory.name == demo_run.report.run_id


def test_demo_mandant_liefert_die_bekannten_dreissig_findings(demo_run):
    """15 + 7 + 8 wie in der Handprobe; die Regression prueft sie einzeln (Aufgabe 5)."""
    findings = gelesen(demo_run.directory, FINDINGS_FILE)
    assert len(findings) == 30
    je_regel = {}
    for finding in findings:
        je_regel[finding["rule_id"]] = je_regel.get(finding["rule_id"], 0) + 1
    assert je_regel == {"AR-VAL-001": 15, "AR-CON-002": 7, "AP-LEA-001": 8}


def test_findings_sind_nach_id_sortiert(demo_run):
    findings = gelesen(demo_run.directory, FINDINGS_FILE)
    assert [f["finding_id"] for f in findings] == sorted(f["finding_id"] for f in findings)


def test_jedes_finding_traegt_die_kopfdaten_des_laufs(demo_run):
    for finding in gelesen(demo_run.directory, FINDINGS_FILE):
        assert finding["run_id"] == demo_run.report.run_id
        assert finding["created_at"] == CREATED_AT
        assert finding["data_as_of"] == "2026-08-28"
        assert finding["engine_version"] == __version__
        assert finding["status"] == "open"  # ohne Entscheidungsgedaechtnis


# --- Der Vertrag zur UI ----------------------------------------------------------------


def test_run_json_traegt_den_ui_vertrag(demo_run):
    """Die sechs Felder von `RunInfo` – `ui/src/types/finding.ts` im Worktree `ui-proto`.

    Die UI hakt `run.json` ohne Pruefung als `RunInfo` durch; fehlt `company_codes`,
    scheitert das Datenstand-Banner. Deshalb steht der Vertrag hier als Test (D-094).
    """
    run = gelesen(demo_run.directory, RUN_FILE)
    assert isinstance(run["run_id"], str) and run["run_id"]
    assert run["data_as_of"] == "2026-08-28"
    assert run["engine_version"] == __version__
    assert isinstance(run["pack_version"], str) and run["pack_version"]
    assert run["tables_loaded"] == 16
    assert run["company_codes"] == ["1000", "2000"]
    assert isinstance(run["tables_loaded"], int)
    assert all(isinstance(code, str) for code in run["company_codes"])


def test_run_json_traegt_scope_und_versionen(demo_run):
    run = gelesen(demo_run.directory, RUN_FILE)
    assert run["scope"] == {
        "company_codes": [],  # der Filter, nicht der Inhalt (D-095)
        "side": "both",
        "item_window_from": None,
        "item_window_to": None,
        "decimal_notation": None,
        "data_as_of_source": "spaetestes Buchungs-/Ausgleichsdatum der Posten",
        "decisions_file": None,
    }
    versions = run["versions"]
    assert versions["engine"] == __version__
    assert versions["finding_schema"] == "1.1"
    assert versions["mapping"] == "0.1"
    assert len(versions["pack_hash"]) == 64  # sha256 ueber logic/ (D-096)


def test_run_json_zeigt_die_stufen_und_die_ampel(demo_run):
    run = gelesen(demo_run.directory, RUN_FILE)
    assert run["totals"]["findings"] == 30
    assert run["totals"]["rejects"] == 0
    assert run["has_problems"] is False
    assert run["exit_code"] == EXIT_CLEAN
    # Hinweise stehen da, aendern den Exit-Code aber nicht (D-097).
    assert any("name_norm" in hint for hint in run["hints"])
    assert run["relevance"]["partners"] == 3500
    assert run["canonical"]["tables"][0]["table"] == "company_code"


def test_kein_float_in_den_artefakten(demo_run):
    """Betraege sind Strings mit Waehrung daneben (Regel 2) – nirgends ein float."""

    def pruefe(value, pfad="run.json"):
        if isinstance(value, float):
            pytest.fail(f"float in {pfad}: {value}")
        if isinstance(value, dict):
            for key, entry in value.items():
                pruefe(entry, f"{pfad}.{key}")
        if isinstance(value, list):
            for index, entry in enumerate(value):
                pruefe(entry, f"{pfad}[{index}]")

    pruefe(gelesen(demo_run.directory, RUN_FILE))
    pruefe(gelesen(demo_run.directory, FINDINGS_FILE), "findings.json")


def test_keine_partnerdaten_in_report_und_run(demo_run):
    """Regel 8: der Report nennt Schluessel und Regel-IDs, keine Namen oder Adressen."""
    text = (demo_run.directory / REPORT_FILE).read_text(encoding="utf-8")
    text += (demo_run.directory / RUN_FILE).read_text(encoding="utf-8")
    for name in ("Müller", "Mueller Maschinenbau", "Bergmann", "Nordwind", "Brandt"):
        assert name not in text, name
    assert "raw_excerpt" not in text


def test_report_txt_haelt_die_feste_breite(demo_run):
    """Ohne feste Breite saehe dieselbe Datei auf zwei Rechnern verschieden aus."""
    zeilen = (demo_run.directory / REPORT_FILE).read_text(encoding="utf-8").splitlines()
    assert zeilen and max(len(zeile) for zeile in zeilen) <= 100
    assert "\x1b[" not in "".join(zeilen)  # keine Farbcodes


def test_laufzeit_unter_60_sekunden(demo_client, tmp_path):
    """Akzeptanz aus SPRINT-3.md; heute sind es rund fuenf Sekunden."""
    directory, _ = demo_client
    start = time.perf_counter()
    execute_run(
        RunOptions(input_dir=directory, out_dir=tmp_path / "runs", created_at=CREATED_AT)
    )
    assert time.perf_counter() - start < 60


# --- Determinismus (D-092) -------------------------------------------------------------


def test_zwei_laeufe_mit_festem_created_at_sind_byte_identisch(demo_client, tmp_path):
    directory, _ = demo_client
    erster = execute_run(
        RunOptions(input_dir=directory, out_dir=tmp_path / "a", created_at=CREATED_AT)
    )
    zweiter = execute_run(
        RunOptions(input_dir=directory, out_dir=tmp_path / "b", created_at=CREATED_AT)
    )
    assert erster.report.run_id == zweiter.report.run_id
    for name in (FINDINGS_FILE, RUN_FILE, REPORT_FILE):
        assert (erster.directory / name).read_bytes() == (zweiter.directory / name).read_bytes(), (
            name
        )


def test_ohne_schalter_unterscheidet_sich_nur_der_zeitpunkt(demo_client, tmp_path):
    """Zusicherung im Wortlaut: ohne `--created-at` identisch bis auf `created_at`."""
    directory, _ = demo_client
    fest = execute_run(
        RunOptions(input_dir=directory, out_dir=tmp_path / "a", created_at=CREATED_AT)
    )
    mit_uhr = execute_run(RunOptions(input_dir=directory, out_dir=tmp_path / "b"))
    assert fest.report.run_id == mit_uhr.report.run_id  # die Uhr geht nicht in den run_id

    def ohne_zeitpunkt(directory: Path, name: str) -> str:
        text = (directory / name).read_text(encoding="utf-8")
        for stamp in (CREATED_AT, mit_uhr.report.created_at):
            text = text.replace(stamp, "<zeitpunkt>")
        return text

    for name in (FINDINGS_FILE, RUN_FILE, REPORT_FILE):
        assert ohne_zeitpunkt(fest.directory, name) == ohne_zeitpunkt(mit_uhr.directory, name)


def test_run_id_haengt_an_den_daten_und_der_frage(tmp_path):
    """D-093: Input-Hashes, Scope, Datenstand, Entscheidungsdatei – keine Versionen."""
    dateien = [("KNA1", "a" * 64), ("BSID", "b" * 64)]
    basis = run_id_for(dateien, Scope(), date(2026, 8, 28), None, None)
    assert basis.startswith("2026-08-28-") and len(basis) == len("2026-08-28-") + 8
    assert run_id_for(list(reversed(dateien)), Scope(), date(2026, 8, 28), None, None) == basis
    assert run_id_for(dateien, Scope(company_codes=("1000",)), date(2026, 8, 28), None, None) != basis
    assert run_id_for(dateien, Scope(side="ap"), date(2026, 8, 28), None, None) != basis
    assert run_id_for(dateien, Scope(), date(2026, 8, 27), None, None) != basis
    assert run_id_for(dateien, Scope(), date(2026, 8, 28), "de", None) != basis
    assert run_id_for(dateien, Scope(), date(2026, 8, 28), None, "c" * 64) != basis


def test_scope_aendert_run_id_und_kopf(tmp_path):
    ohne = lauf(tmp_path / "ohne")
    mit = lauf(tmp_path / "mit", scope=Scope(company_codes=("1000",)))
    assert ohne.report.run_id != mit.report.run_id
    run = gelesen(mit.directory, RUN_FILE)
    assert run["scope"]["company_codes"] == ["1000"]
    assert run["company_codes"] == ["1000"]


# --- Zeitpunkt -------------------------------------------------------------------------


def test_created_at_wird_geprueft():
    assert parse_created_at("2026-08-31T08:00:00Z") == "2026-08-31T08:00:00Z"
    assert parse_created_at("2026-08-31T08:00:00+00:00") == "2026-08-31T08:00:00Z"
    with pytest.raises(RunError):
        parse_created_at("gestern")
    with pytest.raises(RunError) as excinfo:
        parse_created_at("2026-08-31T08:00:00+02:00")
    assert "UTC" in str(excinfo.value)
    with pytest.raises(RunError):
        parse_created_at("2026-08-31T08:00:00")  # ohne Zone


# --- Abbruch und Ersetzen (D-093) ------------------------------------------------------


def test_ohne_t001_bricht_der_lauf_ab_und_schreibt_nichts(tmp_path):
    ohne_t001 = {name: text for name, text in KLEIN.items() if name != "T001"}
    with pytest.raises(RelevanceError) as excinfo:
        lauf(tmp_path, ohne_t001)
    assert "T001" in str(excinfo.value)
    assert not (tmp_path / "runs").exists()


def test_leeres_verzeichnis_ist_ein_abbruch(tmp_path):
    leer = tmp_path / "leer"
    leer.mkdir()
    with pytest.raises(RunError) as excinfo:
        execute_run(RunOptions(input_dir=leer, out_dir=tmp_path / "runs"))
    assert "Keine Exportdateien" in str(excinfo.value)


def test_ein_abbruch_laesst_den_vorhandenen_lauf_unberuehrt(tmp_path):
    """Atomar: erst in ein temporaeres Verzeichnis, dann tauschen."""
    erster = lauf(tmp_path)
    vorher = (erster.directory / RUN_FILE).read_bytes()

    # Zweiter Anlauf auf demselben Ausgabeverzeichnis, aber mit kaputter Eingabe.
    kaputt = schreibe(tmp_path / "kaputt", {name: KLEIN[name] for name in ("KNA1", "KNB1")})
    with pytest.raises(Exception):  # noqa: B017 – jede Stufe darf hier abbrechen
        execute_run(
            RunOptions(input_dir=kaputt, out_dir=tmp_path / "runs", created_at=CREATED_AT)
        )
    assert (erster.directory / RUN_FILE).read_bytes() == vorher
    reste = [p.name for p in (tmp_path / "runs").iterdir() if p.name.startswith(".")]
    assert reste == []


def test_ersetzen_nennt_beide_versionen(tmp_path):
    erster = lauf(tmp_path)
    # Den alten Lauf so tun lassen, als stamme er aus einem aelteren Paket.
    alt = gelesen(erster.directory, RUN_FILE)
    alt["engine_version"] = "0.0.9"
    alt["pack_version"] = "0.0"
    alt["versions"]["pack_hash"] = "0" * 64
    (erster.directory / RUN_FILE).write_text(json.dumps(alt, indent=2), encoding="utf-8")

    zweiter = lauf(tmp_path)
    assert zweiter.replaced is not None
    assert "vorher engine 0.0.9/pack 0.0" in zweiter.replaced
    assert f"jetzt engine {__version__}/pack" in zweiter.replaced
    # Der Vermerk steht auf der Konsole, nicht in den Dateien (D-092).
    assert "ersetzt" not in (zweiter.directory / RUN_FILE).read_text(encoding="utf-8")


def test_ersetzen_ohne_lesbares_run_json(tmp_path):
    erster = lauf(tmp_path)
    (erster.directory / RUN_FILE).write_text("kein JSON", encoding="utf-8")
    zweiter = lauf(tmp_path)
    assert "kein lesbares run.json" in zweiter.replaced


# --- Exit 1: der Lauf lief, hatte aber Auffaelligkeiten (D-097) ------------------------


def test_reject_fuehrt_zu_exit_1(tmp_path):
    """Eine nicht typisierbare Zeile ist ein Reject – der Lauf laeuft, meldet es aber."""
    mit_reject = dict(KLEIN)
    mit_reject["BSID"] = BSID + (
        "0000100001\t1000\t2026\t0100000002\t001\t20260116\tDR\tS\tEUR\tviel\tviel\n"
    )
    ergebnis = lauf(tmp_path, mit_reject)
    assert ergebnis.exit_code == EXIT_PROBLEMS
    run = gelesen(ergebnis.directory, RUN_FILE)
    assert run["totals"]["rejects"] == 1
    assert run["has_problems"] is True
    assert run["exit_code"] == EXIT_PROBLEMS
    # Trotzdem vollstaendig geschrieben – ein Lauf mit Rejects ist kein Abbruch.
    assert (ergebnis.directory / FINDINGS_FILE).exists()


def test_uebersprungene_regel_fuehrt_zu_exit_1(tmp_path, valid_rule_text):
    """Eine Regel, deren Tabellen fehlen, wird genannt statt stillschweigend ausgelassen."""
    regeln = tmp_path / "regeln"
    regeln.mkdir()
    (regeln / "AR-VAL-009.rule.sql").write_text(
        valid_rule_text.replace(
            "requires_tables: [business_partner]", "requires_tables: [change_document, ohne_mich]"
        ),
        encoding="utf-8",
    )
    ergebnis = lauf(tmp_path, rules_dir=regeln)
    assert ergebnis.exit_code == EXIT_PROBLEMS
    run = gelesen(ergebnis.directory, RUN_FILE)
    assert run["rules"] == [
        {
            "rule_id": "AR-VAL-009",
            "status": "skipped",
            "findings": 0,
            "reason": "benötigte Tabellen fehlen: ohne_mich",
        }
    ]
    assert run["totals"]["findings"] == 0


# --- Die Kommandozeile -----------------------------------------------------------------


def test_cli_run_schreibt_und_endet_mit_null(tmp_path):
    quelle = schreibe(tmp_path / "input", KLEIN)
    result = runner.invoke(
        app,
        ["run", "--input", str(quelle), "--out", str(tmp_path / "runs"),
         "--created-at", CREATED_AT],
    )
    assert result.exit_code == EXIT_CLEAN, result.output
    assert "Zeitpunkt (created_at): 2026-08-31T08:00:00Z" in result.output
    assert "Dauer:" in result.output
    geschrieben = list((tmp_path / "runs").iterdir())
    assert len(geschrieben) == 1


def test_cli_run_meldet_nie_einen_leeren_erfolg(tmp_path):
    """D-013 an der Stelle, an der frueher der Stub stand."""
    leer = tmp_path / "leer"
    leer.mkdir()
    result = runner.invoke(app, ["run", "--input", str(leer), "--out", str(tmp_path / "runs")])
    assert result.exit_code == EXIT_ABORTED
    assert "Keine Exportdateien" in result.output


def test_cli_run_weist_falsche_schalter_ab(tmp_path):
    quelle = schreibe(tmp_path / "input", KLEIN)
    for argumente in (
        ["--side", "AR"],
        ["--decimal-notation", "deutsch"],
        ["--created-at", "gestern"],
        ["--data-as-of", "31.08.2026"],
    ):
        result = runner.invoke(
            app,
            ["run", "--input", str(quelle), "--out", str(tmp_path / "runs"), *argumente],
        )
        assert result.exit_code != EXIT_CLEAN, argumente


def test_cli_run_auf_dem_demo_mandanten_endet_sauber(tmp_path):
    """Der ausgelieferte Mandant, ueber die Kommandozeile, mit Exit 0."""
    result = runner.invoke(
        app,
        ["run", "--input", str(DEMO_MANDANT_DIR), "--out", str(tmp_path / "runs"),
         "--created-at", CREATED_AT],
    )
    assert result.exit_code == EXIT_CLEAN, result.output
    assert "30 Findings" in result.output
