# BauPilot — NTV-Nachverknuepfung (143 unverlinkte NTVs)
# Problem: NTVs ab Nr. 201 haben ein abweichendes Dateinamenformat,
# das der Import-Regex nicht erkannt hat.
#
# Dieses Skript:
# 1. Findet alle NTV-Dokumente ohne Vorgangszuordnung
# 2. Extrahiert die NTV-Nummer aus dem Dateinamen (mehrere Muster)
# 3. Sucht den passenden NT-Vorgang
# 4. Erstellt die Verknuepfung in vorgang_dokumente

param(
    [string]$ApiUrl = "http://localhost:8110/api/v1",
    [string]$Email = "svc-automation@baupilot.de",
    [string]$Passwort = $env:BAUPILOT_SVC_PW,
    [string]$Projekt = "FLI",
    [switch]$DryRun
)

# --- Admin-PW aufloesen (KEIN Klartext im Skript — Repo ist public) ---
# Reihenfolge: -Passwort > $env:BAUPILOT_SVC_PW > .env (gitignored).
if (-not $Passwort) {
    $envDatei = Join-Path $PSScriptRoot "..\.env"
    if (Test-Path $envDatei) {
        $treffer = Select-String -Path $envDatei -Pattern '^\s*BAUPILOT_SVC_PW\s*=\s*(.+)$' | Select-Object -First 1
        if ($treffer) { $Passwort = $treffer.Matches[0].Groups[1].Value.Trim() }
    }
}
if (-not $Passwort) {
    Write-Error "Admin-PW fehlt: `$env:BAUPILOT_SVC_PW setzen, -Passwort uebergeben, oder BAUPILOT_SVC_PW in .env pflegen."
    exit 1
}

$ErrorActionPreference = "Stop"
Write-Host "=== NTV-Nachverknuepfung ===" -ForegroundColor Cyan
if ($DryRun) { Write-Host "DRY RUN - Keine Aenderungen" -ForegroundColor Yellow }

# --- Login ---
$loginBody = @{ email = $Email; passwort = $Passwort } | ConvertTo-Json
$login = Invoke-RestMethod -Uri "$ApiUrl/auth/login" -Method Post -ContentType "application/json" -Body $loginBody
$headers = @{ Authorization = "Bearer $($login.access_token)" }
Write-Host "Login OK." -ForegroundColor Green

# --- NT-Vorgaenge laden ---
$ntResult = Invoke-RestMethod -Uri "$ApiUrl/vorgaenge/?projekt=$Projekt&typ=nachtrag&limit=500" -Headers $headers
$ntLookup = @{}
foreach ($nt in $ntResult.vorgaenge) {
    if ($nt.nummer -match '(\d{3})') {
        $ntLookup[$Matches[1]] = $nt.id
    }
}
Write-Host "$($ntLookup.Count) NT-Vorgaenge im Lookup." -ForegroundColor Green

# --- Alle Dokumente laden ---
$dokResult = Invoke-RestMethod -Uri "$ApiUrl/dokumente/?projekt=$Projekt&kategorie=vertrag&limit=1000" -Headers $headers
$alleDocs = $dokResult.dokumente
Write-Host "$($alleDocs.Count) Vertragsdokumente geladen." -ForegroundColor Green

# --- NTV-Nummern-Extraktion: Mehrere Muster ---
function Get-NtvNummer {
    param([string]$Dateiname)

    # Muster 1: "201.NTV LV 204..." oder "201. NTV..."
    if ($Dateiname -match '^(\d+)[\.\s]*NTV') { return $Matches[1].PadLeft(3, '0') }

    # Muster 2: "NTV_201_..." oder "NTV 201..."
    if ($Dateiname -match 'NTV[\s_]+(\d+)') { return $Matches[1].PadLeft(3, '0') }

    # Muster 3: "NTV-201..." oder "NTV201..."
    if ($Dateiname -match 'NTV-?(\d+)') { return $Matches[1].PadLeft(3, '0') }

    # Muster 4: Nur Nummern am Anfang (Fallback)
    if ($Dateiname -match '^(\d{3})[\s_\-]') { return $Matches[1] }

    return $null
}

# --- Verknuepfung herstellen ---
$linked = 0; $noNt = 0; $noNr = 0; $alreadyLinked = 0

foreach ($doc in $alleDocs) {
    $nr = Get-NtvNummer -Dateiname $doc.dateiname

    if (-not $nr) {
        $noNr++
        continue
    }

    $ntId = $ntLookup[$nr]
    if (-not $ntId) {
        Write-Host "  SKIP: $($doc.dateiname) - Kein NT-$nr vorhanden" -ForegroundColor DarkYellow
        $noNt++
        continue
    }

    # Pruefen ob schon verknuepft
    # (vereinfacht: wir versuchen die Verknuepfung, API liefert Fehler bei Duplikat)
    if (-not $DryRun) {
        try {
            Invoke-RestMethod -Uri "$ApiUrl/dokumente/$($doc.id)/vorgang/$ntId" `
                -Method POST -Headers $headers -ContentType "application/json"
            Write-Host "  LINKED: $($doc.dateiname) -> NT-$nr" -ForegroundColor Green
            $linked++
        } catch {
            $msg = $_.ErrorDetails.Message
            if ($msg -match "bereits|duplicate|exists") {
                $alreadyLinked++
            } else {
                Write-Host "  FEHLER: $($doc.dateiname) - $_" -ForegroundColor Red
            }
        }
    } else {
        Write-Host "  WUERDE LINKEN: $($doc.dateiname) -> NT-$nr" -ForegroundColor Cyan
        $linked++
    }
}

Write-Host "`n=== Ergebnis ===" -ForegroundColor Cyan
Write-Host "Neu verknuepft:        $linked" -ForegroundColor Green
Write-Host "Bereits verknuepft:    $alreadyLinked" -ForegroundColor Gray
Write-Host "Kein NT gefunden:      $noNt" -ForegroundColor Yellow
Write-Host "Nummer nicht erkannt:  $noNr" -ForegroundColor Yellow
