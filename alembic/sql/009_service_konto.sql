-- ============================================================
-- Migration 009: Service-Konto-Flag (E14 — TOTP-Bypass abloesen)
-- Fuegt shared.benutzer.ist_dienstkonto hinzu. Dienstkonten
-- (Maschinen-Identitaeten) ueberspringen beim Login TOTP, weil sie
-- kein interaktives 2FA leisten koennen. Ersetzt langfristig den
-- hartkodierten Dev-Bypass (BAUPILOT_DEV_SKIP_TOTP).
--
-- Voraussetzung: Migration 008 ausgefuehrt.
-- Idempotent (ADD COLUMN IF NOT EXISTS); Default FALSE -> keine
-- Verhaltensaenderung fuer bestehende (Menschen-)Konten.
-- Konformitaet: G9 (2FA-Pflicht bleibt fuer Menschen-Konten).
-- ============================================================

BEGIN;

ALTER TABLE shared.benutzer
  ADD COLUMN IF NOT EXISTS ist_dienstkonto BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN shared.benutzer.ist_dienstkonto
  IS 'TRUE = Maschinen-/Service-Konto: ueberspringt TOTP beim Login (headless-Automation). Menschen-Konten bleiben FALSE (TOTP-Pflicht, G9).';

UPDATE shared.alembic_version SET version_num = '009' WHERE version_num = '008';

COMMIT;
