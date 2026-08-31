"""Was die AP-Regeln liefern – geprueft am Lauf des Demo-Mandanten.

Dieselbe Arbeitsteilung wie in `test_rules_ar.py`: die Regression (`test_regression.py`)
prueft, **welche** Findings entstehen, hier steht, **wie** sie aussehen – Maskierung,
Stufe, Soll. Beide teilen sich den Lauf aus `regression_run` (conftest).
"""

from .conftest import findings_of

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
