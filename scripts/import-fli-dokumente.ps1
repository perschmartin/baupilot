# ============================================================
# BauPilot — MK/NTV-Dokumente importieren (AP 1.6 Vorbereitung)
# Laedt Mehrkostenforderungen und Nachtragsvereinbarungen hoch
# und verknuepft sie mit den bestehenden NT-Vorgaengen.
# ============================================================

param(
    [string]$BasePfad = "P:\Datenübergabe FLI",
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

Write-Host "=== BauPilot MK/NTV-Import ===" -ForegroundColor Cyan
if ($DryRun) { Write-Host "DRY RUN - Keine Aenderungen" -ForegroundColor Yellow }

# --- Login ---
Write-Host "`nLogin..." -ForegroundColor Yellow
try {
    $loginBody = @{ email = $Email; passwort = $Passwort } | ConvertTo-Json
    $loginResult = Invoke-RestMethod -Uri "$ApiUrl/auth/login" -Method Post -ContentType "application/json" -Body $loginBody
    $token = $loginResult.access_token
    Write-Host "Login erfolgreich." -ForegroundColor Green
} catch {
    Write-Host "Login fehlgeschlagen: $_" -ForegroundColor Red
    exit 1
}

$headers = @{ Authorization = "Bearer $token" }

# --- Bestehende NT-Vorgaenge laden ---
Write-Host "Lade NT-Vorgaenge..." -ForegroundColor Yellow
try {
    $ntResult = Invoke-RestMethod -Uri "$ApiUrl/vorgaenge/?projekt=$Projekt&typ=nachtrag&limit=500" -Headers $headers
    $ntVorgaenge = $ntResult.vorgaenge
    Write-Host "$($ntVorgaenge.Count) NT-Vorgaenge gefunden." -ForegroundColor Green
} catch {
    Write-Host "Fehler beim Laden der Vorgaenge: $_" -ForegroundColor Red
    exit 1
}

# NT-Lookup: Nummer -> ID (z.B. "NT-001" -> UUID)
$ntLookup = @{}
foreach ($nt in $ntVorgaenge) {
    # Nummer extrahieren: "NT-001" -> "001"
    if ($nt.nummer -match '(\d{3})') {
        $ntLookup[$Matches[1]] = $nt.id
    }
}
Write-Host "$($ntLookup.Count) NT-Nummern im Lookup." -ForegroundColor Green

# --- Upload-Funktion ---
function Upload-Dokument {
    param(
        [string]$Dateipfad,
        [string]$Kategorie,
        [string]$VorgangId,
        [string]$Beschreibung
    )

    $dateiname = Split-Path $Dateipfad -Leaf

    if ($DryRun) {
        Write-Host "  [DRY] $dateiname -> Vorgang $VorgangId" -ForegroundColor DarkGray
        return $true
    }

    try {
        $form = @{
            datei        = Get-Item $Dateipfad
            projekt      = $Projekt
            kategorie    = $Kategorie
        }
        if ($VorgangId) {
            $form["vorgang_id"] = $VorgangId
        }

        $result = Invoke-RestMethod -Uri "$ApiUrl/dokumente/upload" -Method Post -Headers $headers -Form $form
        Write-Host "  OK: $dateiname ($([math]::Round($result.dateigroesse_bytes / 1024, 1)) KB)" -ForegroundColor Green
        if ($result.duplikat_warnung) {
            Write-Host "      Warnung: $($result.duplikat_warnung)" -ForegroundColor Yellow
        }
        return $true
    } catch {
        Write-Host "  FEHLER: $dateiname - $_" -ForegroundColor Red
        return $false
    }
}

# --- MK-Import ---
$mkPfad = Join-Path $BasePfad "02_MK"
Write-Host "`n--- MK-Import ($mkPfad) ---" -ForegroundColor Cyan
$mkDateien = Get-ChildItem $mkPfad -File -ErrorAction SilentlyContinue
$mkOk = 0; $mkFail = 0; $mkSkip = 0

foreach ($datei in $mkDateien) {
    # "MK 001 TW-Ltg.pdf" -> Nummer "001"
    if ($datei.Name -match '^MK\s+(\d{3})') {
        $mkNr = $Matches[1]
        $ntId = $ntLookup[$mkNr]

        if ($ntId) {
            $ok = Upload-Dokument -Dateipfad $datei.FullName -Kategorie "nachtrag" -VorgangId $ntId -Beschreibung "Mehrkostenforderung MK $mkNr"
            if ($ok) { $mkOk++ } else { $mkFail++ }
        } else {
            Write-Host "  SKIP: $($datei.Name) - Kein NT-$mkNr gefunden" -ForegroundColor DarkYellow
            # Trotzdem hochladen, aber ohne Verknuepfung
            $ok = Upload-Dokument -Dateipfad $datei.FullName -Kategorie "nachtrag" -Beschreibung "Mehrkostenforderung MK $mkNr (kein NT zugeordnet)"
            if ($ok) { $mkSkip++ } else { $mkFail++ }
        }
    } else {
        Write-Host "  SKIP: $($datei.Name) - Nummer nicht erkannt" -ForegroundColor DarkYellow
        $ok = Upload-Dokument -Dateipfad $datei.FullName -Kategorie "nachtrag" -Beschreibung "Mehrkostenforderung (Nummer nicht erkannt)"
        if ($ok) { $mkSkip++ } else { $mkFail++ }
    }
}

Write-Host "`nMK-Ergebnis: $mkOk verknuepft, $mkSkip ohne Zuordnung, $mkFail Fehler" -ForegroundColor Cyan

# --- NTV-Import ---
$ntvPfad = Join-Path $BasePfad "04_NTV"
Write-Host "`n--- NTV-Import ($ntvPfad) ---" -ForegroundColor Cyan
$ntvDateien = Get-ChildItem $ntvPfad -File -ErrorAction SilentlyContinue
$ntvOk = 0; $ntvFail = 0; $ntvSkip = 0

foreach ($datei in $ntvDateien) {
    # "1. NTV_TWLeitung.pdf" -> Nummer "1" -> padded "001"
    # "10.NTV_LV 103_..." -> Nummer "10" -> padded "010"
    # "100.NTV LV 204..." -> Nummer "100" -> padded "100"
    if ($datei.Name -match '^(\d+)[\.\s]*NTV') {
        $ntvNr = $Matches[1].PadLeft(3, '0')
        $ntId = $ntLookup[$ntvNr]

        if ($ntId) {
            $ok = Upload-Dokument -Dateipfad $datei.FullName -Kategorie "vertrag" -VorgangId $ntId -Beschreibung "Nachtragsvereinbarung NTV $ntvNr"
            if ($ok) { $ntvOk++ } else { $ntvFail++ }
        } else {
            Write-Host "  SKIP: $($datei.Name) - Kein NT-$ntvNr gefunden" -ForegroundColor DarkYellow
            $ok = Upload-Dokument -Dateipfad $datei.FullName -Kategorie "vertrag" -Beschreibung "Nachtragsvereinbarung NTV $ntvNr (kein NT zugeordnet)"
            if ($ok) { $ntvSkip++ } else { $ntvFail++ }
        }
    } else {
        Write-Host "  SKIP: $($datei.Name) - Nummer nicht erkannt" -ForegroundColor DarkYellow
        $ok = Upload-Dokument -Dateipfad $datei.FullName -Kategorie "vertrag" -Beschreibung "Nachtragsvereinbarung (Nummer nicht erkannt)"
        if ($ok) { $ntvSkip++ } else { $ntvFail++ }
    }
}

Write-Host "`nNTV-Ergebnis: $ntvOk verknuepft, $ntvSkip ohne Zuordnung, $ntvFail Fehler" -ForegroundColor Cyan

# --- Zusammenfassung ---
$gesamt = $mkOk + $mkSkip + $mkFail + $ntvOk + $ntvSkip + $ntvFail
Write-Host "`n=== Zusammenfassung ===" -ForegroundColor Cyan
Write-Host "MK:  $mkOk verknuepft, $mkSkip ohne Zuordnung, $mkFail Fehler (von $($mkDateien.Count))" -ForegroundColor White
Write-Host "NTV: $ntvOk verknuepft, $ntvSkip ohne Zuordnung, $ntvFail Fehler (von $($ntvDateien.Count))" -ForegroundColor White
Write-Host "Gesamt: $gesamt verarbeitet" -ForegroundColor White

# Statistik abrufen
if (-not $DryRun) {
    Write-Host "`nDokumenten-Statistik:" -ForegroundColor Yellow
    try {
        $stats = Invoke-RestMethod -Uri "$ApiUrl/dokumente/statistik?projekt=$Projekt" -Headers $headers
        Write-Host "  Gesamt: $($stats.gesamt) Dokumente, $([math]::Round($stats.gesamtgroesse_bytes / 1024 / 1024, 1)) MB" -ForegroundColor Green
    } catch {
        Write-Host "  Statistik konnte nicht abgerufen werden." -ForegroundColor DarkYellow
    }
}

Write-Host "`nImport abgeschlossen." -ForegroundColor Green
