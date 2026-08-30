"""Die Defekt-Schicht: Zahl der Fälle, Ankerwerte, Negativfälle, erwartete Findings.

Diese Datei ist die Gegenprobe zum Defekt-Katalog in `docs/specs/SPRINT-2.md`. Sie prüft
nicht, ob die Regeln funktionieren – das ist ab Sprint 3 der Regressionstest –, sondern
dass in den Daten genau das steht, was die Defekte versprechen.
"""

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

import pytest
from schwifty import IBAN

from mdq import DEMO_DEFECTS, EXPECTED_FINDINGS
from mdq.demo import DATA_AS_OF, DEFAULT_SEED
from mdq.demo.defects import (
    WINDOW_12M_START,
    DefectError,
    defect_types,
    load_defects,
    render_expected,
)
from mdq.demo.generate import build_client
from mdq.findings import iter_finding_files, load_finding_file
from mdq.formats import parse_amount, parse_date

from .conftest import demo_rows

#: Erwartete Findings je Regel laut Defekt-Katalog in SPRINT-2.md. Diese Zahlen sind die
#: fachliche Vorgabe – sie werden nie an den Generator angepasst (CLAUDE.md Regel 1).
FINDINGS_PER_RULE = {
    "AR-DUP-001": 12,
    "AP-DUP-001": 8,
    "AR-VAL-001": 15,
    "AP-VAL-001": 10,
    "AR-VAL-002": 7,
    "AP-VAL-002": 5,
    "AR-VAL-003": 3,
    "AP-VAL-003": 5,
    "AR-CON-002": 7,
    "AR-COM-002": 20,
    "AR-HYG-001": 40,
    "AP-HYG-001": 25,
    "AP-LEA-001": 10,
    "AP-LEA-002": 8,
    "AP-CON-001": 4,
    "CROSS-DUP-001": 5,
    "AP-COM-003": 30,
    "AR-VAL-005": 10,
    "AR-LEA-001": 6,
}

#: Negativfälle: Defekttyp -> Anzahl Einträge mit ``expected: []``
NEGATIVE_CASES = {
    "central_payer": 30,
    "one_time_lookalike": 5,
    "same_core_name_other_form": 5,
    "deletion_flag": 5,
    "double_payment": 3,
    "discount_usage": 20,
    "anchor": 1,
}


@pytest.fixture(scope="module")
def defects():
    return load_defects(DEMO_DEFECTS, DEFAULT_SEED)


@pytest.fixture(scope="module")
def anchors(defects):
    """Die Parameter der sechs Ankerfälle, nach Konto."""
    return {d.params["bp_key"]: d.params for d in defects if d.type == "anchor"}


@pytest.fixture(scope="module")
def examples(example_findings_dir):
    """Die sechs fachlichen Beispiel-Findings – sie sind die Vorgabe, nicht das Ergebnis."""
    return [load_finding_file(path) for path in sorted(iter_finding_files(example_findings_dir))]


@pytest.fixture(scope="module")
def rows(demo_client):
    """Alle Exportzeilen des ausgelieferten Demo-Mandanten, je Tabelle."""
    out, _ = demo_client
    tables = ("KNA1", "KNB1", "KNBK", "KNVP", "LFA1", "LFB1", "LFBK", "TIBAN",
              "BSID", "BSAD", "BSIK", "BSAK")
    return {table: demo_rows(out, table) for table in tables}


@pytest.fixture(scope="module")
def items_by_account(rows):
    """Posten je Kontonummer, Debitoren und Kreditoren getrennt."""
    result = {"C": defaultdict(list), "V": defaultdict(list)}
    for table, side, key in (("BSID", "C", "KUNNR"), ("BSAD", "C", "KUNNR"),
                             ("BSIK", "V", "LIFNR"), ("BSAK", "V", "LIFNR")):
        for row in rows[table]:
            result[side][row[key]].append({**row, "_open": table in ("BSID", "BSIK")})
    return result


def _master(rows, bp_key):
    table, key = ("KNA1", "KUNNR") if bp_key.startswith("C:") else ("LFA1", "LIFNR")
    number = bp_key.split(":")[1]
    matches = [row for row in rows[table] if row[key] == number]
    assert len(matches) == 1, f"{bp_key} steht nicht genau einmal im Stamm"
    return matches[0]


def _invoices(items, bp_key):
    side, number = bp_key.split(":")
    return [item for item in items[side][number] if item["BLART"] in ("DR", "KR")]


def _volume_12m(items, bp_key) -> Decimal:
    """Volumen laut D-051: Rechnungen brutto nach Buchungsdatum minus Gutschriften."""
    side, number = bp_key.split(":")
    total = Decimal("0.00")
    for item in items[side][number]:
        if not WINDOW_12M_START <= parse_date(item["BUDAT"]) <= DATA_AS_OF:
            continue
        if item["BLART"] in ("DR", "KR"):
            total += parse_amount(item["WRBTR"])
        elif item["BLART"] in ("DG", "KG"):
            total -= parse_amount(item["WRBTR"])
    return total


def _last_activity(items, bp_key) -> date:
    """Letzte Aktivität laut D-062: spätestes Beleg- oder Ausgleichsdatum."""
    side, number = bp_key.split(":")
    dates = []
    for item in items[side][number]:
        dates.append(parse_date(item["BUDAT"]))
        cleared = parse_date(item["AUGDT"])
        if cleared is not None:
            dates.append(cleared)
    return max(dates)


def _open_items(items, bp_key, company_code=None) -> Decimal:
    side, number = bp_key.split(":")
    return sum(
        (parse_amount(item["WRBTR"]) for item in items[side][number]
         if item["_open"] and (company_code is None or item["BUKRS"] == company_code)),
        Decimal("0.00"),
    )


# --- Katalog und Datei ----------------------------------------------------------------


def test_every_defect_type_is_known_and_documented(defects) -> None:
    """Jeder Eintrag nennt einen registrierten Typ und einen fachlichen Satz."""
    for defect in defects:
        assert defect.type in defect_types()
        assert defect.note.strip()


def test_unknown_defect_type_is_an_error(tmp_path) -> None:
    """Regel 4: ein unbekannter Typ wird gemeldet, nicht übersprungen."""
    path = tmp_path / "defects.yaml"
    path.write_text(
        'version: "0.1"\nseed: 1\ndefects:\n'
        '  - id: X-1\n    type: gibt_es_nicht\n    note: "Test"\n'
        '    params: {}\n    expected: []\n',
        encoding="utf-8",
    )
    with pytest.raises(DefectError, match="gibt_es_nicht"):
        load_defects(path, 1)


def test_defect_without_expected_is_an_error(tmp_path) -> None:
    """Ein Negativfall trägt ausdrücklich ``expected: []`` – Schweigen zählt nicht."""
    path = tmp_path / "defects.yaml"
    path.write_text(
        'version: "0.1"\nseed: 1\ndefects:\n'
        '  - id: X-1\n    type: dormant_account\n    note: "Test"\n    params: {}\n',
        encoding="utf-8",
    )
    with pytest.raises(DefectError, match="expected"):
        load_defects(path, 1)


def test_defect_ids_are_unique(defects) -> None:
    ids = [defect.id for defect in defects]
    assert len(set(ids)) == len(ids)


# --- Zahl der Fälle -------------------------------------------------------------------


def test_findings_per_rule_match_the_catalog(demo_expected) -> None:
    """Die Zahl der erwarteten Findings je Regel steht in SPRINT-2.md."""
    counts = Counter(entry.rule_id for entry in demo_expected)
    assert dict(sorted(counts.items())) == dict(sorted(FINDINGS_PER_RULE.items()))


def test_negative_cases_match_the_catalog(defects) -> None:
    """Die Negativfälle sind vollzählig – sie sind der Beweis, dass Regeln schweigen können."""
    counts = Counter(defect.type for defect in defects if not defect.expected)
    assert dict(sorted(counts.items())) == dict(sorted(NEGATIVE_CASES.items()))


def test_two_double_payments_wait_for_rule_version_1_1(demo_expected) -> None:
    """Kontenübergreifende Doppelzahlungen sind bekannt-offen bis AP-LEA-001 1.1 (D-054)."""
    later = [entry for entry in demo_expected if entry.from_rule_version]
    assert len(later) == 2
    assert {entry.rule_id for entry in later} == {"AP-LEA-001"}
    assert {entry.from_rule_version for entry in later} == {"1.1"}


def test_expected_findings_file_is_up_to_date(demo_expected) -> None:
    """Die eingecheckte Erwartung ist genau das, was defects.yaml ergibt (D-010)."""
    assert EXPECTED_FINDINGS.read_text(encoding="utf-8") == render_expected(demo_expected)


def test_every_expected_finding_points_at_an_existing_account(demo_expected, rows) -> None:
    numbers = {f"C:{row['KUNNR']}" for row in rows["KNA1"]}
    numbers |= {f"V:{row['LIFNR']}" for row in rows["LFA1"]}
    assert {entry.bp_key for entry in demo_expected} <= numbers


def test_account_counts_are_unchanged(rows) -> None:
    """D-056: Löschkandidaten entstehen aus bestehenden Konten, nicht durch neue."""
    assert len(rows["KNA1"]) == 2000
    assert len(rows["LFA1"]) == 1500


# --- Ankerfälle: die sechs Beispiel-Findings müssen wörtlich wahr sein ------------------


def test_master_data_of_every_anchor_matches_its_defect(anchors, rows) -> None:
    """Die Stammdaten der sechs Anker stehen genau so in den Dateien wie in defects.yaml.

    Die Werte selbst stehen nicht in dieser Datei: Namen und Adressen gehören nicht in
    Tests (CLAUDE.md Regel 8), auch wenn sie erfunden sind. Quelle ist der Defekt.
    """
    for bp_key, params in anchors.items():
        master = _master(rows, bp_key)
        assert master["LAND1"] == params["country"]
        assert master["NAME1"] == params["name1"]
        assert master["ORT01"] == params["city"]
        assert master["PSTLZ"] == params["postal_code"]
        assert master["REGIO"] == params["region"]
        if "street" in params:
            assert master["STRAS"] == params["street"]
        if "vat_id" in params:
            assert master["STCEG"] == params["vat_id"]
        assert master["LOEVM"] == params.get("deletion_flag", "")
        assert master["XCPDK"] == "", "ein Ankerkonto ist nie CpD, sonst prüft keine Regel es"


def test_relevance_of_every_example_finding_is_true(examples, items_by_account) -> None:
    """Die sechs Beispiel-Findings sind auf dem erzeugten Mandanten wörtlich wahr.

    Geprüft werden die drei Relevanzgrössen: offene Posten, Volumen 12 Monate (D-051) und
    letzte Aktivität (D-062). Bei einem Dubletten-Finding zählt der ganze Cluster – dort ist
    die Relevanz die des zusammengeführten Partners; bei allen anderen nur das Konto selbst,
    auch wenn `related_bp_keys` auf eine Dublette verweist.
    """
    for finding in examples:
        entity = finding["entity"]
        cluster = [entity["bp_key"]]
        if finding["category"] == "duplicate":
            cluster += list(entity.get("related_bp_keys", ()))
        relevance = finding["relevance"]
        company_code = entity.get("company_code")

        assert sum((_open_items(items_by_account, key, company_code) for key in cluster),
                   Decimal("0.00")) == Decimal(relevance["open_items"]), finding["rule_id"]
        assert sum((_volume_12m(items_by_account, key) for key in cluster),
                   Decimal("0.00")) == Decimal(relevance["volume_12m"]), finding["rule_id"]
        assert max(_last_activity(items_by_account, key) for key in cluster) == date.fromisoformat(
            relevance["last_activity_on"]
        ), finding["rule_id"]


def test_anchor_customer_with_foreign_vat_prefix(rows, items_by_account) -> None:
    """F-001: 45.210,00 offene Posten, 27 Zahlungen, letzte am 12.08.2026."""
    assert _open_items(items_by_account, "C:0000100234", "1000") == Decimal("45210.00")
    assert _volume_12m(items_by_account, "C:0000100234") == Decimal("312400.00")
    payments = [item for item in items_by_account["C"]["0000100234"] if item["BLART"] == "DZ"]
    assert len(payments) == 27
    assert max(parse_date(item["BUDAT"]) for item in payments) == date(2026, 8, 12)


def test_anchor_duplicate_partner(rows, items_by_account, anchors) -> None:
    """F-002: zweites Konto derselben Adresse, zwei offene Posten à 3.200,00."""
    leader, twin = anchors["C:0000100234"], anchors["C:0000100987"]
    for field in ("city", "postal_code", "region", "country"):
        assert leader[field] == twin[field], "die Dublette teilt die Adresse"
    assert leader["name1"] != twin["name1"], "und unterscheidet sich nur in der Schreibweise"

    open_items = [item for item in items_by_account["C"]["0000100987"] if item["_open"]]
    assert [parse_amount(item["WRBTR"]) for item in open_items] == [Decimal("3200.00")] * 2
    assert _volume_12m(items_by_account, "C:0000100987") == Decimal("26500.00")
    assert len([i for i in items_by_account["C"]["0000100987"] if i["BLART"] == "DZ"]) == 2

    # "kein RG/RE-Bezug in KNVP" – das schliesst Zentralregulierung aus
    functions = [row for row in rows["KNVP"] if row["KUNNR"] == "0000100987"]
    assert {row["PARVW"] for row in functions} == {"AG"}


def test_anchor_deletion_flag_with_open_items(rows, items_by_account) -> None:
    """F-004: Löschvormerkung zentral, 3 OP über 8.930,00, ältester 03.11.2025."""
    master = _master(rows, "C:0000101502")
    assert master["LOEVM"] == "X"
    open_items = [item for item in items_by_account["C"]["0000101502"] if item["_open"]]
    assert len(open_items) == 3
    assert _open_items(items_by_account, "C:0000101502", "1000") == Decimal("8930.00")
    assert min(parse_date(item["BLDAT"]) for item in open_items) == date(2025, 11, 3)
    # D-051: das Volumen zählt auch offene Rechnungen
    assert _volume_12m(items_by_account, "C:0000101502") == Decimal("8930.00")


def test_anchor_double_payment(rows, items_by_account, anchors) -> None:
    """F-003: zwei bezahlte Rechnungen über 32.000,00 mit RE-4711 und RE4711."""
    items = {item["BELNR"]: item for item in items_by_account["V"]["0000200845"]}
    documents = anchors["V:0000200845"]["postings"]["documents"]
    assert [entry["amount"] for entry in documents] == ["32000.00"] * 2
    for entry in documents:
        number, reference = entry["document_no"], entry["reference"]
        day = date.fromisoformat(entry["document_date"])
        item = items[number]
        assert item["BUKRS"] == "1000" and item["GJAHR"] == "2026"
        assert item["XBLNR"] == reference
        assert parse_date(item["BLDAT"]) == day
        assert parse_amount(item["WRBTR"]) == Decimal("32000.00")
        assert not item["_open"], "beide Rechnungen sind bezahlt"

    assert _volume_12m(items_by_account, "V:0000200845") == Decimal("1284000.00")
    assert _open_items(items_by_account, "V:0000200845") == Decimal("0.00")
    credits = [i for i in items_by_account["V"]["0000200845"] if i["BLART"] == "KG"]
    assert credits == [], "keine Gutschrift – sonst wäre die Doppelzahlung genettet"


def test_anchor_discount_loss(rows, items_by_account) -> None:
    """F-005: 23 von 31 Rechnungen nach Skontofrist bezahlt, Skontobasis 240.620,00."""
    company = [row for row in rows["LFB1"] if row["LIFNR"] == "0000200117"]
    assert [row["ZTERM"] for row in company] == ["ZB02"]

    invoices = _invoices(items_by_account, "V:0000200117")
    in_window = [i for i in invoices if WINDOW_12M_START <= parse_date(i["BUDAT"]) <= DATA_AS_OF]
    assert len(in_window) == 31
    cleared = [i for i in in_window if not i["_open"]]
    assert len(cleared) == 23
    assert sum((parse_amount(i["SKFBT"]) for i in cleared), Decimal("0.00")) == Decimal("240620.00")
    for item in cleared:
        assert parse_amount(item["SKNTO"]) == Decimal("0.00"), "Skonto wurde nicht gezogen"
        assert parse_date(item["AUGDT"]) > parse_date(item["BLDAT"]) + timedelta(days=14)

    assert _open_items(items_by_account, "V:0000200117", "1000") == Decimal("18400.00")
    assert len([i for i in in_window if i["_open"]]) == 8
    assert _volume_12m(items_by_account, "V:0000200117") == Decimal("259020.00")


def test_anchor_invalid_iban(rows, items_by_account, anchors) -> None:
    """F-006: IBAN mit ungültiger Prüfziffer bei 27.300,00 offenen Posten."""
    bank = [row for row in rows["LFBK"] if row["LIFNR"] == "0000201330"]
    assert len(bank) == 1
    ibans = [
        row["IBAN"] for row in rows["TIBAN"]
        if (row["BANKS"], row["BANKL"], row["BANKN"]) == (bank[0]["BANKS"], bank[0]["BANKL"], bank[0]["BANKN"])
    ]
    assert ibans == [anchors["V:0000201330"]["iban"]]
    with pytest.raises(ValueError):
        IBAN(ibans[0])

    assert _open_items(items_by_account, "V:0000201330", "2000") == Decimal("27300.00")
    assert _volume_12m(items_by_account, "V:0000201330") == Decimal("96800.00")


# --- Wirkung der übrigen Defekte -------------------------------------------------------


def _targets(defects, kind, field="bp_keys"):
    """Alle in defects.yaml genannten Zielkonten eines Defekttyps."""
    keys = []
    for defect in defects:
        if defect.type != kind:
            continue
        keys.extend(defect.params.get(field, ()))
    return keys


def test_dormant_accounts_have_no_postings_at_all(defects, items_by_account, demo_expected) -> None:
    """AR-HYG-001/AP-HYG-001: kein Posten im gesamten Fenster (D-049)."""
    keys = _targets(defects, "dormant_account")
    assert len(keys) == 65
    for bp_key in keys:
        side, number = bp_key.split(":")
        assert items_by_account[side][number] == []
    hygiene = {e.bp_key for e in demo_expected if e.rule_id in ("AR-HYG-001", "AP-HYG-001")}
    assert hygiene == set(keys)


def test_deletion_candidates_were_created_before_the_window(defects, rows) -> None:
    """ERDAT vor Fensterbeginn – sonst wäre es AR-HYG-002 statt AR-HYG-001."""
    for bp_key in _targets(defects, "dormant_account"):
        assert parse_date(_master(rows, bp_key)["ERDAT"]) < date(2024, 9, 1)


def test_reprf_is_empty_exactly_for_the_declared_vendors(rows, demo_expected) -> None:
    """AP-COM-003: 30 Kreditoren ohne Prüfung auf doppelte Rechnung, sonst keiner."""
    empty = {(f"V:{row['LIFNR']}", row["BUKRS"]) for row in rows["LFB1"] if not row["REPRF"]}
    expected = {(e.bp_key, e.company_code) for e in demo_expected if e.rule_id == "AP-COM-003"}
    assert empty == expected
    assert len(empty) == 30


def test_payment_terms_are_empty_exactly_for_the_declared_customers(rows, demo_expected) -> None:
    """AR-COM-002: 20 Debitoren ohne Zahlungsbedingung im Buchungskreis."""
    empty = {(f"C:{row['KUNNR']}", row["BUKRS"]) for row in rows["KNB1"] if not row["ZTERM"]}
    expected = {(e.bp_key, e.company_code) for e in demo_expected if e.rule_id == "AR-COM-002"}
    assert empty == expected


def test_broken_ibans_are_exactly_the_declared_ones(rows, demo_expected) -> None:
    """AR-VAL-003/AP-VAL-003: acht ungültige Prüfziffern, alle anderen IBAN sind gültig."""
    broken = set()
    for row in rows["TIBAN"]:
        try:
            IBAN(row["IBAN"])
        except ValueError:
            broken.add((row["BANKS"], row["BANKL"], row["BANKN"]))

    owners = set()
    for table, side, key in (("KNBK", "C", "KUNNR"), ("LFBK", "V", "LIFNR")):
        for row in rows[table]:
            if (row["BANKS"], row["BANKL"], row["BANKN"]) in broken:
                owners.add(f"{side}:{row[key]}")

    expected = {e.bp_key for e in demo_expected if e.rule_id in ("AR-VAL-003", "AP-VAL-003")}
    assert owners == expected
    assert len(expected) == 8


def test_vat_prefixes_differ_from_the_country_exactly_where_declared(rows, demo_expected) -> None:
    """AR-VAL-001/AP-VAL-001: Präfix ≠ Sitzland nur bei den 25 gesetzten Konten."""
    mismatched = set()
    for table, side, key in (("KNA1", "C", "KUNNR"), ("LFA1", "V", "LIFNR")):
        for row in rows[table]:
            value = row["STCEG"].replace(" ", "")
            if len(value) >= 4 and value[:2].isalpha() and value[:2] != row["LAND1"]:
                mismatched.add(f"{side}:{row[key]}")
    expected = {e.bp_key for e in demo_expected if e.rule_id in ("AR-VAL-001", "AP-VAL-001")}
    assert mismatched == expected
    assert len(expected) == 25


def test_tax_number_variant_carries_no_letter_prefix(defects, rows) -> None:
    """D-058: die Steuernummer im Feld STCEG ist ein Format-, kein Präfixfehler."""
    keys = [
        key
        for defect in defects
        if defect.type == "vat_format" and defect.params.get("variant") == "steuernummer"
        for key in defect.params["bp_keys"]
    ]
    assert len(keys) == 5
    for bp_key in keys:
        value = _master(rows, bp_key)["STCEG"]
        assert "/" in value
        assert not value[:2].isalpha(), "sonst griffe zusätzlich AR-VAL-001"


def test_placeholder_names_are_in_the_master_data(defects, rows) -> None:
    """AR-VAL-005: zehn Debitoren mit Platzhalter statt Firmenname."""
    targets = [t for d in defects if d.type == "placeholder_name" for t in d.params["targets"]]
    assert len(targets) == 10
    for target in targets:
        assert _master(rows, target["bp_key"])["NAME1"] == target["name"]


def test_shared_bank_accounts_are_exactly_the_declared_pairs(rows, demo_expected) -> None:
    """AP-CON-001: vier Kreditorenpaare mit derselben Bankverbindung."""
    owners = defaultdict(set)
    for row in rows["LFBK"]:
        owners[(row["BANKS"], row["BANKL"], row["BANKN"])].add(row["LIFNR"])
    shared = [numbers for numbers in owners.values() if len(numbers) > 1]
    assert len(shared) == 4
    leaders = {e.bp_key for e in demo_expected if e.rule_id == "AP-CON-001"}
    assert all(any(f"V:{number}" in leaders for number in group) for group in shared)


def test_central_payers_are_linked_through_knvp(defects, rows) -> None:
    """Negativfall: gleiche Bank und Adresse, aber Partnerrolle RG – keine Dublette."""
    payers = [d for d in defects if d.type == "central_payer"]
    assert len(payers) == 30
    regulators = {row["KUNNR"]: row["KUNN2"] for row in rows["KNVP"] if row["PARVW"] == "RG"}
    for defect in payers:
        member = defect.params["member"].split(":")[1]
        assert regulators[member] == defect.params["payer"].split(":")[1]


def test_one_time_lookalikes_stay_one_time_accounts(defects, rows) -> None:
    """Negativfall: CpD-Konten werden nie auf Dubletten geprüft, auch bei gleichem Namen."""
    keys = _targets(defects, "one_time_lookalike")
    assert len(keys) == 10
    for bp_key in keys:
        assert _master(rows, bp_key)["XCPDK"] == "X"


def test_unapplied_cash_payments_are_open_and_old_enough(defects, items_by_account) -> None:
    """AR-LEA-001: Zahlungseingang ohne Rechnungsbezug, älter als 30 Tage."""
    targets = [t for d in defects if d.type == "unapplied_cash" for t in d.params["targets"]]
    assert len(targets) == 6
    for target in targets:
        number = target["bp_key"].split(":")[1]
        akonto = [i for i in items_by_account["C"][number] if i["BLART"] == "DZ" and i["_open"]]
        assert len(akonto) == 1
        assert akonto[0]["ZUONR"] == "" and akonto[0]["AUGBL"] == ""
        assert (DATA_AS_OF - parse_date(akonto[0]["BUDAT"])).days > 30


# --- Muster von AP-LEA-001 -------------------------------------------------------------


def _normalize(reference: str) -> str:
    return "".join(char for char in reference if char.isalnum()).lower()


def _levenshtein(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, start=1):
        current = [i]
        for j, b in enumerate(right, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def test_double_payment_pattern_matches_the_declared_defects(defects, items_by_account) -> None:
    """Kein Belegpaar im Muster von AP-LEA-001, das kein Defekt gesetzt hat (D-045).

    Gesucht wird das rohe Muster auf **einem** Konto: zwei bezahlte Rechnungen mit gleichem
    Betrag, höchstens 60 Tage auseinander, Referenzen normalisiert gleich oder mit Abstand 1.
    Die Netting-Prüfung der Regel gehört nicht hierher – die drei genetteten Paare müssen
    also gefunden werden, sie sind erst in der Regel ausgeschlossen.
    """
    found = set()
    for number, items in items_by_account["V"].items():
        invoices = [i for i in items if i["BLART"] == "KR" and not i["_open"]]
        for index, first in enumerate(invoices):
            for second in invoices[index + 1:]:
                if parse_amount(first["WRBTR"]) != parse_amount(second["WRBTR"]):
                    continue
                gap = abs((parse_date(first["BLDAT"]) - parse_date(second["BLDAT"])).days)
                if gap > 60:
                    continue
                if _levenshtein(_normalize(first["XBLNR"]), _normalize(second["XBLNR"])) <= 1:
                    found.add((f"V:{number}", *sorted((first["BELNR"], second["BELNR"]))))

    declared = {
        defect.params.get("bp_key")
        for defect in defects
        if defect.type == "double_payment" and defect.params.get("bp_key")
    }
    declared.add("V:0000200845")  # Ankerfall F-003
    assert {entry[0] for entry in found} == declared
    assert len(found) == 11, "8 gemeldete Paare auf einem Konto plus 3 genettete"


# --- Belegungsplan ---------------------------------------------------------------------


def _conflict_file(tmp_path, overlaps: bool):
    path = tmp_path / "defects.yaml"
    second_overlaps = "    overlaps: [DEF-A]\n" if overlaps else ""
    path.write_text(
        'version: "0.1"\n'
        f"seed: {DEFAULT_SEED}\n"
        "defects:\n"
        "  - id: DEF-A\n    type: dormant_account\n"
        '    note: "Erster Zugriff auf das Konto."\n'
        '    params: { bp_keys: ["C:0000100000"] }\n'
        "    expected:\n      - { rule_id: AR-HYG-001 }\n"
        "  - id: DEF-B\n    type: dormant_account\n"
        '    note: "Zweiter Zugriff auf dasselbe Konto."\n'
        '    params: { bp_keys: ["C:0000100000"] }\n'
        f"{second_overlaps}"
        "    expected:\n      - { rule_id: AR-HYG-001 }\n",
        encoding="utf-8",
    )
    return path


def test_two_defects_on_one_account_need_an_overlap_declaration(tmp_path) -> None:
    """Sonst entstünde ein Finding, das kein Defekt allein erklärt."""
    defects = load_defects(_conflict_file(tmp_path, overlaps=False), DEFAULT_SEED)
    with pytest.raises(DefectError, match="overlaps"):
        build_client(DEFAULT_SEED, defects)


def test_declared_overlap_is_allowed(tmp_path) -> None:
    """Gewollte Doppelbelegung – etwa Dublette und falsches USt-ID-Präfix auf einem Konto."""
    defects = load_defects(_conflict_file(tmp_path, overlaps=True), DEFAULT_SEED)
    client = build_client(DEFAULT_SEED, defects)
    assert len(client.expected) == 2
