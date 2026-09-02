"""Was die AP-Regeln liefern – geprueft am Lauf des Demo-Mandanten.

Dieselbe Arbeitsteilung wie in `test_rules_ar.py`: die Regression (`test_regression.py`)
prueft, **welche** Findings entstehen, hier steht, **wie** sie aussehen – Maskierung,
Stufe, Soll. Beide teilen sich den Lauf aus `regression_run` (conftest).
"""

import re

import yaml

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


def test_ap_val_003_beziffert_die_offenen_posten(regression_run) -> None:
    """Die Euro-Wirkung ist der Betrag, der ueber diese Bankverbindung hinausginge.

    Er kommt aus `bp_relevance.open_items_local` und steht deshalb Cent-genau auch in
    `relevance.open_items` desselben Findings - zwei Wege zur selben Zahl.
    """
    findings = [f for f in findings_of(regression_run, "AP-VAL-003") if f.get("impact_eur")]
    assert findings, "ohne Findings mit Euro-Wirkung prueft dieser Test nichts"
    for finding in findings:
        impact = finding["impact_eur"]
        assert impact["amount"] == finding["relevance"]["open_items"]
        assert impact["currency"] == finding["relevance"]["currency"]
        assert impact["formula"].endswith(", die an diese IBAN gezahlt würden")


def test_ap_val_003_ohne_offene_posten_kein_impact(regression_run) -> None:
    """Grenzfall: kein offener Posten, keine Zahl - und keine behauptete 0,00 (Regel 4)."""
    ohne_op = [
        f for f in findings_of(regression_run, "AP-VAL-003")
        if f["relevance"]["open_items"] == "0.00"
    ]
    assert ohne_op, "ohne einen Kreditor ohne offene Posten prueft dieser Test nichts"
    for finding in ohne_op:
        assert "impact_eur" not in finding


def test_ap_val_003_reproduziert_f006_woertlich(regression_run, example_findings_dir) -> None:
    """F-006 ist Victors Spec und nennt die Euro-Wirkung; bis Aufgabe 7 lieferte die
    Regel keine. Dieser Test haelt fest, dass der Lauf den Ankerfall jetzt Wort fuer
    Wort trifft - Betrag, Waehrung und Formel."""
    beispiel = yaml.safe_load(
        (example_findings_dir / "F-006-AP-VAL-003.yaml").read_text(encoding="utf-8")
    )
    anker = beispiel["entity"]["bp_key"]
    finding = next(
        f for f in findings_of(regression_run, "AP-VAL-003") if f["entity"]["bp_key"] == anker
    )
    assert finding["impact_eur"]["amount"] == beispiel["impact_eur"]["amount"] == "27300.00"
    assert finding["impact_eur"]["currency"] == beispiel["impact_eur"]["currency"]
    assert finding["impact_eur"]["formula"] == beispiel["impact_eur"]["formula"]


def test_die_val_003_zwillinge_formulieren_rollengerecht(regression_run) -> None:
    """Dieselbe Rechnung, zwei Saetze: beim Kreditor geht Geld hinaus, beim Debitor wird
    es eingezogen (D-188 - wo die Zwillinge abweichen, weicht die Seite ab, nicht die
    Logik)."""
    ap = [f for f in findings_of(regression_run, "AP-VAL-003") if f.get("impact_eur")]
    ar = [f for f in findings_of(regression_run, "AR-VAL-003") if f.get("impact_eur")]
    assert ap and ar
    assert all(f["impact_eur"]["formula"].startswith("Offene Posten ") for f in ap + ar)
    assert all("an diese IBAN gezahlt würden" in f["impact_eur"]["formula"] for f in ap)
    assert all("über diese IBAN per Lastschrift eingezogen würden" in
               f["impact_eur"]["formula"] for f in ar)


# --- Maskierung, ueber den ganzen Lauf (D-105) ---------------------------------------


#: Regeln, die Bankdaten ins Finding schreiben. Ueber genau sie laeuft die Kehrmaschine.
#: Ein laufweiter Test ist nicht moeglich: eine USt-IdNr. hat dieselbe Form wie eine IBAN
#: ("NL130921080B80"), und ein Formmuster kann beide nicht trennen. Waechst die Liste um
#: eine Regel, die Bankdaten traegt, gehoert sie hier hinein - `test_bankdatenregeln_sind_
#: vollstaendig` haelt fest, dass keine vergessen wird.
#: CROSS-DUP-001 laeuft mit, obwohl es im Demo-Mandanten keinen Bank-Treffer gibt:
#: die Regel *kann* eine IBAN ins Finding schreiben, und genau das entscheidet.
BANKDATENREGELN = ("AR-VAL-003", "AP-VAL-003", "AP-CON-001", "CROSS-DUP-001")


def test_bankdatenregeln_zeigen_nirgends_eine_vollstaendige_iban(regression_run) -> None:
    """Schadensklasse 1: die IBAN steht nur maskiert im Finding (Regel 8, D-105).

    Geprueft wird **jede Zeichenkette jedes Findings** dieser Regeln - `current`,
    `evidence`, `records`, `source_summary`, `params`, `title` -, nicht nur die Felder,
    an die man beim Schreiben der Regel denkt. D-105 hat den Test fuer AR-VAL-003
    eingefuehrt; AP-VAL-003 und AP-CON-001 laufen jetzt mit.
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


# --- AP-CON-001 – dieselbe Bankverbindung bei mehreren Kreditoren --------------------


def test_ap_con_001_liefert_ein_finding_je_cluster(regression_run) -> None:
    """Vier Cluster, vier Findings – der Anker ist der kleinste bp_key des Clusters."""
    findings = findings_of(regression_run, "AP-CON-001")
    assert sorted(f["entity"]["bp_key"] for f in findings) == [
        "V:0000200193",
        "V:0000200195",
        "V:0000200199",
        "V:0000200204",
    ]


def test_ap_con_001_nennt_die_uebrigen_konten_als_verwandt(regression_run) -> None:
    """Die zweiten Konten tragen kein eigenes Finding, sie stehen im Finding des Ankers."""
    verwandt = {
        key
        for finding in findings_of(regression_run, "AP-CON-001")
        for key in finding["entity"]["related_bp_keys"]
    }
    assert verwandt == {"V:0000200194", "V:0000200197", "V:0000200203", "V:0000200214"}
    anker = {f["entity"]["bp_key"] for f in findings_of(regression_run, "AP-CON-001")}
    assert not anker & verwandt


def test_ap_con_001_traegt_beide_konten_als_records(regression_run) -> None:
    """Die Referenzform fuer Sprint 4: je beteiligtem Konto ein Vergleichsdatensatz
    (D-069 Punkt 3 und 4). Der Anker steht mit darin – sonst fehlte in der Tabelle
    genau die Zeile, gegen die verglichen wird."""
    findings = findings_of(regression_run, "AP-CON-001")
    assert findings, "ohne Findings prueft dieser Test nichts"
    for finding in findings:
        records = finding["entity"]["records"]
        assert len(records) == 2
        keys = [record["bp_key"] for record in records]
        assert keys == sorted(keys)
        assert finding["entity"]["bp_key"] in keys
        for record in records:
            felder = record["fields"]
            assert felder["name"]
            assert felder["currency"] == "EUR"
            # Beide Konten teilen sich dieselbe Bankverbindung - das ist der Befund
            assert felder["iban_masked"] == finding["current"]["value"]


def test_ap_con_001_bleibt_stufe_c_ohne_soll(regression_run) -> None:
    """Welches Konto bleibt, ist eine Entscheidung mit Blick in die Beziehung (D-186)."""
    findings = findings_of(regression_run, "AP-CON-001")
    assert findings, "ohne Findings prueft dieser Test nichts"
    for finding in findings:
        assert finding["tier"] == "C"
        assert finding["damage_class"] == 1
        assert "proposed" not in finding
        assert finding["remediation"]["mass_change_eligible"] is False


def test_ap_con_001_belegt_den_regulierer_ausschluss(regression_run) -> None:
    """Die zweite Evidenz haelt fest, dass nach einem Regulierer gesucht wurde.

    Im Demo-Mandanten ist die Klausel nicht ausgeuebt – alle `central_payer`-Defekte
    sind Debitoren, kein Kreditor traegt einen alt_payer_key (R2). Belegt ist damit
    nicht die Wirkung der Klausel, sondern dass das Finding sie ausweist.
    """
    for finding in findings_of(regression_run, "AP-CON-001"):
        gruende = [e["value"] for e in finding["evidence"]]
        assert "kein Regulierer hinterlegt" in gruende


def test_ap_con_001_meldet_keinen_zentralregulierer(regression_run) -> None:
    """Gegenprobe auf der AR-Seite: die Regulierer-Cluster (DEF-0120 ff.) tauchen nirgends
    auf – weder hier (falsche Seite) noch als zweites Konto eines Clusters."""
    beteiligt = {
        key
        for finding in findings_of(regression_run, "AP-CON-001")
        for key in [finding["entity"]["bp_key"], *finding["entity"]["related_bp_keys"]]
    }
    assert not any(key.startswith("C:") for key in beteiligt)


# --- AP-LEA-002 – Skontoverlust -------------------------------------------------------


def test_ap_lea_002_liefert_die_acht_kreditoren(regression_run) -> None:
    findings = findings_of(regression_run, "AP-LEA-002")
    assert sorted(
        (f["entity"]["bp_key"], f["entity"]["company_code"]) for f in findings
    ) == [
        ("V:0000200117", "1000"),
        ("V:0000200177", "1000"),
        ("V:0000200180", "1000"),
        ("V:0000200181", "1000"),
        ("V:0000200186", "2000"),
        ("V:0000200188", "1000"),
        ("V:0000200190", "1000"),
        ("V:0000200191", "1000"),
    ]


def test_ap_lea_002_trifft_den_ankerfall_aus_f005(regression_run) -> None:
    """F-005 ist Victors fachliche Spec fuer diese Regel – der Lauf muss sie treffen.

    Verglichen werden die Zahlen, die aus den Daten kommen: 23 von 31 Rechnungen,
    Skontobasis 240.620,00 EUR, Verlust 4.812,40 EUR bei 2 % und Zahlungsbedingung ZB02.
    """
    finding = next(
        f
        for f in findings_of(regression_run, "AP-LEA-002")
        if f["entity"]["bp_key"] == "V:0000200117"
    )
    assert finding["title"] == "Skontoverlust 12 Monate: 4.812,40 EUR bei 23 Rechnungen"
    assert finding["current"]["display"].startswith("23 von 31 Rechnungen nach Skontofrist")
    assert "ZB02" in finding["current"]["display"]
    assert finding["impact_eur"]["amount"] == "4812.40"
    assert finding["impact_eur"]["currency"] == "EUR"
    assert "240.620,00 EUR × 2 %" in finding["impact_eur"]["formula"]


def test_ap_lea_002_haelt_die_drei_toepfe_auseinander(regression_run) -> None:
    """Realisiert, verfallen-unbezahlt, vermeidbar – nur der dritte ist ein Versprechen.

    `impact_eur` traegt allein den realisierten Verlust; die beiden offenen Toepfe stehen
    in der Evidenz, und ihre Summen sind verschieden benannt.
    """
    findings = findings_of(regression_run, "AP-LEA-002")
    assert findings, "ohne Findings prueft dieser Test nichts"
    for finding in findings:
        offen = next(e for e in finding["evidence"] if e["reference"].startswith("BSIK"))
        assert "verfallen)" in offen["value"]
        assert "vermeidbar)" in offen["value"]
        assert offen["agrees"] is False
        # Der Schaden ist der realisierte Verlust, nicht die Summe aller drei Toepfe
        assert finding["impact_eur"]["amount"] != "0.00"


def test_ap_lea_002_verspricht_nur_was_zu_holen_ist(regression_run) -> None:
    """Der Handlungssatz nennt einen vermeidbaren Betrag nur, wenn es einen gibt.

    Genau ein Kreditor des Demo-Mandanten hat eine offene Rechnung mit laufender
    Skontofrist; bei den uebrigen sieben sagt der Satz ausdruecklich, dass nichts mehr
    zu holen ist – sonst laese der Bericht sich wie eine Einsparung.
    """
    mit_rest, ohne_rest = [], []
    for finding in findings_of(regression_run, "AP-LEA-002"):
        (mit_rest if "vermeidbar" in finding["proposed"]["display"] else ohne_rest).append(
            finding["entity"]["bp_key"]
        )
    assert mit_rest == ["V:0000200117"]
    assert len(ohne_rest) == 7
    for finding in findings_of(regression_run, "AP-LEA-002"):
        if finding["entity"]["bp_key"] in ohne_rest:
            assert "nichts mehr zu holen" in finding["proposed"]["display"]


def test_ap_lea_002_traegt_ein_soll_ohne_wert(regression_run) -> None:
    """Kein Feld ist falsch, sondern ein Takt: der Handlungssatz ist das Soll (D-186)."""
    for finding in findings_of(regression_run, "AP-LEA-002"):
        assert finding["tier"] == "C"
        assert finding["action_type"] == "process"
        assert finding["proposed"]["value"] is None
        assert finding["proposed"]["display"].startswith("Zahllauf-Timing")


def test_ap_lea_002_rechnet_ohne_float(regression_run) -> None:
    """Betraege tragen zwei Dezimalen und keine Fliesskomma-Reste (Regel 2).

    `sum(basis * prozent) / 100` haette in DuckDB ein DOUBLE ergeben – sichtbar an
    Werten wie 1900.0000000000005. Gerechnet wird deshalb mit `* 0.01` in DECIMAL.
    """
    for finding in findings_of(regression_run, "AP-LEA-002"):
        betrag = finding["impact_eur"]["amount"]
        assert re.match(r"^-?[0-9]+\.[0-9]{2}$", betrag), betrag


def test_ap_lea_002_nennt_den_stichtag_des_laufs(regression_run) -> None:
    """Der Zeitraum kommt aus dem Lauf, nicht aus `current_date` (Regel 9).

    Sonst lieferte derselbe Input morgen andere Findings. Taggenau statt als Monatslabel:
    das Fenster beginnt am Stichtag minus zwoelf Monate, nicht am Monatsersten.

    **Der genannte Tag ist der erste eingeschlossene, nicht die Grenze** (D-206): das
    Fenster ist links offen (D-087), Stichtag minus zwoelf Monate ist der 28.08.2025, und
    der erste Beleg, der dazugehoert, ist der vom 29.08.2025. Bis D-206 stand hier die
    ausgeschlossene Grenze – ein Zeiger, der sich inklusiv liest und exklusiv gemeint ist.
    """
    for finding in findings_of(regression_run, "AP-LEA-002"):
        statistik = next(e for e in finding["evidence"] if e["reference"].startswith("BSAK"))
        assert statistik["reference"] == "BSAK 2025-08-29..2026-08-28"
        assert statistik["observed_at"] == "2026-08-28"
