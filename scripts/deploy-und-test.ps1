# BauPilot — Wenn-Du-Zurueck-Bist Checkliste
# 31.05.2026
# Alle Code-Aenderungen sind gemacht. Dieser Block deployt und testet alles.

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " BauPilot — Deploy + Test (31.05.2026)" -ForegroundColor Cyan
Write-Host " Code-Aenderungen: health.py, requirements.txt" -ForegroundColor Cyan
Write-Host " Neue Dateien: common_passwords.txt (10k)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# --- 1. API-Container neu bauen (health.py + pytest + 10k-Passwoerter) ---
Write-Host "`n[1/5] API-Container bauen..." -ForegroundColor Yellow
docker compose -f docker-compose.services.yaml build api
if ($LASTEXITCODE -ne 0) { Write-Host "BUILD FEHLGESCHLAGEN" -ForegroundColor Red; exit 1 }
Write-Host "   Build OK." -ForegroundColor Green

# --- 2. Container starten ---
Write-Host "`n[2/5] Container starten..." -ForegroundColor Yellow
docker compose -f docker-compose.services.yaml up -d api
Start-Sleep -Seconds 5

# --- 3. Health-Check ---
Write-Host "`n[3/5] Health-Check..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8110/health" -TimeoutSec 10
    Write-Host "   API: $($health.status), Version: $($health.version), DB: $($health.database)" -ForegroundColor Green
} catch {
    Write-Host "   API NICHT ERREICHBAR — Logs pruefen: docker logs baupilot-api --tail 30" -ForegroundColor Red
    exit 1
}

# --- 4. Tests im Container ---
Write-Host "`n[4/5] Tests im Container..." -ForegroundColor Yellow
docker exec baupilot-api python -m pytest /app/tests/ -v --tb=short
if ($LASTEXITCODE -eq 0) {
    Write-Host "   Container-Tests: BESTANDEN" -ForegroundColor Green
} else {
    Write-Host "   Container-Tests: FEHLGESCHLAGEN" -ForegroundColor Red
    exit 1
}

# --- 5. Frontend-Check ---
Write-Host "`n[5/5] Frontend-Check..." -ForegroundColor Yellow
try {
    $fe = Invoke-WebRequest -Uri "http://localhost:8091" -TimeoutSec 5 -UseBasicParsing
    Write-Host "   Frontend: HTTP $($fe.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "   Frontend nicht erreichbar" -ForegroundColor Yellow
}

# --- Zusammenfassung ---
Write-Host "`n============================================" -ForegroundColor Green
Write-Host " ALLES OK — Naechste Schritte:" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  git add -A" -ForegroundColor White
Write-Host "  git commit -m 'chore: CLAUDE.md, Konzept v0.5, 10k Passwoerter, health v0.2.0, pytest, Skripte'" -ForegroundColor White
Write-Host ""
Write-Host "  Optional:" -ForegroundColor Gray
Write-Host "  .\scripts\einladung-max-erneuern.ps1    (Max' E-Mail eintragen!)" -ForegroundColor Gray
Write-Host "  .\scripts\ntv-nachverknuepfung.ps1 -DryRun  (erst Trockenlauf)" -ForegroundColor Gray
