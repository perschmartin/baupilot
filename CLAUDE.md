# BauPilot — Projektkontext fuer Claude Code

**Letzte Aktualisierung:** 30. Mai 2026

## Was ist BauPilot?

Mandantenfaehige, vollstaendig lokal betriebene Plattform zur digitalen Steuerung oeffentlicher Hochbauprojekte. Pilotanwendung: FLI Jena (Friedrich-Loeffler-Institut) des TLBV Thueringen. Nachnutzung der SPARK-Module des BMDS.

**Produktiv genutzt. Kein Prototyp.** Jede Aenderung hat operative Konsequenzen.

## Grundregeln (nicht verhandelbar)

- **G1 Sachliche Neutralitaet:** Keine Schuldzuweisungen in Texten/Prompts. Nur Fakten mit Quellenangabe.
- **G2 Digitale Souveraenitaet:** Keine externen KI-APIs zur Laufzeit. Nur lokale LLMs (Ollama via LiteLLM).
- **G3 Revisionssicherheit:** Zeitstempel, Urheber, nicht-loeschbare Historie. Append-Only wo noetig.
- **G6 Mandantenfaehigkeit:** Schema-per-Tenant (B-003). Kein Hardcode auf FLI/TLBV.
- **G7 Code oeffentlich, Daten nie:** GitHub perschmartin/baupilot. Keine Secrets, keine Daten im Repo.
- **G8 Dreiklang:** Qualitaet, Zeit (Arbeitstage), Kosten (EUR) als Pflichtfelder an jedem Vorgang.
- **G9 Secure by Default:** Sicherheit fuer oeffentliches Netz. Lockerungen per .env fuer Landesnetz.

## Stack

- **Backend:** Python 3.12, FastAPI (sync!), SQLAlchemy 2.x (sync, text()-SQL), Alembic, Pydantic v2
- **Frontend:** React 18 als einzelne index.html mit CDN-Imports (kein Build-Step, kein Vite) + Plotly 2.35
- **DB:** PostgreSQL 16 (Schema-per-Tenant)
- **Infrastruktur:** Docker Compose, Qdrant, MinIO, LiteLLM, Ollama
- **LLM:** Qwen 2.5 32B (via Ollama → LiteLLM, Modellname `qwen-32b`)
- **Scripting:** PowerShell 7 (kein WSL/bash fuer Deployment)
- **OS:** Windows 11 Pro (Benutzer: Metis)

## Ports

| Dienst         | Port extern | Port intern | Container          |
|----------------|-------------|-------------|--------------------|
| PostgreSQL     | 5436        | 5432        | baupilot-postgres  |
| Qdrant         | 6345/6346   | 6333/6334   | baupilot-qdrant    |
| MinIO          | 9004/9005   | 9000/9001   | baupilot-minio     |
| LiteLLM        | 4003        | 4000        | baupilot-litellm   |
| BauPilot API   | 8110        | 8000        | baupilot-api       |
| Frontend       | 8091        | 80          | baupilot-frontend  |
| Ollama         | 11434       | —           | lokal (kein Docker) |
| spark-docling  | 8070        | 8070        | spark-docling (externer Container) |

## Verzeichnisstruktur

```
C:\SPARK\spark-baupilot\           ← Dieses Repository
├── api/                           ← FastAPI-Backend (15 Module)
│   ├── main.py                    ← Einstiegspunkt, alle 15 Router registriert
│   ├── config.py                  ← Pydantic Settings aus .env (extra="ignore")
│   ├── database.py                ← Engine, SessionLocal, tenant_session()
│   ├── auth/                      ← AP 1.1: JWT, TOTP, Einladungen, Rate-Limiting
│   ├── aufgaben/                  ← AP 1.3: Aufgabenmanagement mit Delegationskaskade
│   ├── vorgaenge/                 ← Read-Only-Endpunkte fuer alle Vorgangtypen
│   ├── kontakte/                  ← AP 1.4: Firmen + Personen CRUD (9 FLI-Firmen)
│   ├── dokumente/                 ← AP 1.5: MinIO-Upload/Download, Versionierung
│   ├── lv_extraktion/             ← AP 1.2: LV-Parser v2 (Docling + pdfplumber-Fallback)
│   ├── nachtraege/                ← AP 2.1: 7-Schritte-Workflow, LV-Abgleich, BKI
│   ├── behinderungen/             ← AP 2.2a: 6-Schritte-Workflow (140 BehA)
│   ├── bedenken/                  ← AP 2.2b: 6-Schritte-Workflow (124 BED)
│   ├── maengel/                   ← AP 2.2c: 5-Schritte-Workflow (27 MA)
│   ├── benachrichtigungen/        ← In-App-Benachrichtigungen (B-012)
│   ├── tags/                      ← Tag-Hierarchie mit parent_id (B-013)
│   ├── extraktion/                ← LLM-Datenanreicherungspipeline
│   ├── ergebnis/                  ← Ergebnis-Visualisierung (8 Endpoints + JSON-Seed)
│   ├── chat/                      ← BauPilot-Chatbot (Tool-Use, LLM-Streaming)
│   ├── protokolle/                ← Word-Protokollgenerierung (python-docx)
│   ├── middleware/                ← TenantMiddleware, AuditLogMiddleware
│   ├── routers/                   ← health, tenants
│   ├── data/                      ← common_passwords.txt (200 Eintraege)
│   ├── requirements.txt           ← Python-Abhaengigkeiten (HIER, nicht Root)
│   └── Dockerfile
├── frontend/
│   ├── index.html                 ← Gesamte React-SPA (eine Datei, ~5000+ Zeilen)
│   ├── nginx.conf                 ← API-Proxy /api/* → baupilot-api:8000, proxy_read_timeout 180s
│   └── Dockerfile
├── alembic/
│   ├── sql/                       ← Migrationen 001-008 als .sql
│   └── versions/                  ← Alembic-Versionen
├── scripts/                       ← PowerShell-Deployment- und Seed-Scripts
├── tests/                         ← Unit-Tests (pytest): auth, aufgaben, lv_parser, nachtraege
├── docs/                          ← Spezifikationen, Handovers, Feedback-Analyse
├── backup-2026-05-30/             ← Rollback-Sicherung vor Nachtsitzung 30.05.
├── docker-compose.yaml            ← Infrastruktur (Postgres, Qdrant, MinIO)
└── docker-compose.services.yaml   ← Anwendung (API, LiteLLM, Frontend)
```

## Code-Konventionen (KRITISCH)

### Python/Backend
- **Sync SQLAlchemy ueberall.** Kein async. Keine async def in Routern.
- **text()-SQL fuer alle Queries.** Kein ORM-Modell-Zugriff. Immer `from sqlalchemy import text`.
- **Service-Pattern:** `XxxService(db)` — einzige Stelle mit DB-Zugriff.
- **Dependencies:** Direkt aus `database.py` und `config.py` importieren.
- **Spalte heisst `passwort_hash`** (nicht password_hash).
- **Mandant via `benutzer_projekt_rollen.mandant_slug`** — kein mandant_id FK auf benutzer.
- **Enums liegen in `public` Schema.** SET search_path muss public einschliessen. CAST(:param AS typ) verwenden.
- **JSONB-Casts:** `CAST(:param AS jsonb)` statt `::jsonb` (SQLAlchemy-Kompatibilitaet).
- **requirements.txt liegt in `api/`**, nicht im Projektroot. Build-Context ist `./api`.

### Frontend
- **Eine einzige index.html** — alles inline (React, Styles, Logik).
- **React 18 via CDN** — `React.createElement` als `h()`, kein JSX, kein Build-Step.
- **Plotly 2.35 via CDN** — fuer Gantt, Sankey, Wasserfall, Heatmap, Mini-Gantt.
- **Dunkles UI:** #111 Hintergrund, amber/orange (#f59e0b) Akzent, DM Sans Font.
- **API-Funktionen:** `api()` fuer /api/v1/auth/*, `bpApi()` fuer /api/v1/*, `bpUpload()` fuer Datei-Uploads, `bpDownload()` fuer Blob-Downloads.
- **Silent Token Refresh:** Bei 401 automatisch via doRefreshToken(), keine manuelle Intervention noetig.
- **AuthProvider** verwaltet token/refresh/user/phase via React Context.
- **React-Hook-Reihenfolge:** Alle Hooks VOR conditional returns (Memory: `baupilot_react_hook_order`).
- **MSYS_NO_PATHCONV=1** vor `docker cp`/`docker exec` mit absoluten Container-Pfaden.

### PowerShell/Deployment
- `Set-Content -Encoding utf8NoBOM -NoNewline -Force` (kein Out-File, kein BOM).
- SQL-Dateien via `Get-Content | docker exec -i psql` pipen — nicht Alembic im Container.
- `$Host` ist reserviert — immer `$TargetHost` verwenden.
- PowerShell 7+ verwenden (nicht 5.1) — wegen `??` und `&` Operatoren.

### Middleware-Pflicht bei neuem Modul
Jedes neue Backend-Modul MUSS seinen Pfad-Praefix in `api/middleware/__init__.py` unter `TENANT_EXEMPT_PREFIXES` eintragen. Sonst: HTTP 400 vor Router-Erreichen. Aktuell 15 Eintraege (auth, aufgaben, vorgaenge, kontakte, dokumente, lv, nachtraege, behinderungen, bedenken, maengel, benachrichtigungen, tags, extraktion, ergebnis, chat).

## Datenbankschema (Alembic 008)

### Migrationshistorie

| Nr | Alembic | Inhalt |
|----|---------|--------|
| 001 | 001 | Initiales Schema (shared + tenant_tlbv) |
| 002 | 002 | Auth-Erweiterung (passwort_hash, TOTP, Refresh-Tokens, Auth-Log) |
| 003 | 003 | Einladungen (shared.einladungen) |
| 004 | 004 | Aufgabenmanagement (aufgaben_kommentare, Delegationsfelder) |
| 005 | 005 | Dokumentenverwaltung (dokumente, vorgang_dokumente) |
| 006 | 006 | LV-Extraktion (nummernkreis, menge, einheit, langtext an lv_positionen) |
| 007 | 007 | Nachtragsmanagement (nachtragspruefung, bki_baupreise, bki_regionalfaktoren, entscheidungsvorlagen) |
| 008 | 008 | Stoerungsmanagement + Benachrichtigungen + Tag-Hierarchie |

### shared-Schema (7 Tabellen)
- `mandanten` (slug, name)
- `benutzer` (passwort_hash VARCHAR 500, TOTP-Felder, Sperrfelder)
- `benutzer_projekt_rollen` (mandant_slug, projekt_kurz, rolle — alle NOT NULL)
- `refresh_tokens` (Reuse Detection)
- `auth_log` (Append-Only)
- `einladungen` (Token-basiert, einmalig, zeitlich begrenzt)
- `alembic_version`

### tenant_tlbv-Schema (18+ Tabellen)
- `projekte`, `bauteile`, `leistungsverzeichnisse`, `lv_positionen`
- `vorgaenge` (mit Delegations-, Verknuepfungs-, NT-, Stoerungsfeldern: mangelart, gewaehrleistung_bis, verlaengerung_monate, nachtragsfolge_eur, folgekosten_betrieb_eur, minderkosten_eur)
- `nachtragspruefung` (7-Schritte + entscheidung_grund/hoehe + begruendung_grund/hoehe)
- `behinderungspruefung` (6-Schritte-Workflow, AP 2.2a)
- `bedenkenpruefung` (6-Schritte-Workflow, AP 2.2b)
- `mangelpruefung` (5-Schritte-Workflow, AP 2.2c)
- `bki_baupreise`, `bki_regionalfaktoren` (Preisreferenz)
- `entscheidungsvorlagen` (LLM-generiert, freigabepflichtig)
- `aufgaben_kommentare` (revisionssicher)
- `dokumente`, `vorgang_dokumente` (m:n)
- `dokument_tags` (m:n Dokument↔Tag, B-013)
- `firmen`, `personen`, `tags` (mit parent_id, ist_kategorie_wurzel), `vorgang_tags`
- `benachrichtigungen` (In-App, B-012)
- `benachrichtigungs_regeln` (mandantenspezifische Trigger)

### 13 Enums (alle in public)
projektstatus, bauteiltyp, klassifikation, vorgangtyp, vorgangstatus, beziehungstyp, benutzerrolle, auth_ereignis, dokumentkategorie, signaturstatus, mangelart, benachrichtigungstyp, benachrichtigungs_prioritaet

## Datenstand (live, ca. 20.05.2026)

- 614-615 Vorgaenge (322 NT, 140 BehA, 124 BED, 27 MA, 2 AF)
- 322 Nachtragspruefschritte, 140 Behinderungspruefschritte, 124 Bedenkenpruefschritte, 27 Maengelpruefschritte
- 13.155 LV-Positionen (60 LVs, 59 Docling + 1 pdfplumber-text)
- 4.779 BKI-Baupreise (2.334 aus 2025 + 2.445 aus 2026), 7 Regionalfaktoren
- 643 Dokumente (2 GB in MinIO), 318 mit Tags (B-013)
- 9 Firmen, 6 Bauteile (GEB30-GEB34, AUSS)
- 2 Benutzer (admin + Maximilian Mueller, Einladung abgelaufen)
- ~97 Vorgaenge mit LLM-Beschreibung (auto-uebernommen), ~88 mit LV-Bruecke, ~40+ mit Bauteil, ~67+ mit Verursacher
- 1 Entscheidungsvorlage (NT-004, v1)
- 1 Nullterminplan (JSON-Seed aus BWP-xlsx, vorlaeufig)
- Alembic 008

## Aktueller Stand (30.05.2026)

**Phase:** 2 fast abgeschlossen, Phase-3-Elemente (Ergebnis-Visualisierung) vorgezogen.

### Roadmap-Etappen (BauPilot-Roadmap-2026-05-18.md)

| Etappe | Titel | Status |
|--------|-------|--------|
| E0 | Token-Refresh + Clean Commit | ✅ 18.05. |
| E1 | AD B-012 + B-013 | ✅ 18.05. |
| E2 | Migration 008 | ✅ 18.05. |
| E3 | NTV-Doppelbeauftragungspruefung | ✅ 18.05. |
| E4/4b | NT-Frontend-Haertung + Grund/Hoehe | ✅ 18.05. |
| E5 | Behinderungen-Workflow | ✅ 18.05. |
| E6 | Bedenken-Workflow | ✅ 18.05. |
| E7 | Maengel-Workflow | ✅ 18.05. |
| E8 | Aufgaben + Kontakte Erweiterungen | ✅ 18.05. |
| E9 | In-App-Benachrichtigungen | ✅ 18.05. |
| E10 | Dokumentenstruktur-Refactor | ✅ 18.05. |
| E11 | Protokollgenerierung (Word) | ✅ 18.05. |
| E12 | Verknuepfungsanalyse BK→BA→NT | 🔄 erste Stufe (LLM-Extraktor) |
| E13 | Phase 3 Termincontrolling (Asta X83) | 🔄 visuell vorgezogen, X83-Parser offen |
| E14 | Sicherheits-Haertung + Doku v1.0 | ⬜ |
| E15 | Ergebnis-Auswertung + LV-Auswertung | ✅ 19.05. |

### Datenanreicherungs-Pipeline

LLM-gestuetzte Extraktion in 3 Paessen:
- **Pass 1:** PDF → Beschreibung (extraktion-nachtlauf.ps1, ~106 min fuer 139 Vorgaenge)
- **Pass 2:** Verursacher/Bauteil/Z/K (extraktor_v2.py)
- **Pass 3:** Bauteil-Fokus (extraktor_bauteil.py, niedrigere Schwelle)
- **Deterministisch:** lv_bruecke.py (lv_position → lv_id), plan_verknuepfungen.py (xlsx → bauteil_id)

KRITISCH: Kein `docker restart baupilot-api` waehrend Pipeline laeuft! Frontend-Updates via `docker cp` sind OK.

## API-Module und Endpunkte

### Auth (/api/v1/auth)
Login, Refresh, Logout, Profil, Passwort-Aendern, TOTP-Setup/Verify, Einladung, Registrierung, Benutzer-Liste.

### Aufgaben (/api/v1/aufgaben)
CRUD, Statuswechsel, Kommentare (revisionssicher), Delegationskaskade, Timeline.

### Vorgaenge (/api/v1/vorgaenge)
Read-Only fuer alle Vorgangtypen mit Filtern. Fallback-Endpoint fuer aeltere Clients.

### Nachtraege (/api/v1/nachtraege)
7-Schritte-Pruefung, LV-Abgleich (OR + Kompositum-Aufbrechung), Kostenabgleich (LV + BKI regionalisiert), Entscheidungsvorlage (LLM G1-konform), Variante A/B/C, NTV-Doppelbeauftragungspruefung.

### Behinderungen (/api/v1/behinderungen)
6-Schritte-Workflow: Erfassung → Pruefung → Anerkennung/Rueckweisung → Schriftverkehr → ggf. erneute Pruefung → Abmeldung GU.

### Bedenken (/api/v1/bedenken)
6-Schritte-Workflow analog Behinderungen + LV-Position-Zuordnung + Gewaehrleistungsfristen.

### Maengel (/api/v1/maengel)
5-Schritte-Workflow, Mangelart (Ausfuehrungs-/Planungsmangel), Kostenuntergliederung (Nachtragsfolge, Folgekosten, Minderkosten).

### Benachrichtigungen (/api/v1/benachrichtigungen)
In-App-Notifications mit 6 Trigger-Typen. Bell-Menu im Header mit 30s-Polling.

### Tags (/api/v1/tags)
Tag-Hierarchie mit parent_id, Kategorie-Wurzeln. Dokument↔Tag-Verknuepfung.

### Dokumente (/api/v1/dokumente)
MinIO-Upload/Download, Versionierung, SHA-256, Tag-Picker, Signaturvorbereitung (B-011).

### Extraktion (/api/v1/extraktion)
LLM-Datenanreicherung: Beschreibung, Verursacher, Bauteil aus Dokumenten extrahieren.

### Ergebnis (/api/v1/ergebnis)
8 Endpoints: vorgaenge (gefiltert), nullterminplan (JSON), kennzahlen, firmen, bauteile, pipeline-status (Live), lv-uebersicht, lv-detail/{lv_id}. Datenquelle fuer alle 4 Plotly-Charts.

### Chat (/api/v1/chat)
BauPilot-Chatbot mit Tool-Use (Datenbankabfragen) und LLM-Streaming ueber LiteLLM.

### Protokolle (/api/v1/protokolle via api/protokolle/)
Word-Generierung (python-docx) pro Nachtrag mit Pruefergebnissen und Dreiklang.

### LV-Extraktion (/api/v1/lv)
Docling-basierte PDF-Extraktion, Parser v2, 4 Header-Varianten, 28-Unit Baubranche-Vokabular.

### Kontakte (/api/v1/kontakte)
Firmen + Personen CRUD, hierarchisch (GP → Subs → Personen).

## Frontend-Tabs (Stand 19.05.2026)

1. **Dashboard** — Uebersicht, Profil, Passwort, Einladungen
2. **Aufgaben** — Liste, Detail, Timeline, Statuswechsel
3. **Nachtraege** — Liste, Detail mit Stepper (7 Schritte), 4 Tabs (Vorlage/LV/Kosten/Entscheidung)
4. **Behinderungen** — Liste, Detail mit 6-Schritte-Stepper
5. **Bedenken** — Liste, Detail mit 6-Schritte-Stepper
6. **Maengel** — Liste, Detail mit 5-Schritte-Stepper, Edit-Form
7. **Dokumente** — Upload, Tag-Picker, Tree-View (folgt in E11b)
8. **Kontakte** — Firmenliste, hierarchisch nach Rolle
9. **LV** — 13.155 Positionen, Suche/Filter
10. **Ergebnis** — Pipeline-Status-Card, KPI-Bar, 4 Plotly-Charts (Gantt/Sankey/Wasserfall/Heatmap), Click-to-Detail-Modal
11. **LV-Auswertung** — Drill-Down nach LV, Mini-Gantt, OZ-Baum (8 Ebenen)

Plus: **ChatWidget** (ausklappbar, Tool-Use, Streaming, VorgangModal bei Klick).

## Offene Entscheidungen

| ID    | Titel                                              | Status        |
|-------|-----------------------------------------------------|---------------|
| B-006 | VS-NfD-Behandlung: LLM-Verarbeitung zulaessig?     | offen         |
| B-011 | Digitale Signatur FES                               | Rechtsabtlg.  |
| B-013 | Netzplan-Technologie: Vite + React Flow             | Votum Martin ausstehend |
| B-014 | Gantt-Library (SVAR vs. DHTMLX)                     | offen, vor Phase 3 |
| B-015 | Asta-Import-Strategie (MPXJ vs. CSV)               | offen, vor Phase 3 |

## Wie bauen und testen?

```powershell
# API-Container bauen + starten
docker compose -f docker-compose.services.yaml build api
docker compose -f docker-compose.services.yaml up -d api

# Frontend-Container bauen + starten
docker compose -f docker-compose.services.yaml build frontend
docker compose -f docker-compose.services.yaml up -d frontend

# Nur Frontend-HTML austauschen (kein Restart noetig):
docker cp frontend/index.html baupilot-frontend:/usr/share/nginx/html/index.html

# Tests ausfuehren
docker exec baupilot-api pytest /app/tests/ -v

# Migration ausfuehren (Beispiel 008)
.\scripts\run-migration-008.ps1

# Ollama manuell starten (nicht in PATH)
Start-Process "C:\Users\Metis\AppData\Local\Programs\Ollama\ollama.exe" -ArgumentList "serve" -WindowStyle Hidden
```

## Bekannte Fallstricke

- **TOTP-Bypass aktiv:** `BAUPILOT_DEV_SKIP_TOTP=1` in docker-compose.services.yaml — vor Produktivbetrieb entfernen!
- **LiteLLM-Modellname:** `qwen-32b` (nicht `qwen2.5:32b`)
- **DB-Passwort:** noch `CHANGE_ME_IN_PRODUCTION`
- **Maximilian Muellers Einladung:** abgelaufen seit 11.05.2026 — erneuern
- **common_passwords.txt:** nur 200 Eintraege, Soll: 10.000
- **LV 207:** Text-Modus ohne EP/GP — bei Bedarf mit GPU-Server nochmal via Docling
- **Admin-Passwort:** noch nicht rotiert — nach Entwicklungsabschluss aendern
- **Kein `docker restart baupilot-api`** waehrend LLM-Pipeline laeuft
- **MSYS_NO_PATHCONV=1** vor docker-Befehlen mit absoluten Container-Pfaden
- **`nummer`-Spalte ist VARCHAR** (nicht integer) — SQL muss Strings verwenden
- **Plotly-CDN:** `https://cdn.plot.ly/plotly-2.35.2.min.js` — bei Air-Gap lokal hosten
- **nginx proxy_read_timeout:** auf 180s erhoeht (LLM-Aufrufe brauchen 30-120s)
