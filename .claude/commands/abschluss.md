---
description: Definition of Done prüfen, SESSION_LOG schreiben, committen und pushen
---

Aufgabe abschließen: erst prüfen, dann schreiben, dann committen und pushen.
Reihenfolge einhalten – ein Commit auf rotem Stand ist kein Abschluss.

## 1 · Definition of Done aus `CLAUDE.md` prüfen

Jeden Punkt einzeln prüfen und das Ergebnis **zeigen**, nicht behaupten:

- [ ] `uv run pytest` grün, inklusive Demo-Mandant-Regression. Die Zahl (passed/skipped)
      gehört in die Antwort. Ein `skip` wird benannt und begründet.
- [ ] `uv run ruff check .` ohne Befunde
- [ ] Kein float für Beträge, keine stillen `except:`-Blöcke – im eigenen Diff nachsehen
      (`git diff`), nicht aus dem Gedächtnis.
- [ ] Neue oder geänderte Regel: Testfälle (trifft / trifft nicht / Grenzfall) vorhanden,
      Klartext im Regelkopf entspricht dem SQL (Regel 10).
- [ ] Run-Report zeigt keine unerklärten Rejects
- [ ] Findings valide gegen das Schema (`uv run mdq validate logic/examples/findings/`)
- [ ] Keine Geschäftspartnerdaten in Logs oder Tests – nur Schlüssel und Regel-IDs (Regel 8)
- [ ] `docs/DECISIONS.md` aktuell: jede Architekturentscheidung dieser Aufgabe steht dort
      mit Datum, Entscheidung, Grund und verworfener Alternative.

**Schlägt ein Punkt fehl: hier anhalten.** Den Befund melden und fragen, nicht reparieren
und weiterlaufen, und auf keinen Fall eine erwartete Testerwartung anpassen, um grün zu
werden (Regel 1). Das gilt für `testdata/expected/`, die Testfälle in Regelköpfen und
`logic/examples/`.

## 2 · `docs/SESSION_LOG.md` fortschreiben

Ein Eintrag am Ende der Datei, drei Zeilen im Format der bestehenden Einträge:

```
- **JJJJ-MM-TT · <Sprint, Aufgabe>: <Titel>.** <Was gebaut wurde, in Sachbegriffen aus dem Glossar.>
  Ergebnis: <Testzahlen, Lint, was nachweislich läuft>. <Welche D-Nummern ergänzt wurden.>
  Nächster Schritt: <die nächste Aufgabe der Spec, benannt>.
```

Das Datum kommt aus dem Systemkontext, nicht aus der Erinnerung. Keine
Geschäftspartnerdaten, keine Beträge aus echten Daten.

## 3 · Committen

`git status` und `git diff --stat` ansehen, dann alles zur Aufgabe gehörende committen.
Sprechende Message: Betreffzeile `<Sprint, Aufgabe>: <was>`, danach ein kurzer Rumpf mit
dem, was ein Leser in sechs Monaten wissen muss, und den D-Nummern. Message endet mit:

```
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
```

Fremde Änderungen im Arbeitsbaum, die nicht zur Aufgabe gehören, werden gemeldet und
nicht mitcommittet.

## 4 · Pushen

`git push` auf den aktuellen Branch. Ohne Upstream `git push -u origin <branch>`.
Schlägt der Push fehl (abgelehnt, kein Netz), wird das gemeldet – der Commit bleibt
bestehen, es wird nichts erzwungen und nichts umgeschrieben.

## 5 · Antworten

Zum Schluss die abgehakte Liste aus Schritt 1 mit den echten Zahlen, die Commit-Kennung
und den nächsten Schritt. Offene Punkte, die bewusst liegen bleiben, werden benannt
statt verschwiegen.
