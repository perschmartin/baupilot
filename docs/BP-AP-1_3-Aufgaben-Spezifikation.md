# BP-AP 1.3 — Aufgabenmanagement mit Delegationskaskade

**Version:** 0.1
**Datum:** 05. Mai 2026
**Bearbeiter:** Martin Persch, Claude

---

## 1. Ziel

Das Aufgabenmanagement ist das erste sichtbare Fachmodul des BauPiloten (Saeule 4 — Tagesbetrieb). Es ermoeglicht dem TLBV-Projektleiter, Aufgaben zu erstellen, an Projektbeteiligte zu delegieren, den Bearbeitungsstand zu verfolgen und die Kommunikation revisionssicher zu dokumentieren.

## 2. Fachliche Anforderungen

### 2.1 Aufgaben (nutzt bestehende vorgaenge-Tabelle mit typ='aufgabe')

Jede Aufgabe traegt:
- Nummer (AF-001, AF-002, ...), automatisch vergeben pro Projekt
- Gegenstand (Kurztext, max. 1000 Zeichen)
- Beschreibung (Langtext)
- Prioritaet: kritisch, hoch, mittel, niedrig
- Zustaendig (Benutzer-ID)
- Delegiert von (Benutzer-ID)
- Frist (Datum)
- Status: offen, in_bearbeitung, geprueft, abgeschlossen, storniert
- Dreiklang: Kosten (EUR), Zeit (Arbeitstage), Qualitaetsbewertung (Text)
- Optionale Verknuepfungen: Bauteil, LV, Firma

### 2.2 Delegation

Der angemeldete Benutzer erstellt eine Aufgabe und weist sie einem anderen Benutzer zu (zustaendig_benutzer_id). Der Ersteller wird als delegiert_von_benutzer_id gespeichert. Aufgaben koennen zurueckgespielt werden (Statuswechsel + Kommentar).

### 2.3 Kommentarsystem (Aufgaben-Chat)

Pro Aufgabe gibt es einen chronologischen Kommentar-Thread. Jeder Kommentar hat Zeitstempel, Autor, Text und ist nicht loeschbar (G2 Revisionssicherheit).

### 2.4 Statusmaschine

offen → in_bearbeitung → geprueft → abgeschlossen
                                  → abgelehnt (zurueck an delegiert_von)
Jeder Status: → storniert

Statuswechsel erfordern einen Kommentar (ausser offen → in_bearbeitung).

## 3. Schema-Erweiterungen (Migration 004)

### 3.1 Neue Spalten an vorgaenge

- zustaendig_benutzer_id UUID NULL REFERENCES shared.benutzer(id)
- delegiert_von_benutzer_id UUID NULL REFERENCES shared.benutzer(id)
- prioritaet VARCHAR(20) NOT NULL DEFAULT 'mittel'

### 3.2 Neue Tabelle aufgaben_kommentare (pro Tenant-Schema)

- id UUID PK
- vorgang_id UUID NOT NULL REFERENCES vorgaenge(id)
- autor_id UUID NOT NULL REFERENCES shared.benutzer(id)
- autor_name VARCHAR(255) NOT NULL (denormalisiert fuer Performance)
- inhalt TEXT NOT NULL
- erstellt_am TIMESTAMPTZ NOT NULL DEFAULT NOW()
- Indizes auf vorgang_id und erstellt_am

### 3.3 Cleanup

- Duplikat-Spalte password_hash (TEXT) aus shared.benutzer entfernen
- Systemprojekt SYS in tenant_tlbv.projekte anlegen

## 4. API-Endpunkte

Alle unter /api/v1/aufgaben, geschuetzt durch CurrentUser.

| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| GET | / | Aufgaben auflisten (Filter: status, zustaendig, prioritaet, frist) |
| POST | / | Aufgabe erstellen |
| GET | /{id} | Aufgabe mit Kommentaren laden |
| PATCH | /{id} | Aufgabe aktualisieren (Felder, Status) |
| POST | /{id}/kommentar | Kommentar hinzufuegen |
| GET | /meine | Meine Aufgaben (zustaendig = angemeldeter Benutzer) |

## 5. Frontend

Neue Seite "Aufgaben" im Dashboard:
- Tabellarische Uebersicht mit Prioritaetsanzeige, Zustaendig, Frist, Status
- Filter nach Status
- Aufgabe-erstellen-Dialog
- Detail-Ansicht mit Kommentar-Thread
- Aufgabe-zurueckspielen-Button

## 6. Testplan

- Aufgabe erstellen, aktualisieren, Status wechseln
- Delegation pruefen (zustaendig vs. delegiert_von)
- Kommentar hinzufuegen und laden
- Statusmaschine: gueltige und ungueltige Uebergaenge
- Fristfilter
- Mandantentrennung (Aufgaben nur im eigenen Schema sichtbar)

## 7. Abnahmekriterien

- Aufgaben CRUD funktional
- Kommentare revisionssicher (nicht loeschbar)
- Dreiklang-Felder an jeder Aufgabe
- Automatische Nummernvergabe (AF-001, AF-002, ...)
- Frontend zeigt Aufgabenliste und Detail-Ansicht
- Mindestens 20 Tests gruen

---

**Status:** Vorbereitet fuer Deployment-Sitzung.
