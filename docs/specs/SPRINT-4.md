# Sprint 4 – Normalisierung, Dubletten, Doppelzahlung v1.1, Euro-Wirkung, Pilot-Härtung

**Ausgangslage (Sprint 3, 01.09.2026):** 17 von 19 Regeln scharf, 208 von 230 erwarteten Findings, Regression 0/0/0, Endbild „2 bekannt offen (AP-LEA-001 v1.1) + 20 Regel fehlt (AR-DUP-001 12, AP-DUP-001 8)". Die Cluster-Form steht (D-052, D-190), `entity.records` und `proposed.golden_record` sind im Schema (D-069), `name_norm`/`city_norm`/`street_norm` sind kanonisch vorhanden und leer (D-079).

**Ziel:** Am Ende von Sprint 4 liefert `mdq run` alle 230 erwarteten Findings, NOT_YET_BUILT ist leer, „bekannt offen" ist leer, die Euro-Wirkung unterscheidet abgeflossenes von gefährdetem Geld, und die Engine ist für den ersten echten Kundenlauf gehärtet (Skalentest, Gedächtnis-Stabilität, Pilotprotokoll).

**Nicht verhandelbar, zusätzlich zu CLAUDE.md:**
- Kein Modell wird zur Laufzeit trainiert. Alle Schwellen und Gewichte sind benannte, versionierte Parameter: Regelparameter im Regelkopf (D-107), Parameter der `match`-Stufe in `logic/matching/dedup.yaml` (Entscheidung E-7, bewusste Abgrenzung zu D-107 – sie gehören keiner Regel); der `pack_hash` deckt beide ab.
- **Kein Score im Finding.** Konfidenz ist Quellenlage: die Evidenz nennt, *welche Felder wie* übereinstimmen (USt-ID gleich, Name nach Normalisierung exakt, Straße ähnlich), nie eine Wahrscheinlichkeit oder Prozentzahl.
- `proposed.golden_record` schlägt **nie Bankdaten** vor (Schadensklasse 1). Zusammenführung bleibt Entscheidung des Kunden; die Engine liefert den Cluster, die Gegenüberstellung und einen Vorschlag für Name/Adresse/Steuer-ID.
- Arbeitsrhythmus wie Sprint 3: Plan → Freigabe → Umsetzung → Regression grün → Commit. Weicht ein Ergebnis von der Erwartung ab: `render()` plus Beobachtung/Vermutung, kein Fix (R3-Protokoll). Erwartungen werden nie angepasst, um Tests grün zu bekommen (Regel 1).

---

## Vorbedingungen (vor Aufgabe 2, parallel zu Aufgabe 0 und 1 möglich)

**V-1 · Architektur-Review durch Lux (extern).** Gegenstand: `engine/mdq/executor.py`, `canonical.py`, `relevance.py`, `run.py`, das Regelformat (SQL + YAML-Kopf, `${…}`-Injektion), die Regressionsschicht (D-068, D-100), `ID_COLUMNS` (D-185). Leitfragen: Wo würde ein zweiter Entwickler stolpern? Welche Naht bricht bei 50× Daten zuerst? Ist die Injektionsschicht gegen Kundeneingaben abgeschottet? Ergebnis: schriftliche Befundliste, keine Codeänderung. Victor terminiert; Aufgabe 2 startet erst nach Sichtung der Befunde.

**V-2 · READ-ONLY-Audit in frischer Claude-Code-Session.** Auftrag: gesamten Code lesen, nichts ändern, Befundliste in drei Töpfen (Fehler / Inkonsistenz gegen DECISIONS / Verbesserung). Dauer eine Session. Triage der Befunde durch Claude im Chat, Umsetzung nur nach Freigabe.

**V-3 · Skalentest.** Demo-Generator mit Faktor 10 und 50 (Partner und Posten) in Temp-Verzeichnisse; `mdq run` je Stufe messen: Laufzeit je Stufe, Spitzen-Speicher, Zeilen kanonisch. Ergebnis als Tabelle in `docs/SESSION_LOG.md`. Erwartung wird nicht vorgegeben – die Kurve ist das Ergebnis. Liegt 50× über 10 Minuten oder über 8 GB, ist das ein Befund für Lux, kein Blocker für den Sprint.

---

## Aufgabe 0 – Schema 1.2 und Kleinigkeiten mit Vertragswirkung (ein Commit)

- `impact_eur.kind` neu, Enum `loss | exposure`, Pflicht sobald `impact_eur` vorhanden ist. `loss` = Geld ist abgeflossen oder verfallen (AP-LEA-001, AP-LEA-002). `exposure` = Volumen, das gefährdet ist, solange der Befund steht (AR-CON-002, AR-VAL-003, AP-VAL-003). Begründung aus der Handprobe: 862.561,72 € IBAN-Prüfziffer über 42.100,00 € Doppelzahlung in derselben Rangliste erzählt die falsche Geschichte.
- Bestehende Regeln bekommen `kind` explizit; alle **vier** impact-tragenden Beispiele werden nachgezogen: F-003 (AP-LEA-001, loss), F-004 (AR-CON-002, exposure), F-005 (AP-LEA-002, loss), F-006 (AP-VAL-003, exposure) – jede geänderte Zeile im Commit aufgelistet. `mdq validate` 6/6.
- **Versionen (Entscheidung E-8, als eigener DECISIONS-Eintrag):** Inhaltszuwachs im Finding hebt die Regelversion um eine Minor (Präzedenz D-196); reine Schreibweisenänderung hebt nicht (D-187, D-201); und ein Versionssprung darf nie `from_rule_version`-Erwartungen fälschlich fällig machen (Präzedenz D-082). Daraus: `kind` hebt AR-CON-002 1.0 → 1.1, AP-LEA-002 1.0 → 1.1, AP-VAL-003 1.1 → 1.2, AR-VAL-003 1.2 → 1.3, die Beispiel-`rule_version` wandert im selben Commit mit (D-202). **Ausnahme AP-LEA-001: bleibt in Aufgabe 0 auf 1.0** – exakt der D-082-Fall: 1.1 würde die zwei „bekannt offen" (DEF-0081/0082, D-054) fällig machen, bevor die Clusterlogik existiert; der `kind`-Zuwachs wird vom 1.1-Sprung in Aufgabe 4 mit abgedeckt, Begründung im Regelkopf.
- `report.txt` und `run.json`: Summen und Top-10 **je Art**, nie gemischt. Das UI zieht im Verdrahtungsdurchgang nach (Tab 2, nicht Teil dieses Sprints).
- Gegenprobe der Datums-Kehrmaschine um `evidence[].reference` erweitern (D-201 ist entschieden, aber noch nicht erzwungen).
- CLAUDE.md, neue Regel: `${…}`-Platzhalter werden ausschließlich aus Dateien unter `logic/` befüllt – nie aus Kundeneingaben, Laufzeitparametern oder Modellausgaben. Der Test dazu prüft, dass jede Injektionsquelle im Repo liegt.
- **Freigabekriterien:** Schema 1.2 validiert alle 208 Findings des Demo-Laufs; kein `impact_eur` ohne `kind`; Regression 0/0/0 (Erwartung vergleicht kein `impact_eur`); DECISIONS je Punkt.

## Aufgabe 1 – Normalisierung: `name_norm`, `city_norm`, `street_norm`

- Als DuckDB-SQL-Makros in der kanonischen Stufe (Linie D-071), Wörterbücher als Wertepaare injiziert (D-101): `legal_forms.yaml` (Rechtsformen in allen Schreibweisen), `street_abbreviations.yaml` (Str./Straße/Strasse → STR usw.), `postal_code_patterns.yaml` für die Trennung PLZ/Ort.
- Definition je Feld, im Glossar festzuhalten: Großschreibung; ä/ö/ü/ß → AE/OE/UE/SS; Satz- und Sonderzeichen weg; Mehrfachleerzeichen zu einem; `name_norm` ohne Rechtsform (die Rechtsform wird separat als `legal_form_norm` erkannt, nicht verworfen – **neue Spalte in `business_partner`, Erweiterung von `logic/schema/canonical.sql` in diesem Commit, nicht in `ID_COLUMNS`**); `street_norm` mit normalisierter Hausnummer am Ende; `city_norm` ohne PLZ und Ortsteil-Zusatz in Klammern.
- Python-Referenzimplementierung in `formats.py` und Äquivalenztest wie bei D-071: fester Grenzfallsatz (mindestens 30 Namen mit Rechtsformen in allen Schreibweisen, Umlaute, Bindestriche, „&"/„und", Abkürzungen, führende Artikel) plus alle eindeutigen Namen, Orte und Straßen des Demo-Mandanten, Zelle für Zelle.
- Die `*_norm`-Spalten sind **nicht** in `ID_COLUMNS` (D-185): eine Wörterbucherweiterung darf keine `finding_id` verschieben.
- Hinweis D-079 entfällt aus dem Report. Keine Regel liest `*_norm` vor Aufgabe 3 – Regression bleibt unverändert 0/0/0.
- **Freigabekriterien:** Äquivalenztest grün; Messung im Bericht: wie viele Partner je Seite kollabieren nach Normalisierung auf denselben `name_norm` (reine Vorschau auf die Dublettenlage, keine Zusicherung); zwei Läufe byte-identisch.

## Aufgabe 2 – Kandidaten, Ähnlichkeit, Cluster: die Engine-Stufe `match`

Neue Stufe nach `relevance`, schreibt die kanonischen Tabellen `bp_match_pair` und `bp_match_cluster`. Regeln lesen nur diese Tabellen (Regel 5) – keine Ähnlichkeitsrechnung im Regel-SQL.

- **Entscheidung E-1 (vorweggenommen, in DECISIONS zu verschriften): deterministische Ähnlichkeit nativ in DuckDB statt trainiertem probabilistischem Modell.** Vergleiche über `jaro_winkler_similarity` / `damerau_levenshtein` auf den `*_norm`-Feldern, Schwellen als benannte Parameter in `logic/matching/dedup.yaml` (Teil des Regelpakets, im `pack_hash`; Ablageort ist Entscheidung E-7 – Stufen-Parameter gehören keiner Regel, deshalb nicht im Regelkopf nach D-107, eigener DECISIONS-Eintrag mit dieser Abgrenzung). Verworfen für diesen Sprint: Splink. Die Gründe sind Produktgründe, keine Doktrin: Der Demo-Mandant kann keinen Qualitätsunterschied zeigen (beide Wege treffen 20/20), im ersten Piloten schützen wenige, feldgenau erklärbare Fehlalarme das Vertrauen besser als ein Modell, das niemand im Raum erklären kann, und Modellpflege je Kunde ist für einen Solo-Betrieb ein laufender Preis für einen noch ungemessenen Nutzen. Ehrlich festgehalten, wo Splink besser wäre: bei reinen Fuzzy-Fällen ohne starken Schlüssel, weil es aus den Kundendaten lernt, wie viel eine Übereinstimmung wert ist. Zwei Maßnahmen darunter schließen diese Lücke teilweise und machen die Wiedervorlage messbar statt geschätzt.
- **Häufigkeitsgewichtung, deterministisch:** eine Tokenfrequenz-Tabelle über `name_norm` je Seite; seltene Bestandteile („XYLOPHON") wiegen mehr als häufige („MUELLER", „GMBH" ist ohnehin entfernt). Die Gewichtung geht in die Namensähnlichkeit ein, ihre Parameter stehen in `dedup.yaml`. Kein Modell, reine Zählung.
- **Matching-Datenprofil im Report:** je Seite Anzahl Partner, Anteil mit USt-ID, Anteil mit IBAN, Anteil mit mindestens einem starken Schlüssel. Liegt der Anteil mit starkem Schlüssel unter `fuzzy_profile_threshold` (benannter Parameter, Vorgabe 50 %), steht im Report der Hinweis „fuzzy-lastiger Mandant – Splink-Experiment laut Pilotprotokoll einplanen". Damit entscheidet der erste Lauf beim Kunden, nicht eine Vorab-Einschätzung, ob der deterministische Weg dort reicht.
- **Wiedervorlage als Experiment:** Beim ersten Kundenmandanten mit fuzzy-lastigem Profil läuft Splink einmal offline und read-only auf denselben normalisierten Stammdaten; die Cluster werden gegen `bp_match_cluster` gediffen und die Abweichungen mit dem Kunden stichprobenartig bewertet. Erst dieses Ergebnis entscheidet, ob Splink für Kunde 2 als Kandidatengeber *unter* derselben Tabelle nachgerüstet wird – Regeln und UI hängen an `bp_match_cluster`, nicht an der Rechenmethode, der Rückweg bleibt offen und billig.
- **Blocking, deterministisch, je Seite getrennt:** Blöcke über gleiche `value_norm` der USt-ID, gleiche `iban_norm`, gleiche PLZ + erste drei Zeichen von `name_norm`, gleicher `name_norm`. Anzahl Kandidatenpaare je Block im Report; Obergrenze `max_candidate_pairs` als benannter Parameter – Überschreitung ist ein Hinweis mit Zahl, kein stiller Abschnitt.
- **Vergleichsvektor je Paar**, jede Dimension mit drei Ausprägungen (gleich / verschieden / fehlt bzw. ähnlich ab Schwelle): USt-ID, IBAN, `name_norm`, `street_norm`, `postal_code`, `city_norm`. Schwellen `jw_name`, `jw_street` benannt, keine Literale im SQL.
- **Übereinstimmungsmuster → Stufe (Entscheidung E-2):** USt-ID gleich *oder* IBAN gleich = starker Schlüssel → Stufe B. Nur Name und Adresse ähnlich (beide über Schwelle) → Stufe C. Darunter kein Kandidat. Das Muster steht als Text in der Evidenz („USt-ID gleich, Name nach Normalisierung exakt, Straße ähnlich"); der Zahlenwert der Ähnlichkeit bleibt in `bp_match_pair` und geht nie ins Finding.
- **Ausschlüsse:** CpD-Konten; Paare, die als Regulierer-Beziehung verbunden sind – geprüft über **alle drei SAP-Wege wie in D-191**: `business_partner.alt_payer_key`, `bp_company_code.alt_payer_key` und `bp_partner_function` – Testlücke nach D-191-Muster benennen, solange kein Defekt sie belegt. Löschvorgemerkte Konten bleiben drin (eine Dublette mit Löschvormerkung ist genau der Fall, den man sehen will).
- **Cluster** = transitive Hülle über Kandidatenpaare je Seite (Zusammenhangskomponenten, deterministisch), `cluster_id` = kleinster `bp_key` des Clusters (D-190). Cluster mit ausschließlich Stufe-C-Kanten bleiben Stufe C; ein einziger starker Schlüssel im Cluster hebt nicht automatisch auf B – Stufe wird je Paar ausgewiesen, das Finding trägt die Stufe des Ankers gegen jedes Mitglied im schwächsten Fall.
- **Freigabekriterien:** `bp_match_pair` und `bp_match_cluster` sind in `logic/schema/canonical.sql` deklariert (Regel 5 – erst dann darf eine Regel sie in `requires_tables` nennen); zwei Läufe byte-identisch inklusive `bp_match_*`; Kandidatenpaare und Cluster des Demo-Mandanten als Zahlen im Bericht; Skalentest aus V-3 auf die neue Stufe wiederholt (10×/50× Paarzahlen und Laufzeit); Testfälle: Paar mit starkem Schlüssel, Paar nur fuzzy, Paar knapp unter Schwelle (kein Kandidat), Regulierer-Paar (ausgeschlossen), CpD (ausgeschlossen), Kette A~B~C wird ein Cluster.

## Aufgabe 3 – AR-DUP-001 und AP-DUP-001: die letzten 20 Findings (ein Commit je Regel)

- Cluster-Form nach D-052/D-190: ein Finding je Cluster, Anker = kleinster `bp_key`, übrige in `related_bp_keys`, alle Mitglieder in `entity.records` mit den Vergleichsfeldern, **exakt die Feldliste des Schemas** (name, street, postal_code, city, country, vat_id, `iban_masked`, payment_terms, open_items, currency, last_activity_on – kein Anlagedatum, das Schema kennt keins).
- `proposed.golden_record` (D-069) **nach der Survivorship-Definition des Glossars, keine neue Regel**: VIES-geprüft > zuletzt geändert > vollständigster; solange `--enrich vies` nicht existiert, tritt an die erste Stelle die Formatgültigkeit nach `vat_id_patterns.yaml` (so belegt es F-002: gewählt wird die formal gültige USt-ID, nicht die des aktivsten Kontos). Ein Eintrag **nur je Feld mit klarem Gewinner** – F-002 trägt genau eines (vat_id), kein Eintrag je Feld erzwungen. **Bankdaten nie** (E-3); `source_summary` nennt je Feld die Herkunft. Aktion bleibt `review`, Optionen wie D-111: Zusammenführen prüfen / Konto sperren (XD05/XK05) / Löschvormerkung (XD06/XK06) – ohne Empfehlung.
- **Cluster-Relevanz (Entscheidung E-4):** `relevance.open_items` und `volume_12m` sind die Summe über alle Mitglieder, `last_activity_on` das Maximum, Währung die Hauswährung des Laufs. `entity.company_code` bleibt `null`, wenn Mitglieder in verschiedenen Buchungskreisen liegen (so steht es in F-002). `impact_eur` bleibt `null` – eine Dublette ist weder Verlust noch Gefährdung, das Geld steht in der Relevanz.
- `finding_key` = die sortierte Mitgliedermenge des Clusters (Entscheidung E-6): ändert sich die Mitgliedschaft, ist es fachlich ein neuer Befund; das Gedächtnis verwaist den alten Eintrag mit Hinweis (Aufgabe 5 testet genau das).
- Testfälle aus `defects.yaml` Abschnitt 3 (hits nach Cluster, no_hits Ankerkonten, edge: Cross-Seiten-Paar gehört zu CROSS-DUP-001, Regulierer-Paar, Knapp-unter-Schwelle). Die AP-Seite spiegelt die AR-Seite, Rollenfilter als edge.
- **Freigabekriterien:** AR-DUP-001 genau 12, AP-DUP-001 genau 8; Regression 0/0/0; NOT_YET_BUILT leer; Katalogzeilen beider Regeln im jeweiligen Commit `draft → impl`, Tabellen-Spalte um `bp_match_cluster` ergänzt, Stufen-Spalte auf „B/C nach Übereinstimmungsmuster (E-2)" präzisiert (faktischer Nachzug im Regelcommit, wie in Sprint 3 bei den Katalogzeilen von AP-CON-001 und AP-VAL-001 praktiziert; inhaltliche Katalogänderungen bleiben Victors); **F-002 wird von einem Test wörtlich reproduziert (Muster des F-006-Tests aus D-196 – `mdq validate` prüft nur Schema und kann das nicht)**, nach folgender begründeter Spec-Korrektur an genau zwei Feldern, jede Zeile im Commit gelistet: `evidence[0].reference` von „cluster-000412" auf die Ankerform aus D-190 (Cluster-IDs dieser Bauart gibt es seit E-1/D-190 nicht) und `evidence[0].source_type` von `model` auf `deterministic` (E-1). **`related_finding_ids` bleibt unangetastet** – die ID ist F-001 (gleicher Kunde, echter Querverweis); der Literaltest nimmt dieses eine Feld mit begründetem Kommentar aus, weil die Querverweis-Befüllung durch den Executor nicht Teil dieses Sprints ist (benannte Testlücke nach D-191-Muster, siehe „Nicht in Sprint 4"). **records, golden_record und die Relevanzsummen (51.610,00) bleiben unangetastet und sind die bindende Erwartung**; ein Test kämmt alle Dubletten-Findings nach Zahlen zwischen 0 und 1 und nach „%" in jedem Textfeld – kein Score; ein Test belegt, dass kein `golden_record` ein Bankfeld trägt.

## Aufgabe 4 – AP-LEA-001 Version 1.1: Doppelzahlung über Kreditoren-Dubletten

- Umfang laut DEF-0081/DEF-0082 und D-054: dieselbe Rechnung zweimal bezahlt, aber auf zwei Kreditorenkonten desselben Lieferanten. Die Regel liest dafür `bp_match_cluster` (AP-Seite) zusätzlich zum bestehenden Paarvergleich; Kriterien für Referenz, Betrag und Fenster bleiben die von 1.0.
- `entity.documents` strukturiert für **beide** Belege – Referenz, Belegdatum, Ausgleichsdatum, Betrag, Währung – auch für alle 1.0-Treffer. **Das bindende Beispiel ist F-003 (AP-LEA-001): es trägt die volle Belegform bereits heute – die Regel holt F-003 ein, F-003 wird inhaltlich nicht angefasst**; nur seine `rule_version` wandert in diesem Commit auf 1.1 (D-202), und ein Test reproduziert F-003 wörtlich (Muster D-196). `finding_key` bleibt das Belegpaar, damit die acht bestehenden `finding_id`s stehen bleiben; **die Ordnung im Schlüssel ist das Belegdatum (früherer Beleg zuerst), nicht die aufsteigende Nummer** – so führt es die Erwartung (DEF-0082: 1900004459|1900003017), der Plan begründet Anker und Schlüsselordnung aus der Regel.
- Klartext im Regelkopf erweitern (Regel 10), Version 1.0 → 1.1. Damit werden die zwei „bekannt offen" fällig: Regression muss danach 0/0/0 mit leerem `known_open` zeigen – 10 von 10.
- Der Plan nennt vorab, auf welchem `bp_key` die zwei neuen Findings verankert sind (die Erwartung sagt V:0000200001 und V:0000200003 – der Plan begründet die Regel dahinter, nicht die Erwartung).
- **Freigabekriterien:** 10/10; kein 1.0-`finding_id` verschoben (Test über den Lauf vor/nach dem Commit); `requires_tables` der Regel und die Tabellen-Spalte der Katalogzeile um `bp_match_cluster` ergänzt (wie in Sprint 3 für `bp_relevance` praktiziert); die letzte „Offene fachliche Frage" des Katalogs („AP-LEA-001 Version 1.1") wird im Commit als beantwortet geschlossen.

## Aufgabe 5 – Was überlebt einen Neulauf: Gedächtnis-Stabilität

Ein Kapitel in `docs/GLOSSARY.md` oder `docs/CONCEPT.md` („Was überlebt einen Neulauf") und Tests, die es belegen:

- Namenskorrektur im Stammsatz → gleiche `finding_id` (D-185) – **gilt für Nicht-Cluster-Regeln; bei Cluster-Findings gilt E-6: ändert die Korrektur die Mitgliedschaft nicht, bleibt die `finding_id`; ändert sie sie (weil das Matching anders ausgeht), ist das Szenario 3** –, Entscheidung bleibt angewandt.
- Behobener Defekt → Finding verschwindet, der Gedächtniseintrag steht als verwaist im Report mit Grund („Befund nicht mehr erzeugt"), nie still.
- Teilkorrektur eines Clusters (ein Mitglied gefixt) → neuer `finding_key`, alter Eintrag verwaist mit Grund („Mitgliedschaft geändert"), neues Finding offen.
- Regelversion erhöht → `finding_id` unverändert (Version ist nicht Teil der Identität), aber der Report nennt je angewandter Entscheidung die Version, unter der sie getroffen wurde.
- Zweiter Lauf mit `decisions.yaml` aus dem ersten → Zähler „geladen / angewandt / verwaist" stimmen exakt mit einem Testszenario überein.
- **Freigabekriterien:** alle fünf Szenarien als Tests auf handgebauten Mini-Eingaben nach dem Muster von `test_executor.py` (frei erfundene Konten; D-066 gilt hier nicht, weil keine hits/no_hits aus `defects.yaml` gebraucht werden), Verwaiste tragen einen Grund aus einer geschlossenen Liste, keine Datei unter `testdata/` verändert.

## Aufgabe 6 – Regel-Autoren-Command und Pilotprotokoll (Dokumentation, ein Commit)

- **Entscheidung rule-authoring: ja, als Command `/neue-regel`,** keine neue Mechanik. Er schreibt das Verfahren aus **Sprint 3, Aufgaben 6–8** fest: Katalogzeile lesen → Messung vorab am Mandanten → Regelkopf → SQL → Klartext-Abgleich (Regel 10) → hits/no_hits/edge aus `defects.yaml` (D-066) → ID aus NOT_YET_BUILT → Regression → Commit; bei Delta R3-Protokoll. Wert zeigt sich, sobald Victors 24 Findings die 17 Regeln ohne Testfall füttern.
- `docs/PILOT-PROTOKOLL.md`: Ablauf des ersten Kundenlaufs als Checkliste – Datenweg und AVV vor dem ersten Export; Onboarding-Session mit Victor am Tisch (halber Tag); Extraktion nach `SAP-ECC-EXTRACTION.md`; erwartete Abbrüche (unbekannte Spalte, kundeneigene Belegart) und ihr Weg ins Mapping oder Wörterbuch; Regeln einzeln scharf schalten, je Regel Stichprobe von fünf Findings mit dem Kunden, Fehlalarm-Quote je Regel notieren; Schwellen konservativ starten; Übergabe von Report, `findings.json` und `decisions.yaml`; Löschkonzept für `data/` und `runs/`; bei Report-Hinweis „fuzzy-lastiger Mandant" das Splink-Offline-Experiment aus Aufgabe 2 als eigener Tag einplanen (read-only, Cluster-Diff, Stichprobe mit dem Kunden). Kein Code.

## Victors Teil (parallel, unverändert offen)

- AP-`central_payer`-Defekt (D-191) und ein Cross-IBAN-Paar (D-197) in `defects.yaml` – schließen die zwei benannten Testlücken; der Regulierer-Ausschluss in Aufgabe 2 bekommt damit ebenfalls einen Prüfstein.
- Die 24 Beispiel-Findings für die 17 Regeln ohne Testfall (`testdata/README.md`).
- Lux-Termin für V-1; Pilotkandidat mit ECC-Bestätigung (D-081); AVV-Vorlage.

## Definition of Done Sprint 4

- [ ] Regression: 0 fehlend, 0 unerwartet, 0 abweichend; `known_open` leer; NOT_YET_BUILT leer – **230 von 230**
- [ ] Zwei Läufe mit festem `--created-at` byte-identisch, einschließlich `bp_match_pair` und `bp_match_cluster`
- [ ] `mdq run` auf dem Demo-Mandanten unter 60 s; Skalentest-Tabelle (10×/50×, vor und nach der `match`-Stufe) im SESSION_LOG
- [ ] Kein Score, kein Prozentwert in einem Finding (Test); kein `golden_record` mit Bankfeld (Test); kein `impact_eur` ohne `kind`
- [ ] Matching-Datenprofil im Report (Anteil Partner mit starkem Schlüssel je Seite) mit Hinweis bei Fuzzy-Last; Häufigkeitsgewichtung mit Grenzfalltest (seltener vs. häufiger Namensbestandteil)
- [ ] `mdq validate` 6/6 (Schemaprüfung); wörtliche Reproduktion von F-002, F-003 und F-006 als Tests nach dem D-196-Muster; jede Beispieländerung dieses Sprints im jeweiligen Commit aufgelistet (F-002: Aufgabe-3-Korrektur; F-003–F-006: `kind` und Versionen)
- [ ] Schema 1.2 dokumentiert; UI-Typen-Nachzug als Auftrag an Tab 2 im SESSION_LOG vermerkt (nicht Teil dieses Sprints)
- [ ] CLAUDE.md-Regel zur Injektionsquelle; GLOSSARY um Normalisierung, Übereinstimmungsmuster, Cluster, `kind`, „Was überlebt einen Neulauf"
- [ ] DECISIONS je Aufgabe, E-1 bis E-8 als Einträge mit verworfenen Alternativen
- [ ] `docs/PILOT-PROTOKOLL.md` und `/neue-regel` vorhanden
- [ ] V-1-Befundliste gesichtet, V-2-Befunde triagiert, V-3-Zahlen dokumentiert

## Nicht in Sprint 4

- KI-Schicht (4b, D-067) – Extraktion, nie Entscheidung; Mapping-Assistent
- Befüllung von `related_finding_ids` durch den Executor – F-002 hält die Erwartung (Querverweis auf F-001), der Literaltest nimmt das Feld begründet aus; die Befüllungsregel (welche Findings desselben Laufs verweisen aufeinander) ist eine eigene Entscheidung für einen späteren Sprint
- Delta zwischen Läufen, Score, Rangliste über Währungen hinweg
- UI-Verdrahtungsdurchgang (Tab 2, eigener Auftrag nach Aufgabe 4: `entity.records`-Vergleich, Belegkarte ab einem Beleg, Regeln-Ansicht aus `run.json.rules`, `kind` im Dashboard, die sechs NOTES-Punkte)
- S/4-Mapping (D-081), Fremdsysteme, Persistenz der DuckDB-Datei, Packaging/Lizenz/Auth
- Automatische Zusammenführung von Dubletten – `golden_record` ist ein Vorschlag, die Ausführung bleibt beim Kunden
- Cash App – eigenes Repo, eigener Strom, keine Querabhängigkeit
