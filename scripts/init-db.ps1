# BauPilot — Datenbank-Initialisierung
# Ausfuehrung: .\scripts\init-db.ps1
# Voraussetzung: docker compose up -d (Postgres laeuft)

$ErrorActionPreference = "Stop"

Write-Host "=== BauPilot — Datenbank-Initialisierung ===" -ForegroundColor Cyan

# Warten auf PostgreSQL
Write-Host "Warte auf PostgreSQL (Port 5436)..." -ForegroundColor Yellow
$maxRetries = 30
$retry = 0
do {
    $retry++
    try {
        $null = docker exec baupilot-postgres pg_isready -U baupilot 2>$null
        if ($LASTEXITCODE -eq 0) { break }
    } catch {}
    Start-Sleep -Seconds 1
} while ($retry -lt $maxRetries)

if ($retry -ge $maxRetries) {
    Write-Host "FEHLER: PostgreSQL nicht erreichbar nach $maxRetries Sekunden." -ForegroundColor Red
    exit 1
}
Write-Host "PostgreSQL erreichbar." -ForegroundColor Green

# Shared-Schema anlegen
Write-Host "Erstelle shared-Schema..." -ForegroundColor Yellow
docker exec baupilot-postgres psql -U baupilot -d baupilot -c "CREATE SCHEMA IF NOT EXISTS shared;"
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: shared-Schema konnte nicht angelegt werden." -ForegroundColor Red
    exit 1
}
Write-Host "shared-Schema erstellt." -ForegroundColor Green

# Mandanten-Schema TLBV anlegen
Write-Host "Erstelle Mandanten-Schema tenant_tlbv..." -ForegroundColor Yellow
docker exec baupilot-postgres psql -U baupilot -d baupilot -c "CREATE SCHEMA IF NOT EXISTS tenant_tlbv;"
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: tenant_tlbv-Schema konnte nicht angelegt werden." -ForegroundColor Red
    exit 1
}
Write-Host "tenant_tlbv-Schema erstellt." -ForegroundColor Green

# UUID-Extension aktivieren
Write-Host "Aktiviere pgcrypto-Extension..." -ForegroundColor Yellow
docker exec baupilot-postgres psql -U baupilot -d baupilot -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
Write-Host "pgcrypto aktiviert." -ForegroundColor Green

# Alembic-Migration ausfuehren (wenn Python-Umgebung vorhanden)
$alembicPath = Join-Path $PSScriptRoot ".." "alembic"
if (Test-Path (Join-Path $alembicPath "alembic.ini")) {
    Write-Host "Fuehre Alembic-Migrationen aus..." -ForegroundColor Yellow
    Push-Location (Join-Path $PSScriptRoot "..")
    try {
        python -m alembic -c alembic/alembic.ini upgrade head
        Write-Host "Alembic-Migrationen erfolgreich." -ForegroundColor Green
    } catch {
        Write-Host "WARNUNG: Alembic-Migrationen fehlgeschlagen. Manuell ausfuehren." -ForegroundColor Yellow
        Write-Host $_.Exception.Message -ForegroundColor Yellow
    }
    Pop-Location
} else {
    Write-Host "HINWEIS: Alembic nicht gefunden, ueberspringe Migrationen." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Datenbank-Initialisierung abgeschlossen ===" -ForegroundColor Cyan
Write-Host "Schemata: shared, tenant_tlbv" -ForegroundColor White
Write-Host "Naechster Schritt: .\scripts\validate-stack.ps1" -ForegroundColor White
