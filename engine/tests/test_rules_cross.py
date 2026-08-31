"""Was CROSS-DUP-001 liefert – geprueft am Lauf des Demo-Mandanten.

Dieselbe Arbeitsteilung wie in `test_rules_ar.py` und `test_rules_ap.py`: die Regression
prueft, **welche** Findings entstehen, hier steht, **wie** sie aussehen – Anker, Cluster,
Vergleichsfelder, Soll.
"""

from .conftest import findings_of

#: Die fuenf Paare aus `defects.yaml` (DEF-0114 bis DEF-0118): Anker ist der Debitor.
PAARE = {
    "C:0000100285": "V:0000200206",
    "C:0000100286": "V:0000200212",
    "C:0000100287": "V:0000200217",
    "C:0000100288": "V:0000200219",
    "C:0000100289": "V:0000200220",
}


def test_cross_dup_001_liefert_die_fuenf_paare(regression_run) -> None:
    findings = findings_of(regression_run, "CROSS-DUP-001")
    assert sorted(f["entity"]["bp_key"] for f in findings) == sorted(PAARE)


def test_cross_dup_001_ankert_auf_dem_debitor(regression_run) -> None:
    """Der Anker sitzt fest auf der Debitorenseite (D-052) – die Kreditorenkonten stehen
    in `related_bp_keys` und tragen kein eigenes Finding. Ein Finding je Debitor, nicht
    je Paar: die Bearbeiterin entscheidet einmal ueber den Sachverhalt."""
    findings = findings_of(regression_run, "CROSS-DUP-001")
    assert findings, "ohne Findings prueft dieser Test nichts"
    for finding in findings:
        anker = finding["entity"]["bp_key"]
        assert anker.startswith("C:")
        assert finding["entity"]["related_bp_keys"] == [PAARE[anker]]
        assert finding["side"] == "CROSS"
        assert finding["entity"]["role"] == "CUSTOMER"


def test_cross_dup_001_liefert_kein_finding_auf_der_kreditorenseite(regression_run) -> None:
    """Der Gegenpart steht im Finding des Ankers – nie mit einem eigenen daneben."""
    anker = {f["entity"]["bp_key"] for f in findings_of(regression_run, "CROSS-DUP-001")}
    assert not {key for key in anker if key.startswith("V:")}
    assert set(PAARE.values()).isdisjoint(anker)


def test_cross_dup_001_vergleicht_feld_fuer_feld(regression_run) -> None:
    """`entity.records` traegt beide Konten – den Anker mit, sonst fehlte die Zeile,
    gegen die verglichen wird (D-190). Die USt-IdNr. ist auf beiden Seiten dieselbe;
    genau das ist der Treffer."""
    for finding in findings_of(regression_run, "CROSS-DUP-001"):
        records = finding["entity"]["records"]
        anker = finding["entity"]["bp_key"]
        assert [r["bp_key"] for r in records] == sorted([anker, PAARE[anker]])
        ust = {r["fields"]["vat_id"] for r in records}
        assert len(ust) == 1 and ust != {None}
        for record in records:
            assert record["fields"]["open_items"] is not None
            assert record["fields"]["currency"] == "EUR"


def test_cross_dup_001_schlaegt_keine_zusammenfuehrung_vor(regression_run) -> None:
    """Stufe B braucht ein Soll, und hier ist es eine Handlung: verrechnen, nicht
    zusammenfuehren. Ein Konto darf zu Recht Kunde und Lieferant sein."""
    for finding in findings_of(regression_run, "CROSS-DUP-001"):
        assert finding["tier"] == "B"
        assert finding["action_type"] == "review"
        proposed = finding["proposed"]
        assert proposed["value"] is None            # kein fuehrendes Konto (D-186)
        assert "nicht zusammenführen" in proposed["display"]
        assert finding["remediation"]["mass_change_eligible"] is False


def test_cross_dup_001_belegt_den_treffer_deterministisch(regression_run) -> None:
    """Kein Fuzzy: die Evidenz nennt das Feld, an dem der Treffer haengt, und den Wert."""
    for finding in findings_of(regression_run, "CROSS-DUP-001"):
        evidence = finding["evidence"]
        assert evidence
        for eintrag in evidence:
            assert eintrag["source_type"] == "deterministic"
            assert eintrag["reference_kind"] == "master_field"
            assert eintrag["agrees"] is True
        assert "kein Namens- oder Adressabgleich" in finding["proposed"]["source_summary"]


def test_cross_dup_001_traegt_keine_euro_wirkung(regression_run) -> None:
    """Hier ist kein Geld abgeflossen – das Aufrechnungspotenzial ist CROSS-LEA-001.
    Was auf beiden Seiten offen steht, zeigt `records` je Konto."""
    for finding in findings_of(regression_run, "CROSS-DUP-001"):
        assert "impact_eur" not in finding


def test_cross_dup_001_nennt_die_iban_nur_beim_bank_treffer(regression_run) -> None:
    """Testluecke, benannt statt verschwiegen (Muster D-191): das IBAN-Kriterium ist im
    Demo-Mandanten nicht ausgeuebt – kein Debitor teilt eine Bankverbindung mit einem
    Kreditor. Solange das so ist, steht in `records` keine IBAN: sie stuende nur da, wo
    sie das Trefferkriterium war und damit fuer alle Konten dieselbe ist. Faellt dieser
    Test aus, gibt es endlich einen Bank-Treffer – dann gehoert er in die `hits` des
    Regelkopfes."""
    for finding in findings_of(regression_run, "CROSS-DUP-001"):
        bank_treffer = any(
            e["reference"].startswith("TIBAN BANKL ") for e in finding["evidence"]
        )
        for record in finding["entity"]["records"]:
            if bank_treffer:
                assert record["fields"]["iban_masked"] is not None
            else:
                assert record["fields"]["iban_masked"] is None
