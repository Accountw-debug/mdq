"""Woerterbuecher aus `logic/dictionaries/`: Laden, Pruefen, Einsetzen.

Die Belegarten (`document_types.yaml`) werden dort geprueft, wo sie gebraucht werden –
in `test_executor.py` beim Einsetzen ins Regel-SQL. Hier stehen die beiden Woerterbuecher,
die mit Aufgabe 6 dazugekommen sind: die Formatmuster der USt-IdNr. (D-101) und die
Platzhalterbegriffe (D-102).

Alle Werte in dieser Datei sind erfunden; „Testo SE" steht als Beispiel fuer einen realen
Firmennamen, der wie ein Platzhalter aussieht, aber keiner ist.
"""

import re

import pytest

from mdq.dictionaries import (
    DictionaryError,
    load_placeholder_terms,
    load_vat_patterns,
    parse_placeholder_terms,
    parse_vat_patterns,
)

# --- Formatmuster der USt-IdNr. (D-101) ----------------------------------------------


def test_vat_muster_laden() -> None:
    patterns = load_vat_patterns()
    assert patterns.patterns["DE"] == r"^DE\d{9}$"
    assert "DE" in patterns.eu_prefixes
    assert "CH" not in patterns.eu_prefixes   # Nicht-EU: Format ja, VIES nein


def test_norwegen_ist_ein_text_und_kein_boolean() -> None:
    """YAML liest `NO` als Boolean – der Praefix war dadurch unerreichbar (D-109)."""
    patterns = load_vat_patterns()
    assert "NO" in patterns.patterns
    assert patterns.patterns["NO"].startswith("^NO")


def test_vat_muster_als_wertepaare_sind_sortiert(tmp_path) -> None:
    """Gleiche Reihenfolge in jedem Lauf (Regel 9)."""
    patterns = parse_vat_patterns(
        {"version": "0.1", "patterns": {"DE": "^DE1$", "AT": "^AT1$"}},
        tmp_path / "vat_id_patterns.yaml",
    )
    assert patterns.rows() == "('AT', '^AT1$'), ('DE', '^DE1$')"


def test_kaputter_regex_wird_beim_laden_gemeldet(tmp_path) -> None:
    with pytest.raises(DictionaryError) as excinfo:
        parse_vat_patterns(
            {"version": "0.1", "patterns": {"DE": "^DE(\\d{9}$"}},
            tmp_path / "vat_id_patterns.yaml",
        )
    assert "Regex" in str(excinfo.value)


def test_praefix_muss_aus_zwei_grossbuchstaben_bestehen(tmp_path) -> None:
    """Genau der Fall, den D-109 gefunden hat – hier faellt er beim Laden auf."""
    with pytest.raises(DictionaryError) as excinfo:
        parse_vat_patterns(
            {"version": "0.1", "patterns": {False: "^NO1$"}},
            tmp_path / "vat_id_patterns.yaml",
        )
    assert "Praefix" in str(excinfo.value)


# --- Platzhalterbegriffe (D-102) -----------------------------------------------------


def test_platzhalterbegriffe_treffen_als_ganzes_wort() -> None:
    """„Testo SE" ist ein realer Hersteller und darf nicht als Platzhalter gelten."""
    terms = load_placeholder_terms()
    muster = re.compile(terms.pattern())

    def trifft(text: str) -> bool:
        return bool(muster.search("#" + text.lower() + "#"))

    assert trifft("Test GmbH")
    assert trifft("TEST")
    assert trifft("xxx")
    assert trifft("XXX Handel")
    assert trifft("Testkunde 2")
    assert not trifft("Testo SE")
    assert not trifft("Contest Systems GmbH")
    assert not trifft("Bologna")          # endet auf "na", nicht auf "n.a."


def test_platzhalterbegriffe_muessen_klein_geschrieben_sein(tmp_path) -> None:
    """Eine Grossschreibung taeuschte eine Bedeutung vor, die es nicht gibt."""
    with pytest.raises(DictionaryError) as excinfo:
        parse_placeholder_terms(
            {"version": "0.1", "terms": ["Test"]}, tmp_path / "placeholder_terms.yaml"
        )
    assert "Kleinbuchstaben" in str(excinfo.value)


def test_platzhalterbegriffe_ohne_terms_sind_ein_fehler(tmp_path) -> None:
    with pytest.raises(DictionaryError):
        parse_placeholder_terms({"version": "0.1"}, tmp_path / "placeholder_terms.yaml")


def test_zusammensetzungen_sind_optional(tmp_path) -> None:
    """Ein Kunde, der keine Zusammensetzungen pflegt, bekommt keinen Fehler."""
    terms = parse_placeholder_terms(
        {"version": "0.1", "terms": ["test"]}, tmp_path / "placeholder_terms.yaml"
    )
    assert terms.all_terms == ("test",)
