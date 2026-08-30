"""Kanonisches Mapping staged -> canonical: Praefixe, Joins, Scope, Rejects.

Die Stufe ist die erste, die dem Rest der Engine das kanonische Modell zusagt. Geprueft
wird deshalb nicht nur, dass Zeilen entstehen, sondern auch, was **nicht** entsteht und
warum: fehlende Pflichtspalte, leeres Pflichtfeld, Zeile ohne Stammsatz, doppelter
Schluessel, ausserhalb des Scopes. Jeder dieser Faelle hat einen eigenen Weg, und keiner
davon darf still sein (Regel 4).

Die Beispieldaten hier sind erfunden und tragen keine Geschaeftspartnerdaten aus
`testdata/` (Regel 8); der Ganzlauf am Ende arbeitet auf dem Demo-Mandanten.
"""

from datetime import date

import duckdb
import pytest

from mdq import CANONICAL_SCHEMA
from mdq.canonical import (
    CanonicalError,
    Scope,
    build_canonical,
    is_valid_iban,
    parse_schema,
    required_sources,
)
from mdq.loader import load_table
from mdq.mapping import load_mapping
from mdq.staging import stage_all

RUN_ID = "test-run"

#: Zwei Debitoren, einer mit abweichendem Regulierer und drei Steuer-IDs
KNA1 = """KUNNR\tLAND1\tNAME1\tORT01\tSTRAS\tSTCEG\tSTCD1\tKNRZA\tADRNR\tERDAT\tXCPDK
0000100001\tDE\tAlpha AG\tAugsburg\tHauptstr. 1\tDE123456789\t123/456/78901\t0000100002\t0000012345\t20200101\t
0000100002\tDE\tBeta GmbH\tBremen\tNebenweg 2\t\t\t\t\t20210202\tX
"""

#: Ein Kreditor
LFA1 = """LIFNR\tLAND1\tNAME1\tORT01\tSTCEG\tLNRZA\tERDAT
0000200001\tAT\tGamma KG\tWien\tATU12345678\t\t20190303
"""

KNB1 = """KUNNR\tBUKRS\tAKONT\tZTERM\tSPERR\tLOEVM
0000100001\t1000\t140000\tZB01\t\t
0000100001\t2000\t140000\tZB02\tX\t
0000100002\t1000\t140000\tZB01\t\t
"""

LFB1 = """LIFNR\tBUKRS\tAKONT\tZTERM\tREPRF
0000200001\t1000\t160000\tZB01\tX
"""

#: Zwei Posten: eine offene Rechnung, eine Zahlung im zweiten Buchungskreis
BSID = """KUNNR\tBUKRS\tGJAHR\tBELNR\tBUZEI\tBUDAT\tBLART\tSHKZG\tWAERS\tWRBTR\tDMBTR\tXBLNR
0000100001\t1000\t2026\t0100000001\t001\t20260115\tDR\tS\tEUR\t1.000,00\t1.000,00\tRE-4711
0000100001\t2000\t2026\t0100000002\t001\t20260220\tDZ\tH\tEUR\t500,00\t500,00\tre-4711
"""

BSIK = """LIFNR\tBUKRS\tGJAHR\tBELNR\tBUZEI\tBUDAT\tBLART\tSHKZG\tWAERS\tWRBTR\tDMBTR
0000200001\t1000\t2026\t0200000001\t001\t20260310\tKR\tH\tEUR\t250,00\t250,00
"""

BSAD = """KUNNR\tBUKRS\tGJAHR\tBELNR\tBUZEI\tBUDAT\tBLART\tSHKZG\tWAERS\tWRBTR\tDMBTR\tAUGBL
0000100001\t1000\t2025\t0100000900\t001\t20250601\tDR\tS\tEUR\t99,00\t99,00\t0100000901
"""

KNBK = """KUNNR\tBANKS\tBANKL\tBANKN\tBKONT\tKOINH
0000100001\tDE\t50010517\t5407324931\t\tAlpha AG
"""

TIBAN = """BANKS\tBANKL\tBANKN\tBKONT\tIBAN\tVALID_FROM
DE\t50010517\t5407324931\t\tDE44 5001 0517 5407 3249 31\t20200101
"""

T052 = """ZTERM\tZTAGG\tZTAG1\tZPRZ1
ZB01\t00\t14\t2,000
"""

T052U = """ZTERM\tSPRAS\tTEXT1
ZB01\tE\t14 days 2 % cash discount
ZB01\tD\t14 Tage 2 % Skonto
"""

ADR6 = """ADDRNUMBER\tSMTP_ADDR
0000012345\tinfo@example.invalid
"""


def build(tmp_path, files: dict[str, str], scope: Scope | None = None):
    """Legt Exporte an, laedt, stagt und baut das kanonische Modell."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (tmp_path / f"{name}.txt").write_text(content, encoding="utf-8")
    con = duckdb.connect(":memory:")
    con.execute(CANONICAL_SCHEMA.read_text(encoding="utf-8"))
    mapping = load_mapping()
    tables = [load_table(con, path).table for path in sorted(tmp_path.glob("*.txt"))]
    stage_all(con, mapping, tables, RUN_ID)
    return con, build_canonical(con, mapping, RUN_ID, scope)


def rejects(con) -> list[tuple[str, str]]:
    """Die Rejects der Stufe canonical als (Quelltabelle, Grund)."""
    return [
        (table, reason)
        for table, reason in con.execute(
            "SELECT source_table, reason FROM reject WHERE stage = 'canonical' "
            "ORDER BY source_table, row_no"
        ).fetchall()
    ]


# --- Das Schema als Quelle der Pflichtspalten ------------------------------------------


def test_schema_erkennt_pflicht_und_vorgabe():
    """NOT NULL ohne DEFAULT ist Pflicht; mit DEFAULT ist es das nicht."""
    schema = parse_schema()
    columns = {column.name: column for column in schema["business_partner"]}
    assert columns["role"].required
    assert columns["source_id"].required
    assert not columns["deletion_flag"].required  # NOT NULL, aber DEFAULT FALSE
    assert columns["deletion_flag"].default == "FALSE"
    assert not columns["name1"].required


def test_schema_erkennt_beide_formen_des_primaerschluessels():
    """Inline (`bp_key TEXT PRIMARY KEY`) und als Tabellenbedingung (`PRIMARY KEY (...)`)."""
    schema = parse_schema()
    business_partner = {column.name: column for column in schema["business_partner"]}
    company_code = {column.name: column for column in schema["bp_company_code"]}
    assert business_partner["bp_key"].required
    assert company_code["bp_key"].required and company_code["company_code"].required


def test_pflichtspalten_kommen_aus_dem_schema():
    """Was `fi_item` braucht, steht in canonical.sql – nicht in einer Liste im Code."""
    mapping = load_mapping()
    schema = parse_schema()
    needed = required_sources(mapping.table("BSID"), schema)
    # DMBTR traegt zwei Pflichtspalten: den Betrag und – ueber SHKZG – sein Vorzeichen (D-009).
    assert needed["DMBTR"] == ["amount_local", "amount_signed_local"]
    assert needed["SHKZG"] == ["amount_signed_local"]
    assert needed["WAERS"] == ["currency"]
    assert "XBLNR" not in needed  # reference ist optional
    # Nebenziele fuellen keine ganze Tabelle und haben deshalb keine Pflichtspalten.
    assert required_sources(mapping.table("TIBAN"), schema) == {}
    assert required_sources(mapping.table("T052U"), schema) == {}


def test_fehlende_pflichtspalte_bricht_ab(tmp_path):
    """Postentabelle ohne DMBTR: harter Abbruch mit Tabelle und Spalte, kein Hinweis."""
    ohne_dmbtr = "\n".join(
        line.replace("\tDMBTR", "").replace("\t1.000,00\tRE-4711", "\tRE-4711")
        for line in BSID.replace("\t500,00\t500,00\t", "\t500,00\t").splitlines()
    ) + "\n"
    with pytest.raises(CanonicalError) as excinfo:
        build(tmp_path, {"KNA1": KNA1, "BSID": ohne_dmbtr})
    message = str(excinfo.value)
    assert "BSID" in message and "DMBTR" in message
    assert "fi_item.amount_local, fi_item.amount_signed_local" in message


def test_fehlende_optionale_spalte_bricht_nicht_ab(tmp_path):
    """Ohne XBLNR entsteht `fi_item` weiter – `reference` bleibt leer."""
    con, result = build(tmp_path, {"KNA1": KNA1, "KNB1": KNB1, "BSID": _ohne_xblnr()})
    assert _rows(result, "fi_item") == 2
    assert con.execute("SELECT count(*) FROM fi_item WHERE reference IS NOT NULL").fetchone()[0] == 0


def _ohne_xblnr() -> str:
    lines = BSID.splitlines()
    header = lines[0].split("\t")
    index = header.index("XBLNR")
    kept = [
        "\t".join(value for position, value in enumerate(line.split("\t")) if position != index)
        for line in lines
    ]
    return "\n".join(kept) + "\n"


def _rows(result, table: str) -> int:
    return next(entry.rows for entry in result.tables if entry.table == table)


def _rejected(result, table: str) -> int:
    return next(entry.rejected for entry in result.tables if entry.table == table)


def _out_of_scope(result, table: str) -> int:
    return next(entry.out_of_scope for entry in result.tables if entry.table == table)


# --- Abbildung: Praefixe, Nebentabellen, Joins -----------------------------------------


def test_rollenpraefix_und_alt_payer(tmp_path):
    """`bp_key` traegt C:/V:, `alt_payer_key` ebenso – ein leerer Schluessel bleibt leer."""
    con, _ = build(tmp_path, {"KNA1": KNA1, "LFA1": LFA1})
    rows = con.execute(
        "SELECT bp_key, role, source_id, alt_payer_key FROM business_partner ORDER BY bp_key"
    ).fetchall()
    assert rows == [
        ("C:0000100001", "CUSTOMER", "0000100001", "C:0000100002"),
        ("C:0000100002", "CUSTOMER", "0000100002", None),
        ("V:0000200001", "VENDOR", "0000200001", None),
    ]


def test_kennzeichen_werden_zum_vorgabewert(tmp_path):
    """Ein nicht gesetztes Kennzeichen wird FALSE, ein "X" wird TRUE."""
    con, _ = build(tmp_path, {"KNA1": KNA1})
    rows = con.execute(
        "SELECT bp_key, is_one_time, deletion_flag, central_block FROM business_partner "
        "ORDER BY bp_key"
    ).fetchall()
    assert rows == [
        ("C:0000100001", False, False, False),
        ("C:0000100002", True, False, False),  # XCPDK = X; SPERR fehlt im Export
    ]


def test_steuer_ids_werden_zu_zeilen(tmp_path):
    """Je gefuelltem Feld eine Zeile, `value_norm` aus dem Staging, `country` bleibt leer."""
    con, result = build(tmp_path, {"KNA1": KNA1, "LFA1": LFA1})
    rows = con.execute(
        "SELECT bp_key, tax_id_type, value, value_norm, country FROM bp_tax_id "
        "ORDER BY bp_key, tax_id_type"
    ).fetchall()
    assert rows == [
        ("C:0000100001", "TAX1", "123/456/78901", "123/456/78901", None),
        ("C:0000100001", "VAT", "DE123456789", "DE123456789", None),
        ("V:0000200001", "VAT", "ATU12345678", "ATU12345678", None),
    ]
    # Beta GmbH hat kein Steuerfeld gefuellt und erzeugt deshalb keine Zeile.
    assert _rows(result, "bp_tax_id") == 3


def test_tax_id_norm_entfernt_trenner(tmp_path):
    """`value_norm` kommt aus dem Staging – Leerzeichen und Punkte sind fort (D-065-Linie)."""
    kna1 = KNA1.replace("DE123456789", "de 123.456.789")
    con, _ = build(tmp_path, {"KNA1": kna1})
    value, norm = con.execute(
        "SELECT value, value_norm FROM bp_tax_id WHERE tax_id_type = 'VAT'"
    ).fetchone()
    assert value == "de 123.456.789"
    assert norm == "DE123456789"


def test_tiban_join_liefert_iban_und_pruefziffer(tmp_path):
    """Treffer: IBAN, `iban_norm` und `iban_valid` stehen an der Bankverbindung."""
    con, _ = build(tmp_path, {"KNA1": KNA1, "KNBK": KNBK, "TIBAN": TIBAN})
    row = con.execute(
        "SELECT bp_key, iban, iban_norm, iban_valid, valid_from FROM bp_bank_account"
    ).fetchone()
    assert row == (
        "C:0000100001",
        "DE44 5001 0517 5407 3249 31",
        "DE445001051754073249 31".replace(" ", ""),
        True,
        date(2020, 1, 1),
    )


def test_ohne_tiban_treffer_bleibt_die_iban_leer(tmp_path):
    """Kein Treffer ist kein Fehler: die Bankverbindung entsteht ohne IBAN."""
    con, result = build(
        tmp_path,
        {"KNA1": KNA1, "KNBK": KNBK, "TIBAN": TIBAN.replace("50010517", "12345678")},
    )
    row = con.execute("SELECT iban, iban_norm, iban_valid FROM bp_bank_account").fetchone()
    assert row == (None, None, None)
    assert _rejected(result, "bp_bank_account") == 0


def test_juengste_iban_gewinnt(tmp_path):
    """Zwei Gueltigkeitsstaende: die juengste VALID_FROM setzt sich durch (D-078)."""
    tiban = TIBAN + "DE\t50010517\t5407324931\t\tDE02 5001 0517 5407 3249 37\t20240101\n"
    con, result = build(tmp_path, {"KNA1": KNA1, "KNBK": KNBK, "TIBAN": tiban})
    iban_norm, valid_from = con.execute(
        "SELECT iban_norm, valid_from FROM bp_bank_account"
    ).fetchone()
    assert iban_norm == "DE02500105175407324937"
    assert valid_from == date(2024, 1, 1)
    assert _rejected(result, "bp_bank_account") == 0


def test_gleiches_valid_from_ist_mehrdeutig(tmp_path):
    """Zwei IBAN mit demselben VALID_FROM: die Bankverbindung wird abgelehnt, nicht geraten."""
    tiban = TIBAN + "DE\t50010517\t5407324931\t\tDE02 5001 0517 5407 3249 37\t20200101\n"
    con, result = build(tmp_path, {"KNA1": KNA1, "KNBK": KNBK, "TIBAN": tiban})
    assert _rows(result, "bp_bank_account") == 0
    assert _rejected(result, "bp_bank_account") == 1
    (source, reason), = rejects(con)
    assert source == "KNBK"
    assert "VALID_FROM" in reason and "nicht eindeutig" in reason


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("DE44500105175407324931", True),
        ("DE44500105175407324932", False),  # Pruefziffer verdreht
        ("XX12", False),
        ("", None),
        (None, None),
    ],
)
def test_iban_pruefziffer(value, expected):
    """schwifty prueft Pruefziffer und Laenderformat; ohne Wert gibt es kein Urteil."""
    assert is_valid_iban(value) is expected


def test_zahlungsbedingung_bevorzugt_deutsch(tmp_path):
    """SAP fuehrt Deutsch als `D`; der englische Text steht daneben und verliert (D-074)."""
    con, _ = build(tmp_path, {"T052": T052, "T052U": T052U})
    row = con.execute(
        "SELECT terms_key, days1, pct1, description FROM payment_terms"
    ).fetchone()
    assert row[0] == "ZB01"
    assert row[1] == 14
    assert str(row[2]) == "2.000"
    assert row[3] == "14 Tage 2 % Skonto"


def test_zahlungsbedingung_nimmt_englisch_wenn_kein_deutsch(tmp_path):
    """Ohne deutschen Text gewinnt der englische – leer bleibt die Spalte nur ohne T052U."""
    con, _ = build(tmp_path / "englisch", {"T052": T052, "T052U": _nur_englisch()})
    assert con.execute("SELECT description FROM payment_terms").fetchone()[0] == (
        "14 days 2 % cash discount"
    )
    con, _ = build(tmp_path / "ohne", {"T052": T052})
    assert con.execute("SELECT description FROM payment_terms").fetchone()[0] is None


def _nur_englisch() -> str:
    return "\n".join(line for line in T052U.splitlines() if "\tD\t" not in line) + "\n"


def test_email_kommt_aus_adr6(tmp_path):
    """ADR6 wird ueber die Adressnummer angebunden, wenn der Export sie liefert."""
    con, _ = build(tmp_path, {"KNA1": KNA1, "ADR6": ADR6})
    rows = con.execute("SELECT bp_key, email FROM business_partner ORDER BY bp_key").fetchall()
    assert rows == [("C:0000100001", "info@example.invalid"), ("C:0000100002", None)]


def test_ohne_adr6_bleibt_die_email_leer(tmp_path):
    """Der Demo-Mandant liefert ADR6 nicht – das ist kein Fehler."""
    con, _ = build(tmp_path, {"KNA1": KNA1})
    assert con.execute(
        "SELECT count(*) FROM business_partner WHERE email IS NOT NULL"
    ).fetchone()[0] == 0


def test_posten_tragen_item_key_und_is_open(tmp_path):
    """`item_key` haelt die fuehrenden Nullen, `is_open` kommt aus der Quelltabelle."""
    con, _ = build(
        tmp_path, {"KNA1": KNA1, "LFA1": LFA1, "BSID": BSID, "BSAD": BSAD, "BSIK": BSIK}
    )
    rows = con.execute(
        "SELECT item_key, bp_key, is_open, debit_credit, amount_signed_local, reference_norm "
        "FROM fi_item ORDER BY item_key"
    ).fetchall()
    assert rows == [
        ("1000|2025|0100000900|001", "C:0000100001", False, "S", 99.00, None),
        ("1000|2026|0100000001|001", "C:0000100001", True, "S", 1000.00, "RE4711"),
        ("1000|2026|0200000001|001", "V:0000200001", True, "H", -250.00, None),
        ("2000|2026|0100000002|001", "C:0000100001", True, "H", -500.00, "RE4711"),
    ]


def test_normalisierte_namen_bleiben_leer(tmp_path):
    """name_norm/city_norm/street_norm kommen mit der Dubletten-Spec (Sprint 4)."""
    con, result = build(tmp_path, {"KNA1": KNA1})
    assert con.execute(
        "SELECT count(*) FROM business_partner "
        "WHERE name_norm IS NOT NULL OR city_norm IS NOT NULL OR street_norm IS NOT NULL"
    ).fetchone()[0] == 0
    assert any("Sprint 4" in warning for warning in result.warnings)


# --- Scope: erst filtern, dann pruefen (D-075) -----------------------------------------


def test_scope_auf_buchungskreis(tmp_path):
    """`--company-codes` filtert Buchungskreiszeilen und Posten – und nichts sonst still."""
    con, result = build(
        tmp_path,
        {"KNA1": KNA1, "LFA1": LFA1, "KNB1": KNB1, "LFB1": LFB1, "BSID": BSID, "BSIK": BSIK},
        Scope(company_codes=("1000",)),
    )
    assert con.execute(
        "SELECT DISTINCT company_code FROM bp_company_code"
    ).fetchall() == [("1000",)]
    assert con.execute("SELECT DISTINCT company_code FROM fi_item").fetchall() == [("1000",)]
    # Der Posten im Buchungskreis 2000 ist ausserhalb des Scopes, kein Reject (D-075).
    assert _out_of_scope(result, "fi_item") == 1
    assert _rejected(result, "fi_item") == 0


def test_scope_haelt_partner_mit_buchungskreiszeile(tmp_path):
    """Ein Partner bleibt, wenn er mindestens eine Buchungskreiszeile im Scope hat."""
    con, result = build(
        tmp_path,
        {"KNA1": KNA1, "LFA1": LFA1, "KNB1": KNB1, "LFB1": LFB1},
        Scope(company_codes=("2000",)),
    )
    # Nur C:0000100001 ist in 2000 gefuehrt; die uebrigen beiden fallen aus dem Lauf.
    assert con.execute("SELECT bp_key FROM business_partner").fetchall() == [("C:0000100001",)]
    assert _out_of_scope(result, "business_partner") == 2
    assert _rejected(result, "business_partner") == 0


def test_scope_auf_seite(tmp_path):
    """`--side ap` nimmt nur Kreditoren auf; die Debitorenzeilen zaehlen als ausserhalb."""
    con, result = build(
        tmp_path,
        {"KNA1": KNA1, "LFA1": LFA1, "BSID": BSID, "BSIK": BSIK},
        Scope(side="ap"),
    )
    assert con.execute("SELECT DISTINCT role FROM business_partner").fetchall() == [("VENDOR",)]
    assert _out_of_scope(result, "business_partner") == 2
    assert _rows(result, "fi_item") == 1
    assert _out_of_scope(result, "fi_item") == 2


def test_postenfenster_filtert_nach_buchungsdatum(tmp_path):
    """Das Fenster wirkt auf `posting_date`; ohne Angabe filtert es nicht."""
    con, result = build(
        tmp_path,
        {"KNA1": KNA1, "BSID": BSID, "BSAD": BSAD},
        Scope(item_window_from=date(2026, 1, 1)),
    )
    assert con.execute("SELECT min(posting_date) FROM fi_item").fetchone()[0] == date(2026, 1, 15)
    assert _out_of_scope(result, "fi_item") == 1  # der Posten von 2025
    # Berichtet wird trotzdem, was geliefert wurde – das Fenster verdeckt nichts.
    assert result.posting_date_from == date(2025, 6, 1)
    assert result.posting_date_to == date(2026, 2, 20)


def test_unbekannte_seite_wird_abgewiesen():
    """Ein Tippfehler im Scope ist ein Fehler mit Namen, keine stille Vorgabe."""
    with pytest.raises(CanonicalError) as excinfo:
        Scope(side="AR")
    assert "AR" in str(excinfo.value)


# --- Was nicht kanonisch wird ----------------------------------------------------------


def test_posten_ohne_stammsatz_wird_abgelehnt(tmp_path):
    """Referentielle Pruefung: der Grund nennt den Schluessel, nicht die Zeile."""
    con, result = build(tmp_path, {"KNA1": KNA1, "BSIK": BSIK})
    assert _rows(result, "fi_item") == 0
    assert _rejected(result, "fi_item") == 1
    (source, reason), = rejects(con)
    assert source == "BSIK"
    assert reason == (
        "Stammsatz fehlt: V:0000200001 steht nicht in business_partner"
    )


def test_leeres_pflichtfeld_wird_abgelehnt(tmp_path):
    """Ohne Waehrung gibt es keinen Posten – und die Meldung nennt Feld und Quellspalte."""
    bsid = BSID.replace("\tEUR\t1.000,00", "\t\t1.000,00")
    con, result = build(tmp_path, {"KNA1": KNA1, "BSID": bsid})
    assert _rejected(result, "fi_item") == 1
    reason = rejects(con)[0][1]
    assert reason == "fi_item.currency ist leer (WAERS)"


def test_doppelter_schluessel_verliert_beide_zeilen(tmp_path):
    """Bei zwei Zeilen mit demselben `item_key` gewinnt keine still."""
    doppelt = BSID + BSID.splitlines()[1] + "\n"
    con, result = build(tmp_path, {"KNA1": KNA1, "BSID": doppelt})
    assert _rows(result, "fi_item") == 1  # nur der Posten im Buchungskreis 2000 bleibt
    assert _rejected(result, "fi_item") == 2
    reasons = {reason for _, reason in rejects(con)}
    assert reasons == {
        (
            "item_key 1000|2026|0100000001|001 kommt in BSID mehrfach vor – "
            "keine der Zeilen wird uebernommen"
        )
    }


def test_doppelter_schluessel_ueber_zwei_quellen(tmp_path):
    """Derselbe Beleg offen **und** ausgeglichen: die zweite Quelle wird benannt.

    Die Quellen werden nach Namen abgearbeitet (Regel 9), BSAD also vor BSID: abgelehnt
    wird die Zeile, die auf einen schon belegten Schluessel trifft.
    """
    bsad = BSAD.replace("2025\t0100000900", "2026\t0100000001").replace("20250601", "20260115")
    con, result = build(tmp_path, {"KNA1": KNA1, "BSID": BSID, "BSAD": bsad})
    assert _rejected(result, "fi_item") == 1
    (source, reason), = rejects(con)
    assert source == "BSID"
    assert "steht bereits aus einer anderen Quelltabelle in fi_item" in reason


def test_meldungen_tragen_keine_partnerdaten(tmp_path):
    """Regel 8: in `reject.reason` stehen Schluessel und Felder, keine Namen oder IBAN."""
    tiban = TIBAN + "DE\t50010517\t5407324931\t\tDE02 5001 0517 5407 3249 37\t20200101\n"
    con, _ = build(
        tmp_path,
        {"KNA1": KNA1, "KNBK": KNBK, "TIBAN": tiban, "BSIK": BSIK},
    )
    text = " ".join(reason for _, reason in rejects(con))
    for secret in ("Alpha", "Beta", "Gamma", "Augsburg", "Hauptstr", "DE44", "DE02", "5407324931"):
        assert secret not in text
    # Der Rohauszug bleibt leer: die Zeile ist ueber Tabelle und Zeilennummer auffindbar.
    assert con.execute(
        "SELECT count(*) FROM reject WHERE stage = 'canonical' AND raw_excerpt IS NOT NULL"
    ).fetchone()[0] == 0


# --- Der ganze Mandant -----------------------------------------------------------------


def canonical_from_dir(directory, scope: Scope | None = None):
    """Laedt, stagt und mappt ein ganzes Exportverzeichnis."""
    con = duckdb.connect(":memory:")
    con.execute(CANONICAL_SCHEMA.read_text(encoding="utf-8"))
    mapping = load_mapping()
    tables = [
        load_table(con, path).table
        for path in sorted(directory.iterdir())
        if path.suffix == ".txt"
    ]
    stage_all(con, mapping, tables, RUN_ID)
    return con, build_canonical(con, mapping, RUN_ID, scope)


@pytest.fixture(scope="module")
def demo_canonical(demo_client):
    """Der ausgelieferte Demo-Mandant, kanonisch abgebildet."""
    directory, _ = demo_client
    return canonical_from_dir(directory)


def test_demo_mandant_wird_vollstaendig_abgebildet(demo_canonical):
    """Kontenzahlen wie im Manifest, alle Zieltabellen gefuellt."""
    con, result = demo_canonical
    assert con.execute(
        "SELECT role, count(*) FROM business_partner GROUP BY role ORDER BY role"
    ).fetchall() == [("CUSTOMER", 2000), ("VENDOR", 1500)]
    for table in ("bp_tax_id", "bp_company_code", "bp_bank_account", "bp_partner_function",
                  "bp_dunning", "payment_terms", "fi_item"):
        assert _rows(result, table) > 0, table


def test_demo_mandant_verliert_keine_zeile(demo_canonical):
    """Erhaltungssatz: jede gestagte Zeile ist kanonisch, abgelehnt oder ausserhalb des Scopes."""
    con, result = demo_canonical
    for entry in result.tables:
        if entry.table == "bp_tax_id":
            continue  # aus drei Feldern je Stammsatz, kein Zeilenverhaeltnis 1:1
        staged = sum(
            con.execute(f'SELECT count(*) FROM "staged_{source}"').fetchone()[0]
            for source in entry.sources
        )
        assert entry.rows + entry.rejected + entry.out_of_scope == staged, entry.table


def test_demo_mandant_rejects_sind_erklaert(demo_canonical):
    """Die einzigen Rejects sind doppelte Gutschriftsnummern – ein Befund im Generator.

    `postings.py` zieht die Gutschriftsnummer aus dem Nummernkreis des Rechnungsjahres,
    setzt das Geschaeftsjahr des Belegs aber aus dem Gutschriftsdatum. Kreuzt die
    Gutschrift den Jahreswechsel, treffen zwei Kreise im selben Geschaeftsjahr aufeinander
    und `item_key` ist nicht mehr eindeutig. Der Test haelt fest, dass es keinen **anderen**
    Grund gibt; er bleibt gruen, sobald der Generator korrigiert ist.
    """
    con, _ = demo_canonical
    reasons = {reason for _, reason in rejects(con)}
    assert all("kommt in" in reason and "mehrfach vor" in reason for reason in reasons)
    # Betroffen sind ausschliesslich Gutschriften – die Belegarten DG (AR) und KG (AP).
    doc_types = set()
    for source in ("BSID", "BSIK"):
        doc_types.update(
            row[0]
            for row in con.execute(
                f'SELECT DISTINCT s."BLART" FROM "staged_{source}" s '
                "JOIN reject r ON r.row_no = s._row_no AND r.source_table = ? "
                "WHERE r.stage = 'canonical'",
                [source],
            ).fetchall()
        )
    assert doc_types and doc_types <= {"DG", "KG"}


def test_demo_mandant_ist_deterministisch(demo_client):
    """Zwei Laeufe ueber dieselben Dateien ergeben zeilengleiche Tabellen (Regel 9)."""
    directory, _ = demo_client
    first, _ = canonical_from_dir(directory)
    second, _ = canonical_from_dir(directory)
    for table in ("business_partner", "bp_tax_id", "bp_company_code", "bp_bank_account",
                  "fi_item"):
        left = first.execute(f"SELECT * FROM {table}").fetchall()
        right = second.execute(f"SELECT * FROM {table}").fetchall()
        assert left == right, table


def test_demo_mandant_beispielkonto(demo_canonical):
    """Ein Ankerkonto aus SPRINT-2.md steht vollstaendig im kanonischen Modell."""
    con, _ = demo_canonical
    row = con.execute(
        "SELECT role, source_id, country FROM business_partner WHERE bp_key = 'C:0000100234'"
    ).fetchone()
    assert row == ("CUSTOMER", "0000100234", "DE")
    assert con.execute(
        "SELECT count(*) FROM fi_item WHERE bp_key = 'C:0000100234' AND is_open"
    ).fetchone()[0] > 0


def test_encoding_samples_laufen_durch(repo_root):
    """Die Encoding-Samples liefern alle Pflichtspalten – die Stufe bricht nicht ab."""
    _con, result = canonical_from_dir(repo_root / "testdata" / "encoding_samples")
    assert _rows(result, "business_partner") == 5
    assert _rows(result, "fi_item") == 4
    assert result.rejected_total == 0
