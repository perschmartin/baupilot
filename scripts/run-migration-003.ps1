<#
.SYNOPSIS
    Migration 003: Einladungssystem.
#>
$ErrorActionPreference = "Stop"
$ContainerName = "baupilot-postgres"
$DbName = "baupilot"
$DbUser = "baupilot"
$MigrationFile = Join-Path $PSScriptRoot "..\alembic\sql\003_einladungen.sql"

Write-Host "=== Migration 003: Einladungssystem ===" -ForegroundColor Cyan

$version = (docker exec $ContainerName psql -U $DbUser -d $DbName -t -c "SELECT version_num FROM shared.alembic_version;" | Out-String).Trim()
if ($version -ne "002") { Write-Host "FEHLER: Erwartete Version 002, gefunden: $version" -ForegroundColor Red; exit 1 }

$sql = Get-Content $MigrationFile -Raw -Encoding utf8
$sql | docker exec -i $ContainerName psql -U $DbUser -d $DbName 2>&1

$newV = (docker exec $ContainerName psql -U $DbUser -d $DbName -t -c "SELECT version_num FROM shared.alembic_version;" | Out-String).Trim()
if ($newV -eq "003") { Write-Host "Migration 003 erfolgreich." -ForegroundColor Green }
else { Write-Host "FEHLER: Version ist $newV" -ForegroundColor Red; exit 1 }
