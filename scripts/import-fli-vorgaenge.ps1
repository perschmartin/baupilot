# BauPilot - FLI Vorgaenge importieren (v2)
# Liest Dateinamen aus P:\Datenubergabe FLI und legt Vorgaenge an.
# Idempotent: Vorhandene Eintraege werden uebersprungen (WHERE NOT EXISTS).
#
# Verwendung: .\scripts\import-fli-vorgaenge.ps1
# Voraussetzung: baupilot-postgres laeuft, Migration 004 ausgefuehrt, FLI-Projekt existiert

$ErrorActionPreference = "Stop"

$Container = "baupilot-postgres"
$DB        = "baupilot"
$User      = "baupilot"
$BasePath  = "P:\Datenübergabe FLI"
$TempSQL   = Join-Path $env:TEMP "baupilot-fli-import.sql"

function SqlEsc([string]$s) {
    return $s.Replace("'", "''")
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " BauPilot - FLI Vorgaenge Import v2" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Quelle: $BasePath"
Write-Host ""

$sql = [System.Collections.Generic.List[string]]::new()
$sql.Add("-- BauPilot FLI-Vorgaenge-Import v2 (generiert $(Get-Date -Format 'yyyy-MM-dd HH:mm'))")
$sql.Add("SET search_path TO tenant_tlbv, shared, public;")
$sql.Add("BEGIN;")
$sql.Add("")

# --- Hilfsfunktion: Vorgang-INSERT ---
function Add-Vorgang([string]$typ, [string]$nummer, [string]$gegenstand) {
    $nEsc = SqlEsc $nummer
    $gEsc = SqlEsc $gegenstand
    $sql.Add(@"
INSERT INTO vorgaenge (typ, nummer, gegenstand, projekt_id, erstellt_von, geaendert_von, geaendert_am)
SELECT '${typ}'::vorgangtyp, '$nEsc', '$gEsc', p.id, 'import', 'import', NOW()
FROM projekte p WHERE p.kurz = 'FLI'
AND NOT EXISTS (SELECT 1 FROM vorgaenge v WHERE v.nummer = '$nEsc' AND v.typ = '${typ}'::vorgangtyp AND v.projekt_id = p.id);
"@)
}

$summary = [ordered]@{}

# ================================================================
# 1. Nachtraege (03_NT)
# ================================================================
$dir = Join-Path $BasePath "03_NT"
if (Test-Path $dir) {
    $count = 0
    $sql.Add("-- === Nachtraege ===")
    Get-ChildItem $dir -Filter "*.pdf" -Name | ForEach-Object {
        $name = $_ -replace '\.pdf$', ''
        if ($name -match '^\d{6}') { return }
        if ($name -match '^(\d{3}[a-zA-Z]?(?:Ü\d+)?)\s+(.+)$') {
            Add-Vorgang 'nachtrag' "NT-$($Matches[1])" $Matches[2].Trim()
            $count++
        }
    }
    $summary['Nachtraege (NT)'] = $count
    Write-Host "  Nachtraege:            $count" -ForegroundColor Green
}

# ================================================================
# 2. Behinderungsanzeigen (07_BehA)
# ================================================================
$dir = Join-Path $BasePath "07_BehA"
if (Test-Path $dir) {
    $count = 0
    $sql.Add("")
    $sql.Add("-- === Behinderungsanzeigen ===")
    Get-ChildItem $dir -Filter "*.pdf" -Name | ForEach-Object {
        $name = $_ -replace '\.pdf$', ''
        if ($name -match '^(\d{3})\s+(.+)$') {
            Add-Vorgang 'behinderungsanzeige' "BehA-$($Matches[1])" $Matches[2].Trim()
            $count++
        }
    }
    $summary['Behinderungsanzeigen (BehA)'] = $count
    Write-Host "  Behinderungsanzeigen:  $count" -ForegroundColor Green
}

# ================================================================
# 3. Bedenkenanzeigen (06_BED)
# ================================================================
$dir = Join-Path $BasePath "06_BED"
if (Test-Path $dir) {
    $count = 0
    $sql.Add("")
    $sql.Add("-- === Bedenkenanzeigen ===")
    Get-ChildItem $dir -Filter "*.pdf" -Name | ForEach-Object {
        $name = $_ -replace '\.pdf$', ''
        if ($name -match '^BedA\s+(\d{3})\s+(.+)$') {
            Add-Vorgang 'bedenkenanzeige' "BED-$($Matches[1])" $Matches[2].Trim()
            $count++
        }
    }
    $summary['Bedenkenanzeigen (BED)'] = $count
    Write-Host "  Bedenkenanzeigen:      $count" -ForegroundColor Green
}

# ================================================================
# 4. Planungsmaengel (08_Planungsmangel)
# ================================================================
$dir = Join-Path $BasePath "08_Planungsmangel"
if (Test-Path $dir) {
    $count = 0
    $sql.Add("")
    $sql.Add("-- === Planungsmaengel ===")
    Get-ChildItem $dir -Filter "*.pdf" -Name | ForEach-Object {
        $name = $_ -replace '\.pdf$', ''
        if ($name -match '^(\d{3})\s+(.+)$') {
            Add-Vorgang 'mangelanzeige' "MA-P-$($Matches[1])" "Planungsmangel: $($Matches[2].Trim())"
            $count++
        }
    }
    $summary['Planungsmaengel (MA-P)'] = $count
    Write-Host "  Planungsmaengel:       $count" -ForegroundColor Green
}

# ================================================================
# 5. Ausfuehrungsmaengel (09_Ausfuehrungsmangel)
# ================================================================
$dir = Join-Path $BasePath "09_Ausführungsmangel"
if (Test-Path $dir) {
    $count = 0
    $seq = 1
    $sql.Add("")
    $sql.Add("-- === Ausfuehrungsmaengel ===")
    Get-ChildItem $dir -Filter "*.pdf" -Name | ForEach-Object {
        $name = $_ -replace '\.pdf$', ''
        $nummer = "MA-A-{0:D3}" -f $seq
        Add-Vorgang 'mangelanzeige' $nummer "Ausfuehrungsmangel: $name"
        $count++
        $seq++
    }
    $summary['Ausfuehrungsmaengel (MA-A)'] = $count
    Write-Host "  Ausfuehrungsmaengel:   $count" -ForegroundColor Green
}

$sql.Add("")
$sql.Add("COMMIT;")

$total = ($summary.Values | Measure-Object -Sum).Sum

Write-Host ""
Write-Host "Schreibe $total Vorgaenge..." -ForegroundColor Cyan
$sql -join "`n" | Set-Content -Path $TempSQL -Encoding utf8NoBOM -NoNewline -Force

Write-Host "Fuehre Import aus..." -ForegroundColor Cyan
$errors = 0
Get-Content $TempSQL -Raw | docker exec -i $Container psql -U $User -d $DB -q 2>&1 | ForEach-Object {
    if ($_ -match 'ERROR') {
        Write-Host "  $_" -ForegroundColor Red
        $errors++
    }
}

Write-Host ""
Write-Host "Validierung:" -ForegroundColor Cyan
$check = "SET search_path TO tenant_tlbv, shared, public; SELECT typ::text, COUNT(*) as anzahl FROM vorgaenge WHERE projekt_id = (SELECT id FROM projekte WHERE kurz = 'FLI') GROUP BY typ ORDER BY typ;"
$check | docker exec -i $Container psql -U $User -d $DB -t

Write-Host ""
if ($errors -eq 0) {
    Write-Host "============================================" -ForegroundColor Green
    Write-Host " Import erfolgreich: $total Vorgaenge" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
} else {
    Write-Host "============================================" -ForegroundColor Red
    Write-Host " Import mit $errors Fehlern" -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
}
foreach ($k in $summary.Keys) {
    Write-Host "  $k : $($summary[$k])"
}
Write-Host ""

Remove-Item $TempSQL -ErrorAction SilentlyContinue
