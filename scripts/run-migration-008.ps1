# run-migration-008.ps1
# Migration 008: Stoerungsmanagement + Benachrichtigungen + Tag-Hierarchie
# Datum: 18.05.2026
# Konsolidiert: AP 2.2 Vorbereitung (behinderungs-/bedenken-/mangelpruefung),
#   B-012 Benachrichtigungen-Schema, B-013 Tag-Hierarchie + dokument_tags.
# Verifiziert: Sandbox-Test gegen baupilot_test gruen (siehe C:\Tools\claude-sandbox\bp-migration-008\).

$ErrorActionPreference = 'Stop'

Write-Host "=== Migration 008: Stoerung + Benachrichtigung + Tag-Hierarchie ===" -ForegroundColor Cyan

$sqlPath = Join-Path $PSScriptRoot "..\alembic\sql\008_stoerungsmanagement_benachrichtigungen_tags.sql"
if (-not (Test-Path $sqlPath)) {
    Write-Host "FEHLER: $sqlPath nicht gefunden." -ForegroundColor Red
    exit 1
}

# Backup (Pflicht — Rollback-Vorbereitung)
$backupDir = "C:\Tools\claude-sandbox\bp-migration-008"
if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory -Path $backupDir -Force | Out-Null }
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path $backupDir "baupilot_backup_pre008_$timestamp.sql"
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
    Write-Host "FEHLER: Migration 008 fehlgeschlagen. Backup verfuegbar unter $backupPath." -ForegroundColor Red
    exit 1
}

# Validierung
Write-Host "`nValidierung..." -ForegroundColor Yellow
$valSql = @"
SELECT version_num FROM shared.alembic_version;
SELECT 'behinderungspruefung' AS name, COUNT(*)::text AS wert FROM tenant_tlbv.behinderungspruefung
UNION ALL SELECT 'bedenkenpruefung', COUNT(*)::text FROM tenant_tlbv.bedenkenpruefung
UNION ALL SELECT 'mangelpruefung', COUNT(*)::text FROM tenant_tlbv.mangelpruefung
UNION ALL SELECT 'dokument_tags', COUNT(*)::text FROM tenant_tlbv.dokument_tags
UNION ALL SELECT 'benachrichtigungen', COUNT(*)::text FROM tenant_tlbv.benachrichtigungen
UNION ALL SELECT 'benachrichtigungs_regeln', COUNT(*)::text FROM tenant_tlbv.benachrichtigungs_regeln
UNION ALL SELECT 'tag_wurzeln', COUNT(*)::text FROM tenant_tlbv.tags WHERE ist_kategorie_wurzel
UNION ALL SELECT 'tag_kinder', COUNT(*)::text FROM tenant_tlbv.tags WHERE parent_id IS NOT NULL
UNION ALL SELECT 'vorgaenge_unveraendert', COUNT(*)::text FROM tenant_tlbv.vorgaenge
UNION ALL SELECT 'dokumente_unveraendert', COUNT(*)::text FROM tenant_tlbv.dokumente;
"@
$valSql | docker exec -i baupilot-postgres psql -U baupilot -d baupilot

Write-Host "`n=== Migration 008 abgeschlossen ===" -ForegroundColor Green
Write-Host "Erwartete Ergebnisse:" -ForegroundColor Gray
Write-Host "  - alembic_version: 008" -ForegroundColor Gray
Write-Host "  - 3 Stoerungspruefungs-Tabellen: je 0 Zeilen" -ForegroundColor Gray
Write-Host "  - dokument_tags: 0" -ForegroundColor Gray
Write-Host "  - benachrichtigungen: 0" -ForegroundColor Gray
Write-Host "  - benachrichtigungs_regeln: 4 (Seed)" -ForegroundColor Gray
Write-Host "  - tag_wurzeln: 3 (Bauphase, Bauteil, Dokumenttyp)" -ForegroundColor Gray
Write-Host "  - tag_kinder: 24 (9 + 6 + 9)" -ForegroundColor Gray
Write-Host "  - vorgaenge und dokumente: unveraendert" -ForegroundColor Gray
Write-Host "`nRollback: cat $backupPath | docker exec -i baupilot-postgres psql -U baupilot -d baupilot_restore" -ForegroundColor DarkGray
