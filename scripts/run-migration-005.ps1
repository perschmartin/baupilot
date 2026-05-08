# ============================================================
# Migration 005 - Dokumentenverwaltung (AP 1.5)
# Ausfuehrung: .\scripts\run-migration-005.ps1
# ============================================================

Write-Host "=== BauPilot Migration 005: Dokumentenverwaltung ===" -ForegroundColor Cyan

$sqlFile = Join-Path $PSScriptRoot "..\alembic\sql\005_dokumentenverwaltung.sql"

if (-not (Test-Path $sqlFile)) {
    Write-Host "FEHLER: SQL-Datei nicht gefunden: $sqlFile" -ForegroundColor Red
    exit 1
}

Write-Host "SQL-Datei: $sqlFile" -ForegroundColor Yellow
Write-Host "Fuehre Migration aus..." -ForegroundColor Yellow

Get-Content $sqlFile -Raw | docker exec -i baupilot-postgres psql -U baupilot -d baupilot

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "=== Migration 005 erfolgreich ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "Naechste Schritte:" -ForegroundColor Cyan
    Write-Host "1. requirements.txt pruefen: 'minio' muss enthalten sein"
    Write-Host "2. Container neu bauen: docker compose -f docker-compose.services.yaml build api"
    Write-Host "3. Container starten: docker compose -f docker-compose.services.yaml up -d api"
    Write-Host "4. Testen: curl http://localhost:8110/api/v1/dokumente/?projekt=FLI"
} else {
    Write-Host "FEHLER bei Migration 005!" -ForegroundColor Red
    exit 1
}
