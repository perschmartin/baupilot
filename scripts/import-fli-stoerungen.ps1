# ============================================================
# BauPilot — Stoerungs-Dokumente importieren (E13a)
# Laedt PDFs aus 06_BED, 07_BehA, 08_Planungsmangel, 09_Ausfuehrungsmangel
# hoch und verknuepft sie mit den bestehenden Vorgaengen.
#
# Voraussetzung: Vorgaenge sind bereits in der DB (vom Initial-Import).
# Nur die PDFs (Inhalt) werden nachgereicht. LLM-Extraktion folgt in E13b.
#
# Lauf:
#   .\import-fli-stoerungen.ps1 -DryRun         # zeigt was passieren wuerde
#   .\import-fli-stoerungen.ps1                 # echter Lauf
#   .\import-fli-stoerungen.ps1 -OnlyTyp BED    # nur Bedenken
# ============================================================

param(
    [string]$BasePfad = "P:\Datenübergabe FLI",
    [string]$ApiUrl = "http://localhost:8110/api/v1",
    [string]$Email = "admin@baupilot.de",
    [string]$Passwort = "BauPilot-Erststart-2026!",
    [string]$Projekt = "FLI",
    [string]$OnlyTyp = "",   # BED | BehA | MA-P | MA-A — leer = alle
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

Write-Host "=== BauPilot Stoerungs-PDF-Import (E13a) ===" -ForegroundColor Cyan
if ($DryRun) { Write-Host "DRY RUN — keine Aenderungen" -ForegroundColor Yellow }
if ($OnlyTyp) { Write-Host "Nur Typ: $OnlyTyp" -ForegroundColor Yellow }

# --- Login ---
Write-Host "`nLogin..." -ForegroundColor Yellow
try {
    $loginBody = @{ email = $Email; passwort = $Passwort } | ConvertTo-Json
    $r = Invoke-RestMethod -Uri "$ApiUrl/auth/login" -Method Post -ContentType "application/json" -Body $loginBody
    $token = $r.access_token
    if (-not $token) { throw "Kein access_token in Login-Response" }
    Write-Host "Login OK." -ForegroundColor Green
} catch {
    Write-Host "Login fehlgeschlagen: $_" -ForegroundColor Red
    exit 1
}
$headers = @{ Authorization = "Bearer $token" }

# --- Vorgaenge laden (3 Typen) ---
function Get-Vorgaenge($typ) {
    $r = Invoke-RestMethod -Uri "$ApiUrl/vorgaenge/?projekt=$Projekt&typ=$typ&limit=500" -Headers $headers
    return $r.vorgaenge
}

Write-Host "Lade Vorgaenge..." -ForegroundColor Yellow
$bedVorgaenge = Get-Vorgaenge 'bedenkenanzeige'
$behaVorgaenge = Get-Vorgaenge 'behinderungsanzeige'
$maVorgaenge = Get-Vorgaenge 'mangelanzeige'
Write-Host ("  BED:  {0}  |  BehA: {1}  |  MA: {2}" -f $bedVorgaenge.Count, $behaVorgaenge.Count, $maVorgaenge.Count) -ForegroundColor Green

# --- Lookup-Tabellen bauen ---
# BED: BED-003 -> UUID
$bedLookup = @{}
foreach ($v in $bedVorgaenge) {
    if ($v.nummer -match '^BED-(\d+)$') {
        $bedLookup[[int]$Matches[1]] = $v.id
    }
}
# BehA: BehA-001 -> UUID
$behaLookup = @{}
foreach ($v in $behaVorgaenge) {
    if ($v.nummer -match '^BehA-(\d+)$') {
        $behaLookup[[int]$Matches[1]] = $v.id
    }
}
# MA-P / MA-A: getrennte Lookups, Reihenfolge per Nummer-Suffix
$maPLookup = @{}
$maALookup = @{}
foreach ($v in $maVorgaenge) {
    if ($v.nummer -match '^MA-P-(\d+)$') { $maPLookup[[int]$Matches[1]] = $v.id }
    elseif ($v.nummer -match '^MA-A-(\d+)$') { $maALookup[[int]$Matches[1]] = $v.id }
}

Write-Host ("Lookup: BED={0}, BehA={1}, MA-P={2}, MA-A={3}" -f $bedLookup.Count, $behaLookup.Count, $maPLookup.Count, $maALookup.Count) -ForegroundColor Gray

# --- Upload-Funktion ---
function Upload-Pdf {
    param(
        [string]$Pfad,
        [string]$Kategorie,
        [string]$VorgangId,
        [string]$Beschreibung
    )
    $dateiname = Split-Path $Pfad -Leaf
    if ($DryRun) {
        Write-Host ("  [DRY] {0} -> Vorgang {1}" -f $dateiname, $VorgangId.Substring(0, 8)) -ForegroundColor DarkGray
        return $true
    }
    try {
        $form = @{
            datei = Get-Item $Pfad
            projekt = $Projekt
            kategorie = $Kategorie
            vorgang_id = $VorgangId
        }
        if ($Beschreibung) { $form["beschreibung"] = $Beschreibung }
        $res = Invoke-RestMethod -Uri "$ApiUrl/dokumente/upload" -Method Post -Headers $headers -Form $form
        Write-Host ("  ✓ {0}" -f $dateiname) -ForegroundColor Green
        return $true
    } catch {
        Write-Host ("  ✗ {0}: {1}" -f $dateiname, $_.Exception.Message) -ForegroundColor Red
        return $false
    }
}

# --- Generische Import-Funktion fuer eine Ordner-Konfiguration ---
function Import-Ordner {
    param(
        [string]$OrdnerName,
        [string]$Kategorie,    # dokumentkategorie-Enum
        [hashtable]$Lookup,
        [string]$NummerRegex,  # Regex mit (\d+) — Position der Nummer im Dateinamen
        [string]$KurzName      # fuer Anzeige
    )
    $pfad = Join-Path $BasePfad $OrdnerName
    if (-not (Test-Path $pfad)) {
        Write-Host "Ordner fehlt: $pfad" -ForegroundColor Yellow
        return @{ ok = 0; skip = 0; fail = 0 }
    }
    Write-Host "`n=== $KurzName aus $OrdnerName ===" -ForegroundColor Cyan

    $ok = 0; $skip = 0; $fail = 0
    Get-ChildItem -Path $pfad -Filter *.pdf | Sort-Object Name | ForEach-Object {
        $datei = $_.Name
        if ($datei -match $NummerRegex) {
            $nr = [int]$Matches[1]
            if ($Lookup.ContainsKey($nr)) {
                $vid = $Lookup[$nr]
                if (Upload-Pdf -Pfad $_.FullName -Kategorie $Kategorie -VorgangId $vid -Beschreibung "") {
                    $ok++
                } else {
                    $fail++
                }
            } else {
                Write-Host ("  skip: $datei (Nr $nr nicht in DB)") -ForegroundColor Yellow
                $skip++
            }
        } else {
            Write-Host ("  skip: $datei (Nummer nicht extrahierbar)") -ForegroundColor Yellow
            $skip++
        }
    }
    Write-Host ("${KurzName}: $ok OK, $skip skip, $fail fail") -ForegroundColor Gray
    return @{ ok = $ok; skip = $skip; fail = $fail }
}

# --- Sonderfall Ausfuehrungsmangel: kein Nummer-Praefix im Dateinamen, ---
# --- Mapping per sortierter Reihenfolge (alphabetisch nach Dateiname = ---
# --- DB-Reihenfolge nach LV-Nummer) ---
function Import-Ausfuehrungsmangel {
    $pfad = Join-Path $BasePfad "09_Ausführungsmangel"
    Write-Host "`n=== MA-A aus 09_Ausfuehrungsmangel ===" -ForegroundColor Cyan
    $ok = 0; $skip = 0; $fail = 0
    $idx = 1
    Get-ChildItem -Path $pfad -Filter *.pdf | Sort-Object Name | ForEach-Object {
        if ($maALookup.ContainsKey($idx)) {
            $vid = $maALookup[$idx]
            if (Upload-Pdf -Pfad $_.FullName -Kategorie 'mangelanzeige' -VorgangId $vid -Beschreibung "") {
                $ok++
            } else {
                $fail++
            }
        } else {
            Write-Host ("  skip: $($_.Name) (MA-A-$idx nicht in DB)") -ForegroundColor Yellow
            $skip++
        }
        $idx++
    }
    Write-Host ("MA-A: $ok OK, $skip skip, $fail fail") -ForegroundColor Gray
    return @{ ok = $ok; skip = $skip; fail = $fail }
}

# --- Hauptlauf ---
$stats = @{}

if (-not $OnlyTyp -or $OnlyTyp -eq 'BED') {
    $stats['BED'] = Import-Ordner -OrdnerName "06_BED" -Kategorie 'bedenkenanzeige' `
        -Lookup $bedLookup -NummerRegex '^BedA\s+(\d+)' -KurzName "BED"
}
if (-not $OnlyTyp -or $OnlyTyp -eq 'BehA') {
    $stats['BehA'] = Import-Ordner -OrdnerName "07_BehA" -Kategorie 'behinderungsanzeige' `
        -Lookup $behaLookup -NummerRegex '^(\d+)' -KurzName "BehA"
}
if (-not $OnlyTyp -or $OnlyTyp -eq 'MA-P') {
    $stats['MA-P'] = Import-Ordner -OrdnerName "08_Planungsmangel" -Kategorie 'mangelanzeige' `
        -Lookup $maPLookup -NummerRegex '^(\d+)' -KurzName "MA-P"
}
if (-not $OnlyTyp -or $OnlyTyp -eq 'MA-A') {
    $stats['MA-A'] = Import-Ausfuehrungsmangel
}

# --- Zusammenfassung ---
Write-Host "`n=== Zusammenfassung ===" -ForegroundColor Cyan
foreach ($k in $stats.Keys) {
    $s = $stats[$k]
    Write-Host ("  {0,-6} OK={1,3}  skip={2,3}  fail={3,3}" -f $k, $s.ok, $s.skip, $s.fail)
}
Write-Host "`nFertig." -ForegroundColor Green
