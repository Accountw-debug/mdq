"""Katalog, Regeldateien und Defektliste gegeneinander.

Drei Staende koennen auseinanderlaufen: der fachliche Katalog `logic/rules/CATALOG.md`,
die gebauten Regeln in `logic/rules/` und die Defekte in `testdata/demo_mandant/defects.yaml`.
Diese Tests halten sie zusammen (SPRINT-2.md, Aufgabe 3).

Die Bindung an `defects.yaml` steht bewusst hier und nicht im Loader: `mdq/rules.py` und
`mdq/catalog.py` sind Produktcode und duerfen `testdata/` nicht kennen.
"""

from pathlib import Path

import pytest
import yaml

from mdq import DEMO_DEFECTS, EXPECTED_FINDINGS
from mdq.catalog import CatalogError, load_catalog, parse_catalog
from mdq.rules import load_rules

CATALOG = load_catalog()
RULES = load_rules()


def _defect_rule_ids() -> set[str]:
    """Regel-IDs, fuer die `defects.yaml` mindestens ein Finding zusagt."""
    defects = yaml.safe_load(DEMO_DEFECTS.read_text(encoding="utf-8"))["defects"]
    return {
        expected["rule_id"]
        for defect in defects
        for expected in (defect.get("expected") or [])
    }


def _named_bp_keys() -> set[str]:
    """Alle bp_keys, die `defects.yaml` namentlich nennt (`bp_key` oder `bp_keys`)."""
    keys: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "bp_key" and isinstance(value, str):
                    keys.add(value)
                elif key == "bp_keys" and isinstance(value, list):
                    keys.update(entry for entry in value if isinstance(entry, str))
                else:
                    walk(value)
        elif isinstance(node, list):
            for entry in node:
                walk(entry)

    walk(yaml.safe_load(DEMO_DEFECTS.read_text(encoding="utf-8")))
    return keys


def _expected_keys_by_rule() -> dict[str, set[str]]:
    """bp_keys je Regel aus der erzeugten Erwartung."""
    findings = yaml.safe_load(EXPECTED_FINDINGS.read_text(encoding="utf-8"))["findings"]
    result: dict[str, set[str]] = {}
    for finding in findings:
        result.setdefault(finding["rule_id"], set()).add(finding["bp_key"])
    return result


DEFECT_RULE_IDS = _defect_rule_ids()
NAMED_BP_KEYS = _named_bp_keys()
EXPECTED_BY_RULE = _expected_keys_by_rule()


# --- Der Katalog selbst --------------------------------------------------------------


def test_catalog_loads() -> None:
    assert len(CATALOG) == 36
    assert [entry.rule_id for entry in CATALOG] == sorted(entry.rule_id for entry in CATALOG)


def test_catalog_ids_are_unique() -> None:
    ids = [entry.rule_id for entry in CATALOG]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("entry", CATALOG, ids=lambda e: e.rule_id)
def test_catalog_title_is_filled(entry) -> None:
    assert entry.title
    assert entry.category


# --- Katalog gegen defects.yaml ------------------------------------------------------


def test_every_defect_rule_exists_in_catalog() -> None:
    """Ein Defekt darf keine Regel zusagen, die der Katalog nicht kennt."""
    unknown = sorted(DEFECT_RULE_IDS - {entry.rule_id for entry in CATALOG})
    assert unknown == []


@pytest.mark.parametrize("entry", CATALOG, ids=lambda e: e.rule_id)
def test_testdata_column_matches_defects(entry) -> None:
    """Die Spalte `Testdaten` sagt die Wahrheit ueber `defects.yaml` (D-066)."""
    assert entry.has_defect == (entry.rule_id in DEFECT_RULE_IDS), (
        f"{entry.rule_id}: Katalog sagt '{entry.testdata}', defects.yaml sagt "
        f"{'Defekt' if entry.rule_id in DEFECT_RULE_IDS else 'kein Defekt'}"
    )


def test_counts_match_the_documented_numbers() -> None:
    """Die Zahlen in testdata/README.md und SPRINT-2.md."""
    with_defect = [entry.rule_id for entry in CATALOG if entry.has_defect]
    assert len(with_defect) == 19
    assert len(CATALOG) - len(with_defect) == 17
    assert set(with_defect) == DEFECT_RULE_IDS


# --- Katalog gegen die gebauten Regeln -----------------------------------------------


@pytest.mark.parametrize("rule", RULES, ids=lambda r: r.id)
def test_built_rule_is_in_catalog_as_impl(rule) -> None:
    entry = next((e for e in CATALOG if e.rule_id == rule.id), None)
    assert entry is not None, f"{rule.id} fehlt im Katalog"
    assert entry.status == "impl"
    assert entry.category == rule.category


def test_catalog_impl_rows_have_a_rule_file() -> None:
    built = {rule.id for rule in RULES}
    impl = {entry.rule_id for entry in CATALOG if entry.status == "impl"}
    assert impl == built


# --- Testfaelle im Regelkopf gegen die Erwartung -------------------------------------


@pytest.mark.parametrize("rule", RULES, ids=lambda r: r.id)
def test_test_cases_name_known_accounts(rule) -> None:
    """Jeder Testfall nennt ein Konto aus `defects.yaml` – keine Basis-Konten (D-066)."""
    for key in ("hits", "no_hits", "edge"):
        unknown = sorted(set(rule.tests.get(key, ())) - NAMED_BP_KEYS)
        assert unknown == [], f"{rule.id}.tests.{key}: nicht in defects.yaml genannt"


@pytest.mark.parametrize("rule", RULES, ids=lambda r: r.id)
def test_hits_are_expected_findings(rule) -> None:
    """Was treffen muss, steht in der erzeugten Erwartung."""
    expected = EXPECTED_BY_RULE.get(rule.id, set())
    missing = sorted(set(rule.tests["hits"]) - expected)
    assert missing == [], f"{rule.id}: hits ohne Eintrag in expected_findings.yaml"


@pytest.mark.parametrize("rule", RULES, ids=lambda r: r.id)
def test_no_hits_are_not_expected_findings(rule) -> None:
    """Was nicht treffen darf, steht dort nicht."""
    expected = EXPECTED_BY_RULE.get(rule.id, set())
    wrong = sorted(set(rule.tests["no_hits"]) & expected)
    assert wrong == [], f"{rule.id}: no_hits mit Eintrag in expected_findings.yaml"


@pytest.mark.parametrize("rule", RULES, ids=lambda r: r.id)
def test_hits_and_no_hits_are_disjoint(rule) -> None:
    assert not set(rule.tests["hits"]) & set(rule.tests["no_hits"])


# --- Fehlerhafte Kataloge ------------------------------------------------------------

_HEADER = (
    "| ID | Titel | Kategorie | Schwere | SK | Stufe | Aktion | Tabellen | SAP | "
    "Status | Testdaten |\n|---|---|---|---|---|---|---|---|---|---|---|\n"
)
_ROW = "| AR-VAL-009 | Titel | validity | high | 2 | B | review | t | XD02 | draft | Defekt |\n"


def test_unknown_status_is_reported() -> None:
    with pytest.raises(CatalogError) as exc:
        parse_catalog(_HEADER + _ROW.replace("| draft |", "| fertig |"))
    assert "Status 'fertig'" in str(exc.value)


def test_unknown_testdata_mark_is_reported() -> None:
    with pytest.raises(CatalogError) as exc:
        parse_catalog(_HEADER + _ROW.replace("| Defekt |", "| ja |"))
    assert "Testdaten 'ja'" in str(exc.value)


def test_bad_rule_id_is_reported() -> None:
    with pytest.raises(CatalogError) as exc:
        parse_catalog(_HEADER + _ROW.replace("AR-VAL-009", "AR-XXX-009"))
    assert "keine Regel-ID" in str(exc.value)


def test_duplicate_id_is_reported() -> None:
    with pytest.raises(CatalogError) as exc:
        parse_catalog(_HEADER + _ROW + _ROW)
    assert "steht schon in Zeile" in str(exc.value)


def test_missing_column_is_reported() -> None:
    with pytest.raises(CatalogError) as exc:
        parse_catalog(_HEADER + _ROW.replace("| XD02 ", ""))
    assert "Spalten statt 11" in str(exc.value)


def test_row_without_header_is_reported() -> None:
    with pytest.raises(CatalogError) as exc:
        parse_catalog(_ROW)
    assert "ohne vorangehende Kopfzeile" in str(exc.value)


def test_all_problems_are_reported_together() -> None:
    text = _HEADER + _ROW.replace("| draft |", "| fertig |") + _ROW.replace(
        "AR-VAL-009", "AR-XXX-009"
    )
    with pytest.raises(CatalogError) as exc:
        parse_catalog(text)
    message = str(exc.value)
    assert "Status 'fertig'" in message
    assert "keine Regel-ID" in message


def test_unreadable_file_is_reported(tmp_path: Path) -> None:
    missing = tmp_path / "CATALOG.md"
    with pytest.raises(CatalogError) as exc:
        load_catalog(missing)
    assert "nicht als UTF-8 lesbar" in str(exc.value)
