"""Mapping SAP ECC -> kanonisch: Vollstaendigkeit, Typklassen, Spaltenabgleich.

Der wichtigste Test steht am Ende: jede Typklasse muss zum Spaltentyp des kanonischen
Schemas passen. Die Klassen stehen in `logic/mappings/sap_ecc.yaml`, die Typen in
`logic/schema/canonical.sql` – zwei Orte, aber keine zwei Wahrheiten.
"""

import copy

import pytest
import yaml

from mdq import SAP_MAPPING
from mdq.mapping import (
    COLUMN_TYPE,
    TYPE_CLASSES,
    MappingError,
    check_export_columns,
    load_mapping,
    parse_mapping,
)


@pytest.fixture(scope="module")
def mapping():
    """Das ausgelieferte Mapping."""
    return load_mapping()


@pytest.fixture
def document() -> dict:
    """Das Mapping als rohes Dokument – Basis fuer Mutationen."""
    return yaml.safe_load(SAP_MAPPING.read_text(encoding="utf-8"))


def _error(document) -> str:
    with pytest.raises(MappingError) as excinfo:
        parse_mapping(document, SAP_MAPPING)
    return str(excinfo.value)


# --- Das ausgelieferte Mapping laedt ---------------------------------------------------


def test_mapping_loads(mapping) -> None:
    assert mapping.version
    assert "KNA1" in mapping.tables
    assert mapping.table("kna1").name == "KNA1"


def test_tables_marked_later_are_not_staged(mapping) -> None:
    """KNVV, CDHDR und CDPOS sind angemeldet, aber noch nicht Teil der Pipeline."""
    staged = {table.name for table in mapping.staged_tables}
    assert {"KNVV", "CDHDR", "CDPOS"}.isdisjoint(staged)
    assert {"KNA1", "BSID", "BSAD", "BSIK", "BSAK", "TIBAN"} <= staged


def test_merge_keys_give_open_and_cleared_the_same_fields(mapping) -> None:
    """BSAD erbt die Felder von BSID und unterscheidet sich nur in `is_open`."""
    assert list(mapping.table("BSAD").fields) == list(mapping.table("BSID").fields)
    assert mapping.table("BSID").is_open is True
    assert mapping.table("BSAD").is_open is False


def test_unknown_table_is_named(mapping) -> None:
    with pytest.raises(MappingError, match="BKPF"):
        mapping.table("BKPF")


# --- Typklassen ------------------------------------------------------------------------


def test_every_mapped_field_has_a_type(mapping) -> None:
    for table in mapping.tables.values():
        for field in table.fields:
            assert mapping.type_of(field) in TYPE_CLASSES, f"{table.name}.{field}"


def test_amounts_and_dates_are_classified(mapping) -> None:
    """Die Felder, an denen Regel 2 haengt: Betrag, Prozent, Datum, Kennzeichen."""
    assert mapping.type_of("DMBTR") == "amount"
    assert mapping.type_of("WRBTR") == "amount"
    assert mapping.type_of("ZBD1P") == "percent"
    assert mapping.type_of("BUDAT") == "date"
    assert mapping.type_of("ZBD1T") == "integer"
    assert mapping.type_of("LOEVM") == "flag"
    # Schluessel bleiben Text, sonst gehen fuehrende Nullen verloren (Regel 2, D-009)
    for key in ("KUNNR", "LIFNR", "BELNR", "BUKRS", "BUZEI", "GJAHR"):
        assert mapping.type_of(key) == "text", key


def test_missing_type_is_an_error(document) -> None:
    document["field_types"]["date"].remove("BUDAT")
    assert "BUDAT" in _error(document)


def test_type_in_two_classes_is_an_error(document) -> None:
    document["field_types"]["text"].append("BUDAT")
    assert "mehr als einer Typklasse" in _error(document)


def test_type_without_mapped_field_is_an_error(document) -> None:
    document["field_types"]["text"].append("ZZFANTASIE")
    assert "ZZFANTASIE" in _error(document)


def test_unknown_type_class_is_an_error(document) -> None:
    document["field_types"]["waehrung"] = ["WAERS"]
    assert "unbekannte Typklassen" in _error(document)


# --- Struktur ---------------------------------------------------------------------------


def test_field_both_mapped_and_ignored_is_an_error(document) -> None:
    document["tables"]["KNA1"]["ignore"].append("NAME1")
    message = _error(document)
    assert "NAME1" in message and "fields und ignore" in message


def test_unknown_table_key_is_an_error(document) -> None:
    document["tables"]["KNA1"]["zielsystem"] = "S4"
    assert "unbekannte Schluessel" in _error(document)


def test_missing_section_is_an_error(document) -> None:
    del document["field_types"]
    assert "field_types" in _error(document)


def test_all_problems_are_reported_together(document) -> None:
    """Sammelmeldung wie beim Regelloader: ein Durchgang, nicht Fehler fuer Fehler."""
    document["tables"]["KNA1"]["ignore"].append("NAME1")
    document["tables"]["LFA1"]["zielsystem"] = "S4"
    message = _error(document)
    assert "NAME1" in message and "zielsystem" in message


def test_key_must_be_mapped(document) -> None:
    document["tables"]["KNB5"]["key"] = ["KUNNR", "ZZWUNSCH"]
    assert "ZZWUNSCH" in _error(document)


def test_detect_needs_a_described_table(document) -> None:
    document["detect"]["BKPF"] = ["BELNR"]
    assert "BKPF" in _error(document)


# --- Abgleich mit der Kopfzeile eines Exports -------------------------------------------


def test_known_columns_pass(mapping) -> None:
    table = mapping.table("KNB5")
    columns = list(table.fields) + list(table.ignore)
    assert check_export_columns(table, columns) == []


def test_unknown_column_is_named(mapping) -> None:
    """Regel 4: eine unbekannte Spalte wird mit Namen gemeldet, nicht uebergangen."""
    table = mapping.table("KNB5")
    errors = check_export_columns(table, [*table.fields, *table.ignore, "ZZBONUS"])
    assert len(errors) == 1
    assert "ZZBONUS" in errors[0]


def test_missing_column_is_reported_separately(mapping) -> None:
    """Fehlende Spalte und unbekannte Spalte haben verschiedene Ursachen."""
    table = mapping.table("KNB5")
    columns = [name for name in table.fields if name != "MAHNS"]
    errors = check_export_columns(table, [*columns, "ZZBONUS"])
    assert len(errors) == 2
    assert "ZZBONUS" in errors[0]
    assert "MAHNS" in errors[1]


def test_demo_client_columns_match_the_mapping(mapping, demo_client) -> None:
    """Der ausgelieferte Demo-Mandant passt Spalte fuer Spalte zum Mapping."""
    path, manifest = demo_client
    for entry in manifest["tables"]:
        table = mapping.table(entry["table"])
        header = (path / entry["file"]).read_text(encoding="utf-8").splitlines()[0]
        assert check_export_columns(table, header.split("\t")) == [], entry["table"]


# --- Die Bruecke zum kanonischen Schema -------------------------------------------------


def _canonical_types(con) -> dict[tuple[str, str], str]:
    rows = con.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns"
    ).fetchall()
    return {(table, column): data_type for table, column, data_type in rows}


def _canonical_target(table, canonical_field: str) -> tuple[str, str]:
    """Kanonische Spalte eines gemappten Feldes.

    `tax_id.VAT` und Geschwister werden keine Spalte, sondern eine Zeile in `bp_tax_id`
    (Aufgabe 2); geprueft wird deshalb deren Wertspalte.
    """
    if canonical_field.startswith("tax_id."):
        return "bp_tax_id", "value"
    return (table.target or "").split(".")[0], canonical_field


def test_type_classes_match_the_canonical_schema(mapping, canonical_db) -> None:
    """Wo ein Feld eine kanonische Spalte hat, muss die Typklasse zu deren Typ passen."""
    types = _canonical_types(canonical_db)
    geprueft = 0
    for table in mapping.staged_tables:
        for source_field, canonical_field in table.fields.items():
            key = _canonical_target(table, canonical_field)
            if key not in types:
                continue
            expected = COLUMN_TYPE[mapping.type_of(source_field)]
            actual = types[key]
            assert actual == expected or (expected == "TEXT" and actual == "VARCHAR"), (
                f"{table.name}.{source_field} -> {key[0]}.{key[1]}: "
                f"Klasse {mapping.type_of(source_field)} erwartet {expected}, "
                f"Schema hat {actual}"
            )
            geprueft += 1
    assert geprueft > 100, "die Bruecke prueft zu wenige Felder, um etwas zu sichern"


def test_fields_without_a_canonical_column_are_known(mapping, canonical_db) -> None:
    """Die Ausnahmen stehen namentlich hier – eine neue faellt auf, statt durchzurutschen."""
    types = _canonical_types(canonical_db)
    ohne_spalte = {
        f"{table.name}.{source_field}"
        for table in mapping.staged_tables
        for source_field, canonical_field in table.fields.items()
        if _canonical_target(table, canonical_field) not in types
    }
    # T052U traegt die Sprache nur zur Auswahl des Textes (SPRAS DE bevorzugt); eine
    # Spalte `language` hat `payment_terms` bewusst nicht.
    assert ohne_spalte == {"T052U.SPRAS"}


def test_parse_mapping_does_not_change_the_document(document) -> None:
    """Der Loader prueft; er repariert nichts (Regel 3 im Geist: Quelle bleibt Quelle)."""
    before = copy.deepcopy(document)
    parse_mapping(document, SAP_MAPPING)
    assert document == before
