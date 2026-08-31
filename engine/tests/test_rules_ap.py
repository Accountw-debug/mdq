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
