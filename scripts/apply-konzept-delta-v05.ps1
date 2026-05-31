# BauPilot — Konzeptpapier v0.4 → v0.5 Delta anwenden
# Vorbereitet: 31.05.2026
# Liest v0.4, wendet 9 Aenderungen an, schreibt v0.5
# Platzhalter [LV_POSITIONEN_GESAMT] wird durch 13.155 ersetzt.

$ErrorActionPreference = "Stop"

$quellPfad = "C:\Tools\baupilot.work\konzept\intern\BauPilot-Konzept-v0_4.md"
$zielPfad = "C:\Tools\baupilot.work\konzept\intern\BauPilot-Konzept-v0_5.md"

if (Test-Path $zielPfad) {
    Write-Host "WARNUNG: $zielPfad existiert bereits. Wird ueberschrieben." -ForegroundColor Yellow
}

Write-Host "1. Lese v0.4..." -ForegroundColor Cyan
$text = [System.IO.File]::ReadAllText($quellPfad, [System.Text.UTF8Encoding]::new($false))

# --- Delta 1: Version ---
Write-Host "2. Version 0.4 -> 0.5..." -ForegroundColor Cyan
$text = $text.Replace("**Version:** 0.4", "**Version:** 0.5")
$text = $text.Replace("**Stand:** 08. Mai 2026", "**Stand:** 30. Mai 2026")

# --- Delta 2: Changelog ---
Write-Host "3. Changelog-Zeile v0.5 ergaenzen..." -ForegroundColor Cyan
$changelogAlt = "| 0.4     | 08.05.2026  | Phase 1 nahezu abgeschlossen"
$changelogNeu = @"
| 0.4     | 08.05.2026  | Phase 1 nahezu abgeschlossen
"@
# Fuege neue Zeile nach dem v0.4-Eintrag ein (nach der letzten | der Zeile)
$v05Zeile = "| 0.5     | 30.05.2026  | Phase 1 abgeschlossen: AP 1.2 LV-Extraktion deployed. spark-docling als geteilter Extraction-Service (B-012). Schema auf Alembic 008. 13.155 LV-Positionen aus 60 LVs. BKI Baupreise als Preisreferenz (4.779 Positionen). Phase 2 weitgehend abgeschlossen: AP 2.1 Nachtragsmanagement (7-Schritte), AP 2.2 Stoerungsmanagement (Behinderungen/Bedenken/Maengel), In-App-Benachrichtigungen, Protokollgenerierung, Dokumentenstruktur. Ergebnis-Visualisierung vorgezogen (Plotly). 15 Backend-Module, 11+ Frontend-Tabs. |"
# Finde das Ende des v0.4-Changelog-Eintrags und fuege v0.5 davor ein
$idx = $text.IndexOf("| 0.4     | 08.05.2026  |")
if ($idx -ge 0) {
    # Finde das Ende dieser Zeile
    $lineEnd = $text.IndexOf("`n", $idx)
    if ($lineEnd -ge 0) {
        $text = $text.Insert($lineEnd + 1, "$v05Zeile`n")
        Write-Host "   Changelog-Zeile eingefuegt." -ForegroundColor Green
    }
}

# --- Delta 3: §4.2 Alembic-Version ---
Write-Host "4. Alembic 005 -> 008..." -ForegroundColor Cyan
$text = $text.Replace("### 4.2 Datenmodell (Alembic 005, Stand 08.05.2026)", "### 4.2 Datenmodell (Alembic 008, Stand 30.05.2026)")

# --- Delta 4: Migrationshistorie ---
Write-Host "5. Migrationen 006-008 ergaenzen..." -ForegroundColor Cyan
$migAlt = "| 005 | 005 | Dokumentenverwaltung: dokumentkategorie + signaturstatus Enums, 14 Spalten an dokumente, vorgang_dokumente, 6 Indizes |"
$migNeu = @"
| 005 | 005 | Dokumentenverwaltung: dokumentkategorie + signaturstatus Enums, 14 Spalten an dokumente, vorgang_dokumente, 6 Indizes |
| 006 | 006 | LV-Extraktion: nummernkreis (smallint) + menge + einheit + langtext an lv_positionen, Indizes |
| 007 | 007 | Nachtragsmanagement: nachtragspruefung, bki_baupreise, bki_regionalfaktoren, entscheidungsvorlagen |
| 008 | 008 | Stoerungsmanagement: behinderungspruefung, bedenkenpruefung, mangelpruefung, benachrichtigungen, benachrichtigungs_regeln, dokument_tags. Erweiterungen an vorgaenge und nachtragspruefung. tags.parent_id. 3 neue Enums (mangelart, benachrichtigungstyp, benachrichtigungs_prioritaet). |
"@
$text = $text.Replace($migAlt, $migNeu)

# --- Delta 6: Phase 1 AP 1.2 ---
Write-Host "6. AP 1.2 als abgeschlossen markieren..." -ForegroundColor Cyan
$text = $text.Replace(
    "| BP-AP 1.2 | LV-Textextraktion (61 PDFs $([char]0x2192) strukturierte Positionen) | offen, B-005 entschieden |",
    "| BP-AP 1.2 | LV-Textextraktion (60 LVs $([char]0x2192) 13.155 Positionen) | $([char]0x2705) 08.05.2026 |"
)

# --- Delta 7: Reihenfolge ---
Write-Host "7. Reihenfolge aktualisieren..." -ForegroundColor Cyan
$text = $text.Replace(
    "1.6 $([char]0x2705) $([char]0x2192) 1.2 LV-Extraktion.",
    "1.6 $([char]0x2705) $([char]0x2192) 1.2 $([char]0x2705). **Phase 1 abgeschlossen.**"
)

# --- Delta 8: Dokumentstatus ---
Write-Host "8. Dokumentstatus aktualisieren..." -ForegroundColor Cyan
$text = $text.Replace(
    "**Dokumentstatus:** v0.4 — Phase 1 nahezu abgeschlossen (6 von 7 APs deployed). Auth-Architektur, Frontend, Dokumentenverwaltung, Aufgabenmanagement, Kontakte und FLI-Datenimport dokumentiert. Schema auf Alembic 005 (7 shared-Tabellen, 12 Tenant-Tabellen, 10 Enums). Datenstand: 615 Vorgänge, 9 Firmen, 643 Dokumente (2 GB). Letztes offenes Phase-1-AP: LV-Extraktion (AP 1.2).",
    "**Dokumentstatus:** v0.5 — Phase 1 abgeschlossen (7/7 APs), Phase 2 weitgehend abgeschlossen. 15 Backend-Module, 11+ Frontend-Tabs. Schema auf Alembic 008 (7 shared-Tabellen, 18+ Tenant-Tabellen, 13 Enums). Datenstand: 615 Vorgaenge, 13.155 LV-Positionen (60 LVs), 4.779 BKI-Preise, 643 Dokumente (2 GB), 9 Firmen, 6 Bauteile. Naechste Schwerpunkte: E12 Verknuepfungsanalyse, E13 Asta-X83, E14 Sicherheitshaertung."
)

# --- Delta 9: Platzhalter ersetzen ---
Write-Host "9. Platzhalter ersetzen..." -ForegroundColor Cyan
$text = $text.Replace("[LV_POSITIONEN_GESAMT]", "13.155")

# --- Delta 10: ITWO → BKI im Glossar ---
Write-Host "10. Glossar: ITWO-Eintrag aktualisieren, BKI ergaenzen..." -ForegroundColor Cyan
$text = $text.Replace(
    "**ITWO** Regionalpreisliste; jährliche Datenbasis für den Kostenabgleich bei Nachträgen (Nachfolge der früheren CD-basierten Listen)",
    "**BKI** Baukosteninformationszentrum Deutscher Architektenkammern; Quelle fuer statistische Baupreise (Neubau) nach Leistungsbereichen`n**ITWO** Regionalpreisliste (ehemals vorgesehen fuer den Kostenabgleich, ersetzt durch BKI Baupreise ab v0.5)"
)

# --- Schreiben ---
Write-Host "`n11. Schreibe v0.5..." -ForegroundColor Cyan
[System.IO.File]::WriteAllText($zielPfad, $text, [System.Text.UTF8Encoding]::new($false))

# --- Validierung ---
Write-Host "`nValidierung:" -ForegroundColor Cyan
$check = [System.IO.File]::ReadAllText($zielPfad, [System.Text.UTF8Encoding]::new($false))

$tests = @(
    @{Name="Version 0.5"; Pattern="**Version:** 0.5"; Expected=$true},
    @{Name="Alembic 008"; Pattern="Alembic 008"; Expected=$true},
    @{Name="13.155"; Pattern="13.155"; Expected=$true},
    @{Name="Migration 008"; Pattern="| 008 | 008 |"; Expected=$true},
    @{Name="Kein Platzhalter"; Pattern="[LV_POSITIONEN_GESAMT]"; Expected=$false},
    @{Name="Phase 1 abgeschlossen"; Pattern="Phase 1 abgeschlossen"; Expected=$true},
    @{Name="BKI im Glossar"; Pattern="**BKI**"; Expected=$true}
)

$passed = 0
foreach ($t in $tests) {
    $found = $check.Contains($t.Pattern)
    $ok = $found -eq $t.Expected
    if ($ok) {
        Write-Host "   PASS: $($t.Name)" -ForegroundColor Green
        $passed++
    } else {
        Write-Host "   FAIL: $($t.Name) (erwartet: $($t.Expected), gefunden: $found)" -ForegroundColor Red
    }
}

Write-Host "`nErgebnis: $passed / $($tests.Count) Tests bestanden." -ForegroundColor $(if ($passed -eq $tests.Count) {"Green"} else {"Yellow"})
Write-Host "Datei: $zielPfad"
Write-Host "`nHINWEIS: Bitte manuell pruefen, ob die neuen Abschnitte (§4.11 LV-Extraktion, §4.12 BKI-Preisreferenz)" -ForegroundColor Yellow
Write-Host "noch eingefuegt werden muessen — das Skript fuegt die Hauptdeltas automatisch ein," -ForegroundColor Yellow
Write-Host "aber die neuen Abschnitte muessen ggf. per Hand nach §4.10 eingefuegt werden." -ForegroundColor Yellow
