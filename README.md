# MDQ – Finance Master Data & Leakage Check

Prüft Debitoren-/Kreditorenstammdaten aus SAP auf Qualität, Dubletten und Euro-Wirkung.
Ergebnis: Findings mit Ist, Soll, Quellen, Konfidenz-Stufe und SAP-Handlungsanweisung.

- Konzept: `docs/CONCEPT.md`
- Arbeitsregeln für Claude Code: `CLAUDE.md`
- Aktueller Sprint: `docs/specs/`
- Logik-Asset (technologieunabhängig): `logic/`

## Schnellstart

```
uv sync
uv run pytest
```

Echte Kundendaten gehören nie in dieses Repo. `data/` und `runs/` sind ignoriert.
