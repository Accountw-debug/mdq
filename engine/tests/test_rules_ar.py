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
        assert finding["proposed"]["value"] is None
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
        soll = finding["proposed"]["value"]
        if finding["tier"] == "B":
            assert soll, finding["entity"]["bp_key"]
            assert finding["proposed"]["display"], "Stufe B nennt den Klartext aus T052U"
        else:
            assert finding["tier"] == "C"
            assert soll is None
            assert "kein soll" in finding["proposed"]["source_summary"].lower()


def test_ar_com_002_zaehlt_wie_die_belege_es_hergeben(regression_run) -> None:
    """Die Quellenlage nennt Zaehler und Nenner – 15 mit Mehrheit, 5 ohne (DEF-0047..0066)."""
    findings = findings_of(regression_run, "AR-COM-002")
    stufen = {tier: sum(1 for f in findings if f["tier"] == tier) for tier in ("B", "C")}
    assert stufen == {"B": 15, "C": 5}
