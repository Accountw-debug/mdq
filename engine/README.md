# engine/

Engine von MDQ (Python 3.12, DuckDB): lädt SE16N-Exporte, mappt sie auf das kanonische
Schema, führt die Regeln aus `logic/rules/` aus und schreibt Findings.
Paketlayout: `engine/mdq/` (Code), `engine/tests/` (pytest).

Das ist finaler Produktcode, kein Prototyp (D-063) – dieselbe Sorgfalt wie in `logic/`:
Tests je Änderung, keine stillen `except:`-Blöcke, keine floats für Beträge, deterministische
Läufe. Die fachliche Wahrheit steht trotzdem in `logic/`; die Engine führt sie nur aus.

Betrieb, Lizenz, Updates und Auth sind spätere Sprints, nicht gestrichen.
