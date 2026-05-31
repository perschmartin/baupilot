# BauPilot — Feedback-Analyse und Umsetzungsplan

**Datum:** 18. Mai 2026
**Anlass:** Nutzerfeedback zum aktuellen Stand des BauPilot (Phase 2, AP 2.1 deployed)
**Bearbeiter:** Martin Persch, Claude
**Quelle:** Feedback Maximilian Mueller (TLBV)

---

## 1. Feedback-Analyse: Abgleich mit Ist-Stand

Das Feedback wird gegen den aktuellen Entwicklungsstand (Alembic 007, 8 Tabs, 615 Vorgaenge, 643 Dokumente) und die bestehenden Spezifikationen abgeglichen. Jeder Punkt wird einer von drei Kategorien zugeordnet:

- **VORHANDEN** — Funktion existiert bereits oder ist in AP 2.1 spezifiziert
- **GEPLANT** — Funktion ist im Konzeptpapier oder in einem kuenftigen AP vorgesehen, aber noch nicht umgesetzt
- **NEU** — Funktion war bisher nicht vorgesehen und muss ins Backlog aufgenommen werden

### 1.1 Authentifizierung / Token-Ablauf

| Feedback | Ist-Stand | Kategorie |
|----------|-----------|-----------|
| Token laeuft zu schnell ab (15 min) | Access-Token 15min (BAUPILOT_JWT_ACCESS_MINUTES). Refresh-Token 7 Tage mit Rotation. Frontend muesste Refresh automatisch ausfuehren. | BUGFIX |

**Analyse:** Das Problem ist hoechstwahrscheinlich kein Backend-Problem. Der Access-Token hat 15min TTL (branchenkonform), aber das Frontend fuehrt aktuell keinen automatischen Token-Refresh durch. Der Refresh-Token (7 Tage) wird nicht genutzt. Loesung: Silent Refresh im Frontend implementieren — wenn ein API-Call 401 zurueckliefert, automatisch POST /api/v1/auth/refresh aufrufen und den Request wiederholen. Dadurch bleibt die Session 7 Tage aktiv, solange der Browser geoeffnet ist.

**Keine Aenderung der 15-Minuten-TTL noetig.** Die ist sicherheitstechnisch korrekt (G9). Der Fix liegt im Frontend.

### 1.2 Aufgaben

| Feedback | Ist-Stand | Kategorie |
|----------|-----------|-----------|
| Aufgabe Personen direkt zuordnen | zustaendig_benutzer_id existiert (Migration 004). Frontend zeigt Zustaendigen. | VORHANDEN (Erweiterung: Dropdown statt Freitext) |
| Dateien an Aufgabe anfuegen | vorgang_dokumente (m:n) existiert seit Migration 005. API: POST /api/v1/dokumente/upload mit vorgang_id. Frontend-Integration fehlt. | GEPLANT (Frontend-Luecke) |
| Aufgabenhistorie (Wer/Wann/Was) | aufgaben_kommentare existiert (Migration 004, revisionssicher). Anzeige im Frontend nur als Kommentarliste, nicht als Timeline. | VORHANDEN (UI-Verbesserung noetig) |
| Kategorien fuer Aufgaben (Ober-/Unterkategorien) | tags + vorgang_tags existieren. Kein hierarchisches Kategorie-System. | NEU (Kategorie-Hierarchie) |

### 1.3 Nachtraege

| Feedback | Ist-Stand | Kategorie |
|----------|-----------|-----------|
| Verlinkung zu Originaldateien (NT-Schreiben, LV, Plaene) | vorgang_dokumente (m:n) existiert. 329 Dokumente bereits verknuepft. Frontend zeigt Dokumente noch nicht in der Nachtrags-Detailansicht. | GEPLANT (AP 2.1 Frontend-Ausbau) |
| Nachtragspruefung mit Dokumenten-Timeline | nachtragspruefung-Tabelle hat 7 Schritte mit Zeitstempel und bearbeiter_id. Dokumentenzuordnung pro Schritt fehlt. | NEU (Dokument-pro-Pruefschritt) |
| Unterreiter "Nachtragspruefung" | AP 2.1 Spec v0.2 sieht Stepper-UI mit 7 Schritten vor. Noch nicht als separater Unterreiter, sondern als Detailansicht. | VORHANDEN (AP 2.1 Frontend) |
| LV-Abgleich mit NTV-Spalte (Doppelbeauftragungspruefung) | LV-Abgleich in AP 2.1 spezifiziert (Schritt 2). NTV-Abgleich (bereits genehmigte NTs gegen gleiche LV-Position) fehlt. | NEU (kritisch, fachlich wichtig) |
| Kostenabgleich mit Nachvollziehbarkeit (absolut + prozentual) | kostenabgleich.py berechnet Abweichungen gegen LV und BKI. Frontend zeigt noch keine Aufschluesslung. | GEPLANT (AP 2.1 Frontend-Detail) |
| Entscheidung "dem Grunde nach" / "der Hoehe nach" | Variante A/B/C in AP 2.1 spezifiziert. Entscheidungsfelder (entscheidung_grund, entscheidung_hoehe) als getrennte Felder fehlen noch im Schema. | NEU (Schema-Erweiterung) |
| 7. Schritt "Abschluss" mit NTV-Erstellung | Auto-NTV bei Variante A in AP 2.1 v0.2 spezifiziert (F-104 beantwortet: ja, automatisch). NTV-Nummer im UI anzeigen fehlt. | GEPLANT (AP 2.1 Frontend) |
| Zeitauswirkung als "+12 Tage" | zeitauswirkung_tage existiert als INTEGER in nachtragspruefung. Frontend-Darstellung als "+X Tage" fehlt. | VORHANDEN (UI-Formatierung) |

### 1.4 Behinderungen

| Feedback | Ist-Stand | Kategorie |
|----------|-----------|-----------|
| Bearbeitung wie Aufgaben | Behinderungen sind vorgaenge mit typ='behinderungsanzeige'. 140 Vorgaenge importiert. Aktuell nur Read-Only-Ansicht (VorgaengeSeite-Komponente). Kein Workflow. | NEU (AP 2.2 — war bereits als Folge-AP vorgesehen) |
| Pruefschritte: Erfassung → Pruefung → Anerkennung/Rueckweisung → Schriftverkehr → Abmeldung | Kein Workflow-Schema fuer Behinderungen. vorgangstatus-Enum existiert, aber kein strukturierter Ablauf. | NEU (AP 2.2 Kernfunktion) |
| Zusammenfassung nach Grund, Verantwortlich, Kosten, Zeitverzug | Dreiklang Q/Z/K an vorgaenge vorhanden. Aggregations-Endpunkt und Dashboard-Karte fehlen. | NEU (AP 2.2 Reporting) |
| Automatisierte E-Mails bei Rueckweisung (alle 2 Wochen) | Kein E-Mail-System vorhanden (Air-Gap, B-009: kein SMTP). | AD-KANDIDAT (B-012) |

### 1.5 Bedenken

| Feedback | Ist-Stand | Kategorie |
|----------|-----------|-----------|
| Gleicher Workflow wie Behinderungen | 124 Bedenken importiert, Read-Only. | NEU (AP 2.2, gemeinsam mit Behinderungen) |
| Zuordnung zu LV-Position und Gewaehrleistungsfristen | LV-Verknuepfung ueber vorgang → lv_position moeglich (bestehende Felder). Gewaehrleistungsfristen fehlen im Schema. | NEU (Schema-Erweiterung) |
| Zuordnung zu Wartungsvertraegen | Nicht im Scope. Wartungsvertraege sind Betriebsphase, nicht Bauphase. | AUSSERHALB SCOPE (spaeter) |

### 1.6 Maengel

| Feedback | Ist-Stand | Kategorie |
|----------|-----------|-----------|
| Pruefschritte: Erfassung → Mangelschreiben → Schriftverkehr → Abmeldung → Bestaetigung | 27 Maengel importiert, Read-Only. Kein Workflow. | NEU (AP 2.3 oder AP 2.2 erweitert) |
| Bilder, Beschreibung, Planeintrag, Datum, Sachverhalt | Bilder/Dokumente ueber vorgang_dokumente anhaengbar. Planeintrag (Raumzuordnung/Grundrissmarkierung) fehlt. | NEU (Planzuordnung = groesseres Feature) |
| Zuordnung Ausfuehrungs- vs. Planungsmangel | vorgaenge.bezeichnung enthält freien Text. Kein Enum fuer Mangelart. | NEU (Enum mangelart) |
| Zusammenfassung: verantwortlich, Kosten (Nachtraege, Folgekosten, Minderkosten), Zeitverzug, Qualitaet | Dreiklang Q/Z/K vorhanden. Kostenuntergliederung (NT-Folge, Folgekosten Betrieb, Minderkosten) fehlt. | NEU (Schema-Erweiterung) |
| Gewaehrleistungsverlaengerung | Nicht im Schema. | NEU |

### 1.7 LV

| Feedback | Ist-Stand | Kategorie |
|----------|-----------|-----------|
| NTV-Positionen in anderer Farbe | LV-Positionen und NTV-Verknuepfung existieren. Frontend-Tab "LV" existiert (Tab 9). NTV-Markierung fehlt. | NEU (Frontend-Feature) |
| AFU/WMP-Verlinkung an LV-Positionen | Kein AFU/WMP-Modell im Schema. | NEU (spaeter, abhaengig von Dokumentenstruktur) |
| Spalte "Abrechnung" zur Kostenkontrolle | Nicht im Schema. Abrechnungsfelder (Aufmass, Rechnungsbetrag, Zahlungsstatus) fehlen. | NEU (Saeule 1 Erweiterung, Phase 3) |

### 1.8 Kontakte

| Feedback | Ist-Stand | Kategorie |
|----------|-----------|-----------|
| Gliederung nach Vertragsverhältnis (Ober-/Unterkategorien) | 9 Firmen mit Rolle (bauherr, generalplaner, generalunternehmer etc.). Personen an Firmen verknuepft. Hierarchische Darstellung (GP → Subs → Personen) fehlt im Frontend. | NEU (Frontend-Erweiterung) |

### 1.9 Dokumente

| Feedback | Ist-Stand | Kategorie |
|----------|-----------|-----------|
| Ordnerstruktur mit mehreren Ebenen (Bedarfsplanung, ES-Bau, EW-Bau, ...) | 643 Dokumente mit kategorie (Enum: allgemein, technisch, kaufmaennisch, etc.). Keine hierarchische Ordnerstruktur. | NEU (AD-KANDIDAT B-013) |

**Analyse:** Das Feedback schlaegt eine klassische Projektordnerstruktur vor, die sich an den Leistungsphasen und Projektphasen orientiert. Das ist fachlich absolut sinnvoll fuer die Orientierung. Allerdings widerspricht eine starre Ordnerstruktur dem Tag-basierten Ansatz (B-001). Hier braucht es einen AD-Prozess: Ordnerstruktur vs. virtueller Kategoriebaum vs. Tag-Hierarchie.

---

## 2. Umsetzungsplan

### 2.1 Sofort-Massnahmen (vor naechstem Nutzerkontakt)

Diese Punkte sind Quick Wins, die das Nutzererlebnis direkt verbessern.

**QW-01: Silent Token Refresh im Frontend**
- Problem: Session laeuft nach 15min ab, obwohl Refresh-Token 7 Tage gueltig ist
- Loesung: Interceptor in frontend/index.html — bei 401 automatisch /auth/refresh aufrufen, Token erneuern, Request wiederholen
- Aufwand: ~50 Zeilen JavaScript
- Prioritaet: KRITISCH (Nutzbarkeit)

**QW-02: Zeitauswirkung als "+X Tage" formatieren**
- Problem: zeitauswirkung_tage wird als nackte Zahl angezeigt
- Loesung: Frontend-Formatierung
- Aufwand: trivial

**QW-03: Aufgabenhistorie als Timeline darstellen**
- Problem: Kommentare werden als flache Liste angezeigt
- Loesung: aufgaben_kommentare chronologisch als vertikale Timeline mit Bearbeiter-Badge und Zeitstempel
- Aufwand: ~30 Zeilen JSX

### 2.2 AP 2.1 Nachtragsmanagement — Frontend-Komplettierung

Der Backend-Code fuer AP 2.1 ist deployed, aber das Frontend zeigt noch die Basisansicht. Das Feedback bestaetigt: Die Detailansicht mit Stepper, LV-Abgleich und Entscheidungsvorlage muss jetzt kommen.

**NT-F-01: Nachtrags-Detailansicht mit 7-Schritte-Stepper**
- Wie in AP 2.1 Spec v0.2 §6.1 spezifiziert
- Ergaenzung aus Feedback: Dokumenten-Links pro Schritt anzeigen

**NT-F-02: LV-Abgleich-Panel mit NTV-Spalte**
- Bestehende AP 2.1 Spec erweitern: Zusaetzliche Spalte "Bereits genehmigte NTs" an gleicher LV-Position
- Backend: Query ergaenzen — nachtragspruefung JOIN vorgaenge WHERE status='genehmigt' AND gleiche lv_position
- **Fachlich kritisch: Verhindert Doppelbeauftragung** (Kernforderung aus dem Feedback)

**NT-F-03: Kostenabgleich mit Aufschluesselung**
- Darstellung: LV-Originalpreis | NT-Forderung | Abweichung absolut | Abweichung prozentual
- Wie im Feedback gewuenscht: "50 TEUR → 70 TEUR (+40%)"

**NT-F-04: Entscheidung dem Grunde / der Hoehe nach**
- Schema-Erweiterung an nachtragspruefung: entscheidung_grund (BOOLEAN NULL), entscheidung_hoehe (BOOLEAN NULL), begruendung_grund (TEXT), begruendung_hoehe (TEXT)
- Frontend: Zwei getrennte Entscheidungsfelder mit Kommentarmoeglichkeit in Schritt 6
- Migration 008 noetig

**NT-F-05: NTV-Nummer am Abschluss-Schritt anzeigen**
- Auto-NTV-Anlage (Variante A) ist bereits in service.py implementiert
- Frontend: NTV-Nummer und Link zum NTV-Vorgang in Schritt 7 anzeigen

### 2.3 AP 2.2 Stoerungsmanagement (Behinderungen + Bedenken + Maengel)

Das Feedback macht deutlich: Die Anwender erwarten strukturierte Workflows fuer alle Vorgangtypen, nicht nur fuer Nachtraege. Das bestaetigt die Konzept-Saeule 2 (Stoerungsmanagement). Die bisherige Planung hatte AP 2.2 als "Behinderungs- und Bedenkenanzeigen" benannt, aber der Scope war nicht spezifiziert.

**Vorgeschlagener Scope AP 2.2:**

**2.2a Behinderungen — Workflow**
- 6 Pruefschritte: Erfassung → Pruefung → Anerkennung/Rueckweisung → Schriftverkehr → ggf. erneute Pruefung → Abmeldung GU
- Neue Tabelle: behinderungspruefung (analog zu nachtragspruefung)
- Zuordnung: Firma (verantwortlich), Gewerk (LV-Nummernkreis), Bauteil
- Dreiklang Q/Z/K als Pflichtfelder
- Aggregations-Dashboard: Behinderungen nach Grund, Verantwortlichem, Kostenauswirkung, Zeitverzug

**2.2b Bedenken — Workflow**
- Gleiche Pruefschritte wie Behinderungen (VOB/B §4 Abs. 3)
- Zusaetzlich: Zuordnung zu LV-Position (bestehendes Feld, muss im Frontend exponiert werden)
- Gewaehrleistungsfristen: Neues Feld gewaehrleistung_bis (DATE) an vorgaenge oder als separate Tabelle

**2.2c Maengel — Workflow**
- 5 Pruefschritte: Erfassung (mit Bildern/Dokumenten) → Mangelschreiben → Schriftverkehr → Abmeldung GU/GP → Bestaetigung Bauherr
- Neues Enum: mangelart (ausfuehrungsmangel, planungsmangel)
- Mangelzuordnung: Ausfuehrungsmangel → GU (ARGE/AGE), Planungsmangel → GP (BWP)
- Kostenuntergliederung: nachtragsfolge_eur, folgekosten_betrieb_eur, minderkosten_eur
- Gewaehrleistungsverlaengerung: verlaengerung_monate (INTEGER)

**Migration 008 (konsolidiert):**
- behinderungspruefung (Tenant-Tabelle)
- bedenkenpruefung (Tenant-Tabelle)
- mangelpruefung (Tenant-Tabelle)
- Erweiterung vorgaenge: mangelart (Enum), gewaehrleistung_bis (DATE), verlaengerung_monate (INTEGER)
- Erweiterung nachtragspruefung: entscheidung_grund, entscheidung_hoehe, begruendung_grund, begruendung_hoehe

### 2.4 Aufgaben-Erweiterungen

**AE-01: Kategorie-Hierarchie fuer Aufgaben**
- Bestehende tags-Tabelle um parent_id (self-referencing FK) erweitern
- Frontend: Kategorie-Picker mit zwei Ebenen
- Migration 008

**AE-02: Dateien an Aufgabe anfuegen (Frontend)**
- Backend existiert (vorgang_dokumente + Dokument-Upload)
- Frontend: Drag-and-Drop-Zone in Aufgabendetail, verlinkt auf bestehende Upload-API
- Alternativ: Link zu Dokumenten in Kommentaren (wie im Feedback vorgeschlagen)

**AE-03: Personenzuordnung via Dropdown**
- Backend existiert (zustaendig_benutzer_id)
- Frontend: Benutzer-Dropdown statt Freitexteingabe (API: GET /api/v1/auth/benutzer-liste noetig)

### 2.5 AD-Kandidaten aus dem Feedback

**B-012: Automatisierte Benachrichtigungen im Air-Gap**
- Feedback: Automatische E-Mails alle 2 Wochen bei Rueckweisung einer Behinderung
- Problem: Kein SMTP im Air-Gap (B-009). SMTP im kommerziellen Betrieb moeglich, im Landesnetz fraglich.
- AD-Frage: Internes Benachrichtigungssystem (In-App-Benachrichtigungen) vs. optionaler SMTP-Adapter vs. Export-Liste fuer manuellen Versand?
- Empfehlung: In-App-Benachrichtigungen als Push-Ersatz. SMTP als optionales Modul fuer kommerziellen Betrieb.

**B-013: Dokumentenstruktur — Ordner vs. Tags vs. Kategoriebaum**
- Feedback: Hierarchische Ordnerstruktur mit Leistungsphasen
- Bestehendes Konzept: Tag-System (B-001), flache Kategorie (Enum dokumentkategorie)
- AD-Frage: Virtuelle Ordnerstruktur (Kategoriebaum als Tabelle) vs. mehrdimensionale Tags vs. feste Ordnerhierarchie?
- Empfehlung: Virtueller Kategoriebaum, der die im Feedback vorgeschlagene Struktur als Default-Template abbildet, aber mandantenspezifisch anpassbar ist.

### 2.6 Spaetere Phasen (aus Feedback, kein sofortiger Handlungsbedarf)

| Punkt | Einordnung |
|-------|------------|
| AFU/WMP-Verlinkung an LV-Positionen | Phase 3 (abhaengig von Dokumentenstruktur) |
| Spalte "Abrechnung" im LV | Phase 3 (Saeule 1 Erweiterung: Kostenkontrolle / Aufmass) |
| Wartungsvertraege | Phase 4 (Betriebsphase, nicht Bauphase) |
| Planeintrag / Grundrissmarkierung bei Maengeln | Phase 3 (erfordert Plan-Viewer-Komponente, BIM-nahe Funktion) |

---

## 3. Priorisierte Reihenfolge

| Prio | Massnahme | Aufwand | Abhaengigkeit |
|------|-----------|---------|---------------|
| 1 | QW-01: Silent Token Refresh | 2h | keiner |
| 2 | QW-02 + QW-03: Zeitformat + Aufgaben-Timeline | 1h | keiner |
| 3 | NT-F-01 bis NT-F-05: Nachtrags-Frontend komplett | 2-3 Tage | AP 2.1 Backend steht |
| 4 | NT-F-02: NTV-Doppelbeauftragungspruefung | 0,5 Tage | in NT-F-01 integriert |
| 5 | AE-02 + AE-03: Aufgaben-Dateien + Dropdown | 1 Tag | keiner |
| 6 | AD B-012 + B-013 durchfuehren | 1 Sitzung | keiner |
| 7 | Migration 008 vorbereiten | 1 Tag | AD-Ergebnisse B-012, B-013 |
| 8 | AP 2.2a Behinderungen Workflow | 2-3 Tage | Migration 008 |
| 9 | AP 2.2b Bedenken Workflow | 1-2 Tage | AP 2.2a (gleiches Muster) |
| 10 | AP 2.2c Maengel Workflow | 2-3 Tage | AP 2.2a |
| 11 | AE-01: Kategorie-Hierarchie | 1 Tag | Migration 008 |
| 12 | Kontakte: Hierarchische Darstellung | 0,5 Tage | keiner |

**Geschaetzter Gesamtaufwand:** 2-3 Wochen (bei voller Konzentration auf BauPilot)

---

## 4. Feedback-Rueckmeldung an Maximilian

Empfohlene Rueckmeldung (sachlich, G1-konform):

> Vielen Dank fuer das ausfuehrliche Feedback. Wir haben jeden Punkt gegen den aktuellen Entwicklungsstand abgeglichen. Viele der gewuenschten Funktionen sind bereits im Backend vorbereitet (Dokumentenverknuepfung, Dreiklang, LV-Abgleich) und werden in den naechsten Wochen im Frontend sichtbar. Das Session-Timeout-Problem wird sofort behoben — die Session bleibt kuenftig 7 Tage aktiv. Die strukturierten Workflows fuer Behinderungen, Bedenken und Maengel sind als naechstes Arbeitspaket eingeplant.

---

## 5. Offene Entscheidungen (aktualisiert)

| ID | Titel | Status |
|----|-------|--------|
| B-006 | VS-NfD-Behandlung: LLM-Verarbeitung zulaessig? | offen |
| B-011 | Digitale Signatur FES | bei Rechtsabteilung |
| B-012 | Benachrichtigungssystem: In-App vs. SMTP vs. Export | NEU — AD noetig |
| B-013 | Dokumentenstruktur: Ordner vs. Tags vs. Kategoriebaum | NEU — AD noetig |

---

## 6. Naechste Schritte

1. Quick Wins QW-01 bis QW-03 umsetzen (sofort, 3h)
2. Nachtrags-Frontend komplett ausbauen (NT-F-01 bis NT-F-05)
3. AD-Sitzung fuer B-012 und B-013 ansetzen
4. Migration 008 spezifizieren und vorbereiten
5. AP 2.2 Stoerungsmanagement starten
6. Feedback-Rueckmeldung an Maximilian senden
7. Projektanweisung v0.5 und Konzeptpapier v0.5 aktualisieren

---

**Status:** Feedback analysiert, Umsetzungsplan erstellt. Naechste Aktion: QW-01 (Silent Token Refresh).
