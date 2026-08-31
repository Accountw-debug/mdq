"""Was die AR-Stammdatenregeln liefern – geprueft am Lauf des Demo-Mandanten.

Die Regression (`test_regression.py`) prueft, **welche** Findings entstehen. Hier steht,
**wie** sie aussehen: Maskierung, Stufe, Soll. Beide teilen sich denselben Lauf
(`regression_run` in der conftest), damit er nur einmal ausgefuehrt wird.
"""

import re

from .conftest import findings_of

#: Eine Folge aus zwei Buchstaben und mindestens zehn weiteren Zeichen ohne Trenner ist
#: eine unmaskierte IBAN. Die Maske (`DE24 … 8226`) enthaelt Leerzeichen und ist kuerzer.
IBAN_LIKE = re.compile(r"[A-Z]{2}[0-9][0-9][A-Za-z0-9]{10,}")


def _all_text(value) -> list[str]:
    """Jede Zeichenkette irgendwo in einem Finding – auch tief in evidence/params."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _all_text(item)]
    if isinstance(value, list):
        return [text for item in value for text in _all_text(item)]
    return []


# --- AR-VAL-003 – IBAN-Pruefziffer ---------------------------------------------------


def test_ar_val_003_liefert_die_drei_erwarteten_konten(regression_run) -> None:
    findings = findings_of(regression_run, "AR-VAL-003")
    # Findings sind nach `finding_id` sortiert (einem Hash), nicht nach Konto
    assert sorted(f["entity"]["bp_key"] for f in findings) == [
        "C:0000100147",
        "C:0000100152",
        "C:0000100157",
    ]


def test_ar_val_003_zeigt_nirgends_eine_vollstaendige_iban(regression_run) -> None:
    """Schadensklasse 1: die IBAN steht nur maskiert im Finding (CLAUDE.md Regel 8).

    Geprueft wird das ganze Finding – `current`, `evidence`, `source_summary`, `params`,
    `title` –, nicht nur die Felder, an die man beim Schreiben der Regel denkt.
    """
    findings = findings_of(regression_run, "AR-VAL-003")
    assert findings, "ohne Findings prueft dieser Test nichts"
    for finding in findings:
        for text in _all_text(finding):
            assert not IBAN_LIKE.search(text), (
                f"unmaskierte IBAN in {finding['rule_id']} {finding['entity']['bp_key']}"
            )


def test_ar_val_003_maskiert_nach_dem_schema(regression_run) -> None:
    """Vier Stellen vorn, vier hinten, dazwischen die Ellipse (finding.schema.json)."""
    maske = re.compile(r"^[A-Z0-9]{4} … [A-Z0-9]{4}$")
    for finding in findings_of(regression_run, "AR-VAL-003"):
        assert maske.match(finding["current"]["value"]), finding["current"]["value"]


def test_ar_val_003_bleibt_stufe_c_ohne_soll(regression_run) -> None:
    """Aus einer falschen IBAN folgt keine richtige – und Klasse 1 wird nie Stufe A."""
    for finding in findings_of(regression_run, "AR-VAL-003"):
        assert finding["tier"] == "C"
        assert finding["damage_class"] == 1
        assert "proposed" not in finding   # kein Soll, kein Vorschlag (D-186)
        assert finding["remediation"]["mass_change_eligible"] is False


# --- AR-COM-002 – Zahlungsbedingung im Buchungskreis leer ----------------------------


def test_ar_com_002_liefert_zwanzig_findings_je_buchungskreis(regression_run) -> None:
    findings = findings_of(regression_run, "AR-COM-002")
    assert len(findings) == 20
    assert all(finding["entity"].get("company_code") for finding in findings)


def test_ar_com_002_stufe_haengt_an_der_mehrheit(regression_run) -> None:
    """Mehrheit auf den Belegen -> Stufe B mit Soll; ohne Mehrheit Stufe C ohne Soll.

    Ein geratenes Soll waere schlimmer als keins: die Zahlungsbedingung verschiebt die
    Faelligkeit jeder kuenftigen Rechnung.
    """
    for finding in findings_of(regression_run, "AR-COM-002"):
        if finding["tier"] == "B":
            assert finding["proposed"]["value"], finding["entity"]["bp_key"]
            assert finding["proposed"]["display"], "Stufe B nennt den Klartext aus T052U"
        else:
            assert finding["tier"] == "C"
            # Ohne Mehrheit gibt es kein Soll und damit kein `proposed` (D-186)
            assert "proposed" not in finding
            assert "ohne Mehrheit" in finding["current"]["display"]


def test_ar_com_002_zaehlt_wie_die_belege_es_hergeben(regression_run) -> None:
    """Die Quellenlage nennt Zaehler und Nenner – 15 mit Mehrheit, 5 ohne (DEF-0047..0066)."""
    findings = findings_of(regression_run, "AR-COM-002")
    stufen = {tier: sum(1 for f in findings if f["tier"] == tier) for tier in ("B", "C")}
    assert stufen == {"B": 15, "C": 5}


# --- AR-VAL-002 – Format der USt-IdNr. -----------------------------------------------


def test_ar_val_002_liefert_die_sieben_formatfehler(regression_run) -> None:
    findings = findings_of(regression_run, "AR-VAL-002")
    assert len(findings) == 7


def test_ar_val_002_und_ar_val_001_teilen_sich_kein_konto(regression_run) -> None:
    """Ein fremdes Praefix in gueltigem Format ist ein Laender-, kein Formatfehler (D-058).

    Waere das Muster nach dem Sitzland gewaehlt, traege jeder AR-VAL-001-Fall zusaetzlich
    ein AR-VAL-002-Finding – zwei Zeilen fuer einen Sachverhalt.
    """
    format_fehler = {f["entity"]["bp_key"] for f in findings_of(regression_run, "AR-VAL-002")}
    praefix_fehler = {f["entity"]["bp_key"] for f in findings_of(regression_run, "AR-VAL-001")}
    assert not (format_fehler & praefix_fehler)


def test_ar_val_002_nennt_die_steuernummer_im_falschen_feld(regression_run) -> None:
    """Der haeufigste Formatfehler der Praxis bekommt seinen eigenen Hinweis (D-058)."""
    ohne_praefix = [
        f
        for f in findings_of(regression_run, "AR-VAL-002")
        if "Länderpräfix" in f["current"]["display"]
    ]
    assert len(ohne_praefix) == 3   # DEF-0039
    for finding in ohne_praefix:
        # Der Hinweis steht seit D-186 unter `remediation`, nicht in einem Leervorschlag
        assert any("STCD1" in schritt for schritt in finding["remediation"]["steps"])


def test_ar_val_002_schlaegt_kein_soll_vor(regression_run) -> None:
    """Das richtige Format sagt nichts ueber die richtige Nummer – dafuer braucht es VIES."""
    for finding in findings_of(regression_run, "AR-VAL-002"):
        assert finding["tier"] == "C"
        assert "proposed" not in finding
        assert "VIES" in finding["why"]


# --- AR-HYG-001 – Löschkandidaten ----------------------------------------------------


def test_ar_hyg_001_liefert_die_vierzig_stillgelegten_konten(regression_run) -> None:
    assert len(findings_of(regression_run, "AR-HYG-001")) == 40


def test_ar_hyg_001_entscheidet_nicht_sondern_legt_optionen_vor(regression_run) -> None:
    """Ob ein ruhendes Konto geloescht wird, haengt an Fristen, nicht an den Daten."""
    for finding in findings_of(regression_run, "AR-HYG-001"):
        assert finding["tier"] == "decision"
        assert finding["action_type"] == "decision"
        assert finding["proposed"]["value"] is None
        assert len(finding["proposed"]["options"]) == 3
        assert finding["remediation"]["mass_change_eligible"] is False


def test_ar_hyg_001_nennt_den_fensterbeginn_des_laufs(regression_run) -> None:
    """Der Fensterbeginn kommt vom Lauf, nicht aus der Regel (D-110)."""
    fenster = regression_run.report.scope["item_window_from_effective"]
    assert fenster == "2024-09-02"
    for finding in findings_of(regression_run, "AR-HYG-001"):
        assert fenster in finding["title"]
        assert fenster in finding["proposed"]["source_summary"]


# --- AR-VAL-005 – Platzhalter in Name und Ort ----------------------------------------


def test_ar_val_005_liefert_die_zehn_platzhalterkonten(regression_run) -> None:
    assert len(findings_of(regression_run, "AR-VAL-005")) == 10


def test_ar_val_005_nennt_den_getroffenen_begriff(regression_run) -> None:
    """Die Karte soll zeigen, *warum* der Wert ein Platzhalter ist, nicht nur dass."""
    for finding in findings_of(regression_run, "AR-VAL-005"):
        assert "Platzhalter" in finding["current"]["display"]
        begriff = finding["evidence"][0]["value"]
        assert begriff and begriff in finding["current"]["value"].lower()


def test_ar_val_005_ein_finding_je_konto(regression_run) -> None:
    """Name und Ort zugleich ergeben ein Finding, nicht zwei (kein finding_key noetig)."""
    konten = [f["entity"]["bp_key"] for f in findings_of(regression_run, "AR-VAL-005")]
    assert len(konten) == len(set(konten))


def test_ar_val_005_schlaegt_keinen_namen_vor(regression_run) -> None:
    """Der richtige Name steht nirgends in den Daten – ein erfundener waere schlimmer."""
    for finding in findings_of(regression_run, "AR-VAL-005"):
        assert finding["tier"] == "C"
        assert "proposed" not in finding


# --- Soll-Konvention (D-186) ---------------------------------------------------------


def test_ohne_soll_kein_proposed(regression_run) -> None:
    """Ein Vorschlag, der nur erklaert, warum es keinen gibt, ist keiner.

    Die vier Regeln ohne Soll tragen gar kein `proposed`; das Vorgehen steht unter
    `remediation`, die Quellenlage in der Evidenz.
    """
    for rule_id in ("AR-VAL-002", "AR-VAL-003", "AR-VAL-005"):
        findings = findings_of(regression_run, rule_id)
        assert findings, rule_id
        for finding in findings:
            assert "proposed" not in finding, (rule_id, finding["finding_id"])
            assert finding["remediation"].get("steps"), rule_id


def test_ar_com_002_traegt_proposed_nur_mit_mehrheit(regression_run) -> None:
    """Stufe B hat ein Soll (Schema verlangt es), Stufe C traegt gar kein `proposed`."""
    for finding in findings_of(regression_run, "AR-COM-002"):
        if finding["tier"] == "B":
            assert finding["proposed"]["value"]
        else:
            assert "proposed" not in finding
            # Wie sich die Belege verteilen, steht jetzt im Ist statt in einem Leervorschlag
            assert "ohne Mehrheit" in finding["current"]["display"]


def test_jedes_proposed_traegt_ein_soll(regression_run) -> None:
    """Kein Finding des Laufs traegt ein `proposed`, das nur eine Quellenlage ist."""
    for finding in regression_run.findings:
        proposed = finding.get("proposed")
        if proposed is None:
            continue
        assert (
            proposed.get("value") is not None
            or proposed.get("options")
            or proposed.get("display") is not None
        ), finding["finding_id"]
