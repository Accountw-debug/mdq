"""BP-360: Relevanz je Partner, Hauswaehrung, Aktivitaetsstatus.

Der Kern des Tests sind die sechs Ankerfaelle aus `SPRINT-2.md` und `logic/examples/`:
sie nennen offene Posten, Zwoelfmonatsvolumen und letzte Aktivitaet auf den Cent und den
Tag genau. Diese Werte sind erwartete Ergebnisse im Sinn von Regel 1 – sie werden nicht
angepasst, sondern erklaert.

Die uebrigen Faelle arbeiten auf kleinen, erfundenen Exporten (Regel 8) und pruefen, was
zwischen den Ankern liegt: Vorzeichen je Seite, Fenstergrenze, Konto ohne Posten, fehlende
Hauswaehrung, zwei Hauswaehrungen, unbekannte Belegart.
"""

from datetime import date
from decimal import Decimal

import duckdb
import pytest

from mdq import CANONICAL_SCHEMA
from mdq.canonical import Scope, build_canonical
from mdq.dictionaries import DictionaryError, load_document_types, parse_document_types
from mdq.loader import load_table
from mdq.mapping import load_mapping
from mdq.relevance import (
    SOURCE_DERIVED,
    SOURCE_GIVEN,
    RelevanceError,
    build_relevance,
    house_currency,
    resolve_data_as_of,
    window_start,
)
from mdq.staging import stage_all

RUN_ID = "test-run"

#: Datenstand der kleinen Faelle – fest, damit das Fenster nicht mit der Uhr wandert
AS_OF = date(2026, 8, 28)

T001 = """BUKRS\tBUTXT\tWAERS\tLAND1
1000\tDemo Industrie AG\tEUR\tDE
"""

T001_ZWEI_WAEHRUNGEN = """BUKRS\tBUTXT\tWAERS\tLAND1
1000\tDemo Industrie AG\tEUR\tDE
2000\tDemo Suisse AG\tCHF\tCH
"""

#: Ein Debitor (angelegt lange vor dem Fenster) und ein Kreditor
KNA1 = """KUNNR\tLAND1\tNAME1\tORT01\tERDAT
0000100001\tDE\tAlpha AG\tAugsburg\t20200101
"""

LFA1 = """LIFNR\tLAND1\tNAME1\tORT01\tERDAT
0000200001\tDE\tGamma KG\tGera\t20200101
"""

KNB1 = """KUNNR\tBUKRS\tAKONT
0000100001\t1000\t140000
"""

LFB1 = """LIFNR\tBUKRS\tAKONT
0000200001\t1000\t160000
"""

#: Debitor: offene Rechnung 1.000, bezahlte Rechnung 400, Gutschrift 100 – alle im Fenster
BSID = """KUNNR\tBUKRS\tGJAHR\tBELNR\tBUZEI\tBUDAT\tBLART\tSHKZG\tWAERS\tWRBTR\tDMBTR
0000100001\t1000\t2026\t0100000001\t001\t20260115\tDR\tS\tEUR\t1.000,00\t1.000,00
0000100001\t1000\t2026\t0100000003\t001\t20260210\tDG\tH\tEUR\t100,00\t100,00
"""

BSAD = """KUNNR\tBUKRS\tGJAHR\tBELNR\tBUZEI\tBUDAT\tBLART\tSHKZG\tWAERS\tWRBTR\tDMBTR\tAUGDT\tAUGBL
0000100001\t1000\t2026\t0100000002\t001\t20260120\tDR\tS\tEUR\t400,00\t400,00\t20260320\t0100000900
"""

#: Kreditor: offene Rechnung 700 (Haben), Gutschrift 200 (Soll)
BSIK = """LIFNR\tBUKRS\tGJAHR\tBELNR\tBUZEI\tBUDAT\tBLART\tSHKZG\tWAERS\tWRBTR\tDMBTR
0000200001\t1000\t2026\t0200000001\t001\t20260305\tKR\tH\tEUR\t700,00\t700,00
0000200001\t1000\t2026\t0200000002\t001\t20260405\tKG\tS\tEUR\t200,00\t200,00
"""


def build(tmp_path, files: dict[str, str], scope: Scope | None = None, as_of: date | None = AS_OF):
    """Legt Exporte an und baut Pipeline bis einschliesslich der Relevanz."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (tmp_path / f"{name}.txt").write_text(content, encoding="utf-8")
    con = duckdb.connect(":memory:")
    con.execute(CANONICAL_SCHEMA.read_text(encoding="utf-8"))
    mapping = load_mapping()
    tables = [load_table(con, path).table for path in sorted(tmp_path.glob("*.txt"))]
    stage_all(con, mapping, tables, RUN_ID)
    build_canonical(con, mapping, RUN_ID, scope)
    return con, build_relevance(con, as_of)


def relevance(con, bp_key: str) -> tuple:
    return con.execute(
        "SELECT open_items_local, volume_12m_local, currency, last_activity_on, "
        "activity_status FROM bp_relevance WHERE bp_key = ?",
        [bp_key],
    ).fetchone()


ALLE = {
    "T001": T001,
    "KNA1": KNA1,
    "LFA1": LFA1,
    "KNB1": KNB1,
    "LFB1": LFB1,
    "BSID": BSID,
    "BSAD": BSAD,
    "BSIK": BSIK,
}


# --- Betraege, Vorzeichen, Fenster -----------------------------------------------------


def test_forderung_und_verbindlichkeit_sind_beide_positiv(tmp_path):
    """D-085: die Relevanz zeigt die Fachlogik der Seite, nicht das Soll/Haben-Vorzeichen."""
    con, _ = build(tmp_path, ALLE)
    debitor = relevance(con, "C:0000100001")
    kreditor = relevance(con, "V:0000200001")
    # Debitor: offen sind Rechnung 1.000 und Gutschrift -100
    assert debitor[0] == Decimal("900.00")
    # Kreditor: offene Rechnung 700 (Haben) minus Gutschrift 200 (Soll)
    assert kreditor[0] == Decimal("500.00")
    assert kreditor[0] > 0, "eine Verbindlichkeit steht positiv in der Relevanz"


def test_volumen_zaehlt_rechnungen_minus_gutschriften_unabhaengig_vom_ausgleich(tmp_path):
    """D-051: die bezahlte Rechnung zaehlt mit, die Zahlung selbst nicht."""
    con, _ = build(tmp_path, ALLE)
    debitor = relevance(con, "C:0000100001")
    # 1.000 offen + 400 ausgeglichen - 100 Gutschrift
    assert debitor[1] == Decimal("1300.00")
    kreditor = relevance(con, "V:0000200001")
    assert kreditor[1] == Decimal("500.00")


def test_letzte_aktivitaet_zaehlt_auch_das_ausgleichsdatum(tmp_path):
    """D-062: ein spaet ausgeglichener Beleg ist Aktivitaet am Ausgleichstag."""
    con, _ = build(tmp_path, ALLE)
    # Juengstes Buchungsdatum ist der 10.02., das Ausgleichsdatum aber der 20.03.
    assert relevance(con, "C:0000100001")[3] == date(2026, 3, 20)


def test_fenster_ist_links_offen_und_rechts_geschlossen(tmp_path):
    """D-087: der Beleg vom Fensterbeginn zaehlt nicht mehr, der vom Datenstand noch."""
    grenze = (
        "KUNNR\tBUKRS\tGJAHR\tBELNR\tBUZEI\tBUDAT\tBLART\tSHKZG\tWAERS\tWRBTR\tDMBTR\n"
        "0000100001\t1000\t2025\t0100000010\t001\t20250828\tDR\tS\tEUR\t50,00\t50,00\n"
        "0000100001\t1000\t2026\t0100000011\t001\t20260828\tDR\tS\tEUR\t70,00\t70,00\n"
    )
    con, result = build(
        tmp_path, {"T001": T001, "KNA1": KNA1, "KNB1": KNB1, "BSID": grenze}
    )
    assert result.window_from == date(2025, 8, 28)
    # Nur der Beleg vom Datenstand zaehlt; der vom 28.08.2025 liegt genau auf der Grenze.
    assert relevance(con, "C:0000100001")[1] == Decimal("70.00")


def test_window_start_faengt_den_schalttag(tmp_path):
    """Gibt es den Tag im Zielmonat nicht, gilt der letzte Tag des Monats."""
    assert window_start(date(2026, 8, 28)) == date(2025, 8, 28)
    assert window_start(date(2028, 2, 29)) == date(2027, 2, 28)


# --- Aktivitaetsstatus (D-086) ---------------------------------------------------------


def test_konto_mit_bewegung_im_fenster_ist_aktiv(tmp_path):
    con, _ = build(tmp_path, ALLE)
    assert relevance(con, "C:0000100001")[4] == "active"


def test_konto_ohne_bewegung_im_fenster_ist_ruhend(tmp_path):
    """Posten gibt es, aber alle aelter als zwoelf Monate."""
    alt = (
        "KUNNR\tBUKRS\tGJAHR\tBELNR\tBUZEI\tBUDAT\tBLART\tSHKZG\tWAERS\tWRBTR\tDMBTR\n"
        "0000100001\t1000\t2024\t0100000020\t001\t20241201\tDR\tS\tEUR\t80,00\t80,00\n"
    )
    con, _ = build(tmp_path, {"T001": T001, "KNA1": KNA1, "KNB1": KNB1, "BSID": alt})
    row = relevance(con, "C:0000100001")
    assert row[1] == Decimal("0.00")  # ausserhalb des Fensters
    assert row[4] == "dormant"


def test_konto_ohne_posten_vor_fensterbeginn_angelegt_ist_ruhend(tmp_path):
    """Ein altes Konto ohne jede Bewegung ist ruhend, nicht 'nie bebucht' (D-086)."""
    con, _ = build(tmp_path, {"T001": T001, "KNA1": KNA1, "KNB1": KNB1})
    row = relevance(con, "C:0000100001")
    assert row[0] == Decimal("0.00")
    assert row[3] is None  # keine letzte Aktivitaet (D-062)
    assert row[4] == "dormant"


def test_konto_ohne_posten_im_fenster_angelegt_ist_nie_bebucht(tmp_path):
    """Ein frisch angelegtes Konto konnte sich noch gar nicht bewegen."""
    neu = KNA1.replace("20200101", "20260701")
    con, _ = build(tmp_path, {"T001": T001, "KNA1": neu, "KNB1": KNB1})
    assert relevance(con, "C:0000100001")[4] == "never_posted"


def test_jeder_partner_bekommt_eine_zeile(tmp_path):
    """Auch das Konto ohne Posten – sonst waere 'null Umsatz' von 'nicht berechnet'
    nicht zu unterscheiden (Regel 4)."""
    con, result = build(tmp_path, ALLE)
    assert result.partners == 2
    assert con.execute("SELECT count(*) FROM bp_relevance").fetchone()[0] == 2


# --- Hauswaehrung (D-030, D-083) -------------------------------------------------------


def test_hauswaehrung_kommt_aus_t001(tmp_path):
    con, result = build(tmp_path, ALLE)
    assert house_currency(con) == "EUR"
    assert result.house_currency == "EUR"
    assert relevance(con, "C:0000100001")[2] == "EUR"


def test_ohne_t001_bricht_die_stufe_ab_und_nennt_die_tabelle(tmp_path):
    """Kein CLI-Ersatzwert: die Hauswaehrung ist eine Stammdatenauskunft (D-083)."""
    with pytest.raises(RelevanceError) as excinfo:
        build(tmp_path, {"KNA1": KNA1, "KNB1": KNB1, "BSID": BSID})
    assert "T001" in str(excinfo.value)


def test_zwei_hauswaehrungen_brechen_den_lauf_ab(tmp_path):
    """D-030: V1 rechnet nicht um; zwei Waehrungen waeren unvergleichbare Betraege."""
    with pytest.raises(RelevanceError) as excinfo:
        build(tmp_path, {"T001": T001_ZWEI_WAEHRUNGEN, "KNA1": KNA1, "KNB1": KNB1})
    message = str(excinfo.value)
    assert "CHF" in message and "EUR" in message
    assert "--company-codes" in message


def test_scope_auf_einen_buchungskreis_macht_den_lauf_wieder_moeglich(tmp_path):
    """Der Ausweg aus D-030 steht in der Meldung – und er funktioniert."""
    beide_kreise = KNB1 + "0000100001\t2000\t140000\n"
    con, result = build(
        tmp_path,
        {"T001": T001_ZWEI_WAEHRUNGEN, "KNA1": KNA1, "KNB1": beide_kreise},
        Scope(company_codes=("2000",)),
    )
    assert result.house_currency == "CHF"
    assert result.partners == 1
    # Die Waehrung steht neben dem Betrag und ist die des gewaehlten Kreises (Regel 2).
    assert con.execute("SELECT DISTINCT currency FROM bp_relevance").fetchall() == [("CHF",)]


# --- Datenstand ------------------------------------------------------------------------


def test_datenstand_wird_aus_den_posten_abgeleitet(tmp_path):
    """Ohne Angabe gilt das spaeteste Buchungs- oder Ausgleichsdatum – und der Report
    sagt, dass es abgeleitet wurde."""
    con, _ = build(tmp_path, ALLE, as_of=None)
    as_of, source = resolve_data_as_of(con)
    assert as_of == date(2026, 4, 5)  # juengster Beleg des Kreditors
    assert source == SOURCE_DERIVED


def test_angegebener_datenstand_gewinnt(tmp_path):
    con, result = build(tmp_path, ALLE, as_of=date(2026, 6, 30))
    assert result.data_as_of == date(2026, 6, 30)
    assert result.data_as_of_source == SOURCE_GIVEN
    assert resolve_data_as_of(con, date(2026, 6, 30)) == (date(2026, 6, 30), SOURCE_GIVEN)


def test_ohne_posten_ist_der_datenstand_pflicht(tmp_path):
    with pytest.raises(RelevanceError) as excinfo:
        build(tmp_path, {"T001": T001, "KNA1": KNA1, "KNB1": KNB1}, as_of=None)
    assert "--data-as-of" in str(excinfo.value)


# --- Woerterbuch der Belegarten (D-084) ------------------------------------------------


def test_woerterbuch_liest_die_klassen():
    types = load_document_types()
    assert types.for_role("CUSTOMER", "invoice") == ("DR",)
    assert types.for_role("VENDOR", "credit_memo") == ("KG",)
    assert types.of("AP", "invoice", "credit_memo") == ("KG", "KR")


def test_unbekannte_belegart_wird_gemeldet_statt_verschwiegen(tmp_path):
    """Eine Belegart ohne Klasse zaehlt nicht in volume_12m – das steht im Report."""
    fremd = BSID.replace("\tDR\t", "\tZZ\t", 1)
    _con, result = build(tmp_path, {"T001": T001, "KNA1": KNA1, "KNB1": KNB1, "BSID": fremd})
    assert any("ZZ" in warning for warning in result.warnings)
    assert any("document_types.yaml" in warning for warning in result.warnings)


def test_belegart_in_zwei_klassen_ist_ein_fehler(tmp_path):
    document = {
        "version": "0.1",
        "sides": {
            "AR": {"invoice": ["DR"], "credit_memo": ["DR"], "payment": [], "reversal": []},
            "AP": {"invoice": ["KR"], "credit_memo": ["KG"], "payment": [], "reversal": []},
        },
    }
    with pytest.raises(DictionaryError) as excinfo:
        parse_document_types(document, tmp_path / "document_types.yaml")
    assert "DR" in str(excinfo.value)


def test_fehlende_rechnungsklasse_ist_ein_fehler(tmp_path):
    document = {
        "version": "0.1",
        "sides": {
            "AR": {"invoice": [], "credit_memo": ["DG"]},
            "AP": {"invoice": ["KR"], "credit_memo": ["KG"]},
        },
    }
    with pytest.raises(DictionaryError) as excinfo:
        parse_document_types(document, tmp_path / "document_types.yaml")
    assert "AR.invoice" in str(excinfo.value)


# --- Der Demo-Mandant: die Ankerfaelle (Regel 1) ---------------------------------------


@pytest.fixture(scope="module")
def demo_relevance(demo_client):
    """Der ausgelieferte Demo-Mandant bis einschliesslich der Relevanzstufe."""
    directory, _ = demo_client
    con = duckdb.connect(":memory:")
    con.execute(CANONICAL_SCHEMA.read_text(encoding="utf-8"))
    mapping = load_mapping()
    tables = [
        load_table(con, path).table
        for path in sorted(directory.iterdir())
        if path.suffix == ".txt"
    ]
    stage_all(con, mapping, tables, RUN_ID)
    build_canonical(con, mapping, RUN_ID)
    return con, build_relevance(con)


#: Die Ankerwerte aus SPRINT-2.md und logic/examples/findings/:
#: bp_key -> (offene Posten, Volumen 12M, letzte Aktivitaet)
ANCHORS = {
    # F-001 / F-002: OP 45.210,00 in 1000, letzte Zahlung 12.08.2026, Volumen 312.400,00
    "C:0000100234": ("45210.00", "312400.00", date(2026, 8, 12)),
    # SPRINT-2.md: zwei offene Posten a 3.200,00
    "C:0000100987": ("6400.00", None, None),
    # F-004: 3 OP = 8.930,00, aeltester 03.11.2025, Volumen 8.930,00 (nur diese drei)
    "C:0000101502": ("8930.00", "8930.00", date(2025, 11, 3)),
    # F-005: OP 18.400,00 (8 Rechnungen), Volumen 259.020,00
    "V:0000200117": ("18400.00", "259020.00", date(2026, 8, 25)),
    # F-003: beide Rechnungen bezahlt -> nichts offen, Volumen 1.284.000,00
    "V:0000200845": ("0.00", "1284000.00", date(2026, 8, 20)),
    # F-006: OP 27.300,00 in 2000, Volumen 96.800,00
    "V:0000201330": ("27300.00", "96800.00", date(2026, 8, 21)),
}


@pytest.mark.parametrize("bp_key", sorted(ANCHORS))
def test_ankerwerte_stehen_exakt_in_der_relevanz(demo_relevance, bp_key):
    """Regel 1: diese Werte sind Spec. Weicht einer ab, ist die Rechnung falsch – nicht
    die Erwartung."""
    con, _ = demo_relevance
    open_items, volume, last_activity = ANCHORS[bp_key]
    row = relevance(con, bp_key)
    assert row is not None, bp_key
    assert row[0] == Decimal(open_items), f"{bp_key}: offene Posten"
    if volume is not None:
        assert row[1] == Decimal(volume), f"{bp_key}: Volumen 12M"
    if last_activity is not None:
        assert row[3] == last_activity, f"{bp_key}: letzte Aktivitaet"
    assert row[2] == "EUR"


def test_demo_mandant_hat_einen_abgeleiteten_datenstand(demo_relevance):
    """Der Datenstand des Mandanten ist zugleich das Ende des Postenfensters."""
    _con, result = demo_relevance
    assert result.data_as_of == date(2026, 8, 28)
    assert result.data_as_of_source == SOURCE_DERIVED
    assert result.window_from == date(2025, 8, 28)
    assert result.house_currency == "EUR"


def test_demo_mandant_hat_fuer_jeden_partner_eine_relevanzzeile(demo_relevance):
    con, result = demo_relevance
    partners = con.execute("SELECT count(*) FROM business_partner").fetchone()[0]
    assert result.partners == partners == 3500
    assert sum(count for _status, count in result.by_status) == partners


def test_demo_mandant_kennt_keine_belegart_ohne_klasse(demo_relevance):
    """Faellt eine neue Belegart in den Generator, faellt sie hier auf."""
    _con, result = demo_relevance
    assert [w for w in result.warnings if "ohne Klasse" in w] == []


def test_ruhende_konten_des_defektkatalogs_sind_ruhend(demo_relevance):
    """Die 65 `dormant_account`-Defekte sind vor Fensterbeginn angelegt und ohne Posten.

    Regel 1: hier wird verifiziert, nicht angepasst. Taucht eines der Konten als
    `never_posted` auf, ist es entgegen der Notiz in `defects.yaml` **im** Fenster
    angelegt – das ist ein Befund fuer Victor, keine stille Korrektur.
    """
    con, _ = demo_relevance
    rows = con.execute(
        "SELECT r.activity_status, count(*) FROM bp_relevance r "
        "WHERE NOT EXISTS (SELECT 1 FROM fi_item i WHERE i.bp_key = r.bp_key) "
        "GROUP BY 1 ORDER BY 1"
    ).fetchall()
    assert rows == [("dormant", 65)]


def test_relevanz_ist_deterministisch(demo_relevance):
    """Zweimal rechnen ergibt zeilengleiche Werte (Regel 9)."""
    con, _ = demo_relevance
    first = con.execute("SELECT * FROM bp_relevance ORDER BY bp_key").fetchall()
    build_relevance(con)
    second = con.execute("SELECT * FROM bp_relevance ORDER BY bp_key").fetchall()
    assert first == second
