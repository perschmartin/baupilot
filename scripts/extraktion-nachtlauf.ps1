# ============================================================
# BauPilot — LLM-Extraktion Nachtlauf (E13d)
# Geht alle Vorgaenge mit verknuepftem PDF durch und extrahiert
# strukturierte Felder per Qwen 2.5 32B.
# Auto-Uebernahme bei Konfidenz >= 0.8 (B-002-konform).
#
# Lauf:
#   .\extraktion-nachtlauf.ps1                       # alle 525 Vorgaenge
#   .\extraktion-nachtlauf.ps1 -OnlyTyp behinderung  # nur einzelner Typ
#   .\extraktion-nachtlauf.ps1 -MaxAnzahl 3          # Sandbox-Test
#   .\extraktion-nachtlauf.ps1 -KeineUebernahme      # nur Vorschlag, nichts schreiben
#
# Log: scripts\extraktion-nachtlauf-YYYYMMDD-HHMM.log
# ============================================================

param(
    [string]$ApiUrl = "http://localhost:8110/api/v1",
    [string]$Email = "admin@baupilot.de",
    [string]$Passwort = "BauPilot-Erststart-2026!",
    [string]$Projekt = "FLI",
    [string]$OnlyTyp = "",              # behinderungsanzeige | bedenkenanzeige | mangelanzeige | nachtrag — leer = alle
    [double]$KonfidenzSchwelle = 0.8,   # ab dieser Konfidenz wird automatisch uebernommen
    [int]$MaxAnzahl = 0,                # 0 = unbegrenzt; sonst max N Vorgaenge
    [switch]$KeineUebernahme,           # nur Vorschlag generieren, nicht schreiben
    [switch]$Verbose
)

$ErrorActionPreference = 'Continue'  # Einzelne Fehler sollen den Lauf nicht abbrechen

# Log-Datei
$ts = Get-Date -Format "yyyyMMdd-HHmm"
$logfile = Join-Path $PSScriptRoot "extraktion-nachtlauf-$ts.log"
"=== Nachtlauf gestartet: $(Get-Date) ===" | Out-File $logfile

function Log($msg, $color = "Gray") {
    Write-Host $msg -ForegroundColor $color
    $msg | Out-File $logfile -Append
}

Log "=== BauPilot Extraktions-Nachtlauf ===" "Cyan"
Log "Konfidenz-Schwelle: $KonfidenzSchwelle"
if ($KeineUebernahme) { Log "Modus: NUR Vorschlag — keine Uebernahme" "Yellow" }
if ($OnlyTyp) { Log "Filter: nur Typ '$OnlyTyp'" "Yellow" }
if ($MaxAnzahl -gt 0) { Log "Limit: max $MaxAnzahl Vorgaenge" "Yellow" }

# --- Login ---
# Wir kapseln den Login in eine Funktion, damit wir bei 401-Antworten waehrend
# des Nachtlaufs einen frischen Token holen koennen (Access-Token TTL = 15 min,
# der Lauf dauert mehrere Stunden). Token wird im Skript-Scope gehalten.
function Get-FreshToken {
    $loginBody = @{ email = $Email; passwort = $Passwort } | ConvertTo-Json
    $r = Invoke-RestMethod -Uri "$ApiUrl/auth/login" -Method Post -ContentType "application/json" -Body $loginBody
    if (-not $r.access_token) { throw "kein access_token" }
    return $r.access_token
}

try {
    $script:token = Get-FreshToken
    Log "Login OK." "Green"
} catch {
    Log "Login fehlgeschlagen: $_" "Red"
    exit 1
}

# Wrapper fuer API-Calls mit automatischem Token-Refresh bei 401.
# Versucht einmal zu refreshen, wenn das fehlschlaegt, wirft die Originalausnahme.
function Invoke-Api {
    param(
        [string]$Uri,
        [string]$Method = "Get",
        [int]$TimeoutSec = 60
    )
    try {
        return Invoke-RestMethod -Uri $Uri -Method $Method `
            -Headers @{ Authorization = "Bearer $script:token" } `
            -TimeoutSec $TimeoutSec
    } catch {
        if ($_.Exception.Response.StatusCode -eq 401) {
            # Token erneuern und einmal wiederholen
            try {
                $script:token = Get-FreshToken
                Log "    ↻ Token erneuert" "DarkCyan"
            } catch {
                throw "Token-Refresh fehlgeschlagen: $_"
            }
            return Invoke-RestMethod -Uri $Uri -Method $Method `
                -Headers @{ Authorization = "Bearer $script:token" } `
                -TimeoutSec $TimeoutSec
        }
        throw
    }
}

# --- Vorgaenge mit verknuepftem PDF holen (via direktem DB-Query waere
# eleganter, aber wir nutzen die API zur Konsistenz) ---
# Strategie: pro Typ die Liste laden, dann pro Vorgang dessen Detail
# pruefen ob er verknuepftes Dokument hat.

function Get-VorgaengeMitPdf($typ) {
    $r = Invoke-Api -Uri "$ApiUrl/vorgaenge/?projekt=$Projekt&typ=$typ&limit=500" -TimeoutSec 60
    return $r.vorgaenge
}

$alle = @()
$typen = if ($OnlyTyp) { @($OnlyTyp) } else { @('behinderungsanzeige', 'bedenkenanzeige', 'mangelanzeige', 'nachtrag') }
foreach ($t in $typen) {
    Log "Lade $t ..." "Gray"
    $vorgaenge = Get-VorgaengeMitPdf $t
    Log "  $($vorgaenge.Count) gefunden" "Gray"
    foreach ($v in $vorgaenge) {
        $alle += [PSCustomObject]@{ id = $v.id; nummer = $v.nummer; typ = $t; beschreibung = $v.beschreibung }
    }
}

# Filter: nur Vorgaenge, die noch keine beschreibung haben (sonst arbeiten wir doppelt)
$todo = $alle | Where-Object { -not $_.beschreibung -or $_.beschreibung -eq '' }
Log "Vorgaenge gesamt: $($alle.Count) — davon ohne Beschreibung: $($todo.Count)" "Cyan"

if ($MaxAnzahl -gt 0 -and $todo.Count -gt $MaxAnzahl) {
    $todo = $todo | Select-Object -First $MaxAnzahl
    Log "Limitiert auf $MaxAnzahl" "Yellow"
}

# --- Hauptschleife ---
$stat = @{ ok = 0; uebernommen = 0; konfidenz_zu_niedrig = 0; fail = 0; gesamt = $todo.Count }
$idx = 0
$start = Get-Date

foreach ($v in $todo) {
    $idx++
    $eta = if ($idx -gt 1) {
        $verstrichen = ((Get-Date) - $start).TotalSeconds
        $proVorgang = $verstrichen / ($idx - 1)
        $verbleibend = ($stat.gesamt - $idx + 1) * $proVorgang
        "ETA: $([math]::Round($verbleibend / 60, 0))min"
    } else { "" }

    Log "[$idx/$($stat.gesamt)] $($v.typ) $($v.nummer) ... $eta" "DarkGray"

    # POST /vorschlag (lange Operation, kann 60s+) — nutzt Invoke-Api mit Auto-Refresh
    try {
        $resp = Invoke-Api -Uri "$ApiUrl/extraktion/$($v.id)/vorschlag" -Method Post -TimeoutSec 240
        $vorschlag = $resp.vorschlag
        $konf = [double]($vorschlag.konfidenz ?? 0)
        $besch_short = if ($vorschlag.beschreibung) { $vorschlag.beschreibung.Substring(0, [math]::Min(80, $vorschlag.beschreibung.Length)) } else { '(leer)' }
        Log "    konf=$konf · '$besch_short'..." "Gray"

        if (-not $KeineUebernahme -and $konf -ge $KonfidenzSchwelle) {
            try {
                Invoke-Api -Uri "$ApiUrl/extraktion/$($v.id)/uebernehmen" -Method Post -TimeoutSec 60 | Out-Null
                $stat.uebernommen++
                Log "    ✓ uebernommen" "Green"
            } catch {
                $stat.fail++
                Log "    ✗ uebernahme-fehler: $($_.Exception.Message)" "Red"
            }
        } else {
            $stat.konfidenz_zu_niedrig++
            Log "    ↻ konfidenz $konf < $KonfidenzSchwelle, nur Vorschlag gespeichert" "Yellow"
        }
        $stat.ok++
    } catch {
        $stat.fail++
        Log "    ✗ vorschlag-fehler: $($_.Exception.Message)" "Red"
    }
}

# --- Zusammenfassung ---
$dauer = ((Get-Date) - $start).TotalMinutes
Log ""
Log "=== Fertig nach $([math]::Round($dauer, 1)) min ===" "Cyan"
Log "  Verarbeitet:                 $($stat.ok) / $($stat.gesamt)"
Log "  Auto-uebernommen:            $($stat.uebernommen)"
Log "  Konfidenz zu niedrig (skip): $($stat.konfidenz_zu_niedrig)"
Log "  Fehler:                      $($stat.fail)"
Log ""
Log "Log: $logfile"
