# run-migration-009.ps1
# Migration 009: Service-Konto-Flag (ist_dienstkonto) — E14 TOTP-Bypass abloesen.
# Datum: 15.06.2026
# Fuegt shared.benutzer.ist_dienstkonto (BOOLEAN, Default FALSE) hinzu.
# Idempotent; Default FALSE -> keine Verhaltensaenderung fuer bestehende Konten.

$ErrorActionPreference = 'Stop'

Write-Host "=== Migration 009: Service-Konto-Flag (ist_dienstkonto) ===" -ForegroundColor Cyan

$sqlPath = Join-Path $PSScriptRoot "..\alembic\sql\009_service_konto.sql"
if (-not (Test-Path $sqlPath)) {
    Write-Host "FEHLER: $sqlPath nicht gefunden." -ForegroundColor Red
    exit 1
}

# Backup (Pflicht — Rollback-Vorbereitung)
$backupDir = "C:\Tools\claude-sandbox\bp-migration-009"
if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir -Force | Out-Null }
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path $backupDir "baupilot_backup_pre009_$timestamp.sql"
Write-Host "Backup nach $backupPath ..." -ForegroundColor Yellow
docker exec baupilot-postgres pg_dump -U baupilot -d baupilot --no-owner --no-acl | Out-File -FilePath $backupPath -Encoding utf8
if (-not (Test-Path $backupPath) -or (Get-Item $backupPath).Length -lt 100000) {
    Write-Host "FEHLER: Backup zu klein oder nicht erstellt." -ForegroundColor Red
    exit 1
}
Write-Host "Backup OK: $((Get-Item $backupPath).Length) Bytes" -ForegroundColor Green

# Migration ausfuehren
Write-Host "Fuehre Migration aus..." -ForegroundColor Yellow
Get-Content $sqlPath -Raw -Encoding utf8 | docker exec -i baupilot-postgres psql -U baupilot -d baupilot -v ON_ERROR_STOP=1
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER: Migration 009 fehlgeschlagen. Backup verfuegbar unter $backupPath." -ForegroundColor Red
    exit 1
}

# Validierung
Write-Host "`nValidierung..." -ForegroundColor Yellow
$valSql = @"
SELECT version_num FROM shared.alembic_version;
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_schema='shared' AND table_name='benutzer' AND column_name='ist_dienstkonto';
SELECT COUNT(*) AS dienstkonten FROM shared.benutzer WHERE ist_dienstkonto;
"@
$valSql | docker exec -i baupilot-postgres psql -U baupilot -d baupilot

Write-Host "`n=== Migration 009 abgeschlossen ===" -ForegroundColor Green
Write-Host "Erwartet: alembic_version=009; Spalte ist_dienstkonto (boolean, default false); dienstkonten=0." -ForegroundColor Gray
Write-Host "Rollback: cat $backupPath | docker exec -i baupilot-postgres psql -U baupilot -d baupilot_restore" -ForegroundColor DarkGray
