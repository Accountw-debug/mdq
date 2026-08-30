"""MDQ – Finance Master Data & Leakage Check (Prototyp-Engine).

Die Engine ist austauschbar. Alles, was fachlich zaehlt, liegt in ``logic/``.
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

#: JSON-Schema, gegen das jedes Finding validiert wird
FINDING_SCHEMA = LOGIC_DIR / "finding.schema.json"

#: Verzeichnis der Regeldateien ``<ID>.rule.sql``
RULES_DIR = LOGIC_DIR / "rules"

__all__ = [
    "CANONICAL_SCHEMA",
    "FINDING_SCHEMA",
    "LOGIC_DIR",
    "PROJECT_ROOT",
    "RULES_DIR",
    "__version__",
]
