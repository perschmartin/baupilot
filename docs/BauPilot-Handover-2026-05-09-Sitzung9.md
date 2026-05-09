# Handover — BauPilot Sitzung 09. Mai 2026 (Sitzung 9 — Final)

**Chat:** Frontend-Upgrade Mockup + Prompt-Optimierung + Live-Test
**Datum:** 09. Mai 2026
**Bearbeiter:** Martin Persch, Claude

---

## Was in dieser Sitzung erreicht wurde

### 1. Frontend NachtragDetail — komplett neu nach Mockup-Design

Die NachtragDetail-Komponente wurde von 127 auf ~470 Zeilen erweitert und live getestet.

**Umgesetzte Features:**
- Zwei-Spalten-Layout: Stepper-Sidebar (280px) + Content-Bereich
- 4 Tabs: Entscheidungsvorlage / LV-Abgleich / Kostenabgleich / Entscheidung
- Stepper-Klick wechselt automatisch zum passenden Tab
- Entscheidungsvorlage mit farbigen Abschnittsmarkern (amber=Sachverhalt, blau=Pruefergebnis, gruen=BauPilot-Einschaetzung)
- `parseVorlageAbschnitte()` erkennt Section-Marker aus LLM-Output, Fallback auf Paragraphen-Split
- "Freigeben" und "Neu generieren" Buttons
- LV-Abgleich-Tab: Grid mit allen Treffern, OZ, Kurztext (vollstaendig, kein Truncation), EP, Relevanz
- Kostenabgleich-Tab: Gefordert/Regionalfaktor-Karten, Abweichungs-Karten
- Entscheidung-Tab: Variante A/B/C als Karten, deaktiviert bis Schritt 5 abgeschlossen
- Schritte 5 (Pruefung PL) und 7 (Abschluss) mit Freitext-Eingabe und beschreibenden Labels
- Variante A setzt betrag_genehmigt = betrag_gefordert (85.000 EUR korrekt)
- Auto-Tab-Wechsel nach LV-Abgleich, Kostenabgleich und Vorlage-Generierung
- KI-Bestaetigungs-Buttons in allen relevanten Tabs (B-002 Gate)
- Breadcrumb-Header mit Schritt-Badge
- Logo auf Login-Seite zentriert

### 2. Prompt-Optimierung (entscheidungsvorlage.py)

- G1-Haertung: Explizites Verbot von Wertungen, Spekulationen, wertenden Adjektiven
- Markdown-Listen verboten
- "Liefervertrag" verboten → "Werkvertrag" (VOB/B, BGB §631 ff.)
- Section-Marker: `SACHVERHALT` / `PRUEFERGEBNIS` / `BAUPILOT-EINSCHAETZUNG`
- Dreiklang pro Abschnitt erzwungen
- Abschluss-Satz: "Die endgueltige Entscheidung liegt bei der Projektleitung."
- **Live getestet:** Qwen 2.5 32B liefert saubere Vorlagen mit korrekten Abschnitten

### 3. Nginx-Timeout Fix

- `proxy_read_timeout` von 60s (Default) auf 180s erhoeht
- Behebt "Unbekannter Fehler" bei LLM-Aufrufen (30-120s Verarbeitungszeit)

### 4. seed-nachtrag-pruefschritte.ps1 Fix

- PS `$$`-Escaping via SQL-Datei-Piping mit `@'...'@` (wortwörtlicher Here-String)

### 5. AP 2.3 und 2.4 als erledigt markiert

- AP 2.3 (LV-Matching/Regionalpreisvergleich): Absorbiert in AP 2.1
- AP 2.4 (Entscheidungsvorlagen-Generator): Absorbiert in AP 2.1

### 6. Kompletter 7-Schritte-Flow live getestet

NT-004 erfolgreich durch alle 7 Schritte gefuehrt:
1. Erfassung (Import) ✓
2. LV-Abgleich (20 Treffer, bestaetigt) ✓
3. Kostenabgleich (ueber Bandbreite, bestaetigt) ✓
4. Entscheidungsvorlage (Qwen 2.5 32B, bestaetigt) ✓
5. Pruefung PL (Freitext, abgeschlossen) ✓
6. Entscheidung Variante A (85.000 EUR genehmigt) ✓
7. Abschluss (Dokumentation) ✓

---

## Geaenderte Dateien

```
frontend/index.html                          — NachtragDetail komplett neu + Logo-Fix + alle Bugfixes
frontend/nginx.conf                          — proxy_read_timeout 180s
api/nachtraege/entscheidungsvorlage.py       — System-Prompt + User-Prompt optimiert
scripts/seed-nachtrag-pruefschritte.ps1      — PS $$-Escaping Fix
```

---

## Aktueller Stand

**Phase:** 2
**Meilenstein BP-M1:** AP 2.1 deployed, live getestet, 7-Schritte-Flow verifiziert

### Phase 2

| AP | Titel | Status |
|----|-------|--------|
| BP-AP 2.1 | Nachtragsmanagement | **deployed + 7-Schritte-Flow komplett getestet** |
| BP-AP 2.2 | Behinderungs-/Bedenkenanzeigen | offen |
| BP-AP 2.3 | LV-Matching / Regionalpreisvergleich | **erledigt (in 2.1 absorbiert)** |
| BP-AP 2.4 | Entscheidungsvorlagen-Generator | **erledigt (in 2.1 absorbiert)** |
| BP-AP 2.5 | Protokollgenerierung Word/PDF | **naechstes AP** |
| BP-AP 2.6 | Verkuepfungsanalyse (BK → BA → NT → Termin) | offen |

### Offene Entscheidungen

| ID | Titel | Status |
|----|-------|--------|
| B-006 | VS-NfD-Behandlung: LLM-Verarbeitung zulaessig? | offen |
| B-011 | Digitale Signatur FES | bei Rechtsabteilung |

---

## Naechster Thread — Prioritaeten

### 1. AP 2.5 Protokollgenerierung (Abschlussdokument)
- Onepager Word/PDF mit allen NT-Daten, Pruefergebnissen, Entscheidungsvorlage, Dreiklang
- python-docx Template im Backend
- Download-Endpunkt (GET /nachtraege/{id}/protokoll)
- Ablage als Dokument im BauPilot (tenant_tlbv.dokumente)

### 2. B-011 Digitale Signatur
- AD-pflichtig: Welches Verfahren (FES/QES), welcher Anbieter?
- Air-Gap-Kompatibilitaet beachten
- Rechtsabteilung-Rueckmeldung abwarten

### 3. Frontend-Verbesserungen (kleinere Punkte)
- Vorlage-Text editierbar machen (braucht PATCH-Endpoint)
- Schritt 1 (Erfassung): Nachtrag-Kurzbeschreibung anzeigen

### 4. Nacharbeiten (unveraendert)
- Konzeptpapier v0.5 finalisieren (Platzhalter [LV_POSITIONEN_GESAMT] → 13.155)
- Projektanweisung v0.5
- Maximilian Muellers Einladung erneuern
- TOTP-Bypass deaktivieren vor Produktivbetrieb
- Admin-Passwort aendern
- NTV 201–324 nachverknuepfen
- 170 MKs ohne NT-Zuordnung

---

## Hinweise fuer den naechsten Thread

- Ollama manuell starten: `Start-Process "C:\Users\Metis\AppData\Local\Programs\Ollama\ollama.exe" -ArgumentList "serve" -WindowStyle Hidden`
- LiteLLM-Modellname: `qwen-32b`
- TOTP-Bypass aktiv (`BAUPILOT_DEV_SKIP_TOTP=1`)
- NT-004 Testdaten: betrag_gefordert=85000, KG 480, Variante A, alle 7 Schritte durchlaufen
- Nginx-Timeout jetzt 180s (LLM-Aufrufe brauchen 30-120s)
- Prompt liefert Section-Marker: SACHVERHALT / PRUEFERGEBNIS / BAUPILOT-EINSCHAETZUNG

### NT-004 Reset-Skript (fuer erneutes Testen)

```powershell
@"
SET search_path TO tenant_tlbv, shared, public;
DELETE FROM entscheidungsvorlagen WHERE vorgang_id = '28c68598-2fe3-4aa5-97fe-1c994987722c';
DELETE FROM nachtragspruefung WHERE vorgang_id = '28c68598-2fe3-4aa5-97fe-1c994987722c' AND schritt > 1;
UPDATE vorgaenge SET nachtragsvariante = NULL, betrag_geprueft = NULL, betrag_genehmigt = NULL, status = 'in_bearbeitung' WHERE id = '28c68598-2fe3-4aa5-97fe-1c994987722c';
SELECT 'NT-004 zurueckgesetzt' AS ergebnis;
"@ | docker exec -i baupilot-postgres psql -U baupilot -d baupilot
```

---

**Status:** Frontend-Upgrade deployed, Prompt optimiert, 7-Schritte-Flow komplett verifiziert. Naechstes AP: 2.5 Protokollgenerierung.
