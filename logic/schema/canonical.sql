-- MDQ – kanonisches Schema (DuckDB-Dialekt)
-- ERP-unabhängiges Zielmodell. Regeln lesen ausschließlich diese Tabellen.
-- Konventionen: Schlüssel als TEXT mit führenden Nullen, Geld als DECIMAL(15,2), Datum als DATE.
-- bp_key = 'C:' || KUNNR  (Debitor)  |  'V:' || LIFNR  (Kreditor)

CREATE TABLE IF NOT EXISTS run_meta (
    run_id          TEXT PRIMARY KEY,
    engine_version  TEXT NOT NULL,
    pack_version    TEXT NOT NULL,
    dict_version    TEXT NOT NULL,
    data_as_of      DATE NOT NULL,
    started_at      TIMESTAMP NOT NULL,
    finished_at     TIMESTAMP,
    input_files     JSON NOT NULL,           -- [{name, sha256, rows, encoding, delimiter}]
    scope           JSON NOT NULL            -- {company_codes: [...], sides: [...], item_window_from, item_window_to}
);

CREATE TABLE IF NOT EXISTS reject (
    run_id          TEXT NOT NULL,
    stage           TEXT NOT NULL,           -- raw | staged | canonical
    source_table    TEXT NOT NULL,
    row_no          BIGINT,
    reason          TEXT NOT NULL,
    raw_excerpt     TEXT                     -- max. 200 Zeichen, keine BP-Daten in Logs – nur hier
);

CREATE TABLE IF NOT EXISTS business_partner (
    bp_key          TEXT PRIMARY KEY,
    role            TEXT NOT NULL CHECK (role IN ('CUSTOMER','VENDOR')),
    source_id       TEXT NOT NULL,           -- KUNNR / LIFNR unkonvertiert
    name1           TEXT,
    name2           TEXT,
    name3           TEXT,
    name4           TEXT,
    name_norm       TEXT,                    -- normalisiert (Wörterbuch legal_forms, Umlaute, Rauschen)
    search_term     TEXT,
    country         TEXT,                    -- ISO-2 (LAND1)
    region          TEXT,
    city            TEXT,
    city_norm       TEXT,
    postal_code     TEXT,
    street          TEXT,
    street_norm     TEXT,
    po_box          TEXT,
    po_box_postal_code TEXT,
    address_id      TEXT,                    -- ADRNR
    account_group   TEXT,                    -- KTOKD / KTOKK
    is_one_time     BOOLEAN NOT NULL DEFAULT FALSE,   -- XCPDK
    deletion_flag   BOOLEAN NOT NULL DEFAULT FALSE,   -- LOEVM (zentral)
    central_block   BOOLEAN NOT NULL DEFAULT FALSE,   -- SPERR (zentral)
    alt_payer_key   TEXT,                    -- KNRZA / LNRZA -> bp_key
    group_key       TEXT,                    -- KONZS
    language        TEXT,
    created_on      DATE,
    created_by      TEXT,
    phone           TEXT,
    email           TEXT                     -- aus ADR6, falls geliefert
);

CREATE TABLE IF NOT EXISTS bp_tax_id (
    bp_key          TEXT NOT NULL,
    tax_id_type     TEXT NOT NULL CHECK (tax_id_type IN ('VAT','TAX1','TAX2','TAX3')),
    country         TEXT,                    -- Land der ID (bei KNAS/LFAS abweichend möglich)
    value           TEXT NOT NULL,
    value_norm      TEXT NOT NULL            -- ohne Leerzeichen/Punkte, Großbuchstaben
);

CREATE TABLE IF NOT EXISTS bp_bank_account (
    bp_key          TEXT NOT NULL,
    bank_country    TEXT,                    -- BANKS
    bank_key        TEXT,                    -- BANKL
    account_number  TEXT,                    -- BANKN
    bank_control_key TEXT,                   -- BKONT
    iban            TEXT,                    -- aus TIBAN
    iban_norm       TEXT,                    -- ohne Leerzeichen, Großbuchstaben
    iban_valid      BOOLEAN,                 -- Prüfziffer (schwifty), NULL wenn keine IBAN
    partner_bank_type TEXT,                  -- BVTYP
    account_holder  TEXT,                    -- KOINH
    collection_auth BOOLEAN,                 -- XEZER
    valid_from      DATE
);

CREATE TABLE IF NOT EXISTS bp_company_code (
    bp_key          TEXT NOT NULL,
    company_code    TEXT NOT NULL,
    recon_account   TEXT,                    -- AKONT
    payment_terms   TEXT,                    -- ZTERM
    dunning_procedure TEXT,                  -- MAHNA
    posting_block   BOOLEAN NOT NULL DEFAULT FALSE,   -- SPERR (BUKRS)
    deletion_flag   BOOLEAN NOT NULL DEFAULT FALSE,   -- LOEVM (BUKRS)
    payment_methods TEXT,                    -- ZWELS
    payment_block   TEXT,                    -- ZAHLS
    alt_payer_key   TEXT,                    -- KNRZB / LNRZB
    tolerance_group TEXT,                    -- TOGRU
    double_invoice_check BOOLEAN,            -- REPRF (nur Kreditor)
    sort_key        TEXT,                    -- ZUAWA
    created_on      DATE,
    created_by      TEXT,
    PRIMARY KEY (bp_key, company_code)
);

CREATE TABLE IF NOT EXISTS bp_partner_function (
    bp_key          TEXT NOT NULL,
    sales_org       TEXT,
    dist_channel    TEXT,
    division        TEXT,
    function        TEXT NOT NULL,           -- RG Regulierer, RE Rechnungsempfänger, AG Auftraggeber, WE Warenempfänger
    partner_bp_key  TEXT NOT NULL,
    counter         TEXT                     -- PARZA
);

CREATE TABLE IF NOT EXISTS bp_dunning (
    bp_key          TEXT NOT NULL,
    company_code    TEXT NOT NULL,
    dunning_area    TEXT,
    dunning_level   INTEGER,
    last_dunned_on  DATE,
    dunning_block   TEXT,
    dunning_recipient_key TEXT
);

CREATE TABLE IF NOT EXISTS payment_terms (
    terms_key       TEXT NOT NULL,           -- ZTERM
    day_limit       INTEGER,                 -- ZTAGG
    days1           INTEGER,
    pct1            DECIMAL(5,3),
    days2           INTEGER,
    pct2            DECIMAL(5,3),
    days3           INTEGER,
    description     TEXT
);

-- Ein Beleg-Posten (offen oder ausgeglichen), Debitor oder Kreditor.
CREATE TABLE IF NOT EXISTS fi_item (
    item_key        TEXT PRIMARY KEY,        -- BUKRS|GJAHR|BELNR|BUZEI
    bp_key          TEXT NOT NULL,
    company_code    TEXT NOT NULL,
    fiscal_year     TEXT NOT NULL,
    document_no     TEXT NOT NULL,
    line_item       TEXT NOT NULL,
    posting_date    DATE NOT NULL,
    document_date   DATE,
    entry_date      DATE,
    doc_type        TEXT,                    -- BLART
    posting_key     TEXT,                    -- BSCHL
    debit_credit    TEXT CHECK (debit_credit IN ('S','H')),
    special_gl      TEXT,                    -- UMSKZ
    currency        TEXT NOT NULL,
    amount_doc      DECIMAL(15,2) NOT NULL,  -- WRBTR, immer positiv
    amount_local    DECIMAL(15,2) NOT NULL,  -- DMBTR, immer positiv
    amount_signed_local DECIMAL(15,2) NOT NULL,  -- Vorzeichen genau einmal beim Staging angewandt (S=+, H=-)
    reference       TEXT,                    -- XBLNR
    reference_norm  TEXT,                    -- nur [A-Z0-9]
    assignment      TEXT,                    -- ZUONR
    item_text       TEXT,                    -- SGTXT
    baseline_date   DATE,                    -- ZFBDT
    payment_terms   TEXT,                    -- ZTERM
    cash_disc_days1 INTEGER,                 -- ZBD1T
    cash_disc_pct1  DECIMAL(5,3),            -- ZBD1P
    cash_disc_base  DECIMAL(15,2),           -- SKFBT
    cash_disc_taken DECIMAL(15,2),           -- SKNTO
    payment_method  TEXT,                    -- ZLSCH
    payment_block   TEXT,                    -- ZLSPR
    invoice_ref_doc TEXT,                    -- REBZG
    po_number       TEXT,                    -- EBELN (nur AP)
    gl_account      TEXT,                    -- HKONT
    clearing_date   DATE,                    -- AUGDT
    clearing_doc    TEXT,                    -- AUGBL
    is_open         BOOLEAN NOT NULL
);

-- Optional (V2): Änderungsbelege
CREATE TABLE IF NOT EXISTS change_document (
    bp_key          TEXT NOT NULL,
    change_no       TEXT NOT NULL,
    changed_on      DATE NOT NULL,
    changed_at      TIME,
    changed_by      TEXT,
    transaction_code TEXT,
    table_name      TEXT NOT NULL,
    field_name      TEXT NOT NULL,
    value_old       TEXT,
    value_new       TEXT
);

-- Abgeleitete Sicht: Relevanz je BP (wird von der Engine nach dem Laden materialisiert)
CREATE TABLE IF NOT EXISTS bp_relevance (
    bp_key          TEXT PRIMARY KEY,
    open_items_local DECIMAL(15,2) NOT NULL,
    volume_12m_local DECIMAL(15,2) NOT NULL,
    currency        TEXT NOT NULL,           -- Hauswaehrung des Buchungskreises, nicht umgerechnet
    last_activity_on DATE,
    activity_status TEXT NOT NULL CHECK (activity_status IN ('active','dormant','never_posted'))
);

-- Whitelist / Entscheidungen bleiben über Läufe (Engine liest sie vor der Regelausführung)
CREATE TABLE IF NOT EXISTS decision_memory (
    finding_id      TEXT PRIMARY KEY,
    rule_id         TEXT NOT NULL,
    bp_key          TEXT NOT NULL,
    decided_by      TEXT NOT NULL,
    decided_at      TIMESTAMP NOT NULL,
    reason_code     TEXT NOT NULL,           -- intentionally_separate | data_correct | not_relevant | accepted_risk
    reason          TEXT
);
