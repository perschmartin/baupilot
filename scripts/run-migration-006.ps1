# run-migration-006.ps1
# Migration 006: LV-Extraktion (AP 1.2)
# Fuehrt die SQL-Migration gegen baupilot-postgres aus.

$ErrorActionPreference = "Stop"

Write-Host "=== Migration 006: LV-Extraktion ===" -ForegroundColor Cyan

# Aktuelle Alembic-Version pruefen
$version = docker exec baupilot-postgres psql -U baupilot -d baupilot -t -c "SELECT version_num FROM shared.alembic_version;" 2>$null
$version = ($version -replace '\s','')

if ($version -ne "005") {
    Write-Host "WARNUNG: Aktuelle Alembic-Version ist '$version', erwartet '005'." -ForegroundColor Yellow
    $antwort = Read-Host "Trotzdem fortfahren? (j/n)"
    if ($antwort -ne "j") {
        Write-Host "Abgebrochen." -ForegroundColor Red
        exit 1
    }
}

# Migration ausfuehren
Write-Host "Fuehre Migration 006 aus..." -ForegroundColor Green
Get-Content "$PSScriptRoot\..\alembic\sql\006_lv_extraktion.sql" |
    docker exec -i baupilot-postgres psql -U baupilot -d baupilot

if ($LASTEXITCODE -eq 0) {
    Write-Host "Migration 006 erfolgreich. Alembic-Version: 006" -ForegroundColor Green
} else {
    Write-Host "Migration 006 fehlgeschlagen!" -ForegroundColor Red
    exit 1
}

# Verifizierung
Write-Host "`nVerifizierung:" -ForegroundColor Cyan
docker exec baupilot-postgres psql -U baupilot -d baupilot -c "SELECT version_num FROM shared.alembic_version;"
docker exec baupilot-postgres psql -U baupilot -d baupilot -c "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='tenant_tlbv' AND table_name='lv_positionen' AND column_name IN ('kurztext','einheit','hierarchie_ebene','ist_titel','extrahiert_am') ORDER BY column_name;"

Write-Host "`nFertig." -ForegroundColor Green
