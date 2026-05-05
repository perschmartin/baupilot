$ErrorActionPreference = "Continue"
Write-Host "=== BauPilot Stack-Validierung ===" -ForegroundColor Cyan
Write-Host ""
$results = @()
$allPassed = $true

function Test-BPPort {
    param([string]$Name, [int]$Port)
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $tcp.Connect("localhost", $Port)
        $tcp.Close()
        Write-Host "  [PASS] $Name - Port $Port" -ForegroundColor Green
        $script:results += [PSCustomObject]@{Service=$Name;Status="PASS";Detail="Port $Port"}
    } catch {
        Write-Host "  [FAIL] $Name - Port $Port" -ForegroundColor Red
        $script:allPassed = $false
        $script:results += [PSCustomObject]@{Service=$Name;Status="FAIL";Detail="Port $Port"}
    }
}

function Test-BPUrl {
    param([string]$Name, [string]$Url)
    try {
        $r = Invoke-WebRequest -Uri $Url -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        Write-Host "  [PASS] $Name - HTTP $($r.StatusCode)" -ForegroundColor Green
        $script:results += [PSCustomObject]@{Service=$Name;Status="PASS";Detail="HTTP $($r.StatusCode)"}
    } catch {
        $msg = $_.Exception.Message.Substring(0, [Math]::Min(60, $_.Exception.Message.Length))
        Write-Host "  [FAIL] $Name - $msg" -ForegroundColor Red
        $script:allPassed = $false
        $script:results += [PSCustomObject]@{Service=$Name;Status="FAIL";Detail=$msg}
    }
}

Write-Host "Infrastruktur:" -ForegroundColor White
Test-BPPort -Name "PostgreSQL" -Port 5436
Test-BPUrl -Name "Qdrant" -Url "http://localhost:6345/healthz"
Test-BPUrl -Name "MinIO" -Url "http://localhost:9004/minio/health/live"
Write-Host ""
Write-Host "Anwendungsdienste:" -ForegroundColor White
Test-BPUrl -Name "BauPilot API" -Url "http://localhost:8110/health"
try {
    $llm = docker exec baupilot-api curl -sf --max-time 5 http://baupilot-litellm:4000/health/readiness 2>&1
    Write-Host "  [PASS] LiteLLM - intern erreichbar" -ForegroundColor Green
    $script:results += [PSCustomObject]@{Service="LiteLLM";Status="PASS";Detail="intern erreichbar"}
} catch {
    Write-Host "  [FAIL] LiteLLM - intern nicht erreichbar" -ForegroundColor Red
    $script:allPassed = $false
    $script:results += [PSCustomObject]@{Service="LiteLLM";Status="FAIL";Detail="intern nicht erreichbar"}
}
Test-BPUrl -Name "Frontend" -Url "http://localhost:8091"
Write-Host ""
Write-Host "Gemeinsame Dienste:" -ForegroundColor White
Test-BPUrl -Name "Ollama" -Url "http://localhost:11434/api/version"
Write-Host ""
Write-Host "PostgreSQL-Schemata:" -ForegroundColor White
$schemas = docker exec baupilot-postgres psql -U baupilot -d baupilot -t -c "SELECT schema_name FROM information_schema.schemata WHERE schema_name='shared' OR schema_name LIKE 'tenant_%';"
foreach ($s in ($schemas -split [Environment]::NewLine | Where-Object { $_.Trim() })) {
    Write-Host "  [PASS] Schema: $($s.Trim())" -ForegroundColor Green
}
Write-Host ""
Write-Host "=== Ergebnis ===" -ForegroundColor Cyan
if ($allPassed) { Write-Host "Alle Tests bestanden." -ForegroundColor Green }
else { Write-Host "Einige Tests fehlgeschlagen." -ForegroundColor Yellow }
Write-Host ""
$results | Format-Table -AutoSize