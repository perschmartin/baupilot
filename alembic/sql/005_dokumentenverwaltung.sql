-- ============================================================
-- Migration 005: Dokumentenverwaltung (AP 1.5)
-- Datum: 2026-05-08
-- Voraussetzung: Migration 004 (Alembic 004)
-- ============================================================

-- Neue Enum-Typen (in public, wie bestehende Enums)
DO $$ BEGIN
    CREATE TYPE dokumentkategorie AS ENUM (
        'nachtrag', 'behinderungsanzeige', 'bedenkenanzeige', 'mangelanzeige',
        'protokoll', 'plan', 'foto', 'rechnung', 'vertrag', 'sonstiges'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE signaturstatus AS ENUM (
        'nicht_signiert', 'signatur_angefordert', 'signiert', 'signatur_ungueltig'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Erweitere dokumente-Tabelle in tenant_tlbv
SET search_path TO tenant_tlbv, public;

ALTER TABLE dokumente ADD COLUMN IF NOT EXISTS minio_bucket VARCHAR(100);
ALTER TABLE dokumente ADD COLUMN IF NOT EXISTS minio_pfad VARCHAR(500);
ALTER TABLE dokumente ADD COLUMN IF NOT EXISTS dateiname VARCHAR(500) NOT NULL DEFAULT '';
ALTER TABLE dokumente ADD COLUMN IF NOT EXISTS mime_typ VARCHAR(200);
ALTER TABLE dokumente ADD COLUMN IF NOT EXISTS dateigroesse_bytes BIGINT;
ALTER TABLE dokumente ADD COLUMN IF NOT EXISTS sha256_hash VARCHAR(64);
ALTER TABLE dokumente ADD COLUMN IF NOT EXISTS kategorie dokumentkategorie NOT NULL DEFAULT 'sonstiges';
ALTER TABLE dokumente ADD COLUMN IF NOT EXISTS beschreibung TEXT;
ALTER TABLE dokumente ADD COLUMN IF NOT EXISTS version_nummer INTEGER NOT NULL DEFAULT 1;
ALTER TABLE dokumente ADD COLUMN IF NOT EXISTS vorgaenger_version_id UUID REFERENCES dokumente(id);
ALTER TABLE dokumente ADD COLUMN IF NOT EXISTS signatur_status signaturstatus NOT NULL DEFAULT 'nicht_signiert';
ALTER TABLE dokumente ADD COLUMN IF NOT EXISTS signiert_von UUID;
ALTER TABLE dokumente ADD COLUMN IF NOT EXISTS signiert_am TIMESTAMPTZ;
ALTER TABLE dokumente ADD COLUMN IF NOT EXISTS gesperrt BOOLEAN NOT NULL DEFAULT FALSE;

-- m:n Verknüpfung Vorgang <-> Dokument
CREATE TABLE IF NOT EXISTS vorgang_dokumente (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vorgang_id UUID NOT NULL REFERENCES vorgaenge(id),
    dokument_id UUID NOT NULL REFERENCES dokumente(id),
    verknuepfungstyp VARCHAR(50) NOT NULL DEFAULT 'anlage',
    erstellt_am TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    erstellt_von VARCHAR(255),
    UNIQUE(vorgang_id, dokument_id)
);

-- Indizes
CREATE INDEX IF NOT EXISTS idx_dok_projekt ON dokumente(projekt_id);
CREATE INDEX IF NOT EXISTS idx_dok_kategorie ON dokumente(kategorie);
CREATE INDEX IF NOT EXISTS idx_dok_signatur ON dokumente(signatur_status);
CREATE INDEX IF NOT EXISTS idx_dok_sha256 ON dokumente(sha256_hash);
CREATE INDEX IF NOT EXISTS idx_vd_vorgang ON vorgang_dokumente(vorgang_id);
CREATE INDEX IF NOT EXISTS idx_vd_dokument ON vorgang_dokumente(dokument_id);

-- Alembic-Version aktualisieren
SET search_path TO shared, public;
UPDATE alembic_version SET version_num = '005' WHERE version_num = '004';

-- Ergebnis pruefen
SELECT 'Migration 005 erfolgreich' AS status;
