# BauPilot — Konzept-Delta v0.4 → v0.5 (FINAL)

**Zweck:** Anweisungen zum Überführen des kanonischen Konzeptpapiers von v0.4 auf v0.5.
**Datum:** 05.06.2026
**Status:** Final. **Löst den Entwurf `BauPilot-Konzept-v0_5-Delta.md` ab** (der war unfertig: offener Platzhalter, vor AP-2.1-Deployment, geschätzte BKI-Zahl). Dieses Delta ist die maßgebliche v0.5-Quelle.

> Anwendung: gegen die vollständige v0.4-Datei auf `C:\Tools\baupilot.work\konzept\` in einem Durchgang anwenden. Alte Versionen ins Archiv. v0.5 = Re-Baseline auf den Realstand (Phase 2, AP 2.1 deployed, E-Serie in AP-Nummerierung).

---

## 0. Platzhalter auflösen

Globale Suche nach `[LV_POSITIONEN_GESAMT]` (kam im v0.5-Entwurf 4× vor) → ersetzen durch **13.155**.

---

## 1. Changelog-Block ergänzen

Neue Zeile am Ende der Changelog-Tabelle:

```
| 0.5 | 05.06.2026 | Re-Baseline auf Realstand. AP 1.2 LV-Extraktion abgeschlossen → Phase 1 komplett (7/7, 60 LVs → 13.155 Positionen). AP 2.1 Nachtragsmanagement deployed + live (7-Schritte, BKI-Kostenabgleich, lokale Entscheidungsvorlage). AP 2.3 und 2.4 in 2.1 aufgegangen. AP 2.6 als E12 Verknüpfungsanalyse deployed (Feinschliff offen). E-Serie in AP-Nummerierung zurückgeführt (§9). B-012 (spark-docling geteilt) und B-013 (Netzplan = Vite + React Flow) entschieden; B-014/B-015 als Phase-3-Vorentscheidungen vermerkt. Schema Alembic 007 (nachtragspruefung + BKI-Tabellen; Konsolidierung der LV-Hotfixes ausstehend). Datenstand aktualisiert. Glossar: BKI ergänzt, ITWO als ersetzt markiert. |
```

---

## 2. §9 Phasen-Status — Phase 1 abschließen

Phase-1-Tabelle, letzte Zeile:

ALT:
```
| BP-AP 1.2 | LV-Textextraktion (61 PDFs → strukturierte Positionen) | offen, B-005 entschieden |
```
NEU:
```
| BP-AP 1.2 | LV-Textextraktion (60 LVs → 13.155 Positionen) | ✅ 08.05.2026 |
```

Reihenfolge-Zeile:

ALT: `**Reihenfolge (R-001):** 1.1 ✅ → 1.7 ✅ → 1.3 ✅ → 1.4 ✅ → 1.5 ✅ → 1.6 ✅ → 1.2 LV-Extraktion.`
NEU: `**Reihenfolge (R-001):** 1.1 ✅ → 1.7 ✅ → 1.3 ✅ → 1.4 ✅ → 1.5 ✅ → 1.6 ✅ → 1.2 ✅. **Phase 1 abgeschlossen.**`

---

## 3. §9 Phasen-Status — Phase 2 mit Realstand

Die Phase-2-Tabelle um eine Status-Spalte ergänzen und so füllen:

```
| AP | Titel | Status |
|----|-------|--------|
| BP-AP 2.1 | Nachtragsmanagement mit 7-Schritte-Prozess | ✅ deployed + live getestet (09.05.2026) |
| BP-AP 2.3 | LV-Matching und Regionalpreisvergleich | ✅ in AP 2.1 aufgegangen (BKI, Regionalfaktor Jena 1,088) |
| BP-AP 2.4 | Entscheidungsvorlagen-Generator | ✅ in AP 2.1 aufgegangen (Qwen 2.5 32B, lokal) |
| BP-AP 2.6 | Verknüpfungsanalyse (BED → BehA → NT → Termin) | ✅ als „E12" deployed; Feinschliff offen |
| BP-AP 2.2 | Behinderungs- und Bedenkenanzeigen (VOB-Textbausteine) | ⬜ offen — noch nicht begonnen |
| BP-AP 2.5 | Protokollgenerierung Word/PDF | ⬜ in Vorbereitung (F-201–F-205 offen) |
```

Direkt darunter neuer Absatz:

```
**E12-Feinschliff (für Nachtragsverhandlung und Rechnungshof-Dokumentation erforderlich, sonst nicht hinreichend):** (1) Anzeige des `gruende`-Feldes, (2) Q/Z/K-Werte am verknüpften Vorgang, (3) durchgehende Kettenansicht (BED → BehA → NT mit kumulierter Auswirkung), (4) Σ-Zeile mit Σ Kosten und Σ Verzugstage. Verschoben in den E12-Feinschliff bzw. Phase 3.

**E-Serie → AP-Zuordnung:** E12 = AP 2.6 (deployed, Feinschliff offen). E13 = AP 3.1 Asta-Import (Vorarbeit, wartet auf X83-Datei). E14 = offener Auth/TOTP-Faden. Künftig wird ausschließlich die AP-Nummerierung geführt.
```

---

## 4. §9 Datenstand aktualisieren

NEU:
```
**Datenstand:** 615 Vorgänge (322 NT, 140 BehA, 124 BED, 27 MA, 2 AF), 322 Prüfschritte (Schritt 1 geseeded), 9 Firmen, 643 Dokumente (2 GB), 13.155 LV-Positionen (60 LVs), 4.779 BKI-Baupreise (2.334 aus 2025 + 2.445 aus 2026), 7 BKI-Regionalfaktoren, 2 Benutzer, Alembic 007.
```

---

## 5. §4.x Kostenabgleich — Preisreferenz präzisieren

Im Nachtrags-/Kostenabgleich-Abschnitt sicherstellen, dass folgende Aussage steht (statt der ITWO-Formulierung und statt der Schätzung „5.235"):

```
Kostenabgleich gegen (a) eigene LV-Einheitspreise und (b) regionalisierte BKI-Baupreise (Neubau 2025/2026, Regionalfaktor Jena 1,088, Kostenstand Q3 2025). 4.779 BKI-Positionen in shared.bki_baupreise, Stichprobe gegen PDF validiert. Endpunkt POST /api/v1/nachtraege/{id}/kostenabgleich weist die prozentuale Abweichung aus; innerhalb der BKI-Bandbreite (von–bis) gilt der geforderte Preis als angemessen.
```

---

## 6. §12 Entscheidungen aktualisieren

In der „Entschieden"-Tabelle ergänzen (falls noch nicht vorhanden):

```
| B-005 | LV-Extraktion | Docling primär (spark-docling, Port 8070, CPU-Mode), pdfplumber Fallback, einheitliche LVExtractor-Schnittstelle | 08.05.2026 |
| B-012 | spark-docling geteilter Service | Eigener Container im spark-network, von BauPilot und SPARK-BNB genutzt; CPU-Mode gmktec, GPU-Mode TLBV | 08.05.2026 |
| B-013 | Netzplan-Technologie / Frontend-Build | Option C: Vite + React Flow + dagre/elkjs; Vite-Migration beim Übergang Phase 1→2, Netzplan-Umsetzung Phase 3 | 22.05.2026 |
```

In der „Offen"-Tabelle ergänzen:

```
| B-011 | Digitale Signatur FES (eIDAS Art. 26) | Rechtsvorlage eingereicht, bei Rechtsabteilung |
| B-014 | Gantt-Library (SVAR React Gantt vs. DHTMLX) | offen, vor Phase 3 — SVAR (MIT) präferiert, DHTMLX nur bei klarer Feature-Überlegenheit, dann kommerziell statt GPLv2 |
| B-015 | Asta-Import-Strategie (MPXJ vs. CSV-Export) | offen, vor Phase 3 |
```

---

## 7. §15 Glossar — BKI ergänzen, ITWO ändern

Einfügen (alphabetisch):
```
**BKI** Baukosteninformationszentrum Deutscher Architektenkammern; Quelle für statistische Baupreise (Neubau) nach Leistungsbereichen. Regionalisierung über BKI-Regionalfaktoren (Jena 1,088).
```

ITWO-Eintrag ändern:

ALT: `**ITWO** Regionalpreisliste; jährliche Datenbasis für den Kostenabgleich bei Nachträgen`
NEU: `**ITWO** Regionalpreisliste (ehemals vorgesehen für den Kostenabgleich, ab v0.5 durch BKI-Baupreise ersetzt)`

---

## 8. Dokumentstatus am Ende ersetzen

NEU:
```
**Dokumentstatus:** v0.5 — Re-Baseline auf Realstand. Phase 1 abgeschlossen (7/7 APs deployed). AP 2.1 Nachtragsmanagement deployed und live getestet; AP 2.3/2.4 in 2.1 aufgegangen; AP 2.6 als E12 deployed (Feinschliff offen). E-Serie in AP-Nummerierung zurückgeführt. B-013 (Netzplan) entschieden, B-014/B-015 als Phase-3-Vorentscheidungen vermerkt. Schema Alembic 007 (Konsolidierung der LV-Hotfixes ausstehend). Datenstand: 615 Vorgänge, 322 Prüfschritte, 9 Firmen, 643 Dokumente (2 GB), 13.155 LV-Positionen, 4.779 BKI-Baupreise.
```

---

## Prüf-Checkliste nach Anwendung

- `[LV_POSITIONEN_GESAMT]` kommt 0× vor.
- ITWO erscheint nur noch im Glossar als „ersetzt".
- BKI-Zahl ist überall 4.779 (nicht 5.235).
- Phase-2-Tabelle hat Status-Spalte mit AP 2.1 = deployed, AP 2.2 = offen.
- B-013 steht in „Entschieden", B-014/B-015 in „Offen".
- Dokumentstatus endet auf v0.5.
