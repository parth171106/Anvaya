param(
    [ValidateSet('Start', 'Stop', 'Status', 'Collect')][string]$Action = 'Start',
    [ValidateRange(1024, 65535)][int]$Port = 8081,
    [ValidateRange(1024, 65535)][int]$SyslogPort = 5515,
    [switch]$Once
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$runtime = Join-Path $projectRoot 'data\live'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$pidFile = Join-Path $runtime 'service.json'
$apiUrl = "http://127.0.0.1:$Port"
if ($Action -ne 'Start' -and !$PSBoundParameters.ContainsKey('Port') -and (Test-Path -LiteralPath $pidFile)) {
    $Port = (Get-Content -Raw -LiteralPath $pidFile | ConvertFrom-Json).port
    $apiUrl = "http://127.0.0.1:$Port"
}

function Get-PilotProcess {
    if (!(Test-Path -LiteralPath $pidFile)) { return $null }
    $saved = Get-Content -Raw -LiteralPath $pidFile | ConvertFrom-Json
    $proc = Get-Process -Id $saved.process_id -ErrorAction SilentlyContinue
    if (!$proc) { return $null }
    if ($proc.StartTime.ToUniversalTime().Ticks.ToString() -ne $saved.start_ticks) {
        throw 'Saved process ID has been reused. Refusing to control an unrelated process.'
    }
    return $proc
}

if ($Action -eq 'Stop') {
    $proc = Get-PilotProcess
    if ($proc) {
        # Windows' venv redirector can spawn a child Python process. Stop that tree,
        # after checking the saved start time, so the listener is not orphaned.
        & taskkill.exe /PID $proc.Id /T /F | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Could not stop the pilot process tree.' }
        $proc.WaitForExit(10000) | Out-Null
    }
    if (Test-Path -LiteralPath $pidFile) { Remove-Item -LiteralPath $pidFile }
    Write-Output 'Pilot stopped. Logs, signing keys and collector checkpoint are retained.'
    exit 0
}
if ($Action -eq 'Status') {
    $proc = Get-PilotProcess
    if (!$proc) { Write-Output 'Pilot is not running.'; exit 1 }
    Invoke-RestMethod "$apiUrl/api/health" | ConvertTo-Json -Depth 6
    Invoke-RestMethod "$apiUrl/api/stats" | ConvertTo-Json -Depth 6
    exit 0
}
if (!(Test-Path -LiteralPath $python)) { throw 'Create .venv and install backend dependencies first. See docs/LIVE_PILOT.md.' }
if ($Action -eq 'Collect') {
    $arguments = @('-m', 'collectors.windows_auth', '--api', $apiUrl)
    if ($Once) { $arguments += '--once' }
    Push-Location $projectRoot
    try { & $python @arguments; $collectorExit = $LASTEXITCODE } finally { Pop-Location }
    exit $collectorExit
}
if (Get-PilotProcess) {
    $savedPort = (Get-Content -Raw -LiteralPath $pidFile | ConvertFrom-Json).port
    Write-Output "Pilot already running at http://127.0.0.1:$savedPort/overview"
    exit 0
}
if (!(Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) {
    throw 'Build the frontend first: cd frontend; npm ci; npm run build. See docs/LIVE_PILOT.md.'
}
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
# A fresh bind check avoids opening an unrelated application when this port is already occupied.
$probe = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
try { $probe.Start() } finally { $probe.Stop() }
$settings = @{
    PYTHONPATH = "$(Join-Path $projectRoot 'backend');$projectRoot"
    ANVAYA_DEMO_MODE = '0'
    ANVAYA_DATA_DIR = $runtime
    ANVAYA_SYSLOG_BIND_HOST = '127.0.0.1'
    ANVAYA_SYSLOG_UDP_PORT = "$SyslogPort"
    OLLAMA_URL = 'http://127.0.0.1:11434'
    OLLAMA_MODEL = 'qwen2.5:3b'
}
$previous = @{}
try {
    foreach ($key in $settings.Keys) {
        $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, $settings[$key], 'Process')
    }
    $proc = Start-Process -FilePath $python -ArgumentList @('-m', 'uvicorn', 'app.pilot:create_pilot_app', '--factory', '--host', '127.0.0.1', '--port', "$Port", '--no-access-log') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'service.out.log') -RedirectStandardError (Join-Path $runtime 'service.err.log')
} finally {
    foreach ($key in $previous.Keys) { [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process') }
}
@{ process_id = $proc.Id; start_ticks = $proc.StartTime.ToUniversalTime().Ticks.ToString(); port = $Port; syslog_port = $SyslogPort } | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding UTF8
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if ($proc.HasExited) { throw "Pilot exited. Read $runtime\service.err.log" }
    try {
        $health = Invoke-RestMethod "$apiUrl/api/health" -TimeoutSec 2
        if ($health.demo_mode -eq $false) {
            Write-Output "Live pilot ready: $apiUrl/overview"
            Write-Output "HTTP ingestion: $apiUrl/api/ingest ; UDP: 127.0.0.1:$SyslogPort"
            Write-Output 'Start real Windows sign-in collection from an elevated PowerShell: .\pilot.ps1 Collect'
            exit 0
        }
    } catch { Start-Sleep -Milliseconds 500 }
}
throw "Pilot did not become ready. Read $runtime\service.err.log"
