"""Regression: Lauf auf dem Demo-Mandanten gegen `expected_findings.yaml`.

Zwei Teile. Die Vergleichslogik wird an erfundenen Zeilen vollstaendig getestet; danach
laeuft der ganze Lauf auf `testdata/demo_mandant` und wird gegen die Erwartung gestellt.
Weicht er ab, ist entweder die Regel, der Generator oder die Erwartung falsch -- das wird
geklaert, nicht weggetestet (CLAUDE.md Regel 1, D-010).
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from mdq import DEMO_MANDANT_DIR, RULES_DIR
from mdq.cli import app
from mdq.regression import (
    ActualFinding,
    ExpectedFinding,
    RegressionError,
    actual_from_findings,
    compare,
    load_expected,
    parse_version,
)
from mdq.rules import load_rules
from mdq.run import EXIT_CLEAN, RunOptions, execute_run

runner = CliRunner()

VERSIONS = {"AR-VAL-001": "1.0", "AP-LEA-001": "1.0"}


def _expected(rule_id="AR-VAL-001", bp_key="C:0000100014", **kwargs) -> ExpectedFinding:
    kwargs.setdefault("defect", "DEF-0036")
    return ExpectedFinding(rule_id=rule_id, bp_key=bp_key, **kwargs)


def _actual(rule_id="AR-VAL-001", bp_key="C:0000100014", **kwargs) -> ActualFinding:
    return ActualFinding(rule_id=rule_id, bp_key=bp_key, **kwargs)


# --- Versionen -----------------------------------------------------------------------


def test_versions_compare_as_numbers() -> None:
    """Als Text waere '1.10' kleiner als '1.9'."""
    assert parse_version("1.10") > parse_version("1.9")
    assert parse_version("1.0") < parse_version("1.1")


def test_bad_version_is_reported() -> None:
    with pytest.raises(RegressionError):
        parse_version("eins.null")


# --- Die sechs Toepfe ----------------------------------------------------------------


def test_full_match_is_ok() -> None:
    result = compare([_expected()], [_actual()], VERSIONS)
    assert result.ok
    assert result.render() == "Lauf und Erwartung stimmen ueberein."


def test_missing_is_reported() -> None:
    result = compare([_expected()], [], VERSIONS)
    assert not result.ok
    assert [item.bp_key for item in result.missing] == ["C:0000100014"]
    assert "Fehlend (1)" in result.render()


def test_unexpected_is_reported() -> None:
    result = compare([], [_actual()], VERSIONS)
    assert not result.ok
    assert [item.bp_key for item in result.unexpected] == ["C:0000100014"]
    assert "Unerwartet (1)" in result.render()


def test_deviating_company_code_is_its_own_bucket() -> None:
    """Ein falscher Buchungskreis ist eine Abweichung, nicht Fehlend plus Unerwartet."""
    result = compare(
        [_expected(company_code="1000")], [_actual(company_code="2000")], VERSIONS
    )
    assert not result.ok
    assert result.missing == ()
    assert result.unexpected == ()
    assert len(result.deviating) == 1
    assert result.deviating[0].differing_fields == ("company_code",)
    assert "Abweichend (1)" in result.render()


def test_deviating_finding_key_is_reported() -> None:
    result = compare(
        [_expected(rule_id="AP-LEA-001", bp_key="V:0000200151", finding_key="4711|4712")],
        [_actual(rule_id="AP-LEA-001", bp_key="V:0000200151", finding_key="4711|4713")],
        VERSIONS,
    )
    assert result.deviating[0].differing_fields == ("finding_key",)


def test_known_open_is_a_hint_not_a_failure() -> None:
    """D-054: erst ab 1.1 Pflicht, die gebaute Regel steht auf 1.0."""
    item = _expected(rule_id="AP-LEA-001", bp_key="V:0000200001", from_rule_version="1.1")
    result = compare([item], [], VERSIONS)
    assert result.ok
    assert result.missing == ()
    assert [entry.bp_key for entry in result.known_open] == ["V:0000200001"]
    assert "Bekannt offen (1)" in result.render()


def test_early_delivery_is_a_hint_with_an_instruction() -> None:
    """Taucht ein bekannt-offenes Finding schon auf, ist die Angabe zu hoch gegriffen."""
    item = _expected(rule_id="AP-LEA-001", bp_key="V:0000200001", from_rule_version="1.1")
    actual = _actual(rule_id="AP-LEA-001", bp_key="V:0000200001")
    result = compare([item], [actual], VERSIONS)
    assert result.ok
    assert result.unexpected == ()
    assert [entry.bp_key for entry in result.early] == ["V:0000200001"]
    report = result.render()
    assert "Vorzeitig erfuellt (1)" in report
    assert "defects.yaml" in report and "absenken" in report


def test_known_open_becomes_mandatory_at_the_version() -> None:
    item = _expected(rule_id="AP-LEA-001", bp_key="V:0000200001", from_rule_version="1.1")
    result = compare([item], [], {"AP-LEA-001": "1.1"})
    assert not result.ok
    assert [entry.bp_key for entry in result.missing] == ["V:0000200001"]


def test_rule_not_built_is_a_hint() -> None:
    """Sonst waere der Test bis zur letzten der 19 Regeln rot – und damit wertlos."""
    result = compare([_expected(rule_id="AR-DUP-001")], [], VERSIONS)
    assert result.ok
    assert len(result.rule_missing) == 1
    assert "Regel fehlt (1 Findings, 1 Regeln)" in result.render()


def test_duplicate_actual_is_rejected() -> None:
    with pytest.raises(RegressionError) as exc:
        compare([], [_actual(), _actual()], VERSIONS)
    assert "finding_key-Spalte" in str(exc.value)


# --- Ausgabe -------------------------------------------------------------------------


def test_render_is_deterministic() -> None:
    expected = [_expected(bp_key="C:0000100040"), _expected(bp_key="C:0000100014")]
    first = compare(expected, [], VERSIONS).render()
    second = compare(list(reversed(expected)), [], VERSIONS).render()
    assert first == second
    assert first.index("C:0000100014") < first.index("C:0000100040")


def test_render_carries_no_business_partner_data() -> None:
    """Regel 8: nur Schluessel, Buchungskreis, finding_key und Defekt-ID."""
    result = compare([_expected(company_code="1000")], [_actual(company_code="2000")], VERSIONS)
    report = result.render()
    assert "DEF-0036" in report
    assert "C:0000100014" in report
    for forbidden in ("Müller", "Mueller", "DE12", "Robert-Bosch", "Augsburg"):
        assert forbidden not in report


# --- Die echte erwartete Liste -------------------------------------------------------


def test_expected_file_loads() -> None:
    expected = load_expected()
    assert len(expected) == 230
    assert len({item.rule_id for item in expected}) == 19


def test_expected_file_has_no_duplicate_match_keys() -> None:
    expected = load_expected()
    assert len({item.match_key for item in expected}) == len(expected)


def test_current_split_over_the_buckets() -> None:
    """Stand heute: 3 von 19 Regeln gebaut."""
    expected = load_expected()
    versions = {rule.id: rule.version for rule in load_rules()}
    result = compare(expected, [], versions)
    assert len(result.rule_missing) == 198
    assert len(result.known_open) == 2
    assert len(result.missing) == 30
    assert len(result.missing) + len(result.known_open) + len(result.rule_missing) == 230


def test_unknown_field_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "expected_findings.yaml"
    path.write_text(
        'findings:\n  - {rule_id: AR-VAL-001, bp_key: "C:1", defect: DEF-0001, foo: 1}\n',
        encoding="utf-8",
    )
    with pytest.raises(RegressionError) as exc:
        load_expected(path)
    assert "unbekannte Felder ['foo']" in str(exc.value)


def test_missing_required_field_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "expected_findings.yaml"
    path.write_text('findings:\n  - {rule_id: AR-VAL-001, bp_key: "C:1"}\n', encoding="utf-8")
    with pytest.raises(RegressionError) as exc:
        load_expected(path)
    assert "Pflichtfelder fehlen: ['defect']" in str(exc.value)


def test_duplicate_match_key_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "expected_findings.yaml"
    path.write_text(
        'findings:\n'
        '  - {rule_id: AR-VAL-001, bp_key: "C:1", defect: DEF-0001}\n'
        '  - {rule_id: AR-VAL-001, bp_key: "C:1", defect: DEF-0002}\n',
        encoding="utf-8",
    )
    with pytest.raises(RegressionError) as exc:
        load_expected(path)
    assert "finding_key-Spalte" in str(exc.value)


def test_unreadable_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(RegressionError) as exc:
        load_expected(tmp_path / "fehlt.yaml")
    assert "nicht als UTF-8 lesbar" in str(exc.value)


def test_actual_from_findings_reads_entity_and_key() -> None:
    rows = [
        (
            {"rule_id": "AR-CON-002", "entity": {"bp_key": "C:1", "company_code": "1000"}},
            None,
        ),
        ({"rule_id": "AP-LEA-001", "entity": {"bp_key": "V:1"}}, "4711|4712"),
    ]
    actual = actual_from_findings(rows)
    assert actual[0].match_key == ("AR-CON-002", "C:1", "1000", None)
    assert actual[1].match_key == ("AP-LEA-001", "V:1", None, "4711|4712")


# --- Der Lauf selbst -----------------------------------------------------------------


def test_run_schreibt_ein_laufverzeichnis(tmp_path) -> None:
    """Der frueher hier stehende Stolperdraht: `mdq run` ist gebaut (Sprint 3, Aufgabe 4).

    Er hat seinen Zweck erfuellt – der `skip` darunter ist damit angefasst und nennt
    jetzt Aufgabe 5 als Termin, nicht mehr "ab Sprint 3".
    """
    result = runner.invoke(
        app,
        ["run", "--input", str(DEMO_MANDANT_DIR), "--out", str(tmp_path / "runs"),
         "--created-at", "2026-08-31T08:00:00Z"],
    )
    assert result.exit_code == 0, result.output
    laufe = list((tmp_path / "runs").iterdir())
    assert len(laufe) == 1
    assert sorted(p.name for p in laufe[0].iterdir()) == [
        "findings.json", "report.txt", "run.json",
    ]


# --- Die scharfe Regression ----------------------------------------------------------

#: Regeln, die `expected_findings.yaml` erwartet und die es als Datei noch nicht gibt.
#: Diese Menge ist eine Erklaerung, keine Erwartung: sie sagt, welche Regeln gebaut sind
#: – nicht, ob sie das Richtige finden (das pruefen die drei Fehlertoepfe). Ein
#: Regelpaket aus Aufgabe 6-8 entfernt seine IDs hier im selben Commit; am Ende von
#: Sprint 3 muss genau {AR-DUP-001, AP-DUP-001} uebrig sein (D-100). Verschwindet eine
#: Regeldatei versehentlich, faellt der Test rot aus statt still durchzugehen.
NOT_YET_BUILT = {
    "AP-COM-003",
    "AP-CON-001",
    "AP-DUP-001",
    "AP-HYG-001",
    "AP-LEA-002",
    "AP-VAL-001",
    "AP-VAL-002",
    "AP-VAL-003",
    "AR-COM-002",
    "AR-DUP-001",
    "AR-HYG-001",
    "AR-LEA-001",
    "AR-VAL-002",
    "AR-VAL-003",
    "AR-VAL-005",
    "CROSS-DUP-001",
}

#: Die zwei Doppelzahlungspaare ueber Kreditoren-Dubletten hinweg: erst ab AP-LEA-001 1.1
#: Pflicht, bis dahin bekannt-offen (D-054).
KNOWN_OPEN = {
    ("AP-LEA-001", "V:0000200001", "1000", "1900003015|1900003016"),
    ("AP-LEA-001", "V:0000200003", "1000", "1900004459|1900003017"),
}


@pytest.fixture(scope="module")
def regression_run(tmp_path_factory):
    """Ein Lauf auf dem eingecheckten Demo-Mandanten – die Eingabe aus SPRINT-3.md.

    Bewusst `testdata/demo_mandant` und nicht die neu erzeugte Fixture: die Regeln sehen
    im Repo genau diese Dateien. Dass sie dem Generator entsprechen, haelt
    `test_demo_output.test_repo_copy_matches_the_generator` fest.
    """
    return execute_run(
        RunOptions(
            input_dir=DEMO_MANDANT_DIR,
            out_dir=tmp_path_factory.mktemp("regression"),
            created_at="2026-08-31T08:00:00Z",
        )
    )


@pytest.fixture(scope="module")
def comparison(regression_run):
    """Erwartung und Lauf, verglichen ueber `regression.py`."""
    return compare(
        load_expected(),
        actual_from_findings(regression_run.finding_rows),
        {rule.id: rule.version for rule in load_rules(RULES_DIR)},
    )


def test_demo_mandant_regression(comparison) -> None:
    """Der Demo-Mandant liefert exakt `expected_findings.yaml` – nicht mehr, nicht weniger.

    Exporte laden, auf das kanonische Schema mappen, alle Regeln ausfuehren,
    `actual_from_findings` darauf, dann `compare`. Faellt der Vergleich durch, ist die
    Meldung `Comparison.render()` – und die Erwartung wird nicht angepasst (Regel 1).
    """
    assert comparison.ok, "\n" + comparison.render()


def test_lauf_ist_sauber(regression_run) -> None:
    """Ein Lauf mit Rejects oder uebersprungenen Regeln vergliche nicht das Ganze."""
    assert regression_run.exit_code == EXIT_CLEAN
    assert list(regression_run.report.rejects) == []


def test_gebaute_regeln_liefern_ihre_erwarteten_findings(regression_run) -> None:
    """Dieselbe Aussage wie `ok`, nur als Zahl je Regel – die Handprobe aus Aufgabe 4."""
    geliefert: dict[str, int] = {}
    for finding in regression_run.findings:
        geliefert[finding["rule_id"]] = geliefert.get(finding["rule_id"], 0) + 1
    assert geliefert == {"AR-VAL-001": 15, "AR-CON-002": 7, "AP-LEA-001": 8}


def test_bekannt_offen_sind_genau_die_zwei_paare(comparison) -> None:
    """Die beiden Faelle aus D-054 – nicht mehr, und keiner davon still verschwunden."""
    assert {item.match_key for item in comparison.known_open} == KNOWN_OPEN
    assert all(item.from_rule_version == "1.1" for item in comparison.known_open)


def test_nichts_wird_vorzeitig_erfuellt(comparison) -> None:
    """Ein v1.1-Finding, das 1.0 schon liefert, hiesse: `from_rule_version` ist zu hoch."""
    assert comparison.early == (), "\n" + comparison.render()


def test_offene_regeln_sind_genau_die_erklaerte_menge(comparison) -> None:
    """`rule_missing` == `NOT_YET_BUILT` (D-100).

    Landet ein Regelpaket, entfernt derselbe Commit seine IDs oben; am Sprintende bleibt
    genau {AR-DUP-001, AP-DUP-001} uebrig. Faellt eine Regeldatei weg, wird es hier rot.
    """
    assert {item.rule_id for item in comparison.rule_missing} == NOT_YET_BUILT
