<#
.SYNOPSIS
    Fuehrt die Auth-Tests aus.
.DESCRIPTION
    Startet pytest fuer die Auth-Unit-Tests.
    Kann lokal oder im Docker-Container ausgefuehrt werden.
#>

$ErrorActionPreference = "Stop"

Write-Host "=== BauPilot Auth-Tests ===" -ForegroundColor Cyan

# Lokal ausfuehren
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "Fuehre pytest aus..." -ForegroundColor Yellow
Push-Location $ProjectRoot
try {
    python -m pytest tests/test_auth_unit.py -v --tb=short
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`nTests fehlgeschlagen." -ForegroundColor Red
        exit 1
    }
    Write-Host "`nAlle Tests bestanden." -ForegroundColor Green
} finally {
    Pop-Location
}
