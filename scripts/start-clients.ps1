param(
    [switch]$Install,
    [int]$ApiPort = 18000,
    [int]$AppPort = 5174,
    [int]$AdminPort = 5175,
    [switch]$Lan
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtimeRoot = Join-Path $projectRoot '.runtime'
$logRoot = Join-Path $projectRoot '.logs'
$recordFile = Join-Path $runtimeRoot 'client-processes.json'
$backendRoot = Join-Path $projectRoot 'backend'
$python = Join-Path $backendRoot '.venv/Scripts/python.exe'
$node = (Get-Command node.exe -ErrorAction Stop).Source
$started = @()
if (Test-Path -LiteralPath $recordFile) {throw 'Run scripts/stop-clients.ps1 before starting another clients session.'}
if (@($ApiPort,$AppPort,$AdminPort | Sort-Object -Unique).Count -ne 3) {throw 'API, APP and admin ports must be different.'}
New-Item -ItemType Directory -Path $runtimeRoot,$logRoot -Force | Out-Null

function Test-Ready([string]$Url) {
    try {return (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200} catch {return $false}
}
function Start-Checked([string]$Executable,[string[]]$Arguments,[string]$Folder,[string]$Name,[string]$Url) {
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $Folder -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot "$Name.out.log") -RedirectStandardError (Join-Path $logRoot "$Name.err.log")
    $script:started += $process
    $deadline = [DateTime]::UtcNow.AddSeconds(90)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Ready $Url) {return}
        $process.Refresh()
        if ($process.HasExited) {throw "$Name exited; inspect $logRoot/$Name.err.log"}
        Start-Sleep -Milliseconds 400
    }
    throw "$Name did not start within 90 seconds."
}

try {
    if ($Install) {
        if (!(Test-Path -LiteralPath $python)) {throw 'Create backend/.venv with Python 3.12+ first (see backend/README.md).'}
        & $python -m pip install -r (Join-Path $backendRoot 'requirements.txt') -r (Join-Path $backendRoot 'requirements-media.txt')
        if ($LASTEXITCODE -ne 0) {throw 'Backend dependency installation failed.'}
        foreach ($client in @('frontend','mobile','admin')) {
            Push-Location (Join-Path $projectRoot $client)
            try {& npm.cmd ci --cache (Join-Path $runtimeRoot 'npm-cache'); if ($LASTEXITCODE -ne 0) {throw "$client dependency installation failed."}} finally {Pop-Location}
        }
    }
    if (!(Test-Path -LiteralPath $python)) {throw 'Backend dependencies are missing.'}
    $apiUrl = "http://127.0.0.1:$ApiPort"
    $listener = Get-NetTCPConnection -State Listen -LocalPort $ApiPort -ErrorAction SilentlyContinue
    if ($listener) {
        try {$schema = Invoke-RestMethod "$apiUrl/openapi.json" -TimeoutSec 3} catch {throw "Port $ApiPort is in use by another service; choose -ApiPort."}
        if ($schema.info.title -ne '禾观 AgriScan API') {throw "Port $ApiPort belongs to another service; choose -ApiPort."}
        Write-Host "Reusing AgriScan API at $apiUrl"
    } else {
        & docker compose -p agriscan --project-directory $projectRoot -f (Join-Path $projectRoot 'docker-compose.yml') up -d --wait mysql redis
        if ($LASTEXITCODE -ne 0) {throw 'MySQL/Redis did not start. Check Docker Desktop and root .env.'}
        $apiHost = if ($Lan) {'0.0.0.0'} else {'127.0.0.1'}
        Start-Checked $python @('-m','uvicorn','app.main:app','--host',$apiHost,'--port',"$ApiPort") $backendRoot 'clients-api' "$apiUrl/api/health"
    }
    $oldProxy = $env:AGRISCAN_API_PROXY
    try {
        $env:AGRISCAN_API_PROXY = $apiUrl
        foreach ($entry in @(@('mobile',$AppPort),@('admin',$AdminPort))) {
            $client = [string]$entry[0]; $port = [int]$entry[1]
            if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {throw "Port $port is in use; choose a different port. Existing processes have been preserved."}
            $folder = Join-Path $projectRoot $client
            $vite = Join-Path $folder 'node_modules/vite/bin/vite.js'
            if (!(Test-Path -LiteralPath $vite)) {throw "Run npm.cmd ci in $client/ or use -Install."}
            Start-Checked $node @("`"$vite`"",'--host','127.0.0.1','--port',"$port",'--strictPort') $folder "clients-$client" "http://127.0.0.1:$port"
        }
    } finally {$env:AGRISCAN_API_PROXY = $oldProxy}
    @{projectRoot=$projectRoot; processes=@($started | ForEach-Object {@{pid=$_.Id;startedAt=$_.StartTime.ToUniversalTime().ToString('o')}})} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $recordFile -Encoding UTF8
    Write-Host "APP:   http://127.0.0.1:$AppPort"
    Write-Host "Admin: http://127.0.0.1:$AdminPort"
    Write-Host "API:   $apiUrl/docs"
    Write-Host 'Stop: scripts/stop-clients.ps1 (reused API processes are preserved)'
    if ($Lan -and $listener) {Write-Host 'The reused API keeps its existing listen address; restart it with a LAN address for phone access.'}
} catch {
    foreach ($process in $started) {$process.Refresh(); if (!$process.HasExited) {Stop-Process -InputObject $process -ErrorAction SilentlyContinue}}
    throw
}
