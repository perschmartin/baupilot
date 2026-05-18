-- =============================================================================
-- Migration 008: Stoerungsmanagement + Benachrichtigungen + Tag-Hierarchie
-- BauPilot AP 2.2 Vorbereitung + B-012 + B-013 Schema-Beitrag
-- Datum: 18.05.2026
-- Abhaengigkeit: Migration 007 (Nachtragsmanagement)
-- =============================================================================
-- Konsolidiert die Schema-Touches aus:
--   - Feedback-Analyse 18.05.2026 (Behinderungs-/Bedenken-/Mangel-Workflow)
--   - AD-Beschluss B-012 (Benachrichtigungssystem In-App + SMTP-Stub)
--   - AD-Beschluss B-013 (Tag-Hierarchie + dokument_tags)
-- Roadmap-Bezug: Etappe 2.
--
-- WICHTIG: Alle Operationen idempotent (IF NOT EXISTS) wo moeglich.
-- Migration ist transaktional sicher: BEGIN/COMMIT umschliesst die gesamten
-- DDL-Schritte. Bei Fehler in irgendeinem Schritt wird das Schema unveraendert.
-- =============================================================================

BEGIN;

-- =============================================================================
-- 1. NEUE ENUMS IN PUBLIC
-- =============================================================================
-- Konvention (siehe Konzept §4.2): Enums liegen im public-Schema, damit alle
-- Tenant-Schemata sie referenzieren koennen. SET search_path muss public
-- immer einschliessen (sonst Resolve-Fehler).

-- Mangelart: Ausfuehrungsmangel vs. Planungsmangel
-- Steuert die Verantwortungszuordnung in AP 2.2c (Ausfuehrungsmangel -> GU,
-- Planungsmangel -> GP). Spalte vorgaenge.mangelart ist nur fuer
-- vorgangtyp='mangelanzeige' relevant.
DO $$ BEGIN
    CREATE TYPE public.mangelart AS ENUM (
        'ausfuehrungsmangel',
        'planungsmangel',
        'unklar'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Benachrichtigungstyp: 6 Kategorien gemaess B-012 Empfehlung
DO $$ BEGIN
    CREATE TYPE public.benachrichtigungstyp AS ENUM (
        'aufgabe_ueberfaellig',
        'beha_erinnerung',          -- BehA in 'zurueckgewiesen' seit X Tagen
        'neuer_vorgang',            -- neuer Nachtrag/BehA/BED importiert
        'entscheidung_ausstehend',  -- Nachtrag/BehA wartet auf PL-Entscheidung
        'doppelbeauftragung',       -- LV-Doppelbeauftragungs-Warnung aus NT-F-02
        'system'                    -- z.B. Heartbeat-Fehler
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Benachrichtigungs-Prioritaet: visuelles UI-Mapping
DO $$ BEGIN
    CREATE TYPE public.benachrichtigungs_prioritaet AS ENUM (
        'info',     -- blaue Markierung
        'hinweis',  -- amber
        'warnung'   -- rot
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- =============================================================================
-- 2. STOERUNGSPRUEFUNG-TABELLEN (TENANT_TLBV) — AP 2.2 Vorbereitung
-- =============================================================================
-- Drei neue Tabellen analog zu nachtragspruefung. Jeweils n Schritte pro
-- Vorgang (Behinderung: 6 Schritte, Bedenken: 6, Mangel: 5). UNIQUE auf
-- (vorgang_id, schritt) verhindert Duplikate. Audit-Spalten G2-konform.

SET search_path TO tenant_tlbv, shared, public;

-- ----------------------------------------------------------------------------
-- 2a. Behinderungspruefung (6 Schritte fuer AP 2.2a)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS behinderungspruefung (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vorgang_id        UUID NOT NULL REFERENCES vorgaenge(id),
    -- 1=Erfassung, 2=Pruefung, 3=Anerkennung/Rueckweisung, 4=Schriftverkehr,
    -- 5=ggf. erneute Pruefung, 6=Abmeldung GU
    schritt           INTEGER NOT NULL CHECK (schritt BETWEEN 1 AND 6),
    titel             VARCHAR(200) NOT NULL,
    ergebnis          TEXT NULL,
    bearbeiter_id     UUID NULL REFERENCES shared.benutzer(id),
    abgeschlossen     BOOLEAN NOT NULL DEFAULT FALSE,
    abgeschlossen_am  TIMESTAMPTZ NULL,
    -- KI-Felder fuer kuenftige LLM-Unterstuetzung (Bestaetigungs-Gate B-002)
    ki_eingabe        JSONB NULL,
    ki_ergebnis       JSONB NULL,
    ki_konfidenz      REAL NULL CHECK (ki_konfidenz BETWEEN 0.0 AND 1.0),
    ki_bestaetigt     BOOLEAN NULL,
    ki_bestaetigt_von UUID NULL REFERENCES shared.benutzer(id),
    ki_bestaetigt_am  TIMESTAMPTZ NULL,
    -- Audit (G2)
    erstellt_am       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    erstellt_von      UUID NOT NULL REFERENCES shared.benutzer(id),
    geaendert_am      TIMESTAMPTZ NULL,
    geaendert_von     UUID NULL REFERENCES shared.benutzer(id),
    UNIQUE(vorgang_id, schritt)
);
CREATE INDEX IF NOT EXISTS idx_behinderungspruefung_vorgang ON behinderungspruefung(vorgang_id);

-- ----------------------------------------------------------------------------
-- 2b. Bedenkenpruefung (6 Schritte fuer AP 2.2b)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bedenkenpruefung (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vorgang_id        UUID NOT NULL REFERENCES vorgaenge(id),
    -- Gleiches 6-Schritte-Muster wie BehA — VOB/B §4 Abs. 3 Bedenkenpflicht
    schritt           INTEGER NOT NULL CHECK (schritt BETWEEN 1 AND 6),
    titel             VARCHAR(200) NOT NULL,
    ergebnis          TEXT NULL,
    bearbeiter_id     UUID NULL REFERENCES shared.benutzer(id),
    abgeschlossen     BOOLEAN NOT NULL DEFAULT FALSE,
    abgeschlossen_am  TIMESTAMPTZ NULL,
    ki_eingabe        JSONB NULL,
    ki_ergebnis       JSONB NULL,
    ki_konfidenz      REAL NULL CHECK (ki_konfidenz BETWEEN 0.0 AND 1.0),
    ki_bestaetigt     BOOLEAN NULL,
    ki_bestaetigt_von UUID NULL REFERENCES shared.benutzer(id),
    ki_bestaetigt_am  TIMESTAMPTZ NULL,
    erstellt_am       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    erstellt_von      UUID NOT NULL REFERENCES shared.benutzer(id),
    geaendert_am      TIMESTAMPTZ NULL,
    geaendert_von     UUID NULL REFERENCES shared.benutzer(id),
    UNIQUE(vorgang_id, schritt)
);
CREATE INDEX IF NOT EXISTS idx_bedenkenpruefung_vorgang ON bedenkenpruefung(vorgang_id);

-- ----------------------------------------------------------------------------
-- 2c. Mangelpruefung (5 Schritte fuer AP 2.2c)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mangelpruefung (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vorgang_id        UUID NOT NULL REFERENCES vorgaenge(id),
    -- 1=Erfassung (mit Bildern), 2=Mangelschreiben, 3=Schriftverkehr,
    -- 4=Abmeldung GU/GP, 5=Bestaetigung Bauherr
    schritt           INTEGER NOT NULL CHECK (schritt BETWEEN 1 AND 5),
    titel             VARCHAR(200) NOT NULL,
    ergebnis          TEXT NULL,
    bearbeiter_id     UUID NULL REFERENCES shared.benutzer(id),
    abgeschlossen     BOOLEAN NOT NULL DEFAULT FALSE,
    abgeschlossen_am  TIMESTAMPTZ NULL,
    ki_eingabe        JSONB NULL,
    ki_ergebnis       JSONB NULL,
    ki_konfidenz      REAL NULL CHECK (ki_konfidenz BETWEEN 0.0 AND 1.0),
    ki_bestaetigt     BOOLEAN NULL,
    ki_bestaetigt_von UUID NULL REFERENCES shared.benutzer(id),
    ki_bestaetigt_am  TIMESTAMPTZ NULL,
    erstellt_am       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    erstellt_von      UUID NOT NULL REFERENCES shared.benutzer(id),
    geaendert_am      TIMESTAMPTZ NULL,
    geaendert_von     UUID NULL REFERENCES shared.benutzer(id),
    UNIQUE(vorgang_id, schritt)
);
CREATE INDEX IF NOT EXISTS idx_mangelpruefung_vorgang ON mangelpruefung(vorgang_id);

-- =============================================================================
-- 3. ERWEITERUNG vorgaenge — Mangel-/Gewaehrleistungs-/Kostenfelder
-- =============================================================================
-- Nur fuer vorgangtyp='mangelanzeige' und 'bedenkenanzeige' relevant.
-- Andere Vorgangstypen lassen die Felder NULL.

ALTER TABLE vorgaenge ADD COLUMN IF NOT EXISTS mangelart                public.mangelart NULL;
ALTER TABLE vorgaenge ADD COLUMN IF NOT EXISTS gewaehrleistung_bis      DATE             NULL;
ALTER TABLE vorgaenge ADD COLUMN IF NOT EXISTS verlaengerung_monate     INTEGER          NULL;

-- Kostenuntergliederung fuer Maengel (Feedback 18.05.):
--   nachtragsfolge_eur     = bereits genehmigte NTs als Mangelfolge
--   folgekosten_betrieb_eur = laufende Betriebskosten durch Mangel
--   minderkosten_eur       = Anspruch auf Minderung
ALTER TABLE vorgaenge ADD COLUMN IF NOT EXISTS nachtragsfolge_eur       NUMERIC(14,2) NULL;
ALTER TABLE vorgaenge ADD COLUMN IF NOT EXISTS folgekosten_betrieb_eur  NUMERIC(14,2) NULL;
ALTER TABLE vorgaenge ADD COLUMN IF NOT EXISTS minderkosten_eur         NUMERIC(14,2) NULL;

-- =============================================================================
-- 4. ERWEITERUNG nachtragspruefung — Entscheidung Grund/Hoehe (NT-F-04)
-- =============================================================================
-- Feedback 18.05.: Entscheidung "dem Grunde nach" und "der Hoehe nach" sind
-- getrennt zu fuehren (VOB/B-Praxis). Bisher nur einheitliche Variante A/B/C
-- ohne Aufteilung. Diese vier Felder erlauben getrennte Bewertung.
-- Pruefschritt 6 nutzt diese Felder, der Frontend-Stepper rendert zwei
-- getrennte Bereiche (Etappe 4 Roadmap).

ALTER TABLE nachtragspruefung ADD COLUMN IF NOT EXISTS entscheidung_grund   BOOLEAN NULL;
ALTER TABLE nachtragspruefung ADD COLUMN IF NOT EXISTS entscheidung_hoehe   BOOLEAN NULL;
ALTER TABLE nachtragspruefung ADD COLUMN IF NOT EXISTS begruendung_grund    TEXT    NULL;
ALTER TABLE nachtragspruefung ADD COLUMN IF NOT EXISTS begruendung_hoehe    TEXT    NULL;

-- =============================================================================
-- 5. TAG-HIERARCHIE (B-013 Empfehlung)
-- =============================================================================
-- B-013 Beschluss: tags bekommen eine Self-Reference (parent_id), die einen
-- beliebig tiefen Forest erlaubt. Die bestehende (kategorie, wert)-Struktur
-- bleibt erhalten: 'kategorie' wird zur Wurzel-Markierung, 'wert' bleibt
-- der konkrete Tag-Wert.
--
-- ist_kategorie_wurzel=TRUE markiert die obersten Wurzeln (Bauphase, Bauteil,
-- Dokumenttyp im Default-Template). Diese Wurzeln werden nicht direkt
-- zugewiesen, sie strukturieren nur den Tree.

ALTER TABLE tags ADD COLUMN IF NOT EXISTS parent_id            UUID    NULL REFERENCES tags(id) ON DELETE SET NULL;
ALTER TABLE tags ADD COLUMN IF NOT EXISTS ist_kategorie_wurzel BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_tags_parent ON tags(parent_id) WHERE parent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tags_kategorie_wurzel ON tags(ist_kategorie_wurzel) WHERE ist_kategorie_wurzel = TRUE;

-- =============================================================================
-- 6. dokument_tags (m:n Dokument <-> Tag) — B-013 Empfehlung
-- =============================================================================
-- Dokumente werden ueber Tags klassifiziert (Bauphase, Bauteil, Dokumenttyp).
-- Mehrfachzuordnung explizit erlaubt: ein Dokument kann in mehreren Phasen
-- liegen (z.B. Uebergabedokumentation LPH 8 + 9).
-- ON DELETE CASCADE bei Dokument-Loeschung (entfernt automatisch die Tag-Refs).
-- ON DELETE RESTRICT bei Tag-Loeschung (verhindert Loeschung eines genutzten Tags).

CREATE TABLE IF NOT EXISTS dokument_tags (
    dokument_id UUID NOT NULL REFERENCES dokumente(id) ON DELETE CASCADE,
    tag_id      UUID NOT NULL REFERENCES tags(id) ON DELETE RESTRICT,
    erstellt_am TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    erstellt_von VARCHAR(255) NOT NULL,
    PRIMARY KEY (dokument_id, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_dokument_tags_tag ON dokument_tags(tag_id);

-- =============================================================================
-- 7. BENACHRICHTIGUNGEN (B-012 Empfehlung — A In-App)
-- =============================================================================
-- Eine Benachrichtigung pro Trigger-Ereignis und Empfaenger.
-- Eine Benachrichtigung kann (muss aber nicht) auf einen Vorgang verweisen.
-- benachrichtigungen werden lesbar markiert, aber nicht geloescht (G2 Audit).

CREATE TABLE IF NOT EXISTS benachrichtigungen (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    benutzer_id  UUID NOT NULL REFERENCES shared.benutzer(id),
    vorgang_id   UUID NULL REFERENCES vorgaenge(id) ON DELETE SET NULL,
    typ          public.benachrichtigungstyp NOT NULL,
    prioritaet   public.benachrichtigungs_prioritaet NOT NULL DEFAULT 'info',
    titel        VARCHAR(200) NOT NULL,
    inhalt       TEXT NOT NULL,
    gelesen      BOOLEAN NOT NULL DEFAULT FALSE,
    gelesen_am   TIMESTAMPTZ NULL,
    erstellt_am  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Performance-Index: ungelesene pro Benutzer
CREATE INDEX IF NOT EXISTS idx_benachrichtigungen_benutzer
    ON benachrichtigungen(benutzer_id, gelesen, erstellt_am DESC);

-- benachrichtigungs_regeln: mandantenspezifische Konfiguration der Trigger.
-- Beispiel-Eintrag (kommt ueber Seed): 'beha_erinnerung', 14, 'projektleiter'.
CREATE TABLE IF NOT EXISTS benachrichtigungs_regeln (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger        VARCHAR(50) NOT NULL,         -- Trigger-Name (frei, vom Code definiert)
    intervall_tage INTEGER NULL,                 -- bei zeitbasierten Triggern
    empfaenger_rolle public.benutzerrolle NULL,  -- NULL = alle relevanten Rollen
    aktiv          BOOLEAN NOT NULL DEFAULT TRUE,
    erstellt_am    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    erstellt_von   VARCHAR(255) NOT NULL,
    UNIQUE(trigger, empfaenger_rolle)
);

-- =============================================================================
-- 8. SEED — Default-Tag-Hierarchie fuer tenant_tlbv (B-013)
-- =============================================================================
-- Drei Wurzeln + ihre direkten Kinder. Anwender koennen die Struktur spaeter
-- pro Mandant anpassen (Hinzufuegen/Umbenennen/Loeschen).
-- Wichtig: Wir muessen ein projekt_id setzen, weil tags.projekt_id NOT NULL.
-- Wir verwenden hier das Systemprojekt SYS, das in Migration 004 angelegt wurde.

-- Hilfs-Variable: SYS-Projekt-ID auflesen
DO $$
DECLARE
    sys_projekt_id UUID;
    bauphase_id UUID;
    bauteil_id UUID;
    dokumenttyp_id UUID;
BEGIN
    -- SYS-Projekt finden (existiert seit Migration 004)
    SELECT id INTO sys_projekt_id FROM projekte WHERE kurz='SYS' LIMIT 1;
    IF sys_projekt_id IS NULL THEN
        RAISE EXCEPTION 'Systemprojekt SYS nicht gefunden — Migration 004 nicht ausgefuehrt?';
    END IF;

    -- Bauphase-Wurzel + Kinder
    INSERT INTO tags (projekt_id, kategorie, wert, ist_kategorie_wurzel, erstellt_von)
        VALUES (sys_projekt_id, 'struktur', 'Bauphase', TRUE, 'migration_008')
        RETURNING id INTO bauphase_id;
    INSERT INTO tags (projekt_id, kategorie, wert, parent_id, erstellt_von) VALUES
        (sys_projekt_id, 'Bauphase', '1 Bedarfsplanung',          bauphase_id, 'migration_008'),
        (sys_projekt_id, 'Bauphase', '2 Vorentwurf (ES-Bau)',     bauphase_id, 'migration_008'),
        (sys_projekt_id, 'Bauphase', '3 Entwurf (EW-Bau)',        bauphase_id, 'migration_008'),
        (sys_projekt_id, 'Bauphase', '4 Genehmigungsplanung',     bauphase_id, 'migration_008'),
        (sys_projekt_id, 'Bauphase', '5 Ausfuehrungsplanung',     bauphase_id, 'migration_008'),
        (sys_projekt_id, 'Bauphase', '6 Vorbereitung Vergabe',    bauphase_id, 'migration_008'),
        (sys_projekt_id, 'Bauphase', '7 Mitwirkung Vergabe',      bauphase_id, 'migration_008'),
        (sys_projekt_id, 'Bauphase', '8 Objektueberwachung',      bauphase_id, 'migration_008'),
        (sys_projekt_id, 'Bauphase', '9 Bestand / Dokumentation', bauphase_id, 'migration_008');

    -- Bauteil-Wurzel + FLI-Kinder
    INSERT INTO tags (projekt_id, kategorie, wert, ist_kategorie_wurzel, erstellt_von)
        VALUES (sys_projekt_id, 'struktur', 'Bauteil', TRUE, 'migration_008')
        RETURNING id INTO bauteil_id;
    INSERT INTO tags (projekt_id, kategorie, wert, parent_id, erstellt_von) VALUES
        (sys_projekt_id, 'Bauteil', 'Gebaeudeabschnitt 30', bauteil_id, 'migration_008'),
        (sys_projekt_id, 'Bauteil', 'Gebaeudeabschnitt 31', bauteil_id, 'migration_008'),
        (sys_projekt_id, 'Bauteil', 'Gebaeudeabschnitt 32', bauteil_id, 'migration_008'),
        (sys_projekt_id, 'Bauteil', 'Gebaeudeabschnitt 33', bauteil_id, 'migration_008'),
        (sys_projekt_id, 'Bauteil', 'Gebaeudeabschnitt 34', bauteil_id, 'migration_008'),
        (sys_projekt_id, 'Bauteil', 'Aussenanlagen',        bauteil_id, 'migration_008');

    -- Dokumenttyp-Wurzel + Kinder (Spiegel des dokumentkategorie-Enums)
    INSERT INTO tags (projekt_id, kategorie, wert, ist_kategorie_wurzel, erstellt_von)
        VALUES (sys_projekt_id, 'struktur', 'Dokumenttyp', TRUE, 'migration_008')
        RETURNING id INTO dokumenttyp_id;
    INSERT INTO tags (projekt_id, kategorie, wert, parent_id, erstellt_von) VALUES
        (sys_projekt_id, 'Dokumenttyp', 'LV',                 dokumenttyp_id, 'migration_008'),
        (sys_projekt_id, 'Dokumenttyp', 'Nachtrag',           dokumenttyp_id, 'migration_008'),
        (sys_projekt_id, 'Dokumenttyp', 'Behinderungsanzeige',dokumenttyp_id, 'migration_008'),
        (sys_projekt_id, 'Dokumenttyp', 'Bedenkenanzeige',    dokumenttyp_id, 'migration_008'),
        (sys_projekt_id, 'Dokumenttyp', 'Mangelanzeige',      dokumenttyp_id, 'migration_008'),
        (sys_projekt_id, 'Dokumenttyp', 'Protokoll',          dokumenttyp_id, 'migration_008'),
        (sys_projekt_id, 'Dokumenttyp', 'Plan',               dokumenttyp_id, 'migration_008'),
        (sys_projekt_id, 'Dokumenttyp', 'Foto',               dokumenttyp_id, 'migration_008'),
        (sys_projekt_id, 'Dokumenttyp', 'Gutachten',          dokumenttyp_id, 'migration_008');
END $$;

-- =============================================================================
-- 9. SEED — Default-Benachrichtigungsregeln (B-012)
-- =============================================================================
-- Trigger-Namen werden vom Backend-Service erkannt. Beim ersten Roll-out
-- aktivieren wir nur die zwei wichtigsten Regeln. Weitere Regeln und
-- Mandanten-Anpassung folgen.

INSERT INTO benachrichtigungs_regeln (trigger, intervall_tage, empfaenger_rolle, erstellt_von) VALUES
    ('aufgabe_ueberfaellig', NULL, NULL,             'migration_008'),  -- alle Rollen, ohne Intervall
    ('beha_erinnerung',      14,   'projektleiter',  'migration_008'),  -- alle 14 Tage an PL
    ('neuer_vorgang',        NULL, 'projektleiter',  'migration_008'),
    ('doppelbeauftragung',   NULL, NULL,             'migration_008')
ON CONFLICT (trigger, empfaenger_rolle) DO NOTHING;

-- =============================================================================
-- 10. ALEMBIC-VERSION
-- =============================================================================

UPDATE shared.alembic_version SET version_num = '008';

COMMIT;

-- =============================================================================
-- VALIDIERUNGS-QUERIES (manuell, nach erfolgreichem Lauf)
-- =============================================================================
-- SELECT version_num FROM shared.alembic_version;                       -- 008
-- SELECT COUNT(*) FROM tenant_tlbv.behinderungspruefung;                -- 0
-- SELECT COUNT(*) FROM tenant_tlbv.bedenkenpruefung;                    -- 0
-- SELECT COUNT(*) FROM tenant_tlbv.mangelpruefung;                      -- 0
-- SELECT COUNT(*) FROM tenant_tlbv.dokument_tags;                       -- 0
-- SELECT COUNT(*) FROM tenant_tlbv.benachrichtigungen;                  -- 0
-- SELECT COUNT(*) FROM tenant_tlbv.benachrichtigungs_regeln;            -- 4
-- SELECT COUNT(*) FROM tenant_tlbv.tags WHERE ist_kategorie_wurzel;     -- 3 (Bauphase, Bauteil, Dokumenttyp)
-- SELECT COUNT(*) FROM tenant_tlbv.tags WHERE parent_id IS NOT NULL;    -- 24 (9 + 6 + 9)
-- SELECT typname FROM pg_type WHERE typname IN ('mangelart','benachrichtigungstyp','benachrichtigungs_prioritaet');  -- 3 Zeilen
