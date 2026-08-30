"""MDQ – Finance Master Data & Leakage Check.

Alles, was fachlich zaehlt, liegt in ``logic/``; die Engine fuehrt es aus.
Die Pfad-Konstanten hier zeigen dorthin, damit Regeln, kanonisches Schema und
Beispiel-Findings unabhaengig vom Arbeitsverzeichnis gefunden werden.
"""

from pathlib import Path

__version__ = "0.1.0"

#: Wurzel des Repos (engine/mdq/__init__.py -> engine/mdq -> engine -> Repo)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: Technologieunabhaengiger Asset: Schema, Regeln, Mappings, Woerterbuecher
LOGIC_DIR = PROJECT_ROOT / "logic"

#: Kanonisches Schema (DuckDB-Dialekt), das jede Regel liest
CANONICAL_SCHEMA = LOGIC_DIR / "schema" / "canonical.sql"

#: Staging-Makros (Typisierung raw -> staged), die ausgefuehrte Fassung von formats.py
STAGING_MACROS = LOGIC_DIR / "schema" / "staging.sql"

#: JSON-Schema, gegen das jedes Finding validiert wird
FINDING_SCHEMA = LOGIC_DIR / "finding.schema.json"

#: Verzeichnis der Regeldateien ``<ID>.rule.sql``
RULES_DIR = LOGIC_DIR / "rules"

#: Mapping SAP ECC -> kanonisches Schema; Quelle der Wahrheit fuer Feldlisten
SAP_MAPPING = LOGIC_DIR / "mappings" / "sap_ecc.yaml"

#: Woerterbuch der Belegarten (BLART) nach fachlicher Klasse, je Seite
DOCUMENT_TYPES = LOGIC_DIR / "dictionaries" / "document_types.yaml"

#: Fachlicher Regelkatalog: jede Zeile wird spaeter eine Regeldatei
CATALOG_MD = RULES_DIR / "CATALOG.md"

#: Synthetische Testdaten - niemals echte Kundendaten (D-008)
TESTDATA_DIR = PROJECT_ROOT / "testdata"

#: Ausgabeverzeichnis des Demo-Mandanten (16 SE16N-Dateien und manifest.json)
DEMO_MANDANT_DIR = TESTDATA_DIR / "demo_mandant"

#: Liste der eingebauten Fehler - Fehler sind Daten, nicht Code (SPRINT-2.md)
DEMO_DEFECTS = DEMO_MANDANT_DIR / "defects.yaml"

#: Aus den Defekten erzeugte Erwartung; wird nie von Hand gepflegt (Regel 1, D-010)
EXPECTED_FINDINGS = TESTDATA_DIR / "expected" / "expected_findings.yaml"

__all__ = [
    "CANONICAL_SCHEMA",
    "CATALOG_MD",
    "DEMO_DEFECTS",
    "DEMO_MANDANT_DIR",
    "DOCUMENT_TYPES",
    "EXPECTED_FINDINGS",
    "FINDING_SCHEMA",
    "LOGIC_DIR",
    "PROJECT_ROOT",
    "RULES_DIR",
    "SAP_MAPPING",
    "STAGING_MACROS",
    "TESTDATA_DIR",
    "__version__",
]
