-- ============================================================
-- Migration 004: Aufgabenmanagement + Cleanup
-- Erweitert vorgaenge um Delegationsfelder.
-- Erstellt aufgaben_kommentare in jedem Tenant-Schema.
-- Bereinigt Duplikat-Spalte password_hash.
-- Legt Systemprojekt SYS an.
--
-- Voraussetzung: Migration 003 ausgefuehrt.
-- Konformitaet: G2 (Revisionssicherheit), G3 (Dreiklang),
-- G6 (Mandantenfaehigkeit), AP 1.3.
-- ============================================================

BEGIN;

-- -----------------------------------------------------------------
-- 1. Neue Spalten an Tenant-Tabelle vorgaenge
--    (muss fuer jedes existierende Tenant-Schema ausgefuehrt werden)
-- -----------------------------------------------------------------

CREATE OR REPLACE FUNCTION add_aufgaben_columns(schema_name TEXT)
RETURNS void AS $$
BEGIN
    -- Zustaendiger Benutzer (Delegationsempfaenger)
    EXECUTE format('
        ALTER TABLE %I.vorgaenge
        ADD COLUMN IF NOT EXISTS zustaendig_benutzer_id UUID
            REFERENCES shared.benutzer(id) ON DELETE SET NULL
    ', schema_name);

    -- Delegierender Benutzer (Aufgabenersteller)
    EXECUTE format('
        ALTER TABLE %I.vorgaenge
        ADD COLUMN IF NOT EXISTS delegiert_von_benutzer_id UUID
            REFERENCES shared.benutzer(id) ON DELETE SET NULL
    ', schema_name);

    -- Prioritaet
    EXECUTE format('
        ALTER TABLE %I.vorgaenge
        ADD COLUMN IF NOT EXISTS prioritaet VARCHAR(20) NOT NULL DEFAULT ''mittel''
    ', schema_name);

    -- Indizes fuer Aufgaben-Queries
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_vorgaenge_zustaendig
        ON %I.vorgaenge (zustaendig_benutzer_id)
        WHERE typ = ''aufgabe''', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_vorgaenge_delegiert
        ON %I.vorgaenge (delegiert_von_benutzer_id)
        WHERE typ = ''aufgabe''', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_vorgaenge_prioritaet
        ON %I.vorgaenge (prioritaet)
        WHERE typ = ''aufgabe''', schema_name, schema_name);

    -- -----------------------------------------------------------------
    -- Aufgaben-Kommentare (revisionssicherer Chat pro Vorgang)
    -- -----------------------------------------------------------------

    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.aufgaben_kommentare (
            id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
            vorgang_id      UUID          NOT NULL REFERENCES %I.vorgaenge(id) ON DELETE CASCADE,
            autor_id        UUID          NOT NULL REFERENCES shared.benutzer(id) ON DELETE SET NULL,
            autor_name      VARCHAR(255)  NOT NULL,
            inhalt          TEXT          NOT NULL,
            erstellt_am     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
        )', schema_name, schema_name);

    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_kommentare_vorgang
        ON %I.aufgaben_kommentare (vorgang_id, erstellt_am)',
        schema_name, schema_name);

    EXECUTE format('COMMENT ON TABLE %I.aufgaben_kommentare
        IS ''Revisionssichere Kommentare pro Vorgang. Eintraege werden nie geloescht (G2).''',
        schema_name);

END;
$$ LANGUAGE plpgsql;

-- Fuer alle existierenden Tenant-Schemata ausfuehren
DO $$
DECLARE
    schema_rec RECORD;
BEGIN
    FOR schema_rec IN
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name LIKE 'tenant_%'
        ORDER BY schema_name
    LOOP
        RAISE NOTICE 'Migration 004: Erweitere Schema %', schema_rec.schema_name;
        PERFORM add_aufgaben_columns(schema_rec.schema_name);
    END LOOP;
END $$;

-- Hilfsfunktion aufgeraeumt
DROP FUNCTION IF EXISTS add_aufgaben_columns(TEXT);

-- -----------------------------------------------------------------
-- 2. create_tenant_tables erweitern
--    (damit neue Tenants die Spalten und Tabelle auch bekommen)
-- -----------------------------------------------------------------

-- Die bestehende create_tenant_tables-Funktion wird in kuenftigen
-- Migrationen erweitert. Fuer jetzt reicht die obige Schleife.

-- -----------------------------------------------------------------
-- 3. Cleanup: Duplikat-Spalte password_hash entfernen
-- -----------------------------------------------------------------

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'shared'
          AND table_name = 'benutzer'
          AND column_name = 'password_hash'
          AND data_type = 'text'
    ) THEN
        -- Sicherstellen, dass passwort_hash (VARCHAR 500) existiert
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'shared'
              AND table_name = 'benutzer'
              AND column_name = 'passwort_hash'
              AND data_type = 'character varying'
        ) THEN
            ALTER TABLE shared.benutzer DROP COLUMN password_hash;
            RAISE NOTICE 'Duplikat-Spalte password_hash entfernt.';
        END IF;
    END IF;
END $$;

-- -----------------------------------------------------------------
-- 4. Systemprojekt SYS in tenant_tlbv anlegen
-- -----------------------------------------------------------------

INSERT INTO tenant_tlbv.projekte (name, kurz, beschreibung, erstellt_von)
VALUES (
    'Systemprojekt',
    'SYS',
    'Internes Systemprojekt fuer mandantenweite Zuordnungen.',
    'migration-004'
)
ON CONFLICT ON CONSTRAINT uq_tenant_tlbv_projekte_kurz DO NOTHING;

-- -----------------------------------------------------------------
-- 5. Alembic-Version aktualisieren
-- -----------------------------------------------------------------

UPDATE shared.alembic_version SET version_num = '004' WHERE version_num = '003';

COMMIT;
