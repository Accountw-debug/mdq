"""Was die AP-Regeln liefern – geprueft am Lauf des Demo-Mandanten.

Dieselbe Arbeitsteilung wie in `test_rules_ar.py`: die Regression (`test_regression.py`)
prueft, **welche** Findings entstehen, hier steht, **wie** sie aussehen – Maskierung,
Stufe, Soll. Beide teilen sich den Lauf aus `regression_run` (conftest).
"""

import re

from .conftest import findings_of

#: Eine Folge aus zwei Buchstaben und mindestens zehn weiteren Zeichen ohne Trenner ist
#: eine unmaskierte IBAN. Die Maske (`DE44 … 4932`) enthaelt Leerzeichen und ist kuerzer.
IBAN_LIKE = re.compile(r"[A-Z]{2}[0-9][0-9][A-Za-z0-9]{10,}")


def _all_text(value) -> list[str]:
    """Jede Zeichenkette irgendwo in einem Finding – auch tief in evidence/records."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _all_text(item)]
    if isinstance(value, list):
        return [text for item in value for text in _all_text(item)]
    return []

# --- AP-VAL-001 – USt-ID-Praefix passt nicht zum Sitzland ----------------------------


def test_ap_val_001_liefert_die_zehn_kreditoren(regression_run) -> None:
    findings = findings_of(regression_run, "AP-VAL-001")
    assert sorted(f["entity"]["bp_key"] for f in findings) == [
        "V:0000200025",
        "V:0000200030",
        "V:0000200033",
        "V:0000200037",
        "V:0000200039",
        "V:0000200048",
        "V:0000200053",
        "V:0000200057",
        "V:0000200059",
        "V:0000200060",
    ]


def test_ap_val_001_trifft_nur_kreditoren(regression_run) -> None:
    """Der Rollenfilter: die gleichgelagerten Debitoren gehoeren zu AR-VAL-001."""
    for finding in findings_of(regression_run, "AP-VAL-001"):
        assert finding["entity"]["role"] == "VENDOR"
        assert finding["entity"]["bp_key"].startswith("V:")
        assert finding["current"]["source_table"] == "LFA1"


def test_ap_val_001_schlaegt_das_praefix_des_sitzlandes_vor(regression_run) -> None:
    """Stufe B mit Soll: das Praefix wird ersetzt, der Rest der Nummer bleibt stehen."""
    findings = findings_of(regression_run, "AP-VAL-001")
    assert findings, "ohne Findings prueft dieser Test nichts"
    for finding in findings:
        ist = finding["current"]["value"]
        soll = finding["proposed"]["value"]
        assert finding["tier"] == "B"
        assert soll.startswith("DE")           # alle zehn sitzen in DE
        assert soll != ist
        assert soll[2:] == ist.replace(" ", "")[2:]
        # Stufe B heisst hier "ohne VIES bestaetigt" - die Quellenlage sagt es
        assert "VIES" in finding["proposed"]["source_summary"]


# --- AP-VAL-002 – Format der USt-IdNr. -----------------------------------------------


def test_ap_val_002_liefert_die_fuenf_formatfehler(regression_run) -> None:
    findings = findings_of(regression_run, "AP-VAL-002")
    assert sorted(f["entity"]["bp_key"] for f in findings) == [
        "V:0000200061",
        "V:0000200064",
        "V:0000200067",
        "V:0000200068",
        "V:0000200071",
    ]


def test_ap_val_002_und_ap_val_001_teilen_sich_kein_konto(regression_run) -> None:
    """Praefixfehler und Formatfehler schliessen einander aus (D-058).

    Ein Wert ohne Buchstabenpraefix behauptet kein Land und kann dem Sitzland nicht
    widersprechen; ein Wert mit fremdem, aber formal gueltigem Praefix verletzt kein
    Muster. Traegt ein Konto beide Findings, ist eine der beiden Regeln zu weit.
    """
    praefix = {f["entity"]["bp_key"] for f in findings_of(regression_run, "AP-VAL-001")}
    format_ = {f["entity"]["bp_key"] for f in findings_of(regression_run, "AP-VAL-002")}
    assert praefix and format_, "ohne Findings prueft dieser Test nichts"
    assert not praefix & format_


def test_ap_val_002_nennt_die_steuernummer_im_falschen_feld(regression_run) -> None:
    """Der haeufigste Fall der Praxis bekommt seinen eigenen Klartext (D-058)."""
    ohne_praefix = [
        f
        for f in findings_of(regression_run, "AP-VAL-002")
        if f["entity"]["bp_key"] in {"V:0000200061", "V:0000200064"}
    ]
    assert len(ohne_praefix) == 2
    for finding in ohne_praefix:
        assert "Steuernummer" in finding["current"]["display"]
        assert "STCD1" in " ".join(finding["remediation"]["steps"])


def test_ap_val_002_schlaegt_kein_soll_vor(regression_run) -> None:
    """Das richtige Format sagt nichts ueber die richtige Nummer (D-186)."""
    findings = findings_of(regression_run, "AP-VAL-002")
    assert findings, "ohne Findings prueft dieser Test nichts"
    for finding in findings:
        assert finding["tier"] == "C"
        assert "proposed" not in finding


# --- AP-VAL-003 – IBAN-Pruefziffer ---------------------------------------------------


def test_ap_val_003_liefert_die_fuenf_kreditoren(regression_run) -> None:
    findings = findings_of(regression_run, "AP-VAL-003")
    assert sorted(f["entity"]["bp_key"] for f in findings) == [
        "V:0000200072",
        "V:0000200073",
        "V:0000200075",
        "V:0000200077",
        "V:0000201330",
    ]


def test_ap_val_003_maskiert_nach_dem_schema(regression_run) -> None:
    """Vier Stellen vorn, vier hinten, dazwischen die Ellipse (finding.schema.json)."""
    maske = re.compile(r"^[A-Z0-9]{4} … [A-Z0-9]{4}$")
    findings = findings_of(regression_run, "AP-VAL-003")
    assert findings, "ohne Findings prueft dieser Test nichts"
    for finding in findings:
        assert maske.match(finding["current"]["value"]), finding["current"]["value"]


def test_ap_val_003_nennt_bankschluessel_und_bankdetail(regression_run) -> None:
    """Maskiert, aber auffindbar: BANKL und BVTYP identifizieren die Bankverbindung
    im Stammsatz, ohne die Kontonummer zu nennen (D-105)."""
    for finding in findings_of(regression_run, "AP-VAL-003"):
        referenz = finding["evidence"][0]["reference"]
        assert referenz.startswith("TIBAN BANKL ")
        assert " / BVTYP " in referenz


def test_ar_val_003_nennt_bankschluessel_und_bankdetail(regression_run) -> None:
    """Derselbe Nachzug in der AR-Schwester – D-105 gilt fuer beide Regeln."""
    findings = findings_of(regression_run, "AR-VAL-003")
    assert findings, "ohne Findings prueft dieser Test nichts"
    for finding in findings:
        referenz = finding["evidence"][0]["reference"]
        assert referenz.startswith("TIBAN BANKL ")
        assert " / BVTYP " in referenz


def test_ap_val_003_bleibt_stufe_c_ohne_soll(regression_run) -> None:
    """Aus einer falschen IBAN folgt keine richtige – und Klasse 1 wird nie Stufe A."""
    for finding in findings_of(regression_run, "AP-VAL-003"):
        assert finding["tier"] == "C"
        assert finding["damage_class"] == 1
        assert "proposed" not in finding           # kein Soll, kein Vorschlag (D-186)
        assert finding["remediation"]["mass_change_eligible"] is False


# --- Maskierung, ueber den ganzen Lauf (D-105) ---------------------------------------


#: Regeln, die Bankdaten ins Finding schreiben. Ueber genau sie laeuft die Kehrmaschine.
#: Ein laufweiter Test ist nicht moeglich: eine USt-IdNr. hat dieselbe Form wie eine IBAN
#: ("NL130921080B80"), und ein Formmuster kann beide nicht trennen. Waechst die Liste um
#: eine Regel, die Bankdaten traegt, gehoert sie hier hinein - `test_bankdatenregeln_sind_
#: vollstaendig` haelt fest, dass keine vergessen wird.
BANKDATENREGELN = ("AR-VAL-003", "AP-VAL-003")


def test_bankdatenregeln_zeigen_nirgends_eine_vollstaendige_iban(regression_run) -> None:
    """Schadensklasse 1: die IBAN steht nur maskiert im Finding (Regel 8, D-105).

    Geprueft wird **jede Zeichenkette jedes Findings** dieser Regeln - `current`,
    `evidence`, `records`, `source_summary`, `params`, `title` -, nicht nur die Felder,
    an die man beim Schreiben der Regel denkt. D-105 hat den Test fuer AR-VAL-003
    eingefuehrt; AP-VAL-003 laeuft jetzt mit, AP-CON-001 kommt mit seiner Regel dazu.
    """
    for rule_id in BANKDATENREGELN:
        findings = findings_of(regression_run, rule_id)
        assert findings, f"{rule_id} liefert nichts - dieser Test prueft dann nichts"
        for finding in findings:
            for text in _all_text(finding):
                assert not IBAN_LIKE.search(text), (
                    f"unmaskierte IBAN in {rule_id} {finding['entity']['bp_key']}"
                )


def test_bankdatenregeln_sind_vollstaendig() -> None:
    """Jede gebaute Regel, die `bp_bank_account` liest, steht in `BANKDATENREGELN`.

    Sonst waechst die Engine um eine Regel mit Bankdaten, und die Kehrmaschine laeuft
    stillschweigend an ihr vorbei.
    """
    from mdq.rules import load_rules

    mit_bankdaten = {
        rule.id for rule in load_rules() if "bp_bank_account" in rule.requires_tables
    }
    assert mit_bankdaten == set(BANKDATENREGELN)


def test_kein_beispiel_finding_zeigt_eine_vollstaendige_iban(example_findings_dir) -> None:
    """Dieselbe Kehrmaschine ueber `logic/examples/findings/` (D-105, D-069 Punkt 3).

    F-006 zeigte die IBAN bis Aufgabe 7 vollstaendig; ohne diesen Test faellt ein
    Rueckfall dorthin niemandem auf, weil das Schema den Freitext in `current.value`
    nicht gegen das Maskenmuster prueft.
    """
    for path in sorted(example_findings_dir.glob("*.yaml")):
        treffer = IBAN_LIKE.search(path.read_text(encoding="utf-8"))
        assert treffer is None, f"unmaskierte IBAN in {path.name}"


# --- AP-HYG-001 – Loeschkandidaten ----------------------------------------------------


def test_ap_hyg_001_liefert_die_fuenfundzwanzig_stillgelegten_konten(regression_run) -> None:
    findings = findings_of(regression_run, "AP-HYG-001")
    assert len(findings) == 25
    assert all(f["entity"]["bp_key"].startswith("V:") for f in findings)


def test_ap_hyg_001_entscheidet_nicht_sondern_legt_optionen_vor(regression_run) -> None:
    """Loeschen, behalten oder sperren haengt an Fristen, nicht an den Daten (D-111)."""
    findings = findings_of(regression_run, "AP-HYG-001")
    assert findings, "ohne Findings prueft dieser Test nichts"
    for finding in findings:
        assert finding["tier"] == "decision"
        assert finding["action_type"] == "decision"
        assert len(finding["proposed"]["options"]) == 3
        assert "value" not in finding["proposed"] or finding["proposed"]["value"] is None


def test_ap_hyg_001_traegt_keine_offenen_posten(regression_run) -> None:
    """Die Bedingung aus der AR-Schwester gilt hier genauso.

    Eine Loeschung scheitert in SAP, solange eine Verbindlichkeit offen ist – ein
    Loeschvorschlag auf einem Konto mit offenem Posten waere ein Vorschlag ins Leere.
    """
    findings = findings_of(regression_run, "AP-HYG-001")
    assert findings, "ohne Findings prueft dieser Test nichts"
    for finding in findings:
        assert finding["relevance"]["open_items"] == "0.00"


def test_ap_hyg_001_und_ar_hyg_001_sind_deckungsgleich(regression_run) -> None:
    """Zwillinge: gleiche Bedingungen, gleiche Optionen, nur die Seite unterscheidet sie."""
    ar = findings_of(regression_run, "AR-HYG-001")
    ap = findings_of(regression_run, "AP-HYG-001")
    assert ar and ap, "ohne Findings prueft dieser Test nichts"
    assert {o["label"] for o in ar[0]["proposed"]["options"]} == {
        o["label"] for o in ap[0]["proposed"]["options"]
    }
    assert ar[0]["current"]["display"] == ap[0]["current"]["display"]
    assert ar[0]["remediation"]["sap_transaction"] == "XD06"
    assert ap[0]["remediation"]["sap_transaction"] == "XK06"


# --- AP-COM-003 – Pruefung auf doppelte Rechnung -------------------------------------


def test_ap_com_003_liefert_dreissig_findings_je_buchungskreis(regression_run) -> None:
    findings = findings_of(regression_run, "AP-COM-003")
    assert len(findings) == 30
    assert all(f["entity"].get("company_code") for f in findings)


def test_ap_com_003_ist_die_erste_stufe_a_regel(regression_run) -> None:
    """Stufe A mit Massenaenderung – erlaubt, weil das Kennzeichen keinen Wert ueberschreibt.

    Das Schema verlangt bei Stufe A/B ein `proposed`; hier ist es das gesetzte
    Ankreuzfeld. `mass_change` setzt Stufe A voraus (finding.schema.json), und
    Schadensklasse 1 waere von A ausgeschlossen (Regel 11) – diese Regel ist Klasse 3.
    """
    findings = findings_of(regression_run, "AP-COM-003")
    assert findings, "ohne Findings prueft dieser Test nichts"
    for finding in findings:
        assert finding["tier"] == "A"
        assert finding["action_type"] == "mass_change"
        assert finding["damage_class"] == 3
        assert finding["proposed"]["value"] == "X"
        assert finding["remediation"]["mass_change_eligible"] is True


def test_ap_com_003_begruendet_das_soll_aus_der_eigenen_praxis(regression_run) -> None:
    """Die Quellenlage zaehlt, nicht eine Regel von aussen (Muster aus D-108)."""
    for finding in findings_of(regression_run, "AP-COM-003"):
        summary = finding["proposed"]["source_summary"]
        assert "1497 von 1527" in summary
        assert "tragen das Kennzeichen bereits" in summary


def test_ap_com_003_trifft_nur_kreditoren(regression_run) -> None:
    """REPRF gibt es nur in LFB1; KNB1 kennt das Feld nicht."""
    for finding in findings_of(regression_run, "AP-COM-003"):
        assert finding["entity"]["role"] == "VENDOR"
        assert finding["current"]["source_table"] == "LFB1"
        assert finding["current"]["value"] is None
