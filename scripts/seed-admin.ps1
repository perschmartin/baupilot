$ErrorActionPreference = "Stop"
$ContainerName = "baupilot-postgres"
$DbName = "baupilot"
$DbUser = "baupilot"
$EnvFile = Join-Path $PSScriptRoot "..\.env"

Write-Host "=== BauPilot Admin-Seed ===" -ForegroundColor Cyan

# .env laden
$envVars = @{}
Get-Content $EnvFile -Encoding utf8 | ForEach-Object {
    if ($_ -match "^\s*([^#][^=]+?)\s*=\s*(.+?)\s*$") {
        $envVars[$matches[1]] = $matches[2]
    }
}

$email = $envVars["BAUPILOT_ADMIN_EMAIL"]
$vorname = $envVars["BAUPILOT_ADMIN_VORNAME"]
$nachname = $envVars["BAUPILOT_ADMIN_NACHNAME"]
$initialPw = $envVars["BAUPILOT_ADMIN_INITIAL_PW"]

if (-not $email -or -not $initialPw) {
    Write-Host "FEHLER: BAUPILOT_ADMIN_EMAIL und BAUPILOT_ADMIN_INITIAL_PW in .env setzen." -ForegroundColor Red
    exit 1
}

Write-Host "  E-Mail: $email"

# Passwort hashen
Write-Host "[1/3] Hashe Passwort..." -ForegroundColor Yellow
$pyCmd = "from argon2 import PasswordHasher; ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16); print(ph.hash('$($initialPw.Replace("'","''"))'))"
$pwHash = python -c $pyCmd 2>&1
if ($LASTEXITCODE -ne 0) { Write-Host "FEHLER: argon2-cffi installiert?" -ForegroundColor Red; exit 1 }
$pwHash = ($pwHash | Out-String).Trim()
Write-Host "  Hash erzeugt." -ForegroundColor Green

# Admin einfuegen
Write-Host "[2/3] Fuege Admin ein..." -ForegroundColor Yellow
$escapedHash = $pwHash.Replace("'", "''")

$sql = @"
INSERT INTO shared.benutzer (id, email, vorname, nachname, passwort_hash, aktiv, muss_passwort_aendern, erstellt_am, geaendert_am, erstellt_von)
VALUES (gen_random_uuid(), '$email', '$vorname', '$nachname', '$escapedHash', TRUE, TRUE, NOW(), NOW(), 'seed-admin')
ON CONFLICT (email) DO UPDATE SET
    passwort_hash = EXCLUDED.passwort_hash,
    muss_passwort_aendern = TRUE,
    geaendert_am = NOW();
"@

$sql | docker exec -i $ContainerName psql -U $DbUser -d $DbName 2>&1
if ($LASTEXITCODE -ne 0) { Write-Host "FEHLER: Insert fehlgeschlagen." -ForegroundColor Red; exit 1 }

# Admin-Rolle setzen
Write-Host "[3/3] Admin-Rolle setzen..." -ForegroundColor Yellow
$rolleSql = @"
INSERT INTO shared.benutzer_projekt_rollen (id, benutzer_id, mandant_slug, rolle, erstellt_am, geaendert_am, erstellt_von)
SELECT gen_random_uuid(), b.id, 'tlbv', 'admin', NOW(), NOW(), 'seed-admin'
FROM shared.benutzer b
WHERE b.email = '$email'
AND NOT EXISTS (
    SELECT 1 FROM shared.benutzer_projekt_rollen r
    WHERE r.benutzer_id = b.id AND r.rolle = 'admin'
);
"@

$rolleSql | docker exec -i $ContainerName psql -U $DbUser -d $DbName 2>&1
Write-Host "  Admin '$email' angelegt." -ForegroundColor Green