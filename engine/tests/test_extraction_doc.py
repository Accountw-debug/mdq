"""Die Extraktionsanleitung und das Mapping dürfen nicht auseinanderlaufen.

`docs/extraction/SAP-ECC-EXTRACTION.md` ist das, was der Kunde in die Hand bekommt;
`logic/mappings/sap_ecc.yaml` ist das, was die Engine liest. Weichen sie ab, merkt es
niemand im Repo, sondern der SAP-Key-User beim Kunden – und zwar auf die unangenehme
Art (SPRINT-3.md, Aufgabe 9):

* **Ein Feld im Mapping, das die Anleitung nicht nennt**, fehlt im Export. Der Lauf
  meldet es mit Namen, aber der Termin ist vorbei und der Export muss wiederholt werden.
* **Ein Feld in der Anleitung, das das Mapping nicht kennt**, ist eine unbekannte Spalte
  und bricht den Lauf ab (Regel 4) – die Anleitung hätte den Fehler selbst verursacht.

Geprüft werden beide Richtungen. Die Anleitung führt dafür je Tabelle **eine** Zeile mit
dem blanken Tabellennamen in der ersten Spalte und der Feldliste in der dritten; steht
eine Tabelle als Querverweis („wie oben"), ist sie hier nicht prüfbar und fällt auf.
"""

import re

import pytest
import yaml

from mdq import PROJECT_ROOT, SAP_MAPPING
from mdq.mapping import load_mapping

DOC = PROJECT_ROOT / "docs" / "extraction" / "SAP-ECC-EXTRACTION.md"

#: Eine Tabellenzeile der Anleitung: | NAME | Inhalt | Felder | ggf. Filter |
_ROW = re.compile(r"^\|\s*([A-Z][A-Z0-9_]{2,})\s*\|([^|]*)\|([^|]*)\|")

#: Ein technischer SAP-Feldname
_FIELD = re.compile(r"[A-Z][A-Z0-9_]{2,}")


def doc_fields() -> dict[str, set[str]]:
    """Tabelle -> Feldnamen, wie die Anleitung sie nennt."""
    found: dict[str, set[str]] = {}
    for line in DOC.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if not match:
            continue
        table, _, fields = match.groups()
        found.setdefault(table, set()).update(_FIELD.findall(fields))
    return found


def mapping_fields() -> dict[str, tuple[set[str], set[str]]]:
    """Tabelle -> (gebrauchte Felder, zusätzlich erlaubte Namen).

    Gebraucht ist, was das Mapping abbildet (``fields``) oder für später vormerkt
    (``fields_of_interest``). Erlaubt ist zusätzlich, was unter ``ignore`` steht: eine
    solche Spalte darf im Export stehen, ohne den Lauf abzubrechen.

    Die abgebildeten Felder kommen aus dem **geprüften** Mapping; ``fields_of_interest``
    liest der Parser bewusst nicht (die Tabellen stehen auf ``status: later`` und werden
    nicht gestagt), deshalb kommt allein dieser Teil aus der YAML-Datei.
    """
    parsed = load_mapping().tables
    raw = yaml.safe_load(SAP_MAPPING.read_text(encoding="utf-8"))["tables"]

    result = {}
    for table, spec in raw.items():
        later = set(spec.get("fields_of_interest") or ())
        entry = parsed.get(table)
        needed = (set(entry.fields) if entry else set()) | later
        allowed = set(entry.ignore) if entry else set(spec.get("ignore") or ())
        result[table] = (needed, allowed)
    return result


MAPPED = mapping_fields()
DOCUMENTED = doc_fields()


@pytest.mark.parametrize("table", sorted(MAPPED))
def test_the_guide_lists_every_field_the_mapping_uses(table: str) -> None:
    """Jedes Feld des Mappings steht in der Zeile seiner Tabelle.

    Fehlt eines, liefert der Kunde einen unvollständigen Export – und merkt es erst,
    wenn der Lauf die Spalte mit Namen einfordert.
    """
    needed, _ = MAPPED[table]
    if not needed:
        pytest.skip(f"{table}: im Mapping ohne Feldliste")
    assert table in DOCUMENTED, (
        f"{table} hat in der Extraktionsanleitung keine eigene Zeile – ein Querverweis "
        "reicht nicht, die Feldliste muss dastehen."
    )
    missing = sorted(needed - DOCUMENTED[table])
    assert not missing, f"{table}: in der Anleitung fehlen {missing}"


@pytest.mark.parametrize("table", sorted(set(MAPPED) & set(DOCUMENTED)))
def test_the_guide_asks_for_nothing_the_mapping_rejects(table: str) -> None:
    """Kein Feld in der Anleitung, das das Mapping weder abbildet noch ignoriert.

    Eine unbekannte Spalte bricht den Lauf ab (Regel 4). Eine Anleitung, die sie
    anfordert, hätte den Abbruch selbst verschuldet.
    """
    needed, allowed = MAPPED[table]
    unknown = sorted(DOCUMENTED[table] - needed - allowed)
    assert not unknown, (
        f"{table}: die Anleitung nennt {unknown} – im Mapping unter fields aufnehmen "
        "oder unter ignore eintragen, sonst bricht der Lauf beim Kunden ab."
    )


def test_every_staged_table_appears_in_the_guide() -> None:
    """Keine Tabelle, die der Lauf lädt, fehlt in der Anleitung.

    Der Gegentest zur Feldebene: eine neue Quelltabelle im Mapping würde sonst
    stillschweigend aus dem Auftrag an den Kunden herausfallen.
    """
    staged = {table.name for table in load_mapping().staged_tables}
    assert staged <= set(DOCUMENTED), sorted(staged - set(DOCUMENTED))
