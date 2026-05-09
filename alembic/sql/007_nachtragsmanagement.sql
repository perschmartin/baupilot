-- Migration 007: Nachtragsmanagement + BKI-Baupreise + Schema-Hotfixes
-- BauPilot AP 2.1
-- Datum: 09.05.2026
-- Abhaengigkeit: Migration 006 (LV-Extraktion)

-- =============================================================================
-- 0. Schema-Hotfixes konsolidieren (Volllauf-Fixes aus 08.05.2026)
-- =============================================================================

SET search_path TO tenant_tlbv, shared, public;

-- einheit: Volllauf-Fehler, z.B. "Montagewände mit Brandschutzanforderung F30"
ALTER TABLE lv_positionen ALTER COLUMN einheit TYPE VARCHAR(100);
-- kurztext: 400er-LVs haben Langtext im Kurztext (>1000 Zeichen)
ALTER TABLE lv_positionen ALTER COLUMN kurztext TYPE TEXT;
-- oz: Zusammengesetzte OZ koennen laenger als 20 Zeichen sein
ALTER TABLE lv_positionen ALTER COLUMN oz TYPE TEXT;
-- einheitspreis/gesamtpreis: Praezision ohne Limit fuer Import
ALTER TABLE lv_positionen ALTER COLUMN einheitspreis TYPE NUMERIC;
ALTER TABLE lv_positionen ALTER COLUMN gesamtpreis TYPE NUMERIC;

-- =============================================================================
-- 1. Nachtragsspezifische Spalten an vorgaenge (tenant_tlbv)
-- =============================================================================

ALTER TABLE vorgaenge ADD COLUMN IF NOT EXISTS betrag_gefordert     NUMERIC(14,2) NULL;
ALTER TABLE vorgaenge ADD COLUMN IF NOT EXISTS betrag_geprueft      NUMERIC(14,2) NULL;
ALTER TABLE vorgaenge ADD COLUMN IF NOT EXISTS betrag_genehmigt     NUMERIC(14,2) NULL;
ALTER TABLE vorgaenge ADD COLUMN IF NOT EXISTS zeitauswirkung_tage  INTEGER       NULL;
ALTER TABLE vorgaenge ADD COLUMN IF NOT EXISTS nachtragsvariante    VARCHAR(1)    NULL CHECK (nachtragsvariante IN ('A','B','C'));
ALTER TABLE vorgaenge ADD COLUMN IF NOT EXISTS ntv_id               UUID          NULL REFERENCES vorgaenge(id);
ALTER TABLE vorgaenge ADD COLUMN IF NOT EXISTS lv_id                UUID          NULL REFERENCES leistungsverzeichnisse(id);
ALTER TABLE vorgaenge ADD COLUMN IF NOT EXISTS kostengruppe_din276  VARCHAR(10)   NULL;
ALTER TABLE vorgaenge ADD COLUMN IF NOT EXISTS qualitaetsauswirkung TEXT          NULL;

CREATE INDEX IF NOT EXISTS idx_vorgaenge_ntv ON vorgaenge(ntv_id) WHERE ntv_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_vorgaenge_lv  ON vorgaenge(lv_id)  WHERE lv_id IS NOT NULL;

-- =============================================================================
-- 2. Nachtragspruefung (7-Schritte-Workflow)
-- =============================================================================

CREATE TABLE IF NOT EXISTS nachtragspruefung (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vorgang_id        UUID NOT NULL REFERENCES vorgaenge(id),
    schritt           INTEGER NOT NULL CHECK (schritt BETWEEN 1 AND 7),
    titel             VARCHAR(200) NOT NULL,
    ergebnis          TEXT NULL,
    bearbeiter_id     UUID NULL REFERENCES shared.benutzer(id),
    abgeschlossen     BOOLEAN NOT NULL DEFAULT FALSE,
    abgeschlossen_am  TIMESTAMPTZ NULL,
    -- KI-Felder (Schritte 2-4)
    ki_eingabe        JSONB NULL,
    ki_ergebnis       JSONB NULL,
    ki_konfidenz      REAL NULL CHECK (ki_konfidenz BETWEEN 0.0 AND 1.0),
    ki_bestaetigt     BOOLEAN NULL,
    ki_bestaetigt_von UUID NULL REFERENCES shared.benutzer(id),
    ki_bestaetigt_am  TIMESTAMPTZ NULL,
    -- Audit
    erstellt_am       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    erstellt_von      UUID NOT NULL REFERENCES shared.benutzer(id),
    geaendert_am      TIMESTAMPTZ NULL,
    geaendert_von     UUID NULL REFERENCES shared.benutzer(id),
    UNIQUE(vorgang_id, schritt)
);

CREATE INDEX IF NOT EXISTS idx_nachtragspruefung_vorgang ON nachtragspruefung(vorgang_id);

-- =============================================================================
-- 3. Entscheidungsvorlagen
-- =============================================================================

CREATE TABLE IF NOT EXISTS entscheidungsvorlagen (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vorgang_id       UUID NOT NULL REFERENCES vorgaenge(id),
    version          INTEGER NOT NULL DEFAULT 1,
    vorlage_text     TEXT NOT NULL,
    basisdaten       JSONB NOT NULL,
    generiert_von    VARCHAR(20) NOT NULL DEFAULT 'baupilot',
    freigegeben      BOOLEAN NOT NULL DEFAULT FALSE,
    freigegeben_von  UUID NULL REFERENCES shared.benutzer(id),
    freigegeben_am   TIMESTAMPTZ NULL,
    erstellt_am      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    erstellt_von     UUID NOT NULL REFERENCES shared.benutzer(id),
    UNIQUE(vorgang_id, version)
);

CREATE INDEX IF NOT EXISTS idx_entscheidungsvorlagen_vorgang ON entscheidungsvorlagen(vorgang_id);

-- =============================================================================
-- 4. BKI Baupreise (shared — mandantenuebergreifend)
-- =============================================================================

SET search_path TO shared, public;

CREATE TABLE IF NOT EXISTS bki_baupreise (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    leistungsbereich    VARCHAR(3) NOT NULL,
    lb_bezeichnung      VARCHAR(200) NULL,
    position_nr         INTEGER NOT NULL,
    kurztext            TEXT NOT NULL,
    stichworte          TEXT NULL,
    einheit             VARCHAR(20) NOT NULL,
    kostengruppe        VARCHAR(10) NOT NULL,
    preis_min_netto     NUMERIC(10,2) NOT NULL,
    preis_von_netto     NUMERIC(10,2) NOT NULL,
    preis_mittel_netto  NUMERIC(10,2) NOT NULL,
    preis_bis_netto     NUMERIC(10,2) NOT NULL,
    preis_max_netto     NUMERIC(10,2) NOT NULL,
    preis_min_brutto    NUMERIC(10,2) NOT NULL,
    preis_von_brutto    NUMERIC(10,2) NOT NULL,
    preis_mittel_brutto NUMERIC(10,2) NOT NULL,
    preis_bis_brutto    NUMERIC(10,2) NOT NULL,
    preis_max_brutto    NUMERIC(10,2) NOT NULL,
    preis_jahr          INTEGER NOT NULL,
    UNIQUE(leistungsbereich, position_nr, preis_jahr)
);

CREATE INDEX IF NOT EXISTS idx_bki_lb_jahr ON bki_baupreise(leistungsbereich, preis_jahr);
CREATE INDEX IF NOT EXISTS idx_bki_kg ON bki_baupreise(kostengruppe);
CREATE INDEX IF NOT EXISTS idx_bki_kurztext ON bki_baupreise USING gin(to_tsvector('german', kurztext || ' ' || COALESCE(stichworte, '')));

-- =============================================================================
-- 5. BKI Regionalfaktoren (shared)
-- =============================================================================

CREATE TABLE IF NOT EXISTS bki_regionalfaktoren (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    landkreis  VARCHAR(200) NOT NULL,
    faktor     NUMERIC(5,3) NOT NULL,
    preis_jahr INTEGER NOT NULL,
    UNIQUE(landkreis, preis_jahr)
);

-- FLI-relevante Regionalfaktoren (aus BKI 2026, Anhang S.452ff)
INSERT INTO bki_regionalfaktoren (landkreis, faktor, preis_jahr) VALUES
    ('Jena, Stadt', 1.088, 2026),
    ('Erfurt, Stadt', 0.926, 2026),
    ('Saale-Holzland-Kreis', 0.821, 2026),
    ('Saale-Orla-Kreis', 0.940, 2026),
    ('Saalfeld-Rudolstadt', 0.918, 2026),
    ('Weimar, Stadt', 0.912, 2026),
    ('Weimarer Land', 0.812, 2026)
ON CONFLICT (landkreis, preis_jahr) DO NOTHING;

-- =============================================================================
-- 6. Alembic-Version aktualisieren
-- =============================================================================

UPDATE shared.alembic_version SET version_num = '007';

-- =============================================================================
-- Validierung
-- =============================================================================
-- Nach Ausfuehrung pruefen:
--   SELECT COUNT(*) FROM tenant_tlbv.nachtragspruefung;  -- 0
--   SELECT COUNT(*) FROM tenant_tlbv.entscheidungsvorlagen;  -- 0
--   SELECT COUNT(*) FROM shared.bki_baupreise;  -- 0 (INSERTs kommen separat)
--   SELECT COUNT(*) FROM shared.bki_regionalfaktoren;  -- 7
--   SELECT version_num FROM shared.alembic_version;  -- 007
--   \d tenant_tlbv.vorgaenge  -- neue Spalten vorhanden
