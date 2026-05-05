-- ============================================================
-- Migration 002: Auth-Erweiterung
-- Erweitert shared.benutzer um Auth-Spalten.
-- Erstellt shared.refresh_tokens und shared.auth_log.
--
-- Voraussetzung: Migration 001 ausgefuehrt (shared-Schema,
-- Tabellen mandanten, benutzer, benutzer_projekt_rollen).
--
-- Konformitaet: G2 (Revisionssicherheit), G3 (Dreiklang-Urheber),
-- B-003 (Schema-per-Tenant), B-008 (HS256 JWT), B-009 (Admin-Reset).
-- ============================================================

BEGIN;

-- -----------------------------------------------------------------
-- 1. Neue Spalten an shared.benutzer
-- -----------------------------------------------------------------

ALTER TABLE shared.benutzer
  ADD COLUMN IF NOT EXISTS password_hash          TEXT          NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS totp_secret            TEXT          NULL,
  ADD COLUMN IF NOT EXISTS totp_aktiviert         BOOLEAN       NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS totp_setup_secret      TEXT          NULL,
  ADD COLUMN IF NOT EXISTS backup_codes           JSONB         DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS letzter_login          TIMESTAMPTZ   NULL,
  ADD COLUMN IF NOT EXISTS fehlversuche           INTEGER       NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS gesperrt_bis           TIMESTAMPTZ   NULL,
  ADD COLUMN IF NOT EXISTS passwort_geaendert_am  TIMESTAMPTZ   NULL,
  ADD COLUMN IF NOT EXISTS muss_passwort_aendern  BOOLEAN       NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN shared.benutzer.password_hash
  IS 'Argon2id-Hash. Default '''' verhindert Login ohne gesetztes Passwort.';
COMMENT ON COLUMN shared.benutzer.totp_secret
  IS 'AES-256-GCM-verschluesseltes TOTP-Secret (Hex). Nie Klartext in DB.';
COMMENT ON COLUMN shared.benutzer.totp_setup_secret
  IS 'Temporaer verschluesseltes Secret waehrend TOTP-Setup. Wird nach Bestaetigung geloescht.';
COMMENT ON COLUMN shared.benutzer.backup_codes
  IS 'JSONB-Array mit Argon2id-gehashten Backup-Codes. Einmal-Verwendung.';
COMMENT ON COLUMN shared.benutzer.fehlversuche
  IS 'Aufeinanderfolgende Fehlversuche. Zurueckgesetzt bei erfolgreichem Login.';
COMMENT ON COLUMN shared.benutzer.gesperrt_bis
  IS 'Zeitpunkt, bis zu dem der Account gesperrt ist. Progressive Sperrdauer.';
COMMENT ON COLUMN shared.benutzer.muss_passwort_aendern
  IS 'TRUE nach Admin-Reset. Erzwingt Passwortwechsel beim naechsten Login.';

-- -----------------------------------------------------------------
-- 2. Auth-Ereignis-Enum
-- -----------------------------------------------------------------

DO $$ BEGIN
  CREATE TYPE shared.auth_ereignis AS ENUM (
    'login',
    'login_fehlgeschlagen',
    'login_totp_pending',
    'token_refresh',
    'totp_aktiviert',
    'totp_deaktiviert',
    'totp_verifiziert',
    'passwort_geaendert',
    'account_gesperrt',
    'account_entsperrt',
    'admin_reset',
    'logout',
    'logout_alle',
    'backup_code_verwendet'
  );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- -----------------------------------------------------------------
-- 3. Refresh-Tokens
-- -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS shared.refresh_tokens (
    id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    benutzer_id     UUID          NOT NULL REFERENCES shared.benutzer(id) ON DELETE CASCADE,
    token_hash      TEXT          NOT NULL,
    ablauf          TIMESTAMPTZ   NOT NULL,
    erstellt_am     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    widerrufen      BOOLEAN       NOT NULL DEFAULT FALSE,
    widerrufen_am   TIMESTAMPTZ   NULL,
    ersetzt_durch   UUID          NULL REFERENCES shared.refresh_tokens(id),
    user_agent      TEXT          NULL,
    ip_adresse      TEXT          NULL
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_benutzer
  ON shared.refresh_tokens(benutzer_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash
  ON shared.refresh_tokens(token_hash) WHERE NOT widerrufen;
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_ablauf
  ON shared.refresh_tokens(ablauf) WHERE NOT widerrufen;

COMMENT ON TABLE shared.refresh_tokens
  IS 'Refresh-Tokens fuer JWT-Rotation. Nur SHA-256-Hash gespeichert, nie Klartext.';
COMMENT ON COLUMN shared.refresh_tokens.ersetzt_durch
  IS 'Verweis auf den Nachfolge-Token. Ermoeglicht Reuse Detection.';

-- -----------------------------------------------------------------
-- 4. Auth-Log (Append-Only, G2)
-- -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS shared.auth_log (
    id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    benutzer_id     UUID          NULL REFERENCES shared.benutzer(id) ON DELETE SET NULL,
    ereignis        TEXT          NOT NULL,
    zeitpunkt       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    ip_adresse      TEXT          NULL,
    user_agent      TEXT          NULL,
    details         JSONB         NULL,
    erfolgreich     BOOLEAN       NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_log_benutzer
  ON shared.auth_log(benutzer_id, zeitpunkt);
CREATE INDEX IF NOT EXISTS idx_auth_log_zeitpunkt
  ON shared.auth_log(zeitpunkt);

COMMENT ON TABLE shared.auth_log
  IS 'Append-Only Audit-Log. Eintraege werden nie geloescht oder geaendert (G2).';

-- -----------------------------------------------------------------
-- 5. Alembic-Version aktualisieren
-- -----------------------------------------------------------------

UPDATE shared.alembic_version SET version_num = '002' WHERE version_num = '001';

COMMIT;
