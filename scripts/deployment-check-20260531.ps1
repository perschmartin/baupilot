# BauPilot — Deployment-Checkliste 31.05.2026
# Alle Schritte nacheinander ausfuehren.
# Abbrechen bei ROT, weiter bei GRUEN.

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " BauPilot — Deployment-Checkliste" -ForegroundColor Cyan
Write-Host " Stand: 31.05.2026" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# ============================================================
# 1. API Health-Check
# ============================================================
Write-Host "`n--- 1/8 API Health-Check ---" -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8110/health" -TimeoutSec 5
    Write-Host "   API laeuft: $($health | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host "   API nicht erreichbar! Container pruefen:" -ForegroundColor Red
    Write-Host "   docker compose -f docker-compose.services.yaml up -d api" -ForegroundColor Yellow
    Write-Host "   Dann Skript erneut starten." -ForegroundColor Yellow
    exit 1
}

# ============================================================
# 2. Tests lokal ausfuehren (pytest ist nicht im Container)
# ============================================================
Write-Host "`n--- 2/8 Tests lokal ---" -ForegroundColor Yellow
Push-Location (Join-Path $PSScriptRoot ".." "api")
try {
    $testResult = python -m pytest tests/ -v --tb=short 2>&1
    $testResult | ForEach-Object { Write-Host "   $_" }
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   Tests: BESTANDEN" -ForegroundColor Green
    } else {
        Write-Host "   Tests: FEHLGESCHLAGEN — bitte pruefen" -ForegroundColor Red
        Pop-Location
        exit 1
    }
} catch {
    Write-Host "   pytest nicht verfuegbar — ueberspringe (pip install pytest httpx)" -ForegroundColor Yellow
}
Pop-Location

# ============================================================
# 3. Common-Passwords Validierung
# ============================================================
Write-Host "`n--- 3/8 Common-Passwords pruefen ---" -ForegroundColor Yellow
$pwFile = Join-Path $PSScriptRoot ".." "api" "data" "common_passwords.txt"
$pwLines = (Get-Content $pwFile | Where-Object { $_ -and -not $_.StartsWith("#") }).Count
if ($pwLines -ge 9500) {
    Write-Host "   common_passwords.txt: $pwLines Eintraege (Soll: 10.000)" -ForegroundColor Green
} else {
    Write-Host "   common_passwords.txt: nur $pwLines Eintraege — .\scripts\expand-common-passwords.ps1 noetig" -ForegroundColor Red
}

# ============================================================
# 4. Frontend erreichbar?
# ============================================================
Write-Host "`n--- 4/8 Frontend-Check ---" -ForegroundColor Yellow
try {
    $fe = Invoke-WebRequest -Uri "http://localhost:8091" -TimeoutSec 5 -UseBasicParsing
    Write-Host "   Frontend erreichbar: HTTP $($fe.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "   Frontend nicht erreichbar — Container pruefen" -ForegroundColor Red
}

# ============================================================
# 5. Konzeptpapier v0.5 pruefen
# ============================================================
Write-Host "`n--- 5/8 Konzeptpapier v0.5 ---" -ForegroundColor Yellow
$konzeptPfad = "C:\Tools\baupilot.work\konzept\intern\BauPilot-Konzept-v0_5.md"
if (Test-Path $konzeptPfad) {
    $k = Get-Content $konzeptPfad -Raw
    $checks = @(
        @{Name="Version 0.5"; OK=$k.Contains("**Version:** 0.5")},
        @{Name="13.155"; OK=$k.Contains("13.155")},
        @{Name="Alembic 008"; OK=$k.Contains("Alembic 008")},
        @{Name="BKI §4.14"; OK=$k.Contains("### 4.14 BKI")},
        @{Name="LV §4.13"; OK=$k.Contains("### 4.13 LV-Extraktion")}
    )
    foreach ($c in $checks) {
        $color = if ($c.OK) {"Green"} else {"Red"}
        $mark = if ($c.OK) {"PASS"} else {"FAIL"}
        Write-Host "   $mark : $($c.Name)" -ForegroundColor $color
    }
} else {
    Write-Host "   FEHLT — .\scripts\apply-konzept-delta-v05.ps1 ausfuehren" -ForegroundColor Red
}

# ============================================================
# 6. Projektanweisung v0.5 pruefen
# ============================================================
Write-Host "`n--- 6/8 Projektanweisung v0.5 ---" -ForegroundColor Yellow
$paPfad = "C:\Tools\baupilot.work\konzept\intern\BauPilot-Projektanweisung-v0_5.md"
if (Test-Path $paPfad) {
    Write-Host "   Vorhanden" -ForegroundColor Green
} else {
    Write-Host "   FEHLT" -ForegroundColor Red
}

# ============================================================
# 7. Obsidian-Kopie
# ============================================================
Write-Host "`n--- 7/8 Obsidian-Kopie ---" -ForegroundColor Yellow
$obsidianZiel = "P:\Obsidian\Martin\03_Projekte\Baupilot"
$filesToCopy = @(
    "C:\Tools\baupilot.work\konzept\intern\BauPilot-Handover-2026-05-30.md"
)
foreach ($f in $filesToCopy) {
    $name = Split-Path $f -Leaf
    try {
        Copy-Item $f (Join-Path $obsidianZiel $name) -Force
        Write-Host "   Kopiert: $name" -ForegroundColor Green
    } catch {
        Write-Host "   FEHLER bei $name : $_" -ForegroundColor Red
    }
}

# ============================================================
# 8. Zusammenfassung
# ============================================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host " Naechste manuelle Schritte:" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. Git Commit:" -ForegroundColor White
Write-Host "     git add CLAUDE.md api/data/common_passwords.txt scripts/" -ForegroundColor Gray
Write-Host "     git commit -m 'chore: CLAUDE.md aktualisiert, 10k Passwoerter, Deployment-Skripte'" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Max Einladung erneuern (abgelaufen 11.05.)" -ForegroundColor White
Write-Host ""
Write-Host "  3. B-013 Netzplan-Technologie entscheiden" -ForegroundColor White
Write-Host "     Vorlage: konzept\intern\BP-V-18-B-013-Netzplan-Technologie.md" -ForegroundColor Gray
Write-Host ""
