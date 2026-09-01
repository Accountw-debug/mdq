"""Loader für SE16N-Exporte: Encoding, Trenner, Rohtabelle, Rejects.

Die vier KNA1-Dateien in testdata/encoding_samples/ enthalten dieselben Zeilen in
verschiedenen Encodings – der Loader muss sie identisch einlesen.
"""

from pathlib import Path

import pytest

from mdq import DEMO_MANDANT_DIR, PROJECT_ROOT
from mdq.loader import (
    RAW_EXCERPT_LIMIT,
    ROW_NO_COLUMN,
    LoaderError,
    check_table_names,
    default_table_name,
    detect_delimiter,
    detect_encoding,
    load_table,
    record_reject,
    sha256_of,
)

SAMPLES = PROJECT_ROOT / "testdata" / "encoding_samples"

KNA1_FILES = [
    ("KNA1_utf8_tab.txt", "UTF-8", "Tab"),
    ("KNA1_cp1252_semicolon.txt", "CP1252", "Semikolon"),
    ("KNA1_utf16_tab.txt", "UTF-16-LE", "Tab"),
    ("KNA1_utf8bom_tab_quoted.txt", "UTF-8-BOM", "Tab"),
]

KNA1_COLUMNS = (
    "KUNNR", "LAND1", "NAME1", "NAME2", "ORT01",
    "PSTLZ", "STRAS", "STCEG", "XCPDK", "LOEVM", "ERDAT",
)


def _load(db, name: str, table: str = "KNA1"):
    return load_table(db, SAMPLES / name, table=table)


def _rows(db, table: str = "raw_KNA1") -> list[tuple]:
    return db.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall()


# --- Der Spec-Fall: alle vier Dateien ergeben dieselbe Tabelle ------------------------


def test_all_encodings_yield_identical_tables(canonical_db) -> None:
    snapshots = {}
    for name, _, _ in KNA1_FILES:
        _load(canonical_db, name)
        snapshots[name] = _rows(canonical_db)
    reference = snapshots["KNA1_utf8_tab.txt"]
    assert len(reference) == 5
    for name, rows in snapshots.items():
        assert rows == reference, f"{name} weicht von der Referenz ab"


@pytest.mark.parametrize(("name", "encoding", "delimiter"), KNA1_FILES, ids=[f[0] for f in KNA1_FILES])
def test_encoding_and_delimiter_are_detected(canonical_db, name, encoding, delimiter) -> None:
    result = _load(canonical_db, name)
    assert result.encoding == encoding
    assert result.delimiter == delimiter
    assert result.rows == 5
    assert result.columns == KNA1_COLUMNS


@pytest.mark.parametrize("name", [f[0] for f in KNA1_FILES])
def test_umlauts_survive(canonical_db, name) -> None:
    _load(canonical_db, name)
    names = {row[0] for row in canonical_db.execute('SELECT NAME1 FROM "raw_KNA1"').fetchall()}
    assert "Müller Maschinenbau GmbH" in names
    assert "Österreichische Prüf GmbH" in names
    streets = {row[0] for row in canonical_db.execute('SELECT STRAS FROM "raw_KNA1"').fetchall()}
    assert "Robert Bosch Straße 12" in streets


@pytest.mark.parametrize("name", [f[0] for f in KNA1_FILES])
def test_leading_zeros_survive(canonical_db, name) -> None:
    """Regel 2 / D-009: Schlüssel sind Text, führende Nullen bleiben erhalten."""
    _load(canonical_db, name)
    keys = {row[0] for row in canonical_db.execute('SELECT KUNNR FROM "raw_KNA1"').fetchall()}
    assert "0000100234" in keys
    assert all(key.startswith("0000") for key in keys)


@pytest.mark.parametrize("name", [f[0] for f in KNA1_FILES])
def test_empty_cells_become_null(canonical_db, name) -> None:
    """Leere Zelle -> NULL, auch wenn sie als "" quotiert ist."""
    _load(canonical_db, name)
    row = canonical_db.execute(
        'SELECT NAME2, XCPDK FROM "raw_KNA1" WHERE KUNNR = \'0000100234\''
    ).fetchone()
    assert row == (None, None)


@pytest.mark.parametrize("name", [f[0] for f in KNA1_FILES])
def test_all_columns_are_text(canonical_db, name) -> None:
    """Alle Spalten der Datei sind TEXT; nur die Zeilennummer der Engine ist eine Zahl."""
    _load(canonical_db, name)
    types = canonical_db.execute(
        "SELECT DISTINCT data_type FROM duckdb_columns() "
        f"WHERE table_name = 'raw_KNA1' AND column_name <> '{ROW_NO_COLUMN}'"
    ).fetchall()
    assert types == [("VARCHAR",)]


@pytest.mark.parametrize("name", [f[0] for f in KNA1_FILES])
def test_row_no_counts_the_data_lines(canonical_db, name) -> None:
    """``_row_no`` ist 1-basiert ohne Kopfzeile – die Grundlage jedes spaeteren Rejects."""
    result = _load(canonical_db, name)
    numbers = canonical_db.execute(
        f'SELECT "{ROW_NO_COLUMN}" FROM "raw_KNA1" ORDER BY 1'
    ).fetchall()
    assert [number for (number,) in numbers] == list(range(1, result.rows + 1))
    assert ROW_NO_COLUMN not in result.columns


# --- BSID: Formatdatei liest ebenfalls sauber ----------------------------------------


def test_bsid_sample_loads(canonical_db) -> None:
    result = load_table(canonical_db, SAMPLES / "BSID_formats.txt", table="BSID")
    assert result.rows == 4
    assert result.encoding == "UTF-8"
    assert result.delimiter == "Tab"
    amounts = [
        row[0]
        for row in canonical_db.execute('SELECT WRBTR FROM "raw_BSID" ORDER BY BELNR').fetchall()
    ]
    assert amounts == ["1.234,56", "1234.56", "1.234,56-", "8.930,00"]


# --- Warnung beim Raten ---------------------------------------------------------------


def test_cp1252_fallback_is_marked_as_warning(canonical_db) -> None:
    """Der Fallback ist die einzige geratene Annahme – Aufgabe 6 zeigt sie im Report."""
    result = _load(canonical_db, "KNA1_cp1252_semicolon.txt")
    assert len(result.warnings) == 1
    assert "CP1252" in result.warnings[0]


@pytest.mark.parametrize("name", ["KNA1_utf8_tab.txt", "KNA1_utf16_tab.txt"])
def test_recognised_encodings_warn_not(canonical_db, name) -> None:
    assert _load(canonical_db, name).warnings == ()


# --- sha256 ---------------------------------------------------------------------------


def test_sha256_is_over_original_bytes(canonical_db) -> None:
    """Der Hash belegt die Eingabedatei, nicht die UTF-8-Zwischenfassung."""
    name = "KNA1_utf16_tab.txt"
    result = _load(canonical_db, name)
    assert result.sha256 == sha256_of(SAMPLES / name)
    assert len(result.sha256) == 64


def test_sha256_differs_between_encodings(canonical_db) -> None:
    digests = {_load(canonical_db, name).sha256 for name, _, _ in KNA1_FILES}
    assert len(digests) == len(KNA1_FILES)


# --- Determinismus --------------------------------------------------------------------


def test_loading_twice_is_identical(canonical_db) -> None:
    _load(canonical_db, "KNA1_utf8_tab.txt")
    first = _rows(canonical_db)
    second_result = _load(canonical_db, "KNA1_utf8_tab.txt")
    assert _rows(canonical_db) == first
    assert second_result.rows == 5


# --- Fehlerfälle ----------------------------------------------------------------------


def test_missing_file_raises(canonical_db, tmp_path) -> None:
    with pytest.raises(LoaderError) as excinfo:
        load_table(canonical_db, tmp_path / "gibtsnicht.txt", table="KNA1")
    assert "gibtsnicht.txt" in str(excinfo.value)


def test_empty_file_raises(canonical_db, tmp_path) -> None:
    path = tmp_path / "KNA1_leer.txt"
    path.write_text("", encoding="utf-8")
    with pytest.raises(LoaderError) as excinfo:
        load_table(canonical_db, path, table="KNA1")
    assert "leer" in str(excinfo.value)


def test_missing_delimiter_raises(canonical_db, tmp_path) -> None:
    path = tmp_path / "KNA1_ohne.txt"
    path.write_text("KUNNR\n0000100234\n", encoding="utf-8")
    with pytest.raises(LoaderError) as excinfo:
        load_table(canonical_db, path, table="KNA1")
    assert "Spaltentrenner" in str(excinfo.value)


def test_duplicate_column_names_raise(canonical_db, tmp_path) -> None:
    path = tmp_path / "KNA1_dubl.txt"
    path.write_text("KUNNR\tKUNNR\nA\tB\n", encoding="utf-8")
    with pytest.raises(LoaderError) as excinfo:
        load_table(canonical_db, path, table="KNA1")
    assert "KUNNR" in str(excinfo.value)


def test_tab_wins_over_semicolon() -> None:
    assert detect_delimiter("A\tB;C", Path("x.txt")) == ("\t", "Tab")


def test_detect_encoding_prefers_bom() -> None:
    assert detect_encoding(b"\xef\xbb\xbfA\tB", Path("x.txt"))[0] == "UTF-8-BOM"
    assert detect_encoding(b"\xff\xfeA\x00", Path("x.txt"))[0] == "UTF-16-LE"


def test_detect_encoding_falls_back_to_cp1252() -> None:
    label, codec, warnings = detect_encoding(b"M\xfcller", Path("x.txt"))
    assert (label, codec) == ("CP1252", "cp1252")
    assert warnings


def test_default_table_name() -> None:
    assert default_table_name(Path("KNA1_utf8_tab.txt")) == "KNA1"
    assert default_table_name(Path("BSID.txt")) == "BSID"


# --- Kollidierende Tabellennamen -------------------------------------------------------


def test_colliding_table_names_are_refused() -> None:
    """Trifft: zwei Dateien, ein Tabellenname – die zweite wuerde die erste ueberschreiben."""
    with pytest.raises(LoaderError) as excinfo:
        check_table_names([Path("in/KNA1.txt"), Path("in/KNA1_alt.txt")])
    message = str(excinfo.value)
    assert "KNA1" in message
    assert "KNA1.txt" in message and "KNA1_alt.txt" in message
    # Die Meldung nennt den Ausweg, nicht nur das Problem.
    assert "zusammenführen" in message


def test_colliding_table_names_report_every_pair() -> None:
    """Alle Kollisionen gemeinsam – eine Datei soll in einem Durchgang zu klaeren sein."""
    with pytest.raises(LoaderError) as excinfo:
        check_table_names(
            [
                Path("in/KNA1.txt"),
                Path("in/KNA1_alt.txt"),
                Path("in/BSID.txt"),
                Path("in/BSID_2024.txt"),
            ]
        )
    message = str(excinfo.value)
    assert "KNA1_alt.txt" in message and "BSID_2024.txt" in message


def test_collision_message_lists_every_file_of_the_group() -> None:
    """Bei mehr als zwei Dateien zaehlt die Meldung auf, sortiert – nicht nur die ersten.

    Der Fall aus dem eigenen Repo: vier KNA1-Fassungen in `testdata/encoding_samples/`.
    Wer nur zwei Namen liest, sucht die uebrigen von Hand.
    """
    namen = [
        "KNA1_utf8bom_tab_quoted.txt",
        "KNA1_cp1252_semicolon.txt",
        "KNA1_utf16_tab.txt",
        "KNA1_utf8_tab.txt",
    ]
    with pytest.raises(LoaderError) as excinfo:
        check_table_names([Path("in") / name for name in namen])
    message = str(excinfo.value)
    stelle = -1
    for name in sorted(namen):
        gefunden = message.find(name)
        assert gefunden > stelle, f"{name} fehlt oder steht unsortiert: {message}"
        stelle = gefunden


def test_the_demo_client_has_no_colliding_names() -> None:
    """Gegenprobe: die 16 Dateien des ausgelieferten Mandanten fallen auf 16 Namen."""
    files = sorted(DEMO_MANDANT_DIR.glob("*.txt"))
    assert len(files) == 16
    check_table_names(files)  # keine Ausnahme


def test_distinct_table_names_pass() -> None:
    check_table_names([Path("in/KNA1.txt"), Path("in/KNB1.txt")])


# --- Rejects --------------------------------------------------------------------------


def test_record_reject_writes_row(canonical_db) -> None:
    record_reject(canonical_db, "run-1", "staged", "BSID", 7, "Betrag nicht parsebar", "roh")
    row = canonical_db.execute(
        "SELECT run_id, stage, source_table, row_no, reason, raw_excerpt FROM reject"
    ).fetchone()
    assert row == ("run-1", "staged", "BSID", 7, "Betrag nicht parsebar", "roh")


def test_record_reject_truncates_excerpt(canonical_db) -> None:
    record_reject(canonical_db, "run-1", "raw", "BSID", 1, "zu lang", "x" * 500)
    excerpt = canonical_db.execute("SELECT raw_excerpt FROM reject").fetchone()[0]
    assert len(excerpt) == RAW_EXCERPT_LIMIT


def test_record_reject_accepts_no_excerpt(canonical_db) -> None:
    record_reject(canonical_db, "run-1", "raw", "BSID", None, "ohne Auszug")
    assert canonical_db.execute("SELECT raw_excerpt FROM reject").fetchone()[0] is None


# --- Regel 8 --------------------------------------------------------------------------


def test_error_messages_contain_no_cell_values(canonical_db, tmp_path) -> None:
    """Meldungen nennen Datei- und Spaltennamen, nie Zellinhalte."""
    secret = "Mustermann Handels GmbH"
    path = tmp_path / "KNA1_kaputt.txt"
    path.write_text(f"KUNNR\tKUNNR\n0000100234\t{secret}\n", encoding="utf-8")
    with pytest.raises(LoaderError) as excinfo:
        load_table(canonical_db, path, table="KNA1")
    assert secret not in str(excinfo.value)
