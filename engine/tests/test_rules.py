"""Regel-Loader: Kopf parsen, Pflichtfelder und Invarianten pruefen."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from mdq import RULES_DIR
from mdq.cli import EXIT_INVALID, EXIT_NO_INPUT, app
from mdq.rules import RuleError, iter_rule_files, load_rule_file, load_rules, parse_rule

runner = CliRunner()

TEMPLATE = RULES_DIR / "_TEMPLATE.rule.sql"


def _write(tmp_path: Path, text: str, name: str = "AR-VAL-009.rule.sql") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- Die echten Regeln des Repos -----------------------------------------------------


def test_repo_rules_load() -> None:
    """Jede Regeldatei laedt, und die Reihenfolge ist die des Verzeichnisses (Regel 9).

    Bewusst keine Aufzaehlung der IDs: welche Regeln gebaut sind, sagt der Katalog
    (`test_catalog.py`) und die Regression (`NOT_YET_BUILT`) – eine dritte Liste liefe
    auseinander.
    """
    rules = load_rules()
    assert rules, "das Repo hat Regeln"
    assert [rule.id for rule in rules] == sorted(
        path.name.removesuffix(".rule.sql") for path in iter_rule_files()
    )


def test_template_is_skipped() -> None:
    assert TEMPLATE.exists()
    assert TEMPLATE not in iter_rule_files()


def test_template_alone_would_be_rejected() -> None:
    """Das Template wird uebersprungen, nicht milder geprueft."""
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(TEMPLATE)
    assert "id" in str(excinfo.value)


@pytest.mark.parametrize("rule", load_rules(), ids=lambda r: r.id)
def test_required_tables_exist_in_canonical_schema(rule, canonical_db) -> None:
    """Tippfehler in requires_tables fallen jetzt auf, nicht erst in Sprint 3."""
    rows = canonical_db.execute("SELECT table_name FROM duckdb_tables()").fetchall()
    known = {row[0] for row in rows}
    assert set(rule.requires_tables) <= known


@pytest.mark.parametrize("rule", load_rules(), ids=lambda r: r.id)
def test_plain_logic_is_maintained(rule) -> None:
    """Regel 10: Klartext muss gepflegt sein. Die inhaltliche Deckung mit dem SQL
    bleibt eine fachliche Pruefung – Code kann nur die Pflege erzwingen."""
    assert len(rule.plain_logic) > 40


@pytest.mark.parametrize("rule", load_rules(), ids=lambda r: r.id)
def test_damage_class_1_is_never_tier_a(rule) -> None:
    if rule.damage_class == 1:
        assert rule.default_tier != "A"
        assert rule.remediation.get("mass_change_eligible") is False


def test_loading_is_deterministic() -> None:
    assert [r.id for r in load_rules()] == [r.id for r in load_rules()]


# --- Gueltiger Kopf ------------------------------------------------------------------


def test_valid_rule_parses(tmp_path, valid_rule_text) -> None:
    rule = load_rule_file(_write(tmp_path, valid_rule_text))
    assert rule.id == "AR-VAL-009"
    assert rule.requires_tables == ("business_partner",)
    assert rule.tests["hits"] == ("C:0000000001",)
    assert rule.sql.startswith("SELECT")
    assert rule.tests["edge"] == ()


def test_empty_edge_stays_allowed(tmp_path, valid_rule_text) -> None:
    """Nicht jede Regel hat einen Grenzfall; ein erfundener waere schlechter (D-066)."""
    rule = load_rule_file(_write(tmp_path, valid_rule_text))
    assert rule.tests["edge"] == ()


@pytest.mark.parametrize(
    ("key", "filled"),
    [("hits", '  hits: ["C:0000000001"]'), ("no_hits", '  no_hits: ["C:0000000002"]')],
)
def test_empty_test_cases_are_rejected(tmp_path, valid_rule_text, key, filled) -> None:
    """D-021: seit der Demo-Mandant steht, ist eine leere Testliste ein Fehler."""
    assert filled in valid_rule_text
    text = valid_rule_text.replace(filled, f"  {key}: []")
    with pytest.raises(RuleError) as exc:
        load_rule_file(_write(tmp_path, text))
    message = str(exc.value)
    assert f"tests.{key}: leer" in message
    assert "defects.yaml" in message


# --- Fehlerhafte Koepfe --------------------------------------------------------------


def test_missing_plain_logic_is_reported(tmp_path, valid_rule_text) -> None:
    """Der in SPRINT-1.md geforderte Fall."""
    text = valid_rule_text.replace(
        "plain_logic: >\n  Trifft nie – Testregel fuer den Loader.\n", ""
    )
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(_write(tmp_path, text))
    assert "plain_logic" in str(excinfo.value)


def test_missing_title_is_reported(tmp_path, valid_rule_text) -> None:
    """`title` ist Pflicht, seit das Finding-Schema es verlangt."""
    text = valid_rule_text.replace('title: "Testregel"\n', "")
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(_write(tmp_path, text))
    assert "title" in str(excinfo.value)


def test_empty_title_is_reported(tmp_path, valid_rule_text) -> None:
    text = valid_rule_text.replace('title: "Testregel"', 'title: "   "')
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(_write(tmp_path, text))
    assert "title" in str(excinfo.value)


def test_missing_header_is_reported(tmp_path) -> None:
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(_write(tmp_path, "SELECT 1;\n"))
    assert "YAML-Kopf" in str(excinfo.value)


def test_broken_yaml_in_header_is_reported(tmp_path) -> None:
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(_write(tmp_path, "/* ---\nid: [offen\n--- */\nSELECT 1;\n"))
    assert "YAML" in str(excinfo.value)


def test_empty_sql_body_is_reported(tmp_path, valid_rule_text) -> None:
    text = valid_rule_text.split("--- */")[0] + "--- */\n\n"
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(_write(tmp_path, text))
    assert "SQL-Rumpf" in str(excinfo.value)


def test_unknown_header_field_is_reported(tmp_path, valid_rule_text) -> None:
    """Regel 4: nichts wird stumm geschluckt."""
    text = valid_rule_text.replace("side: AR", "side: AR\nerfundenes_feld: 1")
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(_write(tmp_path, text))
    assert "erfundenes_feld" in str(excinfo.value)


def test_id_must_match_filename(tmp_path, valid_rule_text) -> None:
    path = _write(tmp_path, valid_rule_text, name="AR-VAL-777.rule.sql")
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(path)
    assert "Dateinamen" in str(excinfo.value)


def test_category_must_match_id(tmp_path, valid_rule_text) -> None:
    text = valid_rule_text.replace("category: validity", "category: hygiene")
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(_write(tmp_path, text))
    assert "category" in str(excinfo.value)


def test_side_must_match_id(tmp_path, valid_rule_text) -> None:
    text = valid_rule_text.replace("side: AR", "side: AP")
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(_write(tmp_path, text))
    assert "side" in str(excinfo.value)


def test_bad_version_is_reported(tmp_path, valid_rule_text) -> None:
    text = valid_rule_text.replace('version: "1.0"', "version: eins")
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(_write(tmp_path, text))
    assert "version" in str(excinfo.value)


def test_unknown_enum_value_is_reported(tmp_path, valid_rule_text) -> None:
    text = valid_rule_text.replace("severity: medium", "severity: sehr hoch")
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(_write(tmp_path, text))
    assert "severity" in str(excinfo.value)


def test_all_problems_are_reported_together(tmp_path, valid_rule_text) -> None:
    text = valid_rule_text.replace("severity: medium", "severity: sehr hoch").replace(
        'version: "1.0"', "version: eins"
    )
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(_write(tmp_path, text))
    message = str(excinfo.value)
    assert "severity" in message and "version" in message


# --- Invarianten ---------------------------------------------------------------------


def test_damage_class_1_must_not_default_to_tier_a(tmp_path, valid_rule_text) -> None:
    text = valid_rule_text.replace("damage_class: 3", "damage_class: 1").replace(
        "default_tier: B", "default_tier: A"
    )
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(_write(tmp_path, text))
    assert "Schadensklasse 1" in str(excinfo.value)


def test_damage_class_1_must_not_be_mass_change_eligible(tmp_path, valid_rule_text) -> None:
    text = valid_rule_text.replace("damage_class: 3", "damage_class: 1").replace(
        "mass_change_eligible: false", "mass_change_eligible: true"
    )
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(_write(tmp_path, text))
    assert "mass_change_eligible" in str(excinfo.value)


def test_mass_change_requires_tier_a(tmp_path, valid_rule_text) -> None:
    text = valid_rule_text.replace("default_action_type: review", "default_action_type: mass_change")
    with pytest.raises(RuleError) as excinfo:
        load_rule_file(_write(tmp_path, text))
    assert "mass_change" in str(excinfo.value)


def test_tier_a_with_mass_change_is_allowed(tmp_path, valid_rule_text) -> None:
    text = (
        valid_rule_text.replace("default_action_type: review", "default_action_type: mass_change")
        .replace("default_tier: B", "default_tier: A")
        .replace("mass_change_eligible: false", "mass_change_eligible: true")
    )
    assert load_rule_file(_write(tmp_path, text)).default_tier == "A"


# --- Verzeichnisse und CLI -----------------------------------------------------------


def test_missing_directory_is_reported(tmp_path) -> None:
    with pytest.raises(RuleError):
        load_rules(tmp_path / "gibtsnicht")


def test_parse_rule_takes_path_for_messages(tmp_path, valid_rule_text) -> None:
    path = tmp_path / "AR-VAL-009.rule.sql"
    assert parse_rule(valid_rule_text, path).path == path


def test_cli_rules_list() -> None:
    result = runner.invoke(app, ["rules", "list"])
    assert result.exit_code == 0
    rules = load_rules()
    for rule in rules:
        assert rule.id in result.stdout
    assert f"{len(rules)} Regeln" in result.stdout


def test_cli_rules_list_reports_broken_rule(tmp_path, valid_rule_text) -> None:
    _write(tmp_path, valid_rule_text.replace("severity: medium", "severity: sehr hoch"))
    result = runner.invoke(app, ["rules", "list", "--dir", str(tmp_path)])
    assert result.exit_code == EXIT_INVALID
    assert "AR-VAL-009.rule.sql" in result.output


def test_cli_rules_list_empty_directory(tmp_path) -> None:
    result = runner.invoke(app, ["rules", "list", "--dir", str(tmp_path)])
    assert result.exit_code == EXIT_NO_INPUT
