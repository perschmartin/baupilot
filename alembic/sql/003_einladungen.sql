-- ============================================================
-- Migration 003: Einladungssystem
-- Neue Tabelle shared.einladungen fuer Admin-gesteuerten Zugang.
-- Kein Benutzer kommt ohne gueltige Einladung ins System.
-- B-010: Einladungssystem als einziger Registrierungsweg.
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS shared.einladungen (
    id              UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash      TEXT          NOT NULL UNIQUE,
    email           VARCHAR(255)  NOT NULL,
    rolle           VARCHAR(50)   NOT NULL DEFAULT 'leser',
    mandant_slug    VARCHAR(63)   NOT NULL,
    projekt_kurz    VARCHAR(63)   NOT NULL,
    ablauf          TIMESTAMPTZ   NOT NULL,
    erstellt_von    UUID          NOT NULL REFERENCES shared.benutzer(id),
    erstellt_am     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    verwendet       BOOLEAN       NOT NULL DEFAULT FALSE,
    verwendet_am    TIMESTAMPTZ   NULL
);

CREATE INDEX IF NOT EXISTS idx_einladungen_email
  ON shared.einladungen(email);
CREATE INDEX IF NOT EXISTS idx_einladungen_hash
  ON shared.einladungen(token_hash) WHERE NOT verwendet;

COMMENT ON TABLE shared.einladungen
  IS 'Admin-gesteuerte Einladungen. Einziger Weg zur Kontoerstellung (B-010).';

UPDATE shared.alembic_version SET version_num = '003' WHERE version_num = '002';

COMMIT;
