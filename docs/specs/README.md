# Specs

Eine Datei je Sprint. Claude Code arbeitet immer die aktuelle Spec ab (höchste Nummer),
Aufgabe für Aufgabe: Plan → Freigabe → Umsetzung → Tests → Commit.

| Sprint | Inhalt | Stand |
|---|---|---|
| 1 | Engine-Gerüst: Schema-Validierung, Regel-Loader, Regel-Ausführung, SE16N-Loader, Run-Report | `SPRINT-1.md`, abgeschlossen |
| 2 | Demo-Mandant: Generator, Defekt-Schicht, erwartete Findings, Katalog-Anbindung, Regression (skip) | `SPRINT-2.md`, laufend |
| 3 | Mapping SAP → kanonisch, Staging, Notationserkennung je Datei (D-035), `reference_norm` großgeschrieben (D-065), erste Regeln aus dem Katalog | offen |
| 4 | Dubletten und Euro-Wirkung | offen |
| **4b** | **KI-Schicht (D-067)** | **Platzhalter, noch keine Spec** |
| 5 | UI: Dashboard, Findings-Explorer, Review-Karte, Dubletten-Vergleich, Belegpaar | offen |

## Sprint 4b – KI-Schicht (Platzhalter)

Kommt **nach** Sprint 4, weil die Dubletten-Logik und die Euro-Wirkung erst deterministisch
stehen müssen, bevor ein Modell ihnen zuarbeitet. Entschieden ist der Rahmen bereits: die acht
Festlegungen in `docs/DECISIONS.md`, D-067, und der Absatz in `docs/CONCEPT.md` Abschnitt 7.
Kurzfassung – **Extraktion, nicht Entscheidung**:

- Ort: Staging, vor dem kanonischen Modell. Findings-Regeln bleiben deterministisches SQL,
  Euro-Beträge kommen nie aus einem Modell.
- Ablauf: Wörterbuch → Regex → Modell, gecacht je Eingabe-Hash, Temperatur 0, versionierter
  Prompt, strukturierte Ausgabe per JSON-Schema.
- Herkunft je Feld (`dictionary` | `regex` | `model`) plus Konfidenz; Modell-Feld ohne zweite
  Quelle nie über Stufe B.
- Provider-neutral über eine OpenAI-kompatible Schnittstelle, Konfiguration statt Code;
  Pilot-Standard Azure OpenAI im Tenant des Kunden, lokal als Option (dann nur Stufe C).
- Zwei Modellklassen: klein für Extraktion, groß für Weltwissen im Dubletten-Graubereich
  (optional, abschaltbar).
- Eigene Regressionsdatei mit hässlichen Adressen, Namen, Zahlungstexten und erwarteter
  Zerlegung; Prompt-Änderung = Testlauf.
- Mapping-Assistent für unbekannte Spalten beim Import, Vorschlag mit Begründung, ein Mensch
  bestätigt.
- Lernschleife: Ablehnungen mit Grund und Graubereich-Fälle als Beispiele für Prompts und
  spätere Regeln (Erfassung in der UI ab Sprint 5, Auswertung ab 4b).

Offen und vor der Spec zu klären: welche Felder überhaupt an das Modell gehen, wie die
Konfidenz je Herkunft auf die Stufe wirkt, und wo der Cache liegt (Lauf oder Kunde).
