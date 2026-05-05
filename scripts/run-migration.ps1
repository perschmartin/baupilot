# =============================================================================
# BauPilot — run-migration.ps1
# =============================================================================
# Fuehrt Migration 001 (Initiales Schema) direkt via psql im Postgres-Container
# aus. Kein Alembic auf dem Host noetig.
#
# Voraussetzung:
#   - docker compose up -d gelaufen (Postgres auf Port 5436)
#   - init-db.ps1 gelaufen (Schemata shared + tenant_tlbv existieren)
#
# Verwendung:
#   .\scripts\run-migration.ps1
# =============================================================================

$ErrorActionPreference = "Stop"

$ContainerName = "baupilot-postgres"
$DbUser = "baupilot"
$DbName = "baupilot"
$SqlFile = "/tmp/001_initial_schema.sql"
$LocalSqlFile = Join-Path $PSScriptRoot ".." "alembic" "sql" "001_initial_schema.sql"

function Write-Step { param([string]$M) Write-Host "`n[$((Get-Date).ToString('HH:mm:ss'))] $M" -ForegroundColor Cyan }
function Write-Pass { param([string]$M) Write-Host "  PASS  $M" -ForegroundColor Green }
function Write-Fail { param([string]$M) Write-Host "  FAIL  $M" -ForegroundColor Red }

Write-Host ""
Write-Host "  =========================================" -ForegroundColor Cyan
Write-Host "  BauPilot — Migration 001                 " -ForegroundColor Cyan
Write-Host "  Initiales Datenbankschema                " -ForegroundColor Cyan
Write-Host "  =========================================" -ForegroundColor Cyan

# --- 1. Voraussetzungen ----------------------------------------------------

Write-Step "Pruefe ob $ContainerName laeuft..."
$state = docker inspect -f '{{.State.Running}}' $ContainerName 2>&1
if ($state -ne "true") { Write-Fail "$ContainerName laeuft nicht."; exit 1 }
Write-Pass "$ContainerName laeuft."

Write-Step "Pruefe SQL-Datei..."
if (-not (Test-Path $LocalSqlFile)) { Write-Fail "Nicht gefunden: $LocalSqlFile"; exit 1 }
Write-Pass "SQL-Datei vorhanden."

Write-Step "Pruefe Schemata..."
$schemas = docker exec $ContainerName psql -U $DbUser -d $DbName -tAc "SELECT string_agg(schema_name, ', ' ORDER BY schema_name) FROM information_schema.schemata WHERE schema_name = 'shared' OR schema_name LIKE 'tenant_%';" 2>&1
if (-not $schemas -or $schemas.Trim() -eq "") { Write-Fail "Keine Schemata. init-db.ps1 zuerst."; exit 1 }
Write-Pass "Schemata: $($schemas.Trim())"

# --- 2. Bereits gelaufen? --------------------------------------------------

Write-Step "Pruefe ob Migration 001 bereits ausgefuehrt..."
$ver = docker exec $ContainerName psql -U $DbUser -d $DbName -tAc "SELECT version_num FROM shared.alembic_version WHERE version_num = '001';" 2>&1
if ($ver -and $ver.Trim() -eq "001") {
    $tc = docker exec $ContainerName psql -U $DbUser -d $DbName -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'tenant_tlbv' AND table_type = 'BASE TABLE';" 2>&1
    if ([int]$tc.Trim() -ge 10) {
        Write-Pass "Migration 001 bereits komplett ($($tc.Trim()) Tabellen in tenant_tlbv)."
        exit 0
    }
    Write-Host "  Version 001 eingetragen, aber Tabellen fehlen. Erneuter Versuch..." -ForegroundColor Yellow
}

# --- 3. Migration ausfuehren -----------------------------------------------

Write-Step "Kopiere SQL in Container..."
docker cp $LocalSqlFile "${ContainerName}:${SqlFile}"
if ($LASTEXITCODE -ne 0) { Write-Fail "Kopieren fehlgeschlagen."; exit 1 }
Write-Pass "Kopiert."

Write-Step "Fuehre Migration 001 aus..."
$out = docker exec $ContainerName psql -U $DbUser -d $DbName -f $SqlFile 2>&1
$ec = $LASTEXITCODE

$out | ForEach-Object {
    $l = $_.ToString().Trim()
    if ($l -match "^NOTICE:") { Write-Host "  $l" -ForegroundColor DarkGray }
    elseif ($l -match "^ERROR:") { Write-Host "  $l" -ForegroundColor Red }
}

if ($ec -ne 0) {
    Write-Fail "Migration fehlgeschlagen (Exit $ec)."
    $out | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
    exit 1
}

docker exec $ContainerName rm -f $SqlFile 2>&1 | Out-Null

# --- 4. Validierung --------------------------------------------------------

Write-Step "Validierung..."
$allPass = $true

# Tabellen zaehlen
foreach ($s in @("shared", "tenant_tlbv")) {
    $c = docker exec $ContainerName psql -U $DbUser -d $DbName -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema = '$s' AND table_type = 'BASE TABLE';" 2>&1
    $c = [int]$c.Trim()
    $min = if ($s -eq "shared") { 4 } else { 10 }  # shared: 3 + alembic_version
    if ($c -ge $min) { Write-Pass "$s : $c Tabellen" }
    else { Write-Fail "$s : $c Tabellen (erwartet >= $min)"; $allPass = $false }
}

# Enums
$ec2 = docker exec $ContainerName psql -U $DbUser -d $DbName -tAc "SELECT count(*) FROM pg_type WHERE typtype = 'e' AND typname IN ('projektstatus','bauteiltyp','klassifikation','vorgangtyp','vorgangstatus','beziehungstyp','benutzerrolle');" 2>&1
if ([int]$ec2.Trim() -eq 7) { Write-Pass "7/7 Enum-Typen" }
else { Write-Fail "$($ec2.Trim())/7 Enum-Typen"; $allPass = $false }

# Alembic-Version
$v = docker exec $ContainerName psql -U $DbUser -d $DbName -tAc "SELECT version_num FROM shared.alembic_version;" 2>&1
if ($v.Trim() -eq "001") { Write-Pass "Alembic-Version: 001" }
else { Write-Fail "Alembic-Version: $($v.Trim())"; $allPass = $false }

# Mandant
$m = docker exec $ContainerName psql -U $DbUser -d $DbName -tAc "SELECT slug FROM shared.mandanten WHERE slug = 'tlbv';" 2>&1
if ($m.Trim() -eq "tlbv") { Write-Pass "Mandant 'tlbv' geseedet" }
else { Write-Fail "Mandant 'tlbv' fehlt"; $allPass = $false }

# B-001: nullable FK
$nb = docker exec $ContainerName psql -U $DbUser -d $DbName -tAc "SELECT is_nullable FROM information_schema.columns WHERE table_schema='tenant_tlbv' AND table_name='vorgaenge' AND column_name='bauteil_id';" 2>&1
if ($nb.Trim() -eq "YES") { Write-Pass "B-001: bauteil_id nullable" }
else { Write-Fail "B-001: bauteil_id nicht nullable"; $allPass = $false }

# B-002: Verknuepfung
$b2 = docker exec $ContainerName psql -U $DbUser -d $DbName -tAc "SELECT count(*) FROM information_schema.columns WHERE table_schema='tenant_tlbv' AND table_name='vorgaenge' AND column_name IN ('vorgaenger_id','konfidenz','konfidenz_bestaetigt');" 2>&1
if ([int]$b2.Trim() -ge 3) { Write-Pass "B-002: Verknuepfungsspalten komplett" }
else { Write-Fail "B-002: Verknuepfungsspalten unvollstaendig"; $allPass = $false }

# G3: Dreiklang
$d = docker exec $ContainerName psql -U $DbUser -d $DbName -tAc "SELECT count(*) FROM information_schema.columns WHERE table_schema='tenant_tlbv' AND table_name='vorgaenge' AND column_name IN ('kosten_eur','zeit_arbeitstage','qualitaet_bewertung');" 2>&1
if ([int]$d.Trim() -ge 3) { Write-Pass "G3: Dreiklang Q/Z/K komplett" }
else { Write-Fail "G3: Dreiklang unvollstaendig"; $allPass = $false }

# --- 5. Ergebnis -----------------------------------------------------------

Write-Host ""
if ($allPass) {
    Write-Host "  =========================================" -ForegroundColor Green
    Write-Host "  Migration 001 erfolgreich!               " -ForegroundColor Green
    Write-Host "                                           " -ForegroundColor Green
    Write-Host "  shared:       3 Tabellen + alembic_version" -ForegroundColor Green
    Write-Host "  tenant_tlbv: 10 Tabellen                 " -ForegroundColor Green
    Write-Host "  7 Enum-Typen, TLBV-Mandant geseedet      " -ForegroundColor Green
    Write-Host "                                           " -ForegroundColor Green
    Write-Host "  BP-AP 0.8 abgeschlossen.                 " -ForegroundColor Green
    Write-Host "  =========================================" -ForegroundColor Green
} else {
    Write-Host "  =========================================" -ForegroundColor Red
    Write-Host "  Migration unvollstaendig!                " -ForegroundColor Red
    Write-Host "  Fehler oben pruefen.                     " -ForegroundColor Red
    Write-Host "  =========================================" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  Naechste Schritte:" -ForegroundColor Cyan
Write-Host "    1. Konzeptpapier v0.3 (Paket 2 + 3)" -ForegroundColor DarkGray
Write-Host "    2. Projektanweisung v0.2 (Ports, AP-Status, Entscheidungen)" -ForegroundColor DarkGray
Write-Host ""
