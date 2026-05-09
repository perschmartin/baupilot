# run-migration-007.ps1
# Migration 007: Nachtragsmanagement + BKI-Baupreise + Schema-Hotfixes
# Datum: 09.05.2026

$ErrorActionPreference = 'Stop'

Write-Host "=== Migration 007: Nachtragsmanagement ===" -ForegroundColor Cyan

# SQL-Datei einlesen und an PostgreSQL senden
$sqlPath = Join-Path $PSScriptRoot "..\alembic\sql\007_nachtragsmanagement.sql"
if (-not (Test-Path $sqlPath)) {
    Write-Host "FEHLER: $sqlPath nicht gefunden." -ForegroundColor Red
    exit 1
}

Write-Host "SQL-Datei: $sqlPath" -ForegroundColor Gray
Write-Host "Fuehre Migration aus..." -ForegroundColor Yellow

Get-Content $sqlPath -Raw -Encoding utf8 | docker exec -i baupilot-postgres psql -U baupilot -d baupilot -v ON_ERROR_STOP=1

if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: Migration 007 fehlgeschlagen." -ForegroundColor Red
    exit 1
}

Write-Host "`nValidierung..." -ForegroundColor Yellow

# Validierung
$validierung = @"
SET search_path TO tenant_tlbv, shared, public;
SELECT 'nachtragspruefung' AS tabelle, COUNT(*) AS zeilen FROM nachtragspruefung
UNION ALL
SELECT 'entscheidungsvorlagen', COUNT(*) FROM entscheidungsvorlagen
UNION ALL
SELECT 'bki_baupreise', COUNT(*) FROM shared.bki_baupreise
UNION ALL
SELECT 'bki_regionalfaktoren', COUNT(*) FROM shared.bki_regionalfaktoren;
SELECT version_num FROM shared.alembic_version;
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'tenant_tlbv' AND table_name = 'vorgaenge'
  AND column_name IN ('betrag_gefordert','betrag_geprueft','betrag_genehmigt',
                       'zeitauswirkung_tage','nachtragsvariante','ntv_id',
                       'kostengruppe_din276','qualitaetsauswirkung')
ORDER BY column_name;
"@

$validierung | docker exec -i baupilot-postgres psql -U baupilot -d baupilot

Write-Host "`n=== Migration 007 abgeschlossen ===" -ForegroundColor Green
Write-Host "Erwartete Ergebnisse:" -ForegroundColor Gray
Write-Host "  - nachtragspruefung: 0 Zeilen" -ForegroundColor Gray
Write-Host "  - entscheidungsvorlagen: 0 Zeilen" -ForegroundColor Gray
Write-Host "  - bki_baupreise: 0 (INSERTs kommen separat)" -ForegroundColor Gray
Write-Host "  - bki_regionalfaktoren: 7" -ForegroundColor Gray
Write-Host "  - alembic_version: 007" -ForegroundColor Gray
Write-Host "  - 8 neue Spalten an vorgaenge" -ForegroundColor Gray
