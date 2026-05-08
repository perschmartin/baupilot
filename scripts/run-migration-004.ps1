# ============================================================
# Migration 004: Aufgabenmanagement + Cleanup
# Ausfuehrung: .\scripts\run-migration-004.ps1
# ============================================================

Write-Host "`n=== BauPilot Migration 004: Aufgabenmanagement ===" -ForegroundColor Cyan

$sqlFile = Join-Path $PSScriptRoot "..\alembic\sql\004_aufgabenmanagement.sql"

if (-not (Test-Path $sqlFile)) {
    Write-Host "FEHLER: SQL-Datei nicht gefunden: $sqlFile" -ForegroundColor Red
    exit 1
}

Write-Host "Lese SQL aus: $sqlFile"
$sql = Get-Content -Path $sqlFile -Raw -Encoding utf8

Write-Host "Fuehre Migration aus..."
$env:PGPASSWORD = $env:POSTGRES_PASSWORD
if (-not $env:PGPASSWORD) { $env:PGPASSWORD = "baupilot_dev" }

$result = docker exec -i baupilot-postgres psql `
    -U ($env:POSTGRES_USER ?? "baupilot") `
    -d ($env:POSTGRES_DB ?? "baupilot") `
    -v ON_ERROR_STOP=1 `
    -c $sql 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER bei Migration 004:" -ForegroundColor Red
    Write-Host $result -ForegroundColor Red
    exit 1
}

Write-Host $result
Write-Host "`nMigration 004 erfolgreich." -ForegroundColor Green

# Pruefen
$version = docker exec baupilot-postgres psql `
    -U ($env:POSTGRES_USER ?? "baupilot") `
    -d ($env:POSTGRES_DB ?? "baupilot") `
    -t -c "SELECT version_num FROM shared.alembic_version" 2>&1

Write-Host "Alembic-Version: $($version.Trim())" -ForegroundColor Yellow
