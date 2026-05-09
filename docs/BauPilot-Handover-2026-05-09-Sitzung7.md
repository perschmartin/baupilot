# Handover — BauPilot Sitzung 09. Mai 2026 (Sitzung 7)

**Chat:** AP 2.1 Nachtragsmanagement — Code-Vorbereitung (komplett)
**Datum:** 09. Mai 2026
**Bearbeiter:** Martin Persch, Claude

---

## Was in dieser Sitzung erarbeitet wurde

### 1. Projektueberblick erstellt

Vollstaendige Bestandsaufnahme: Phase 1 abgeschlossen (7/7 APs), 13.155 LV-Positionen, 615 Vorgaenge, 643 Dokumente. Offene Nacharbeiten identifiziert. Phase 2 Einstieg vorbereitet.

### 2. AP 2.1 Nachtragsmanagement — Code komplett vorbereitet

Alle Dateien fuer AP 2.1 erstellt und lokal getestet (26 Unit-Tests gruen). Kein Deployment durchgefuehrt — liegt bei Martin.

### 3. Migration 007 konsolidiert

Schema-Hotfixes aus dem Volllauf (5 ALTER TABLE auf lv_positionen) in Migration 007 integriert. Zusaetzlich: lb_bezeichnung an bki_baupreise ergaenzt.

### 4. config.py Bug behoben

Duplikate (jwt_secret, totp_key) entfernt. `extra = "ignore"` ergaenzt, damit .env-Variablen die nicht in Settings definiert sind keinen Crash ausloesen.

### 5. requirements.txt bereinigt

Duplikate (minio 2x, httpx 2x) entfernt.

---

## Neue/geaenderte Dateien

```
api/nachtraege/__init__.py             — Modul-Export
api/nachtraege/schemas.py              — 16 Pydantic-Schemas (202 Zeilen)
api/nachtraege/service.py              — NachtragsService: CRUD, 7-Schritte-Workflow,
                                         Variantenlogik A/B/C, NTV-Anlage (696 Zeilen)
api/nachtraege/router.py               — 12 API-Endpunkte (412 Zeilen)
api/nachtraege/lv_abgleich.py          — PostgreSQL-Volltextsuche (124 Zeilen)
api/nachtraege/kostenabgleich.py       — LV-Preise + BKI regionalisiert (208 Zeilen)
api/nachtraege/entscheidungsvorlage.py — LLM-Prompt G1-konform, Freigabe (280 Zeilen)
api/main.py                            — nachtraege_router registriert
api/middleware/__init__.py             — /api/v1/nachtraege exempt
api/config.py                          — Duplikate entfernt, extra="ignore"
api/requirements.txt                   — Duplikate entfernt
alembic/sql/007_nachtragsmanagement.sql — Schema-Hotfixes + NT-Tabellen + BKI
frontend/index.html                    — LVSeite (9. Tab) + NachtraegeSeite mit Stepper
scripts/run-migration-007.ps1          — Migrations-Skript
scripts/seed-nachtrag-pruefschritte.ps1 — Seed fuer 322 bestehende NTs
tests/test_nachtraege_unit.py          — 26 Unit-Tests
```

**Gesamt: ~4.000 Zeilen neuer/geaenderter Code.**

---

## API-Endpunkte (AP 2.1)

| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| GET | /api/v1/nachtraege/ | Nachtraege auflisten (Filter, Summen) |
| POST | /api/v1/nachtraege/ | Nachtrag manuell anlegen |
| GET | /api/v1/nachtraege/{id} | Nachtrag mit Pruefschritten |
| PATCH | /api/v1/nachtraege/{id} | Nachtrag aktualisieren |
| POST | /api/v1/nachtraege/{id}/schritt/{nr} | Pruefschritt abschliessen |
| POST | /api/v1/nachtraege/{id}/lv-abgleich | LV-Abgleich (Schritt 2) |
| POST | /api/v1/nachtraege/{id}/kostenabgleich | Kostenabgleich (Schritt 3) |
| POST | /api/v1/nachtraege/{id}/entscheidungsvorlage | Vorlage generieren (Schritt 4) |
| POST | /api/v1/nachtraege/{id}/ki-bestaetigung/{nr} | KI-Ergebnis bestaetigen/ablehnen |
| POST | /api/v1/nachtraege/{id}/entscheidung | Variante A/B/C (Schritt 6) |
| POST | /api/v1/nachtraege/vorlagen/{id}/freigeben | Vorlage freigeben |
| GET | /api/v1/nachtraege/{id}/vorlagen | Vorlagen eines Nachtrags |

---

## Aktueller Stand

**Phase:** 1 abgeschlossen, Phase 2 vorbereitet
**Meilenstein BP-M0:** Erreicht (04.05.2026)

### Phase 1 — abgeschlossen

Alle 7 APs deployed (1.1, 1.7, 1.3, 1.4, 1.5, 1.6, 1.2).

### Phase 2

| AP | Titel | Status |
|----|-------|--------|
| BP-AP 2.1 | Nachtragsmanagement | **Code vorbereitet, Deployment ausstehend** |

**Datenstand:** 615 Vorgaenge, 9 Firmen, 643 Dokumente (2 GB), 13.155 LV-Positionen, 2 Benutzer, Alembic 006 (007 vorbereitet).

---

## Deployment-Anleitung (fuer Martin)

### Schritt 1: Dateien kopieren

Die ZIP-Datei entpacken und alle Dateien nach `C:\SPARK\spark-baupilot\` kopieren (bestehende ueberschreiben).

### Schritt 2: API-Container neu bauen

```powershell
cd C:\SPARK\spark-baupilot
docker compose -f docker-compose.services.yaml build api
docker compose -f docker-compose.services.yaml build frontend
docker compose -f docker-compose.services.yaml up -d
```

### Schritt 3: Migration 007 ausfuehren

```powershell
.\scripts\run-migration-007.ps1
```

Erwartetes Ergebnis: 8 neue Spalten an vorgaenge, 3 neue Tabellen (nachtragspruefung, entscheidungsvorlagen, bki_baupreise + bki_regionalfaktoren), Alembic 007, 7 Regionalfaktoren.

### Schritt 4: BKI-Daten laden (separat)

Die BKI SQL-INSERTs (bki_baupreise_insert.sql) muessen noch aus den BKI-PDFs extrahiert und geladen werden. Falls die Datei schon existiert:

```powershell
Get-Content .\alembic\sql\bki_baupreise_insert.sql -Raw | docker exec -i baupilot-postgres psql -U baupilot -d baupilot
```

### Schritt 5: Seed — Pruefschritte fuer bestehende NTs

```powershell
.\scripts\seed-nachtrag-pruefschritte.ps1
```

Erwartetes Ergebnis: 322 Pruefschritte (Schritt 1: "Importiert aus Bestandsdaten").

### Schritt 6: Tests

```powershell
docker exec -i baupilot-api python -m pytest /app/tests/test_nachtraege_unit.py -v
```

### Schritt 7: Rauchtest

```powershell
# Nachtraege auflisten
$token = "<access-token>"
Invoke-RestMethod -Uri "http://localhost:8110/api/v1/nachtraege/?projekt=FLI" -Headers @{Authorization="Bearer $token"}

# Nachtrag-Detail mit Pruefschritten
Invoke-RestMethod -Uri "http://localhost:8110/api/v1/nachtraege/<id>" -Headers @{Authorization="Bearer $token"}
```

### Schritt 8: GitHub-Commit

```powershell
git add -A
git commit -m "AP 2.1: Nachtragsmanagement (7-Schritte-Workflow, LV-Abgleich, Kostenabgleich, Entscheidungsvorlage)"
git push
```

---

## Entscheidungen

Keine neuen B-Entscheidungen in dieser Sitzung. Alle Fragen (F-101 bis F-105) waren bereits entschieden.

### Offen (unveraendert)

| ID | Titel | Status |
|----|-------|--------|
| B-006 | VS-NfD-Behandlung: LLM-Verarbeitung zulaessig? | offen |
| B-011 | Digitale Signatur FES | bei Rechtsabteilung |

---

## Bug-Fixes in dieser Sitzung

1. **config.py:** Duplikate jwt_secret/totp_key entfernt. `extra = "ignore"` ergaenzt.
2. **requirements.txt:** Duplikate minio/httpx entfernt.
3. **Migration 007:** Schema-Hotfixes (5 ALTER TABLE) konsolidiert.

---

## Nacharbeit (unveraendert)

- BKI-Daten aus PDFs extrahieren und laden (5.235 Positionen)
- Konzeptpapier v0.5 finalisieren (13.155 LV-Positionen einsetzen)
- Projektanweisung auf v0.5 aktualisieren
- NTV 201-324 nachverknuepfen
- 170 MKs ohne NT-Zuordnung
- Maximilian Muellers Einladung erneuern (abgelaufen 11.05.2026)
- TOTP-Bypass deaktivieren
- Admin-Passwort aendern
- Qdrant-Embedding der LV-Positionen (fuer semantische Suche in Schritt 2)

---

## Hinweise fuer den naechsten Thread

- **AP 2.1 Code ist komplett** — nur Deployment + BKI-Daten fehlen
- TOTP-Bypass aktiv (`BAUPILOT_DEV_SKIP_TOTP=1`)
- Frontend hat jetzt 9 Tabs (+ LV, Nachtraege mit Stepper)
- Nachtraege-Tab nutzt neuen /api/v1/nachtraege Endpoint mit Fallback auf alten /api/v1/vorgaenge
- LLM-Aufruf fuer Entscheidungsvorlage hat Fallback-Text wenn Ollama/LiteLLM nicht laeuft
- Entscheidungsvorlage braucht `qwen2.5:32b` ueber LiteLLM — muss manuell gepullt werden
- BKI-Regionalfaktoren werden mit Migration 007 geseedet (7 Landkreise)
- BKI-Baupreise muessen separat geladen werden (SQL-INSERTs aus PDF-Extraktion)

---

**Status:** AP 2.1 Nachtragsmanagement — Code komplett vorbereitet. 26 Unit-Tests gruen. Deployment wartet auf Martin.
