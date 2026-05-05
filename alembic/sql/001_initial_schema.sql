-- =============================================================================
-- BauPilot — Migration 001: Initiales Datenbankschema
-- =============================================================================
-- Entscheidungen: B-001 (Bauteil), B-002 (Verknuepfung), B-003 (Schema-per-Tenant)
-- Grundsaetze:    G2 (Revisionssicherheit), G3 (Dreiklang), G10 (Mandantenfaehigkeit)
-- Datum:          04.05.2026
-- =============================================================================

-- Transaktionsklammer: alles oder nichts
BEGIN;

-- ==========================================================================
-- 1. ENUM-TYPEN (datenbankweit)
-- ==========================================================================

DO $$ BEGIN
    CREATE TYPE projektstatus AS ENUM (
        'aktiv', 'abgeschlossen', 'archiviert', 'pausiert'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE bauteiltyp AS ENUM (
        'gebaeudeabschnitt', 'brandabschnitt', 'aussenanlage', 'sonstiges'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE klassifikation AS ENUM (
        'offen', 'intern', 'vertraulich', 'vs_nfd',
        'vs_vertraulich', 'vs_geheim', 'vs_streng_geheim'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE vorgangtyp AS ENUM (
        'nachtrag', 'behinderungsanzeige', 'bedenkenanzeige',
        'mangelanzeige', 'aufgabe'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE vorgangstatus AS ENUM (
        'offen', 'in_bearbeitung', 'geprueft', 'genehmigt',
        'abgelehnt', 'abgeschlossen', 'storniert'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE beziehungstyp AS ENUM (
        'loest_aus', 'widerspricht', 'ersetzt', 'konkretisiert',
        'gehoert_zu', 'llm_vorschlag'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE benutzerrolle AS ENUM (
        'admin', 'projektleiter', 'objektueberwacher',
        'fachplaner', 'bauleiter', 'leser'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;


-- ==========================================================================
-- 2. SHARED-SCHEMA: mandanten, benutzer, benutzer_projekt_rollen
-- ==========================================================================

-- --- mandanten -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS shared.mandanten (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    erstellt_am     TIMESTAMPTZ NOT NULL DEFAULT now(),
    erstellt_von    VARCHAR(255) NOT NULL DEFAULT 'system',
    geaendert_am    TIMESTAMPTZ,
    geaendert_von   VARCHAR(255),
    geloescht       BOOLEAN NOT NULL DEFAULT false,
    geloescht_am    TIMESTAMPTZ,
    geloescht_von   VARCHAR(255),
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(63) NOT NULL,
    beschreibung    TEXT,
    aktiv           BOOLEAN NOT NULL DEFAULT true,
    CONSTRAINT uq_mandanten_slug UNIQUE (slug)
);

-- --- benutzer ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shared.benutzer (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    erstellt_am     TIMESTAMPTZ NOT NULL DEFAULT now(),
    erstellt_von    VARCHAR(255) NOT NULL DEFAULT 'system',
    geaendert_am    TIMESTAMPTZ,
    geaendert_von   VARCHAR(255),
    geloescht       BOOLEAN NOT NULL DEFAULT false,
    geloescht_am    TIMESTAMPTZ,
    geloescht_von   VARCHAR(255),
    email           VARCHAR(255) NOT NULL,
    passwort_hash   VARCHAR(500) NOT NULL,
    vorname         VARCHAR(127) NOT NULL,
    nachname        VARCHAR(127) NOT NULL,
    aktiv           BOOLEAN NOT NULL DEFAULT true,
    totp_secret     VARCHAR(255),
    totp_aktiviert  BOOLEAN NOT NULL DEFAULT false,
    CONSTRAINT uq_benutzer_email UNIQUE (email)
);

-- --- benutzer_projekt_rollen ---------------------------------------------
CREATE TABLE IF NOT EXISTS shared.benutzer_projekt_rollen (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    erstellt_am     TIMESTAMPTZ NOT NULL DEFAULT now(),
    erstellt_von    VARCHAR(255) NOT NULL DEFAULT 'system',
    geaendert_am    TIMESTAMPTZ,
    geaendert_von   VARCHAR(255),
    geloescht       BOOLEAN NOT NULL DEFAULT false,
    geloescht_am    TIMESTAMPTZ,
    geloescht_von   VARCHAR(255),
    benutzer_id     UUID NOT NULL REFERENCES shared.benutzer(id) ON DELETE CASCADE,
    mandant_slug    VARCHAR(63) NOT NULL,
    projekt_kurz    VARCHAR(31) NOT NULL,
    rolle           benutzerrolle NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_bpr_benutzer
    ON shared.benutzer_projekt_rollen (benutzer_id);
CREATE INDEX IF NOT EXISTS ix_bpr_mandant_projekt
    ON shared.benutzer_projekt_rollen (mandant_slug, projekt_kurz);


-- ==========================================================================
-- 3. TENANT-TABELLEN (als Funktion, pro Schema aufrufbar)
-- ==========================================================================

CREATE OR REPLACE FUNCTION create_tenant_tables(schema_name TEXT)
RETURNS void AS $$
BEGIN

    -- --- projekte --------------------------------------------------------
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.projekte (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            erstellt_am         TIMESTAMPTZ NOT NULL DEFAULT now(),
            erstellt_von        VARCHAR(255) NOT NULL DEFAULT ''system'',
            geaendert_am        TIMESTAMPTZ,
            geaendert_von       VARCHAR(255),
            geloescht           BOOLEAN NOT NULL DEFAULT false,
            geloescht_am        TIMESTAMPTZ,
            geloescht_von       VARCHAR(255),
            name                VARCHAR(255) NOT NULL,
            kurz                VARCHAR(31) NOT NULL,
            beschreibung        TEXT,
            status              projektstatus NOT NULL DEFAULT ''aktiv'',
            auftraggeber        VARCHAR(255),
            ort                 VARCHAR(255),
            baubeginn           DATE,
            bauende_soll        DATE,
            bauende_ist         DATE,
            gesamtkosten_eur    NUMERIC(14,2),
            CONSTRAINT uq_%s_projekte_kurz UNIQUE (kurz)
        )', schema_name, schema_name);

    -- --- bauteile (B-001) ------------------------------------------------
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.bauteile (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            erstellt_am     TIMESTAMPTZ NOT NULL DEFAULT now(),
            erstellt_von    VARCHAR(255) NOT NULL DEFAULT ''system'',
            geaendert_am    TIMESTAMPTZ,
            geaendert_von   VARCHAR(255),
            geloescht       BOOLEAN NOT NULL DEFAULT false,
            geloescht_am    TIMESTAMPTZ,
            geloescht_von   VARCHAR(255),
            projekt_id      UUID NOT NULL REFERENCES %I.projekte(id) ON DELETE CASCADE,
            kennung         VARCHAR(31) NOT NULL,
            name            VARCHAR(255) NOT NULL,
            typ             bauteiltyp NOT NULL DEFAULT ''gebaeudeabschnitt'',
            beschreibung    TEXT,
            CONSTRAINT uq_%s_bauteile_kennung UNIQUE (projekt_id, kennung)
        )', schema_name, schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_bauteile_projekt
        ON %I.bauteile (projekt_id)', schema_name, schema_name);

    -- --- leistungsverzeichnisse ------------------------------------------
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.leistungsverzeichnisse (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            erstellt_am     TIMESTAMPTZ NOT NULL DEFAULT now(),
            erstellt_von    VARCHAR(255) NOT NULL DEFAULT ''system'',
            geaendert_am    TIMESTAMPTZ,
            geaendert_von   VARCHAR(255),
            geloescht       BOOLEAN NOT NULL DEFAULT false,
            geloescht_am    TIMESTAMPTZ,
            geloescht_von   VARCHAR(255),
            projekt_id      UUID NOT NULL REFERENCES %I.projekte(id) ON DELETE CASCADE,
            bauteil_id      UUID REFERENCES %I.bauteile(id) ON DELETE SET NULL,
            nummer          VARCHAR(31) NOT NULL,
            bezeichnung     VARCHAR(500) NOT NULL,
            nummernkreis    SMALLINT,
            klassifikation  klassifikation NOT NULL DEFAULT ''intern'',
            vertragsdatum   DATE,
            auftragnehmer   VARCHAR(255),
            CONSTRAINT uq_%s_lv_nummer UNIQUE (projekt_id, nummer)
        )', schema_name, schema_name, schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_lv_projekt
        ON %I.leistungsverzeichnisse (projekt_id)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_lv_bauteil
        ON %I.leistungsverzeichnisse (bauteil_id)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_lv_nummernkreis
        ON %I.leistungsverzeichnisse (nummernkreis)', schema_name, schema_name);

    -- --- lv_positionen ---------------------------------------------------
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.lv_positionen (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            erstellt_am     TIMESTAMPTZ NOT NULL DEFAULT now(),
            erstellt_von    VARCHAR(255) NOT NULL DEFAULT ''system'',
            geaendert_am    TIMESTAMPTZ,
            geaendert_von   VARCHAR(255),
            geloescht       BOOLEAN NOT NULL DEFAULT false,
            geloescht_am    TIMESTAMPTZ,
            geloescht_von   VARCHAR(255),
            lv_id           UUID NOT NULL REFERENCES %I.leistungsverzeichnisse(id) ON DELETE CASCADE,
            oz              VARCHAR(31) NOT NULL,
            kurztext        VARCHAR(1000) NOT NULL,
            langtext        TEXT,
            einheit         VARCHAR(31),
            menge           NUMERIC(14,4),
            einheitspreis   NUMERIC(14,4),
            gesamtpreis     NUMERIC(14,2),
            CONSTRAINT uq_%s_lvpos_oz UNIQUE (lv_id, oz)
        )', schema_name, schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_lvpos_lv
        ON %I.lv_positionen (lv_id)', schema_name, schema_name);

    -- --- firmen ----------------------------------------------------------
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.firmen (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            erstellt_am     TIMESTAMPTZ NOT NULL DEFAULT now(),
            erstellt_von    VARCHAR(255) NOT NULL DEFAULT ''system'',
            geaendert_am    TIMESTAMPTZ,
            geaendert_von   VARCHAR(255),
            geloescht       BOOLEAN NOT NULL DEFAULT false,
            geloescht_am    TIMESTAMPTZ,
            geloescht_von   VARCHAR(255),
            projekt_id      UUID NOT NULL REFERENCES %I.projekte(id) ON DELETE CASCADE,
            name            VARCHAR(255) NOT NULL,
            kuerzel         VARCHAR(15),
            rolle           VARCHAR(127),
            adresse         TEXT,
            telefon         VARCHAR(63),
            email           VARCHAR(255)
        )', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_firmen_projekt
        ON %I.firmen (projekt_id)', schema_name, schema_name);

    -- --- personen --------------------------------------------------------
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.personen (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            erstellt_am     TIMESTAMPTZ NOT NULL DEFAULT now(),
            erstellt_von    VARCHAR(255) NOT NULL DEFAULT ''system'',
            geaendert_am    TIMESTAMPTZ,
            geaendert_von   VARCHAR(255),
            geloescht       BOOLEAN NOT NULL DEFAULT false,
            geloescht_am    TIMESTAMPTZ,
            geloescht_von   VARCHAR(255),
            firma_id        UUID NOT NULL REFERENCES %I.firmen(id) ON DELETE CASCADE,
            vorname         VARCHAR(127) NOT NULL,
            nachname        VARCHAR(127) NOT NULL,
            rolle           VARCHAR(127),
            telefon         VARCHAR(63),
            email           VARCHAR(255)
        )', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_personen_firma
        ON %I.personen (firma_id)', schema_name, schema_name);

    -- --- vorgaenge (Nachtrag, BA, BK, Mangel, Aufgabe) ------------------
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.vorgaenge (
            id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            erstellt_am                 TIMESTAMPTZ NOT NULL DEFAULT now(),
            erstellt_von                VARCHAR(255) NOT NULL DEFAULT ''system'',
            geaendert_am                TIMESTAMPTZ,
            geaendert_von               VARCHAR(255),
            geloescht                   BOOLEAN NOT NULL DEFAULT false,
            geloescht_am                TIMESTAMPTZ,
            geloescht_von               VARCHAR(255),
            projekt_id                  UUID NOT NULL REFERENCES %I.projekte(id) ON DELETE CASCADE,
            bauteil_id                  UUID REFERENCES %I.bauteile(id) ON DELETE SET NULL,
            lv_id                       UUID REFERENCES %I.leistungsverzeichnisse(id) ON DELETE SET NULL,
            typ                         vorgangtyp NOT NULL,
            nummer                      VARCHAR(31) NOT NULL,
            gegenstand                  VARCHAR(1000) NOT NULL,
            beschreibung                TEXT,
            status                      vorgangstatus NOT NULL DEFAULT ''offen'',
            kosten_eur                  NUMERIC(14,2),
            zeit_arbeitstage            INTEGER,
            qualitaet_bewertung         VARCHAR(500),
            vorgaenger_id               UUID REFERENCES %I.vorgaenge(id) ON DELETE SET NULL,
            beziehungstyp               beziehungstyp,
            konfidenz                   FLOAT,
            konfidenz_bestaetigt        BOOLEAN,
            konfidenz_bestaetigt_von    VARCHAR(255),
            konfidenz_bestaetigt_am     TIMESTAMPTZ,
            verantwortlich_firma_id     UUID REFERENCES %I.firmen(id) ON DELETE SET NULL,
            frist                       DATE,
            CONSTRAINT uq_%s_vorgaenge_nummer UNIQUE (projekt_id, typ, nummer)
        )', schema_name, schema_name, schema_name, schema_name,
           schema_name, schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_vorgaenge_projekt
        ON %I.vorgaenge (projekt_id)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_vorgaenge_typ
        ON %I.vorgaenge (typ)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_vorgaenge_status
        ON %I.vorgaenge (status)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_vorgaenge_bauteil
        ON %I.vorgaenge (bauteil_id)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_vorgaenge_lv
        ON %I.vorgaenge (lv_id)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_vorgaenge_vorgaenger
        ON %I.vorgaenge (vorgaenger_id)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_vorgaenge_frist
        ON %I.vorgaenge (frist)', schema_name, schema_name);

    -- --- dokumente -------------------------------------------------------
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.dokumente (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            erstellt_am         TIMESTAMPTZ NOT NULL DEFAULT now(),
            erstellt_von        VARCHAR(255) NOT NULL DEFAULT ''system'',
            geaendert_am        TIMESTAMPTZ,
            geaendert_von       VARCHAR(255),
            geloescht           BOOLEAN NOT NULL DEFAULT false,
            geloescht_am        TIMESTAMPTZ,
            geloescht_von       VARCHAR(255),
            projekt_id          UUID NOT NULL REFERENCES %I.projekte(id) ON DELETE CASCADE,
            vorgang_id          UUID REFERENCES %I.vorgaenge(id) ON DELETE SET NULL,
            dateiname           VARCHAR(500) NOT NULL,
            dateipfad_minio     VARCHAR(1000) NOT NULL,
            mime_type           VARCHAR(127),
            groesse_bytes       BIGINT,
            klassifikation      klassifikation NOT NULL DEFAULT ''intern'',
            version             INTEGER NOT NULL DEFAULT 1,
            pruefsumme_sha256   VARCHAR(64),
            beschreibung        TEXT
        )', schema_name, schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_dokumente_projekt
        ON %I.dokumente (projekt_id)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_dokumente_vorgang
        ON %I.dokumente (vorgang_id)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_dokumente_klassifikation
        ON %I.dokumente (klassifikation)', schema_name, schema_name);

    -- --- tags (B-001: Tag-System) ----------------------------------------
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.tags (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            erstellt_am     TIMESTAMPTZ NOT NULL DEFAULT now(),
            erstellt_von    VARCHAR(255) NOT NULL DEFAULT ''system'',
            geaendert_am    TIMESTAMPTZ,
            geaendert_von   VARCHAR(255),
            geloescht       BOOLEAN NOT NULL DEFAULT false,
            geloescht_am    TIMESTAMPTZ,
            geloescht_von   VARCHAR(255),
            projekt_id      UUID NOT NULL REFERENCES %I.projekte(id) ON DELETE CASCADE,
            kategorie       VARCHAR(63) NOT NULL,
            wert            VARCHAR(255) NOT NULL,
            CONSTRAINT uq_%s_tags_kat_wert UNIQUE (projekt_id, kategorie, wert)
        )', schema_name, schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_tags_projekt
        ON %I.tags (projekt_id)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_tags_kategorie
        ON %I.tags (kategorie)', schema_name, schema_name);

    -- --- vorgang_tags (Zuordnung Vorgang <-> Tag) ------------------------
    EXECUTE format('
        CREATE TABLE IF NOT EXISTS %I.vorgang_tags (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            erstellt_am     TIMESTAMPTZ NOT NULL DEFAULT now(),
            erstellt_von    VARCHAR(255) NOT NULL DEFAULT ''system'',
            geaendert_am    TIMESTAMPTZ,
            geaendert_von   VARCHAR(255),
            geloescht       BOOLEAN NOT NULL DEFAULT false,
            geloescht_am    TIMESTAMPTZ,
            geloescht_von   VARCHAR(255),
            vorgang_id      UUID NOT NULL REFERENCES %I.vorgaenge(id) ON DELETE CASCADE,
            tag_id          UUID NOT NULL REFERENCES %I.tags(id) ON DELETE CASCADE,
            CONSTRAINT uq_%s_vorgang_tags UNIQUE (vorgang_id, tag_id)
        )', schema_name, schema_name, schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_vorgang_tags_vorgang
        ON %I.vorgang_tags (vorgang_id)', schema_name, schema_name);
    EXECUTE format('CREATE INDEX IF NOT EXISTS ix_%s_vorgang_tags_tag
        ON %I.vorgang_tags (tag_id)', schema_name, schema_name);

END;
$$ LANGUAGE plpgsql;


-- ==========================================================================
-- 4. TENANT-TABELLEN FUER ALLE EXISTIERENDEN SCHEMATA ANLEGEN
-- ==========================================================================

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
        RAISE NOTICE 'Erstelle Tabellen in Schema: %', schema_rec.schema_name;
        PERFORM create_tenant_tables(schema_rec.schema_name);
    END LOOP;
END $$;


-- ==========================================================================
-- 5. ALEMBIC-VERSIONSTABELLE (damit Alembic den Stand kennt)
-- ==========================================================================

CREATE TABLE IF NOT EXISTS shared.alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Revision 001 als aktuellen Stand eintragen
INSERT INTO shared.alembic_version (version_num)
VALUES ('001')
ON CONFLICT (version_num) DO NOTHING;


-- ==========================================================================
-- 6. SEED: TLBV-Mandant eintragen
-- ==========================================================================

INSERT INTO shared.mandanten (name, slug, beschreibung, erstellt_von)
VALUES (
    'Thueringer Landesamt fuer Bau und Verkehr',
    'tlbv',
    'Erster Mandant. Pilotprojekt FLI Jena.',
    'migration-001'
)
ON CONFLICT ON CONSTRAINT uq_mandanten_slug DO NOTHING;


COMMIT;

-- Hilfsfunktion kann bestehen bleiben (fuer kuenftige Tenants)
-- DROP FUNCTION IF EXISTS create_tenant_tables(TEXT);
