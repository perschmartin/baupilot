-- Migration 006: LV-Extraktion (AP 1.2) — KORRIGIERT
-- FK heisst lv_id (nicht leistungsverzeichnis_id), nummernkreis ist smallint
-- Alembic 005 -> 006

BEGIN;

-- ============================================================
-- 1. Neue Spalten an leistungsverzeichnisse
-- ============================================================

ALTER TABLE tenant_tlbv.leistungsverzeichnisse
    ADD COLUMN IF NOT EXISTS dateiname VARCHAR(500),
    ADD COLUMN IF NOT EXISTS positionen_anzahl INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS extraktion_status VARCHAR(50) DEFAULT 'ausstehend',
    ADD COLUMN IF NOT EXISTS minio_pfad VARCHAR(1000),
    ADD COLUMN IF NOT EXISTS minio_bucket VARCHAR(200);

-- ============================================================
-- 2. Neue Spalten an lv_positionen
-- ============================================================

ALTER TABLE tenant_tlbv.lv_positionen
    ADD COLUMN IF NOT EXISTS hierarchie_ebene INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS ist_titel BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS extrahiert_am TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS extrahiert_mit VARCHAR(100),
    ADD COLUMN IF NOT EXISTS roh_text TEXT;

-- ============================================================
-- 3. Indizes fuer LV-Suche
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_lv_positionen_lv_id
    ON tenant_tlbv.lv_positionen(lv_id);

CREATE INDEX IF NOT EXISTS idx_lv_positionen_oz
    ON tenant_tlbv.lv_positionen(oz);

CREATE INDEX IF NOT EXISTS idx_lv_extraktion_status
    ON tenant_tlbv.leistungsverzeichnisse(extraktion_status);

-- ============================================================
-- 4. Alembic-Version
-- ============================================================

UPDATE shared.alembic_version SET version_num = '006' WHERE version_num = '005';

COMMIT;
