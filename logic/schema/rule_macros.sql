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
