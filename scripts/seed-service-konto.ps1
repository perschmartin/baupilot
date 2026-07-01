# ============================================================
# BauPilot — Service-Konto seeden (svc-automation@baupilot.de)
# ------------------------------------------------------------
# Legt das Maschinen-Konto fuer die headless-Nachtlauf-Skripte an:
#   ist_dienstkonto=TRUE  -> Login ohne TOTP (Maschine kann kein 2FA)
#   Rolle objektueberwacher @ tlbv/FLI (nicht-Admin, least privilege)
# PW wird in .env (BAUPILOT_SVC_PW) gehalten, nie im Code/Output.
# Idempotent (ON CONFLICT (email) DO UPDATE).
#
# VORAUSSETZUNG: Migration 009 (ist_dienstkonto) ausgefuehrt.
# Aufruf:  pwsh -NoProfile -File scripts\seed-service-konto.ps1
# ============================================================
param(
    [string]$Container   = "baupilot-postgres",
    [string]$DbName      = "baupilot",
    [string]$DbUser      = "baupilot",
    [string]$Rolle       = "objektueberwacher",
    [string]$MandantSlug = "tlbv",
    [string]$ProjektKurz = "FLI"
)
$ErrorActionPreference = "Stop"

$envFile = Join-Path $PSScriptRoot "..\.env"
if (-not (Test-Path $envFile)) { Write-Error ".env nicht gefunden: $envFile"; exit 1 }

Write-Host "=== BauPilot Service-Konto-Seed ===" -ForegroundColor Cyan

# --- .env einlesen ---
$lines = Get-Content $envFile
function Get-EnvVal([string]$name) {
    foreach ($l in $lines) { if ($l -match "^\s*$name\s*=\s*(.+)$") { return $Matches[1].Trim() } }
    return $null
}
$email = Get-EnvVal 'BAUPILOT_SVC_EMAIL'; if (-not $email) { $email = "svc-automation@baupilot.de" }
$svcPw = Get-EnvVal 'BAUPILOT_SVC_PW'

# --- PW generieren, falls noch nicht in .env (krypto-stark, alphanumerisch) ---
if (-not $svcPw) {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    $svcPw = ([Convert]::ToBase64String($bytes) -replace '[+/=]', '')
    if (-not (Get-EnvVal 'BAUPILOT_SVC_EMAIL')) { $lines += "BAUPILOT_SVC_EMAIL=$email" }
    $lines += "BAUPILOT_SVC_PW=$svcPw"
    Set-Content -Path $envFile -Value $lines -Encoding utf8
    Write-Host "  Neues Service-PW generiert und in .env gesetzt (nicht angezeigt)." -ForegroundColor Green
} else {
    Write-Host "  BAUPILOT_SVC_PW bereits in .env vorhanden - wiederverwendet." -ForegroundColor Green
}
Write-Host "  Konto: $email  Rolle: $Rolle @ $MandantSlug/$ProjektKurz" -ForegroundColor Gray

# --- PW hashen (Argon2id, gleiche Parameter wie die App) ---
Write-Host "[1/3] Hashe Passwort..." -ForegroundColor Yellow
$pyCmd = "from argon2 import PasswordHasher; ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16); print(ph.hash('$($svcPw.Replace("'","''"))'))"
$pwHash = python -c $pyCmd 2>&1
if ($LASTEXITCODE -ne 0) { Write-Host "FEHLER: argon2-cffi installiert?" -ForegroundColor Red; exit 1 }
$pwHash = ($pwHash | Out-String).Trim()
$escapedHash = $pwHash.Replace("'", "''")

# --- Service-Konto upsert (ist_dienstkonto=TRUE, kein TOTP, kein PW-Wechselzwang) ---
Write-Host "[2/3] Service-Konto upsert..." -ForegroundColor Yellow
$sql = @"
INSERT INTO shared.benutzer
  (id, email, vorname, nachname, passwort_hash, aktiv, muss_passwort_aendern, totp_aktiviert, ist_dienstkonto, erstellt_am, geaendert_am, erstellt_von)
VALUES
  (gen_random_uuid(), '$email', 'Service', 'Automation', '$escapedHash', TRUE, FALSE, FALSE, TRUE, NOW(), NOW(), 'seed-service-konto')
ON CONFLICT (email) DO UPDATE SET
    passwort_hash         = EXCLUDED.passwort_hash,
    ist_dienstkonto       = TRUE,
    totp_aktiviert        = FALSE,
    muss_passwort_aendern = FALSE,
    aktiv                 = TRUE,
    geaendert_am          = NOW();
"@
$sql | docker exec -i $Container psql -U $DbUser -d $DbName -v ON_ERROR_STOP=1
if ($LASTEXITCODE -ne 0) { Write-Host "FEHLER: Upsert fehlgeschlagen (Migration 009 ausgefuehrt?)." -ForegroundColor Red; exit 1 }

# --- Rolle setzen (projekt_kurz ist NOT NULL — anders als seed-admin!) ---
Write-Host "[3/3] Rolle setzen ($Rolle @ $MandantSlug/$ProjektKurz)..." -ForegroundColor Yellow
$rolleSql = @"
INSERT INTO shared.benutzer_projekt_rollen
  (id, benutzer_id, mandant_slug, projekt_kurz, rolle, erstellt_am, geaendert_am, erstellt_von)
SELECT gen_random_uuid(), b.id, '$MandantSlug', '$ProjektKurz', '$Rolle'::benutzerrolle, NOW(), NOW(), 'seed-service-konto'
FROM shared.benutzer b
WHERE b.email = '$email'
AND NOT EXISTS (
    SELECT 1 FROM shared.benutzer_projekt_rollen r
    WHERE r.benutzer_id = b.id AND r.mandant_slug = '$MandantSlug'
      AND r.projekt_kurz = '$ProjektKurz' AND r.rolle = '$Rolle'::benutzerrolle
);
"@
$rolleSql | docker exec -i $Container psql -U $DbUser -d $DbName -v ON_ERROR_STOP=1
if ($LASTEXITCODE -ne 0) { Write-Host "FEHLER: Rollen-Insert fehlgeschlagen." -ForegroundColor Red; exit 1 }

Write-Host "`nOK: Service-Konto '$email' bereit (ist_dienstkonto=TRUE, $Rolle @ $MandantSlug/$ProjektKurz)." -ForegroundColor Green
Write-Host "PW steht in .env (BAUPILOT_SVC_PW), nicht angezeigt. Die 4 Nachtlauf-Skripte lesen es von dort." -ForegroundColor Cyan
