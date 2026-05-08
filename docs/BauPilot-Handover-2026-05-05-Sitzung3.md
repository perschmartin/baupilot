# Handover — BauPilot Sitzung 05. Mai 2026 (Sitzung 3)

**Chat:** AP 1.3 Aufgabenmanagement — Vorbereitung
**Datum:** 05. Mai 2026
**Bearbeiter:** Martin Persch, Claude

---

## Was in dieser Sitzung erarbeitet wurde

### AP 1.3 Aufgabenmanagement — Backend und Migration vorbereitet

Martin war in einer Besprechung. Claude hat eigenstaendig den gesamten Code-Stand analysiert und folgende Artefakte vorbereitet:

**1. Spezifikation BP-AP-1_3-Aufgaben-Spezifikation.md**
- Fachliche Anforderungen: Delegation, Kommentarsystem, Statusmaschine
- Schema-Erweiterungen fuer Migration 004
- API-Endpunkte (6 Endpunkte unter /api/v1/aufgaben)
- Frontend-Anforderungen
- Testplan mit 26 Testfaellen

**2. Migration 004 (alembic/sql/004_aufgabenmanagement.sql)**
- 3 neue Spalten an vorgaenge: zustaendig_benutzer_id, delegiert_von_benutzer_id, prioritaet
- Neue Tabelle aufgaben_kommentare pro Tenant-Schema (revisionssicher, G2)
- Indizes fuer Aufgaben-Queries (WHERE typ = 'aufgabe')
- Cleanup: Duplikat-Spalte password_hash (TEXT) entfernt
- Systemprojekt SYS in tenant_tlbv.projekte angelegt
- Alembic-Version 003 → 004

**3. Backend-Modul api/aufgaben/**
- __init__.py — Modul-Export
- schemas.py — Pydantic v2 Schemas (Erstellen, Aktualisieren, Detail, Kommentar, Liste)
- service.py — Geschaeftslogik mit AufgabenService(db) nach Auth-Service-Pattern
  - Automatische Nummernvergabe (AF-001, AF-002, ...)
  - Statusmaschine mit validierten Uebergaengen
  - Dreiklang-Felder (G3) durchgaengig
  - Benutzer-Joins fuer zustaendig_name und delegiert_von_name
- router.py — 6 FastAPI-Endpunkte (alle geschuetzt durch CurrentUser)

**4. Integrationen**
- api/main.py — aufgaben_router eingebunden
- api/middleware/__init__.py — /api/v1/aufgaben von Tenant-Header-Pflicht ausgenommen (CurrentUser regelt Tenant via JWT)

**5. Tests (tests/test_aufgaben_unit.py)**
- 26 Unit-Tests: Schema-Validierung, Statusmaschine, Dreiklang
- Alle 26 Tests gruen

**6. Deployment-Script (scripts/run-migration-004.ps1)**
- PowerShell-Skript zur Ausfuehrung der Migration gegen baupilot-postgres

### Noch nicht erledigt (gemeinsam mit Martin)

- **Frontend:** Aufgaben-Seite muss in frontend/index.html integriert werden (UI-Entscheidungen erforderlich)
- **Deployment:** Migration 004 ausfuehren, Container neu bauen
- **FLI-Projekt:** Projekt "FLI" in tenant_tlbv.projekte anlegen (Aufgaben brauchen ein Projekt)
- **Integrationstests:** Gegen laufende DB testen

---

## Deployment-Schritte (wenn Martin zurueck ist)

1. Neue Dateien in C:\SPARK\spark-baupilot\ entpacken (ZIP oder einzeln kopieren)
2. Migration ausfuehren: `.\scripts\run-migration-004.ps1`
3. FLI-Projekt anlegen (einmalig, per psql oder Seed-Skript)
4. Container neu bauen: `docker compose -f docker-compose.services.yaml build api`
5. Container neu starten: `docker compose -f docker-compose.services.yaml up -d api`
6. API testen: `curl http://localhost:8110/api/v1/aufgaben/?projekt=FLI -H "Authorization: Bearer <token>"`
7. Unit-Tests: `python -m pytest tests/test_aufgaben_unit.py -v`

---

## Naechste Schritte

1. Frontend fuer Aufgaben bauen (innerhalb dieser oder naechster Sitzung)
2. Integrationstests schreiben
3. AP 1.4 Kontakte/Firmen/Personen (Router + Frontend fuer bestehende Tabellen)
4. Konzeptpapier v0.4 aktualisieren

---

## Dateien in diesem Paket

```
alembic/sql/004_aufgabenmanagement.sql     — Migration
api/aufgaben/__init__.py                    — Modul-Export
api/aufgaben/schemas.py                     — Pydantic-Schemas
api/aufgaben/service.py                     — Geschaeftslogik
api/aufgaben/router.py                      — API-Endpunkte
api/main.py                                 — Aktualisiert (aufgaben_router)
api/middleware/__init__.py                   — Aktualisiert (Aufgaben-Exempt)
scripts/run-migration-004.ps1               — Deployment-Script
tests/test_aufgaben_unit.py                 — 26 Unit-Tests
docs/BP-AP-1_3-Aufgaben-Spezifikation.md   — Spezifikation
```

---

**Status:** Backend fuer AP 1.3 vorbereitet. Deployment und Frontend ausstehend.
