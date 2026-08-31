-- Darstellungshilfen für Regel-SQL (D-187).
--
-- Hier steht, was eine Regel zum **Schreiben von Text** braucht – nicht zum Rechnen.
-- Bisher genau eine Sache: ein Betrag, der in einem Titel oder in `source_summary`
-- auftaucht, wird deutsch geschrieben und trägt seine Währung neben sich (Regel 2).
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
CREATE OR REPLACE MACRO mdq_money(amount, currency) AS (
    CASE WHEN amount IS NULL THEN NULL ELSE
        CASE WHEN amount < 0 THEN '-' ELSE '' END
        || mdq_group_digits(split_part(replace(CAST(abs(CAST(amount AS DECIMAL(15,2))) AS VARCHAR), '-', ''), '.', 1))
        || ','
        || rpad(coalesce(nullif(split_part(CAST(abs(CAST(amount AS DECIMAL(15,2))) AS VARCHAR), '.', 2), ''), '0'), 2, '0')
        || CASE WHEN currency IS NULL THEN '' ELSE ' ' || currency END
    END
);
