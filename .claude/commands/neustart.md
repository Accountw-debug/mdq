---
description: Einlesen und Plan für die nächste offene Aufgabe vorschlagen – ohne etwas zu ändern
---

Du steigst in eine laufende Session ein. Lies dich zuerst vollständig ein, schlage dann
den Plan für die nächste offene Aufgabe vor – **nur den Plan, keine Umsetzung**.

## 1 · Einlesen (in dieser Reihenfolge, vollständig)

1. `CLAUDE.md` – Ordnerrollen, die nicht verhandelbaren Regeln, Definition of Done.
2. `docs/DECISIONS.md` ab der letzten Nummer: mindestens die zehn neuesten Einträge
   (`grep -c '^- \*\*D-' docs/DECISIONS.md`, dann den Tail lesen). Zusätzlich jede
   D-Nummer nachschlagen, die in der Spec oder im letzten Log-Eintrag genannt wird –
   eine Entscheidung, die deine Aufgabe betrifft, darfst du nicht nur vom Hörensagen kennen.
3. Den **letzten** Eintrag in `docs/SESSION_LOG.md` (`tail -20`). Seine Zeile
   „Nächster Schritt" ist der Ausgangspunkt.
4. Die aktuelle Spec: die Datei mit der höchsten Nummer in `docs/specs/`
   (`ls docs/specs/SPRINT-*.md | sort -V | tail -1`), **ganz** – nicht nur die eine Aufgabe.
   Ziel, Definition of Done und „Nicht in diesem Sprint" gehören dazu.
5. `docs/GLOSSARY.md` und `docs/CONCEPT.md` bei jedem Begriff, den du sonst raten würdest.

Prüfe außerdem `git log --oneline -10` und `git status`: was zuletzt committet wurde,
ist erledigt – auch wenn das Log es anders nahelegt. Ein unsauberer Arbeitsbaum wird
gemeldet, nicht stillschweigend übergangen.

## 2 · Nächste offene Aufgabe bestimmen

Die erste Aufgabe der aktuellen Spec, die weder im Session-Log noch in den Commits als
erledigt auftaucht. Weicht sie von der Zeile „Nächster Schritt" ab, sag das ausdrücklich
und nenne beide Lesarten, statt eine davon still zu wählen.

## 3 · Plan vorschlagen

Der Plan nennt:
- **Umfang:** welche Dateien angefasst werden und welche ausdrücklich nicht. Was zu einem
  eigenen, späteren Commit gehört, wird als solches benannt.
- **Schritte** in Reihenfolge, klein geschnitten (eine Regel, eine Tabelle, ein Screen).
- **Tests:** welche Testfälle dazukommen (trifft / trifft nicht / Grenzfall) und welche
  bestehenden Tests sich ändern müssten. Erwartete Testergebnisse werden nie angepasst,
  um Tests grün zu bekommen (Regel 1) – fällt dir eine falsch wirkende Erwartung auf,
  gehört sie in die Rückfragen, nicht in den Plan.
- **Entscheidungen**, die die Aufgabe erzwingt, mit deinem Vorschlag und der verworfenen
  Alternative – sie werden am Ende zu Einträgen in `docs/DECISIONS.md`.
- **Rückfragen:** jede fachliche Unklarheit einzeln, mit Empfehlung, damit eine kurze
  Antwort genügt. Bei fachlichen Fragen (Was ist eine Dublette? Welche Schwere?) wird
  gefragt, nicht geraten.

## 4 · Nicht tun

Keine Datei anlegen, ändern oder löschen. Kein Commit. Keine Umsetzung „schon mal
vorbereitet". Warte auf die Freigabe.
