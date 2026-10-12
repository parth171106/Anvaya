param(
    [string]$Api,
    [switch]$Once
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$keyFile = Join-Path $projectRoot 'secrets\collector.key'
$checkpoint = Join-Path $projectRoot 'data\cloud-windows-auth-checkpoint.json'
if (!$Api) {
    $endpointFile = Join-Path $projectRoot 'data\cloud-endpoint.txt'
    if (!(Test-Path -LiteralPath $endpointFile)) { throw 'Supply -Api https://your-hostname on the first run.' }
    $Api = (Get-Content -LiteralPath $endpointFile -Raw).Trim()
}
if (!(Test-Path -LiteralPath $python)) { throw 'Install the local Python dependencies first. See docs/DEPLOYMENT.md.' }
if (!(Test-Path -LiteralPath $keyFile)) { throw 'The private collector key file is missing: secrets/collector.key' }
$arguments = @('-m', 'collectors.windows_auth', '--api', $Api, '--api-key-file', $keyFile, '--checkpoint', $checkpoint)
if ($Once) { $arguments += '--once' }
Write-Output "Collecting Windows sign-ins for $Api. Keep this window open; Ctrl+C stops collection."
Push-Location $projectRoot
try { & $python @arguments; $collectorExit = $LASTEXITCODE } finally { Pop-Location }
exit $collectorExit
