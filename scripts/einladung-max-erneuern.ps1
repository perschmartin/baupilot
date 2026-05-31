# BauPilot — Maximilian Muellers Einladung erneuern
# Seine alte Einladung ist seit 11.05.2026 abgelaufen.
# HINWEIS: Max' echte E-Mail-Adresse muss eingesetzt werden.

$ErrorActionPreference = "Stop"

Write-Host "=== Max-Einladung erneuern ===" -ForegroundColor Cyan

# 1. Login
Write-Host "1. Admin-Login..." -ForegroundColor Yellow
$loginBody = @{
    email = "admin@baupilot.de"
    passwort = "BauPilot-Erststart-2026!"
} | ConvertTo-Json

$login = Invoke-RestMethod -Uri "http://localhost:8110/api/v1/auth/login" `
    -Method POST -ContentType "application/json" -Body $loginBody

$token = $login.access_token
Write-Host "   Token erhalten." -ForegroundColor Green

# 2. Einladung erstellen
Write-Host "2. Einladung erstellen..." -ForegroundColor Yellow

# HIER Max' echte E-Mail eintragen:
$maxEmail = "BITTE_ECHTE_EMAIL_EINSETZEN"

if ($maxEmail -eq "BITTE_ECHTE_EMAIL_EINSETZEN") {
    Write-Host "   ABBRUCH: Bitte Max' E-Mail in Zeile 22 eintragen!" -ForegroundColor Red
    exit 1
}

$einladungBody = @{
    email        = $maxEmail
    rolle        = "objektueberwacher"
    mandant_slug = "tlbv"
    projekt_kurz = "FLI"
} | ConvertTo-Json

$result = Invoke-RestMethod -Uri "http://localhost:8110/api/v1/auth/einladung" `
    -Method POST -ContentType "application/json" `
    -Headers @{Authorization = "Bearer $token"} `
    -Body $einladungBody

Write-Host "   Einladung erstellt!" -ForegroundColor Green
Write-Host "   Token: $($result.token)" -ForegroundColor White
Write-Host "   Gueltig bis: $($result.gueltig_bis)" -ForegroundColor White
Write-Host ""
Write-Host "   Max kann sich damit registrieren:" -ForegroundColor Cyan
Write-Host "   https://fli.baupilot.work -> Registrieren -> Token eingeben" -ForegroundColor Gray
