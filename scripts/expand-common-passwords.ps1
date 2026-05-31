# BauPilot — common_passwords.txt auf 10.000 erweitern
# Vorbereitet: 30.05.2026 (Nachtsitzung)
# Quelle: SecLists 10k-most-common.txt (MIT License)
#
# HINWEIS: Dieses Skript aendert nur die Datei auf der Festplatte.
# Der laufende API-Container muss danach neu gebaut werden,
# damit die neue Liste geladen wird.

$ErrorActionPreference = "Stop"

$zielPfad = "C:\SPARK\spark-baupilot\api\data\common_passwords.txt"
$backupPfad = "C:\SPARK\spark-baupilot\backup-2026-05-30\common_passwords_original.txt"
$tempPfad = "$env:TEMP\10k-passwords-raw.txt"

# 1. Backup der aktuellen Datei
Write-Host "1. Backup der aktuellen common_passwords.txt..." -ForegroundColor Cyan
Copy-Item $zielPfad $backupPfad -Force
Write-Host "   Backup: $backupPfad"

# 2. Download von GitHub
Write-Host "2. Download SecLists 10k-most-common.txt..." -ForegroundColor Cyan
$url = "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/Common-Credentials/10k-most-common.txt"
Invoke-WebRequest -Uri $url -OutFile $tempPfad
$rawCount = (Get-Content $tempPfad).Count
Write-Host "   $rawCount Eintraege heruntergeladen."

# 3. Verarbeitung: Kleinbuchstaben, Sortierung, Deduplizierung, Header
Write-Host "3. Verarbeitung (lowercase, sort, deduplizieren)..." -ForegroundColor Cyan
$header = @(
    "# BauPilot — Haeufig kompromittierte Passwoerter"
    "# Quelle: SecLists 10k-most-common.txt (danielmiessler/SecLists, MIT License)"
    "# Stand: $(Get-Date -Format 'dd.MM.yyyy')"
    "# Format: ein Passwort pro Zeile, Kleinbuchstaben"
)

$passwords = Get-Content $tempPfad |
    ForEach-Object { $_.Trim().ToLower() } |
    Where-Object { $_ -and -not $_.StartsWith("#") } |
    Sort-Object -Unique

$finalContent = ($header + $passwords) -join "`n"
[System.IO.File]::WriteAllText($zielPfad, $finalContent, [System.Text.UTF8Encoding]::new($false))

$finalCount = $passwords.Count
Write-Host "   $finalCount eindeutige Passwoerter geschrieben." -ForegroundColor Green

# 4. Validierung
Write-Host "4. Validierung..." -ForegroundColor Cyan
$check = Get-Content $zielPfad
$dataLines = ($check | Where-Object { $_ -and -not $_.StartsWith("#") }).Count
Write-Host "   Datei: $zielPfad"
Write-Host "   Zeilen gesamt: $($check.Count)"
Write-Host "   Passwoerter: $dataLines"

if ($dataLines -ge 9500) {
    Write-Host "`nERFOLG: common_passwords.txt auf $dataLines Eintraege erweitert." -ForegroundColor Green
} else {
    Write-Host "`nWARNUNG: Nur $dataLines Eintraege — weniger als erwartet." -ForegroundColor Yellow
}

# 5. Hinweis
Write-Host "`nNaechster Schritt:" -ForegroundColor Yellow
Write-Host "  docker compose -f docker-compose.services.yaml build api"
Write-Host "  docker compose -f docker-compose.services.yaml up -d api"
Write-Host "  docker exec baupilot-api pytest /app/tests/ -v"

# Aufraeumen
Remove-Item $tempPfad -ErrorAction SilentlyContinue
