<#
.SYNOPSIS
    BauPilot AP 1.1 Auth — Komplettes Deployment
.DESCRIPTION
    Fuehrt alle Schritte aus: ZIP entpacken, .env erweitern,
    Migration 002, Container-Rebuild, Admin-Seed, Tests.

    Ausfuehren aus: C:\SPARK\spark-baupilot\
#>

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = "C:\SPARK\spark-baupilot"
$ZipPath = "$env:USERPROFILE\Downloads\baupilot-auth-ap11.zip"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  BauPilot AP 1.1 — Auth Deployment" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# =================================================================
# SCHRITT 1: ZIP entpacken
# =================================================================
Write-Host "[1/9] ZIP entpacken..." -ForegroundColor Yellow

if (-not (Test-Path $ZipPath)) {
    Write-Host "  ZIP nicht gefunden unter $ZipPath" -ForegroundColor Red
    Write-Host "  Bitte Pfad anpassen oder Datei dorthin kopieren." -ForegroundColor Red
    exit 1
}

Unblock-File -Path $ZipPath
Expand-Archive -Path $ZipPath -DestinationPath $Root -Force
Write-Host "  Entpackt nach $Root" -ForegroundColor Green

# =================================================================
# SCHRITT 2: Secrets generieren und .env erweitern
# =================================================================
Write-Host "`n[2/9] .env erweitern..." -ForegroundColor Yellow

$envFile = Join-Path $Root ".env"
$envContent = Get-Content $envFile -Raw -Encoding utf8

if ($envContent -notmatch "BAUPILOT_JWT_SECRET") {
    $jwtSecret = python -c "import secrets; print(secrets.token_hex(32))"
    $totpKey   = python -c "import secrets; print(secrets.token_hex(32))"

    $authBlock = @"

# === Auth (AP 1.1) ===
BAUPILOT_JWT_SECRET=$jwtSecret
BAUPILOT_JWT_ACCESS_MINUTES=15
BAUPILOT_JWT_REFRESH_DAYS=7
BAUPILOT_TOTP_KEY=$totpKey
BAUPILOT_PASSWORT_MIN_LAENGE=12

# === Admin-Seed ===
BAUPILOT_ADMIN_EMAIL=admin@tlbv.de
BAUPILOT_ADMIN_VORNAME=Admin
BAUPILOT_ADMIN_NACHNAME=BauPilot
BAUPILOT_ADMIN_INITIAL_PW=BauPilot-Erststart-2026!
"@

    Add-Content -Path $envFile -Value $authBlock -Encoding utf8NoBOM -NoNewline:$false
    Write-Host "  JWT_SECRET und TOTP_KEY generiert, .env erweitert." -ForegroundColor Green
    Write-Host "  WICHTIG: Initial-Passwort nach erstem Login aendern!" -ForegroundColor Yellow
} else {
    Write-Host "  Auth-Variablen bereits vorhanden, uebersprungen." -ForegroundColor Green
}

# =================================================================
# SCHRITT 3: requirements.txt erweitern
# =================================================================
Write-Host "`n[3/9] requirements.txt erweitern..." -ForegroundColor Yellow

$reqFile = Join-Path $Root "requirements.txt"
$reqContent = if (Test-Path $reqFile) { Get-Content $reqFile -Raw -Encoding utf8 } else { "" }

$neuePakete = @(
    "argon2-cffi>=23.1.0",
    "PyJWT>=2.8.0",
    "pyotp>=2.9.0",
    "qrcode[pil]>=7.4.0",
    "cryptography>=42.0.0",
    "pydantic[email]>=2.0.0"
)

$hinzugefuegt = 0
foreach ($paket in $neuePakete) {
    $name = ($paket -split "[>=<\[]")[0]
    if ($reqContent -notmatch [regex]::Escape($name)) {
        Add-Content -Path $reqFile -Value $paket -Encoding utf8NoBOM
        $hinzugefuegt++
    }
}
Write-Host "  $hinzugefuegt Pakete hinzugefuegt." -ForegroundColor Green

# =================================================================
# SCHRITT 4: Migration 002
# =================================================================
Write-Host "`n[4/9] Migration 002 ausfuehren..." -ForegroundColor Yellow

& "$Root\scripts\run-migration-002.ps1"

# =================================================================
# SCHRITT 5: API-Container neu bauen
# =================================================================
Write-Host "`n[5/9] API-Container rebuilden..." -ForegroundColor Yellow

Push-Location $Root
docker compose -f docker-compose.services.yaml build api
docker compose -f docker-compose.services.yaml up -d
Pop-Location

Write-Host "  API-Container laeuft." -ForegroundColor Green

# =================================================================
# SCHRITT 6: Warten bis API bereit
# =================================================================
Write-Host "`n[6/9] Warte auf API..." -ForegroundColor Yellow

$maxRetries = 15
$ready = $false
for ($i = 1; $i -le $maxRetries; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8110/health" -TimeoutSec 3
        $ready = $true
        break
    } catch {
        Write-Host "  Versuch $i/$maxRetries..." -ForegroundColor Gray
        Start-Sleep -Seconds 2
    }
}

if (-not $ready) {
    Write-Host "  API nicht erreichbar nach $maxRetries Versuchen." -ForegroundColor Red
    Write-Host "  Pruefe: docker compose -f docker-compose.services.yaml logs api" -ForegroundColor Yellow
    exit 1
}
Write-Host "  API bereit." -ForegroundColor Green

# =================================================================
# SCHRITT 7: Admin-Seed
# =================================================================
Write-Host "`n[7/9] Admin-Seed..." -ForegroundColor Yellow

& "$Root\scripts\seed-admin.ps1"

# =================================================================
# SCHRITT 8: Tests
# =================================================================
Write-Host "`n[8/9] Tests ausfuehren..." -ForegroundColor Yellow

& "$Root\scripts\run-tests-auth.ps1"

# =================================================================
# SCHRITT 9: Rauchtest
# =================================================================
Write-Host "`n[9/9] Rauchtest..." -ForegroundColor Yellow

try {
    $loginBody = @{
        email    = "admin@tlbv.de"
        passwort = "BauPilot-Erststart-2026!"
    } | ConvertTo-Json

    $login = Invoke-RestMethod -Uri "http://localhost:8110/api/v1/auth/login" `
        -Method Post -ContentType "application/json" -Body $loginBody

    if ($login.access_token) {
        Write-Host "  Login erfolgreich. Token erhalten." -ForegroundColor Green

        $headers = @{ Authorization = "Bearer $($login.access_token)" }
        $me = Invoke-RestMethod -Uri "http://localhost:8110/api/v1/auth/me" -Headers $headers
        Write-Host "  Profil: $($me.vorname) $($me.nachname) ($($me.email))" -ForegroundColor Green
        Write-Host "  Mandant: $($me.mandant.name)" -ForegroundColor Green
    }
    if ($login.muss_passwort_aendern) {
        Write-Host "  Hinweis: Passwort muss beim naechsten Login geaendert werden." -ForegroundColor Yellow
    }
} catch {
    Write-Host "  Rauchtest fehlgeschlagen: $_" -ForegroundColor Red
    Write-Host "  Das kann normal sein, wenn main.py den Auth-Router noch nicht registriert." -ForegroundColor Yellow
    Write-Host "  Siehe README.md: Integration in main.py" -ForegroundColor Yellow
}

# =================================================================
# ERGEBNIS
# =================================================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Deployment abgeschlossen." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Naechster Schritt: Auth-Router in main.py registrieren:" -ForegroundColor Yellow
Write-Host ""
Write-Host '  from api.auth import auth_router' -ForegroundColor White
Write-Host '  import api.auth.dependencies as auth_deps' -ForegroundColor White
Write-Host '  auth_deps.get_db = real_get_db' -ForegroundColor White
Write-Host '  auth_deps.get_jwt_secret = lambda: get_settings().jwt_secret' -ForegroundColor White
Write-Host '  auth_deps.get_totp_key = lambda: get_settings().totp_key' -ForegroundColor White
Write-Host '  app.include_router(auth_router)' -ForegroundColor White
Write-Host ""
