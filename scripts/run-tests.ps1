# BauPilot — Tests ausfuehren
# Ausfuehrung: .\scripts\run-tests.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== BauPilot — Tests ===" -ForegroundColor Cyan

Push-Location (Join-Path $PSScriptRoot ".." "api")

try {
    python -m pytest tests/ -v --tb=short
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "Alle Tests bestanden." -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "Tests fehlgeschlagen." -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "FEHLER: pytest konnte nicht ausgefuehrt werden." -ForegroundColor Red
    Write-Host "Bitte sicherstellen: pip install pytest httpx" -ForegroundColor Yellow
    exit 1
} finally {
    Pop-Location
}
