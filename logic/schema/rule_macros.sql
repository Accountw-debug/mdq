-- Darstellungshilfen für Regel-SQL (D-187).
--
-- Hier steht, was eine Regel zum **Schreiben von Text** braucht – nicht zum Rechnen.
-- Zwei Dinge: ein Betrag, der in einem Titel oder in `source_summary` auftaucht, wird
-- deutsch geschrieben und trägt seine Währung neben sich (Regel 2, D-187); und ein Datum
-- in einem Satz wird deutsch geschrieben (D-201).
--
-- Beides gilt **nur für Prosa**. In Datenfeldern – `observed_at`, `params` mit
-- Datumsinhalt, `documents[].document_date`, `entity.records[].last_activity_on` – bleibt
-- ISO stehen: dort liest eine Maschine mit, und ISO ist sortierbar und eindeutig.
--
-- Ohne locale und ohne float: gruppiert wird über Zeichenketten, damit derselbe Lauf auf
-- jedem Rechner dieselbe Zeile schreibt (Regel 9). `engine/mdq/formats.py:format_amount`
-- macht dasselbe in Python für den Run-Report; ein Äquivalenztest hält beide zusammen.
--
-- Das kanonische Schema muss beim Einspielen dieser Datei stehen: das letzte Makro
-- schlägt in `payment_terms` nach, und DuckDB verlangt die Tabelle schon beim Anlegen
-- (D-206). Im Lauf ist das gegeben – dort ist das Schema das Erste, was geladen wird.

-- Ziffern von rechts in Dreiergruppen: "42100" -> "42.100".
-- Umgedreht, alle drei Ziffern ein Punkt, wieder umgedreht – RE2 kennt kein Lookahead,
-- der übliche Trick `(?=(\d{3})+$)` fällt damit aus.
CREATE OR REPLACE MACRO mdq_group_digits(digits) AS (
    ltrim(reverse(regexp_replace(reverse(digits), '(\d{3})', '\1.', 'g')), '.')
);

-- Betrag als deutscher Freitext, Währung daneben: 42100.00, 'EUR' -> '42.100,00 EUR'.
-- NULL bleibt NULL. Eine Währung, die NULL ist, lässt die Zahl allein stehen.
--
-- Mehr als zwei Nachkommastellen sind ein Fehler mit Namen, kein Rundungsfall: bis D-204
-- schnitt der Cast nach DECIMAL(15,2) die dritte Stelle still ab (1.234 -> '1,23 EUR'),
-- während `format_amount` in Python für denselben Wert einen Fehler wirft. Runden gehört
-- in die Regel, nicht in die Darstellung – dort steht auch die Währung dazu.
CREATE OR REPLACE MACRO mdq_money(amount, currency) AS (
    CASE WHEN amount IS NULL THEN NULL
         WHEN CAST(amount AS DECIMAL(15,2)) <> amount
             THEN error('mdq_money: Betrag hat mehr als zwei Nachkommastellen. '
                        || 'Runden gehoert in die Regel, nicht in die Darstellung.')
         ELSE
        CASE WHEN amount < 0 THEN '-' ELSE '' END
        || mdq_group_digits(split_part(replace(CAST(abs(CAST(amount AS DECIMAL(15,2))) AS VARCHAR), '-', ''), '.', 1))
        || ','
        || rpad(coalesce(nullif(split_part(CAST(abs(CAST(amount AS DECIMAL(15,2))) AS VARCHAR), '.', 2), ''), '0'), 2, '0')
        || CASE WHEN currency IS NULL THEN '' ELSE ' ' || currency END
    END
);

-- Datum als deutscher Freitext: DATE '2026-03-17' -> '17.03.2026'. NULL bleibt NULL.
-- Über `strftime` mit festem Muster, nicht über ein Locale-Format: derselbe Lauf schreibt
-- auf jedem Rechner dieselbe Zeile (Regel 9). `engine/mdq/formats.py:format_date` macht
-- dasselbe in Python für den Run-Report; ein Äquivalenztest hält beide zusammen.
CREATE OR REPLACE MACRO mdq_date(value) AS (
    CASE WHEN value IS NULL THEN NULL
         ELSE strftime(CAST(value AS DATE), '%d.%m.%Y')
    END
);

-- Der Text einer Zahlungsbedingung – **eine** Zeile je ZTERM, für den ganzen Lauf gleich.
--
-- T052 ist nach Tagesgrenze gestaffelt (ZTAGG): eine Zahlungsbedingung kann mehrere
-- Zeilen haben, und das kanonische `payment_terms` führt sie alle – zu Recht, es ist
-- Kundendatenbestand und kein Fehler. Ein `JOIN payment_terms` in einer Regel
-- vervielfacht damit ihre Findings und lässt deren `finding_id` kollidieren (D-027,
-- Befund 11). Deshalb steht die Auswahl hier und nicht in einer Regel: **die Variante
-- ohne Tagesgrenze, sonst die mit der kleinsten `day_limit`, bei Gleichstand die
-- alphabetisch erste Beschreibung** (Regel 9 – die Wahl muss reproduzierbar sein).
--
-- Einmal definiert, weil sie für den Lauf gilt und nicht für eine Regel: AP-LEA-002 und
-- AR-COM-002 lesen denselben Text, und der Lauf-Hinweis zur Staffelung meint dieselbe
-- Variante, die beide benutzen (D-206). `coalesce(day_limit, 0)` liest "keine
-- Tagesgrenze" und "00" als dasselbe – so schreibt SAP es.
CREATE OR REPLACE MACRO mdq_payment_terms_text(terms) AS (
    (SELECT t.description
     FROM payment_terms t
     WHERE t.terms_key = terms
     ORDER BY coalesce(t.day_limit, 0), t.description
     LIMIT 1)
);
