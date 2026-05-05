<#
.SYNOPSIS
    Migration 002: Auth-Erweiterung ausfuehren.
.DESCRIPTION
    Fuehrt die SQL-Migration 002_auth_erweiterung.sql gegen die BauPilot-Datenbank aus.
    Prueft vorher, ob Migration 001 vorhanden ist, und validiert danach das Ergebnis.
#>

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# --- Konfiguration ---
$ContainerName = "baupilot-postgres"
$DbName = "baupilot"
$DbUser = "baupilot"
$MigrationFile = Join-Path $PSScriptRoot "..\alembic\sql\002_auth_erweiterung.sql"

Write-Host "=== BauPilot Migration 002: Auth-Erweiterung ===" -ForegroundColor Cyan

# --- Vorpruefung: Migration 001 vorhanden? ---
Write-Host "`n[1/4] Pruefe Alembic-Version..." -ForegroundColor Yellow
$version = docker exec $ContainerName psql -U $DbUser -d $DbName -t -c `
    "SELECT version_num FROM shared.alembic_version LIMIT 1;" 2>&1

if ($version -is [System.Management.Automation.ErrorRecord]) {
    Write-Host "FEHLER: Alembic-Version konnte nicht gelesen werden." -ForegroundColor Red
    Write-Host "Wurde Migration 001 ausgefuehrt?" -ForegroundColor Red
    exit 1
}

$versionClean = ($version | Out-String).Trim()
if ($versionClean -ne "001") {
    Write-Host "FEHLER: Erwartete Version 001, gefunden: '$versionClean'" -ForegroundColor Red
    exit 1
}
Write-Host "  Alembic-Version: $versionClean (OK)" -ForegroundColor Green

# --- Migration ausfuehren ---
Write-Host "`n[2/4] Fuehre Migration 002 aus..." -ForegroundColor Yellow

if (-not (Test-Path $MigrationFile)) {
    Write-Host "FEHLER: $MigrationFile nicht gefunden." -ForegroundColor Red
    exit 1
}

$sql = Get-Content -Path $MigrationFile -Raw -Encoding utf8
$sql | docker exec -i $ContainerName psql -U $DbUser -d $DbName 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: Migration fehlgeschlagen." -ForegroundColor Red
    exit 1
}
Write-Host "  Migration ausgefuehrt." -ForegroundColor Green

# --- Validierung ---
Write-Host "`n[3/4] Validiere Schema..." -ForegroundColor Yellow

# Neue Spalten an benutzer pruefen
$spalten = @(
    "password_hash", "totp_secret", "totp_aktiviert", "totp_setup_secret",
    "backup_codes", "letzter_login", "fehlversuche", "gesperrt_bis",
    "passwort_geaendert_am", "muss_passwort_aendern"
)
$fehler = 0

foreach ($spalte in $spalten) {
    $check = docker exec $ContainerName psql -U $DbUser -d $DbName -t -c `
        "SELECT column_name FROM information_schema.columns WHERE table_schema='shared' AND table_name='benutzer' AND column_name='$spalte';" 2>&1
    $checkClean = ($check | Out-String).Trim()
    if ($checkClean -ne $spalte) {
        Write-Host "  FEHLT: shared.benutzer.$spalte" -ForegroundColor Red
        $fehler++
    }
}
Write-Host "  Spalten: $($spalten.Count - $fehler)/$($spalten.Count) vorhanden" -ForegroundColor $(if ($fehler -eq 0) { "Green" } else { "Red" })

# Neue Tabellen pruefen
foreach ($tabelle in @("refresh_tokens", "auth_log")) {
    $check = docker exec $ContainerName psql -U $DbUser -d $DbName -t -c `
        "SELECT table_name FROM information_schema.tables WHERE table_schema='shared' AND table_name='$tabelle';" 2>&1
    $checkClean = ($check | Out-String).Trim()
    if ($checkClean -ne $tabelle) {
        Write-Host "  FEHLT: shared.$tabelle" -ForegroundColor Red
        $fehler++
    } else {
        Write-Host "  Tabelle shared.$tabelle vorhanden" -ForegroundColor Green
    }
}

# Alembic-Version
$newVersion = docker exec $ContainerName psql -U $DbUser -d $DbName -t -c `
    "SELECT version_num FROM shared.alembic_version LIMIT 1;" 2>&1
$newVersionClean = ($newVersion | Out-String).Trim()
if ($newVersionClean -ne "002") {
    Write-Host "  Alembic-Version: $newVersionClean (ERWARTET: 002)" -ForegroundColor Red
    $fehler++
} else {
    Write-Host "  Alembic-Version: 002 (OK)" -ForegroundColor Green
}

# --- Ergebnis ---
Write-Host "`n[4/4] Ergebnis:" -ForegroundColor Yellow
if ($fehler -eq 0) {
    Write-Host "  Migration 002 erfolgreich. $($spalten.Count) Spalten, 2 Tabellen, 1 Enum." -ForegroundColor Green
} else {
    Write-Host "  $fehler Fehler gefunden. Migration unvollstaendig." -ForegroundColor Red
    exit 1
}
