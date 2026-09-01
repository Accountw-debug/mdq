-- MDQ – Staging-Makros (DuckDB-Dialekt)
-- Typisierung raw -> staged: SAP-Text wird Betrag, Prozentsatz, Datum, Ganzzahl, Kennzeichen.
--
-- Diese Makros sind die ausgefuehrte Fassung der Regeln aus `engine/mdq/formats.py`.
-- `formats.py` bleibt die Referenz-Implementierung und beschreibt die Faelle im Klartext;
-- hier steht dasselbe als SQL, weil die Typisierung im SQL laeuft (D-071). Dass beide
-- gleich rechnen, ist kein Vorsatz, sondern gepruefte Zusage: `engine/tests/test_staging.py`
-- laesst sie ueber einen festen Grenzfallsatz **und** ueber jeden einzelnen Wert des
-- Demo-Mandanten laufen und verlangt Gleichheit Zelle fuer Zelle.
--
-- Jede Aenderung hier verlangt dieselbe Aenderung in `formats.py` – und umgekehrt.
--
-- Nicht lesbare Werte ergeben NULL, keinen Fehler: die Zeile wird danach als Reject
-- ausgewiesen (Regel 4). Ob ein NULL ein SAP-Initialwert oder ein Lesefehler ist,
-- entscheidet `staging.py` am Rohwert, nicht dieses SQL.

-- --- Bausteine -----------------------------------------------------------------------

-- Vorzeichen als Praefix des Zahlliterals: SAP schreibt es vorangestellt oder nachgestellt,
-- das nachgestellte gilt zuerst (wie `formats._strip_sign`).
CREATE OR REPLACE MACRO mdq_sign(v) AS (
    CASE
        WHEN regexp_matches(trim(v), '-$') THEN '-'
        WHEN regexp_matches(trim(v), '\+$') THEN ''
        WHEN regexp_matches(trim(v), '^-') THEN '-'
        ELSE ''
    END
);

-- Der Wert ohne Vorzeichen; getrimmt wie in Python (rstrip nach hinten, lstrip nach vorn).
CREATE OR REPLACE MACRO mdq_body(v) AS (
    CASE
        WHEN regexp_matches(trim(v), '[+-]$') THEN rtrim(regexp_replace(trim(v), '[+-]$', ''))
        WHEN regexp_matches(trim(v), '^[+-]') THEN ltrim(regexp_replace(trim(v), '^[+-]', ''))
        ELSE trim(v)
    END
);

-- Ziffern und Trenner ohne Leerzeichen; NULL, sobald ein unerlaubtes Zeichen vorkommt.
-- Leerzeichen sind als Tausendertrenner erlaubt und werden entfernt.
--
-- Mindestens eine Ziffer muss da sein: '.', ',' oder '...' sind kein Betrag von null,
-- sondern kein Betrag. Ohne diese Bedingung baute `mdq_literal` aus dem leeren Vorkomma-
-- teil eine '0' und der Wert wurde stillschweigend zu 0,00 (Regel 4, D-204). Ein fehlender
-- Vorkommateil allein bleibt erlaubt: ',56' ist 0,56.
CREATE OR REPLACE MACRO mdq_clean(v) AS (
    CASE
        WHEN v IS NULL OR trim(v) = '' THEN NULL
        WHEN NOT regexp_matches(mdq_body(v), '^[0-9., ]+$') THEN NULL
        WHEN NOT regexp_matches(mdq_body(v), '[0-9]') THEN NULL
        ELSE replace(mdq_body(v), ' ', '')
    END
);

CREATE OR REPLACE MACRO mdq_before_dot(s) AS (
    CASE WHEN contains(s, '.') THEN substr(s, 1, instr(s, '.') - 1) ELSE s END
);

CREATE OR REPLACE MACRO mdq_after_dot(s) AS (
    CASE WHEN contains(s, '.') THEN substr(s, instr(s, '.') + 1) ELSE '' END
);

-- Der Dezimaltrenner: '.' oder ',' – '' heisst ganzzahlig, NULL heisst nicht entscheidbar.
-- Kommen beide Trenner vor, ist der letzte der Dezimaltrenner. Kommt nur einer vor und
-- mehrfach, ist er der Tausendertrenner. Kommt er genau einmal mit genau drei folgenden
-- Ziffern vor, ist der Wert mehrdeutig (`1.234`): dann entscheidet die Notation der Datei,
-- und ohne sie bleibt es bei NULL – geraten wird nicht (D-035).
CREATE OR REPLACE MACRO mdq_decimal_sep(clean, notation) AS (
    CASE
        WHEN clean IS NULL THEN NULL
        WHEN contains(clean, '.') AND contains(clean, ',')
            THEN CASE
                     WHEN instr(reverse(clean), '.') < instr(reverse(clean), ',') THEN '.'
                     ELSE ','
                 END
        WHEN NOT contains(clean, '.') AND NOT contains(clean, ',') THEN ''
        WHEN contains(clean, '.')
            THEN CASE
                     WHEN length(clean) - length(replace(clean, '.', '')) > 1 THEN ''
                     WHEN length(clean) - instr(clean, '.') <> 3 THEN '.'
                     WHEN notation = 'iso' THEN '.'
                     WHEN notation = 'de' THEN ''
                     ELSE NULL
                 END
        ELSE CASE
                 WHEN length(clean) - length(replace(clean, ',', '')) > 1 THEN ''
                 WHEN length(clean) - instr(clean, ',') <> 3 THEN ','
                 WHEN notation = 'de' THEN ','
                 WHEN notation = 'iso' THEN ''
                 ELSE NULL
             END
    END
);

-- Der Wert mit '.' als Dezimaltrenner und ohne Tausendertrenner.
CREATE OR REPLACE MACRO mdq_dotted(clean, sep) AS (
    CASE
        WHEN clean IS NULL OR sep IS NULL THEN NULL
        WHEN sep = '' THEN replace(replace(clean, '.', ''), ',', '')
        WHEN sep = '.' THEN replace(clean, ',', '')
        ELSE replace(replace(clean, '.', ''), ',', '.')
    END
);

-- Das fertige Zahlliteral. Fehlt der ganzzahlige Teil, steht dort '0' (",56" -> "0.56");
-- ist der Nachkommateil leer, entfaellt der Punkt ("1." -> "1"). Genau so baut
-- `formats.parse_amount` sein Literal.
CREATE OR REPLACE MACRO mdq_literal(clean, sep) AS (
    CASE
        WHEN mdq_dotted(clean, sep) IS NULL THEN NULL
        ELSE coalesce(nullif(mdq_before_dot(mdq_dotted(clean, sep)), ''), '0')
             || CASE
                    WHEN mdq_after_dot(mdq_dotted(clean, sep)) = '' THEN ''
                    ELSE '.' || mdq_after_dot(mdq_dotted(clean, sep))
                END
    END
);

-- Passt das Literal verlustfrei in DECIMAL(precision, scale)? Runden waere ein stumm
-- verworfener Unterschied (Regel 4): ein Betrag mit drei Nachkommastellen ist in einer
-- DECIMAL(15,2)-Spalte kein Betrag, sondern ein Hinweis auf eine falsch gelesene Spalte.
CREATE OR REPLACE MACRO mdq_fits(lit, total_digits, decimals) AS (
    lit IS NOT NULL
    AND length(mdq_after_dot(lit)) <= decimals
    AND length(ltrim(mdq_before_dot(lit), '0')) <= total_digits - decimals
);

-- --- Die fuenf Typklassen --------------------------------------------------------------

-- Betrag -> DECIMAL(15,2). `notation` ist die Notation der Datei ('de' | 'iso' | ''),
-- sie greift nur bei mehrdeutigen Werten (D-035).
CREATE OR REPLACE MACRO mdq_parse_amount(v, notation) AS (
    CASE
        WHEN mdq_fits(mdq_literal(mdq_clean(v), mdq_decimal_sep(mdq_clean(v), notation)), 15, 2)
            THEN TRY_CAST(
                mdq_sign(v)
                || mdq_literal(mdq_clean(v), mdq_decimal_sep(mdq_clean(v), notation))
                AS DECIMAL(15, 2)
            )
        ELSE NULL
    END
);

-- Prozentsatz -> DECIMAL(5,3). Prozentfelder tragen nie einen Tausendertrenner: ein
-- einzelner Trenner ist immer der Dezimaltrenner, unabhaengig von der Notation der
-- Datei (D-048). Zwei Trennerarten oder derselbe Trenner mehrfach sind ein Fehler.
CREATE OR REPLACE MACRO mdq_percent_sep(clean) AS (
    CASE
        WHEN clean IS NULL THEN NULL
        WHEN contains(clean, '.') AND contains(clean, ',') THEN NULL
        WHEN NOT contains(clean, '.') AND NOT contains(clean, ',') THEN ''
        WHEN contains(clean, '.')
            THEN CASE WHEN length(clean) - length(replace(clean, '.', '')) > 1 THEN NULL ELSE '.' END
        ELSE CASE WHEN length(clean) - length(replace(clean, ',', '')) > 1 THEN NULL ELSE ',' END
    END
);

CREATE OR REPLACE MACRO mdq_parse_percent(v) AS (
    CASE
        WHEN mdq_fits(mdq_literal(mdq_clean(v), mdq_percent_sep(mdq_clean(v))), 5, 3)
            THEN TRY_CAST(
                mdq_sign(v) || mdq_literal(mdq_clean(v), mdq_percent_sep(mdq_clean(v)))
                AS DECIMAL(5, 3)
            )
        ELSE NULL
    END
);

-- Datum -> DATE. Leerer Wert und SAP-Initialwerte ergeben NULL, kein Reject (D-035).
-- Erkannt: 20260830, 2026-08-30, 30.08.2026. Ein unmoeglicher Kalendertag ergibt NULL.
CREATE OR REPLACE MACRO mdq_parse_date(v) AS (
    CASE
        WHEN v IS NULL OR trim(v) = '' THEN NULL
        WHEN trim(v) IN ('00000000', '00.00.0000', '0000-00-00') THEN NULL
        WHEN regexp_matches(trim(v), '^[0-9]{8}$')
            THEN CAST(try_strptime(trim(v), '%Y%m%d') AS DATE)
        WHEN regexp_matches(trim(v), '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
            THEN CAST(try_strptime(trim(v), '%Y-%m-%d') AS DATE)
        WHEN regexp_matches(trim(v), '^[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{4}$')
            THEN CAST(try_strptime(trim(v), '%-d.%-m.%Y') AS DATE)
        ELSE NULL
    END
);

-- Ganzzahl -> INTEGER. Fuehrende Nullen sind erlaubt, ein Trenner ist ein Fehler:
-- ein Zahlungsziel in Tagen hat keine Nachkommastelle.
CREATE OR REPLACE MACRO mdq_parse_integer(v) AS (
    CASE
        WHEN v IS NULL OR trim(v) = '' THEN NULL
        WHEN NOT regexp_matches(mdq_body(v), '^[0-9]+$') THEN NULL
        ELSE TRY_CAST(mdq_sign(v) || mdq_body(v) AS INTEGER)
    END
);

-- Kennzeichen -> BOOLEAN. "X" ist wahr, leer ist NULL; alles andere ist ein Fehler und
-- keine stille Annahme. Das kanonische DEFAULT FALSE setzt erst das Mapping (Aufgabe 2).
CREATE OR REPLACE MACRO mdq_parse_flag(v) AS (
    CASE
        WHEN v IS NULL OR trim(v) = '' THEN NULL
        WHEN upper(trim(v)) = 'X' THEN TRUE
        ELSE NULL
    END
);
