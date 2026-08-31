"""Was die AR-Stammdatenregeln liefern – geprueft am Lauf des Demo-Mandanten.

Die Regression (`test_regression.py`) prueft, **welche** Findings entstehen. Hier steht,
**wie** sie aussehen: Maskierung, Stufe, Soll. Beide teilen sich denselben Lauf
(`regression_run` in der conftest), damit er nur einmal ausgefuehrt wird.
"""

import re
from datetime import date

from mdq.formats import format_date

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


def test_ar_val_003_beziffert_den_lastschrifteinzug(regression_run) -> None:
    """Die Euro-Wirkung ist der Betrag, der ueber diese Bankverbindung eingezogen wuerde.

    Er kommt aus `bp_relevance.open_items_local` und steht deshalb Cent-genau auch in
    `relevance.open_items` desselben Findings.
    """
    findings = [f for f in findings_of(regression_run, "AR-VAL-003") if f.get("impact_eur")]
    assert findings, "ohne Findings mit Euro-Wirkung prueft dieser Test nichts"
    for finding in findings:
        impact = finding["impact_eur"]
        assert impact["amount"] == finding["relevance"]["open_items"]
        assert impact["currency"] == finding["relevance"]["currency"]
        assert impact["formula"].endswith(
            ", die über diese IBAN per Lastschrift eingezogen würden"
        )


def test_ar_val_003_schreibt_den_betrag_deutsch(regression_run) -> None:
    """Der Betrag in der Formel ist Freitext und wird deshalb schon beim Entstehen
    geschrieben - deutsch, mit Waehrung daneben (D-187, `mdq_money`)."""
    for finding in findings_of(regression_run, "AR-VAL-003"):
        impact = finding.get("impact_eur")
        if impact is None:
            continue
        ganzzahl, _, rest = impact["amount"].partition(".")
        erwartet = f"{int(ganzzahl):,}".replace(",", ".") + "," + rest
        assert f"Offene Posten {erwartet} {impact['currency']}," in impact["formula"]


# --- AR-LEA-001 – Unapplied Cash -----------------------------------------------------


#: Die sechs Akontozahlungen aus DEF-0119: Konto -> (Buchungskreis, Beleg).
AKONTO = {
    "C:0000100293": ("1000", "1400003882"),
    "C:0000100295": ("1000", "1400003883"),
    "C:0000100298": ("2000", "1400001219"),
    "C:0000100302": ("2000", "1400001220"),
    "C:0000100303": ("1000", "1400003884"),
    "C:0000100305": ("1000", "1400003885"),
}


def test_ar_lea_001_liefert_die_sechs_akontozahlungen(regression_run) -> None:
    findings = findings_of(regression_run, "AR-LEA-001")
    geliefert = {
        f["entity"]["bp_key"]: (
            f["entity"]["company_code"],
            f["entity"]["documents"][0]["document_no"],
        )
        for f in findings
    }
    assert geliefert == AKONTO


def test_ar_lea_001_ein_finding_je_beleg(regression_run) -> None:
    """Der `finding_key` ist die Belegnummer: zwei unzugeordnete Zahlungen desselben
    Kontos muessen zwei Findings ergeben, nicht eines. Im Demo-Mandanten traegt jedes
    Konto genau eine - der Schluessel haelt trotzdem die `finding_id` auseinander."""
    findings = findings_of(regression_run, "AR-LEA-001")
    assert len({f["finding_id"] for f in findings}) == len(findings)
    for finding in findings:
        assert len(finding["entity"]["documents"]) == 1


def test_ar_lea_001_zeigt_das_leere_feld_und_den_betrag(regression_run) -> None:
    """Das Ist ist ein leeres XBLNR; was fehlt, sagt die Anzeige - mit dem Betrag
    deutsch geschrieben (D-187) und dem Alter in Tagen."""
    for finding in findings_of(regression_run, "AR-LEA-001"):
        assert finding["current"]["source_table"] == "BSID"
        assert finding["current"]["source_field"] == "XBLNR"
        assert finding["current"]["value"] is None
        beleg = finding["entity"]["documents"][0]
        ganzzahl, _, rest = beleg["amount"].partition(".")
        erwartet = f"{int(ganzzahl):,}".replace(",", ".") + "," + rest
        assert f"Zahlungseingang über {erwartet} {beleg['currency']}" in finding["current"]["display"]
        assert "ohne Rechnungsbezug und ohne Ausgleich" in finding["current"]["display"]
        assert beleg["cleared_on"] is None and beleg["reference"] is None


def test_ar_lea_001_nennt_das_buchungsdatum_deutsch(regression_run) -> None:
    """Das Buchungsdatum steht im Satz und deshalb deutsch (D-201).

    Verglichen wird gegen das Datum, das derselbe Beleg im Datenfeld traegt – dort in
    ISO. Damit haelt der Test beide Seiten zusammen, statt eine Schreibweise zu wiederholen.
    """
    for finding in findings_of(regression_run, "AR-LEA-001"):
        beobachtet = finding["evidence"][0]["observed_at"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", beobachtet), beobachtet
        assert f" vom {format_date(beobachtet)}," in finding["current"]["display"]


def test_ar_lea_001_ist_aelter_als_die_schwelle(regression_run) -> None:
    """Grenzfall: gemessen wird gegen den Datenstand des Laufs, nie gegen heute (D-193).
    Eine Zahlung, die am Datenstand 30 Tage oder juenger ist, ist kein Befund."""
    findings = findings_of(regression_run, "AR-LEA-001")
    assert findings, "ohne Findings prueft dieser Test nichts"
    for finding in findings:
        stichtag = date.fromisoformat(finding["data_as_of"])
        gebucht = date.fromisoformat(finding["evidence"][0]["observed_at"])
        assert (stichtag - gebucht).days > 30


def test_ar_lea_001_schlaegt_eine_handlung_vor_und_zaehlt_die_kandidaten(regression_run) -> None:
    """Stufe B braucht ein Soll; welche Rechnung gemeint ist, sagen die Daten nicht.
    Das Soll ist deshalb eine Handlung - und welche, haengt daran, ob ueberhaupt eine
    offene Rechnung auf dem Konto steht."""
    for finding in findings_of(regression_run, "AR-LEA-001"):
        assert finding["tier"] == "B"
        assert finding["action_type"] == "review"
        proposed = finding["proposed"]
        assert proposed["value"] is None
        kandidaten = finding["evidence"][1]
        if kandidaten["agrees"]:
            assert "zuordnen (F-32)" in proposed["display"]
            assert "offene Rechnung" in kandidaten["value"]
        else:
            assert "Rückzahlung veranlassen" in proposed["display"]
            assert kandidaten["value"] == "keine offene Rechnung"


def test_ar_lea_001_traegt_keine_euro_wirkung(regression_run) -> None:
    """Unapplied Cash ist gebundenes, nicht verlorenes Geld: der Betrag steht im Ist und
    in `entity.documents`, aber nicht in der Schadenssumme (D-192)."""
    findings = findings_of(regression_run, "AR-LEA-001")
    assert findings, "ohne Findings prueft dieser Test nichts"
    for finding in findings:
        assert "impact_eur" not in finding
        assert finding["entity"]["documents"][0]["amount"] is not None


def test_ar_lea_001_bleibt_auf_der_debitorenseite(regression_run) -> None:
    """Ein offener Zahlungsausgang an einen Kreditor hat dieselbe Form und gehoert nicht
    hierher - ein fehlender Rollenfilter faellt hier auf."""
    for finding in findings_of(regression_run, "AR-LEA-001"):
        assert finding["side"] == "AR"
        assert finding["entity"]["role"] == "CUSTOMER"
        assert finding["entity"]["bp_key"].startswith("C:")


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
    """Der Fensterbeginn kommt vom Lauf, nicht aus der Regel (D-110).

    Im Freitext steht er deutsch (D-201); der Lauf fuehrt ihn weiter in ISO. Verglichen
    wird deshalb gegen `format_date` und nicht gegen eine zweite Schreibweise im Testcode.
    """
    fenster = regression_run.report.scope["item_window_from_effective"]
    assert fenster == "2024-09-02"
    for finding in findings_of(regression_run, "AR-HYG-001"):
        assert format_date(fenster) in finding["title"]
        assert format_date(fenster) in finding["proposed"]["source_summary"]


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


# --- Betraege im Freitext (D-187) ----------------------------------------------------


def _freitexte(finding: dict) -> list[str]:
    """Die Felder eines Findings, die ein Mensch als Satz liest.

    `evidence[].value` und `.note` gehoeren dazu – die Beispiel-Findings schreiben dort
    „RE-4711, Belegdatum 01.03.2026". **Nicht** dazu gehoert `evidence[].reference`: das
    ist ein Zeiger („BSAK 2025-08-28..2026-08-28", „1000/2026/1900004411") und kein Satz;
    eine Zeitspanne darin bleibt in ISO sortierbar und eindeutig.
    """
    proposed = finding.get("proposed") or {}
    texte = [
        finding["title"],
        finding["current"].get("display") or "",
        proposed.get("source_summary") or "",
        proposed.get("display") or "",
    ]
    for eintrag in finding.get("evidence") or ():
        texte.append(eintrag.get("value") or "")
        texte.append(eintrag.get("note") or "")
    return texte


def test_betraege_in_titeln_sind_deutsch_geschrieben(regression_run) -> None:
    """Kein `42100.00 EUR` mehr im Titel – der Betrag steht wie ueberall sonst (D-187).

    Geprueft ueber alle Findings: eine Ziffernfolge mit Punkt und genau zwei Stellen
    danach ist die englische Schreibweise und darf in keinem Titel und keiner
    Quellenlage mehr vorkommen.
    """
    # `(?!\.\d{4})` schliesst das deutsche Datum aus: "02.09.2024" traegt dieselbe Form
    # wie ein englischer Betrag, seit D-201 steht es so in der Prosa. Ein Betrag am
    # Satzende ("... 42100.00.") wird weiterhin gefunden.
    englisch = re.compile(r"\d+\.\d{2}(?!\d)(?!\.\d{4})")
    for finding in regression_run.findings:
        for text in _freitexte(finding):
            assert not englisch.search(text), (finding["finding_id"], text)


def test_datumsangaben_in_prosa_sind_deutsch_geschrieben(regression_run) -> None:
    """Kein `2024-09-02` in einem Satz – dort steht `02.09.2024` (D-201).

    Das Gegenstueck zur Betragskehrmaschine, und aus demselben Grund laufweit: ISO
    gehoert in die Datenfelder, wo eine Maschine mitliest, nicht in einen Satz, den
    jemand vorliest. Eine neue Regel, die ein Datum unformatiert in den Titel schreibt,
    faellt hier auf und nicht beim Kunden.
    """
    iso = re.compile(r"\d{4}-\d{2}-\d{2}")
    for finding in regression_run.findings:
        for text in _freitexte(finding):
            assert not iso.search(text), (finding["finding_id"], text)


def test_datenfelder_bleiben_iso(regression_run) -> None:
    """Die Gegenprobe: `data_as_of` und `observed_at` sind sortierbar, nicht huebsch."""
    deutsch = re.compile(r"\d{2}\.\d{2}\.\d{4}")
    for finding in regression_run.findings:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", finding["data_as_of"])
        for eintrag in finding.get("evidence") or ():
            beobachtet = eintrag.get("observed_at")
            if beobachtet:
                assert not deutsch.fullmatch(beobachtet), (finding["finding_id"], beobachtet)


def test_ap_lea_001_nennt_den_betrag_einmal(regression_run) -> None:
    """Der Titel trug Betrag und Waehrung getrennt; jetzt kommt beides aus `mdq_money`."""
    for finding in findings_of(regression_run, "AP-LEA-001"):
        assert "32.000,00 EUR" in finding["title"] or "EUR" in finding["title"]
        assert " EUR EUR" not in finding["title"]
