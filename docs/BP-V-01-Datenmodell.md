# BP-V-01 — Datenmodell-Schema

**Version:** 1.0
**Stand:** 04. Mai 2026
**Grundlage:** Entscheidungen B-001, B-002, B-003

---

## 1. Architektur-Entscheidungen

Das Datenmodell setzt drei Architekturentscheidungen um:

**B-001 Bauteil-Ebene:** Eigene Tabelle `bauteile` zwischen Projekt und Vorgang/LV. Referenz optional (NULL erlaubt). Zusaetzliches Tag-System fuer flexible Dimensionen.

**B-002 Verknuepfungsanalyse:** Deterministische Kaskade ueber `vorgaenger_id` an der Tabelle `vorgaenge`. Konfidenzfeld fuer LLM-Vorschlaege (Schicht 2).

**B-003 Schema-per-Tenant:** Tabellen `mandanten`, `benutzer` und `benutzer_projekt_rollen` im shared-Schema. Alle projektbezogenen Tabellen im Mandanten-Schema (z.B. `tenant_tlbv`).

---

## 2. Entity-Relationship-Diagramm

```mermaid
erDiagram
    MANDANT ||--o{ BENUTZER_PROJEKT_ROLLE : "hat"
    BENUTZER ||--o{ BENUTZER_PROJEKT_ROLLE : "hat"

    PROJEKT ||--o{ BAUTEIL : "enthaelt"
    PROJEKT ||--o{ LEISTUNGSVERZEICHNIS : "hat"
    PROJEKT ||--o{ VORGANG : "hat"
    PROJEKT ||--o{ FIRMA : "hat"
    PROJEKT ||--o{ TAG : "hat"
    PROJEKT ||--o{ DOKUMENT : "hat"

    BAUTEIL ||--o{ LEISTUNGSVERZEICHNIS : "optional"
    BAUTEIL ||--o{ VORGANG : "optional"

    LEISTUNGSVERZEICHNIS ||--o{ LV_POSITION : "enthaelt"
    LEISTUNGSVERZEICHNIS ||--o{ VORGANG : "optional"

    VORGANG ||--o{ DOKUMENT : "hat"
    VORGANG ||--o{ VORGANG_TAG : "hat"
    VORGANG ||--o| VORGANG : "vorgaenger"

    TAG ||--o{ VORGANG_TAG : "zugeordnet"

    FIRMA ||--o{ PERSON : "beschaeftigt"

    MANDANT {
        uuid id PK
        string name
        string slug UK
        bool aktiv
    }

    BENUTZER {
        uuid id PK
        string email UK
        string passwort_hash
        string vorname
        string nachname
        bool totp_aktiviert
    }

    PROJEKT {
        uuid id PK
        string name
        string kurz UK
        enum status
    }

    BAUTEIL {
        uuid id PK
        uuid projekt_id FK
        string kennung
        string name
        enum typ
    }

    LEISTUNGSVERZEICHNIS {
        uuid id PK
        uuid projekt_id FK
        uuid bauteil_id FK "nullable"
        string nummer
        string bezeichnung
        int nummernkreis
        enum klassifikation
    }

    LV_POSITION {
        uuid id PK
        uuid lv_id FK
        string oz
        string kurztext
        decimal menge
        decimal einheitspreis
        decimal gesamtpreis
    }

    VORGANG {
        uuid id PK
        uuid projekt_id FK
        uuid bauteil_id FK "nullable"
        uuid lv_id FK "nullable"
        enum typ
        string nummer
        string gegenstand
        enum status
        decimal kosten_eur
        int zeit_arbeitstage
        string qualitaet_bewertung
        uuid vorgaenger_id FK "nullable"
        enum beziehungstyp "nullable"
        float konfidenz "nullable"
    }

    DOKUMENT {
        uuid id PK
        uuid vorgang_id FK "nullable"
        uuid projekt_id FK
        string dateiname
        string dateipfad_minio
        enum klassifikation
        int version
    }

    FIRMA {
        uuid id PK
        uuid projekt_id FK
        string name
        string kuerzel
        string rolle
    }

    PERSON {
        uuid id PK
        uuid firma_id FK
        string vorname
        string nachname
        string rolle
    }

    TAG {
        uuid id PK
        uuid projekt_id FK
        string kategorie
        string wert
    }

    VORGANG_TAG {
        uuid id PK
        uuid vorgang_id FK
        uuid tag_id FK
    }
```

---

## 3. Schema-Aufteilung

**shared-Schema:**
- `mandanten` — Mandantenverzeichnis
- `benutzer` — Benutzerkonten
- `benutzer_projekt_rollen` — Zuordnung Benutzer → Mandant/Projekt → Rolle

**tenant_{slug}-Schema (pro Mandant):**
- `projekte`
- `bauteile`
- `leistungsverzeichnisse`
- `lv_positionen`
- `vorgaenge`
- `dokumente`
- `firmen`
- `personen`
- `tags`
- `vorgang_tags`

---

## 4. Audit-Felder (an jeder Tabelle)

Jede Tabelle traegt die folgenden Felder (G2 Revisionssicherheit):

- `id` (UUID, PK, server-generiert)
- `erstellt_am` (timestamp with timezone)
- `erstellt_von` (string)
- `geaendert_am` (timestamp with timezone, nullable)
- `geaendert_von` (string, nullable)
- `geloescht` (bool, default false)
- `geloescht_am` (timestamp with timezone, nullable)
- `geloescht_von` (string, nullable)

Physisches Loeschen ist nicht vorgesehen. Soft-Delete ueber das `geloescht`-Flag.

---

## 5. FLI-Stammdaten (Erstbefuellung)

Nach Schema-Migration werden folgende Stammdaten fuer das FLI-Projekt angelegt:

**Mandant:** TLBV (slug: `tlbv`)

**Projekt:** FLI Jena (kurz: `fli`, status: `bau`)

**Bauteile:** Geb. 30, Geb. 31, Geb. 32, Geb. 33, Geb. 34, Aussenanlagen

**Firmen:** TLBV (Bauherr), BWP Architekten (GP), AGE (GU), IBB (Fachbuero), VA Heinekamp (Fachbuero), Gerwert und Partner (Fachbuero), FLI (Nutzer)

**Tags (Beispiele):**
- Kategorie `bauphase`: Rohbau, Fassade, HLS, Elektro, Innenausbau, Aussenanlagen
- Kategorie `gewerk`: AA, ARC, TGA, LAB, LAP, TWP, VAI

---

**Dokumentstatus:** v1.0 — Erstfassung auf Basis der Entscheidungen B-001 bis B-003.
