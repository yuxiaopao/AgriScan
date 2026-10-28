param(
    [switch]$Install,
    [string]$Python,
    [ValidateRange(1024, 65535)]
    [int]$ApiPort = 18000,
    [ValidateRange(1024, 65535)]
    [int]$WebPort = 5173,
    [ValidateRange(30, 600)]
    [int]$WaitTimeout = 120
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"
$viteEntry = Join-Path $frontendDir "node_modules\vite\bin\vite.js"
$runtimeDir = Join-Path $projectRoot ".runtime"
$logDir = Join-Path $projectRoot ".logs"
$pidFile = Join-Path $runtimeDir "dev-processes.json"
$startedProcesses = @()
$previousApiTarget = [Environment]::GetEnvironmentVariable("AGRISCAN_API_TARGET", "Process")
$apiTargetChanged = $false

function Assert-FreePort([int]$Port) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    try {
        $listener.Start()
    } catch {
        throw "Port $Port is already in use. Stop the existing server before starting AgriScan."
    } finally {
        $listener.Stop()
    }
}

function Wait-Endpoint([string]$Url, [System.Diagnostics.Process]$Process) {
    $deadline = [DateTime]::UtcNow.AddSeconds($WaitTimeout)
    while ([DateTime]::UtcNow -lt $deadline) {
        $Process.Refresh()
        if ($Process.HasExited) { throw "Server exited. Check logs in $logDir." }
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 1
            if ($response.StatusCode -eq 200) { return }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "Server did not become ready: $Url. Check logs in $logDir."
}

if (Test-Path -LiteralPath $pidFile) {
    throw "An existing development session is recorded. Run .\scripts\stop-dev.ps1 first."
}

$node = (Get-Command node.exe -ErrorAction Stop).Source
& $node -e "const v=process.versions.node.split('.').map(Number);process.exit(v[0]>22||(v[0]===22&&v[1]>=12)?0:1)"
if ($LASTEXITCODE -ne 0) { throw "Node.js 22.12+ is required." }
$composeFile = Join-Path $projectRoot "docker-compose.yml"
$composeOptions = @("-p", "agriscan", "--project-directory", $projectRoot, "-f", $composeFile)
$docker = (Get-Command docker -ErrorAction SilentlyContinue).Source
if (!$docker) { throw "Docker was not found. Start Docker Desktop with Linux containers." }
& $docker compose version --short
if ($LASTEXITCODE -ne 0) { throw "Docker Compose v2 is required." }
try {
    $engineType = & $docker info --format "{{.OSType}}" 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Docker is unavailable." }
} catch { throw "Docker is not running or cannot be accessed. Start Docker Desktop." }
if ([string]$engineType -ne "linux") { throw "Switch Docker Desktop to Linux containers." }
if (!(Test-Path -LiteralPath (Join-Path $projectRoot ".env"))) {
    Copy-Item -LiteralPath (Join-Path $projectRoot ".env.example") -Destination (Join-Path $projectRoot ".env")
    Write-Host "Created root .env for MySQL/Redis. Existing configuration was not overwritten."
}
if (!(Test-Path -LiteralPath (Join-Path $backendDir ".env"))) {
    Copy-Item -LiteralPath (Join-Path $backendDir ".env.example") -Destination (Join-Path $backendDir ".env")
    Write-Host "Created backend/.env; confirm its host database URLs and application settings."
}
Assert-FreePort $ApiPort
Assert-FreePort $WebPort
& $docker compose @composeOptions config --quiet
if ($LASTEXITCODE -ne 0) { throw "Compose configuration is invalid; review root .env." }
# Start database containers only. API and Vite run on the host; no app images are built.
& $docker compose @composeOptions up -d --wait --wait-timeout $WaitTimeout mysql redis
if ($LASTEXITCODE -ne 0) { throw "MySQL/Redis did not become healthy. Inspect docker compose -p agriscan logs mysql redis." }

if ($Install) {
    if (!(Test-Path -LiteralPath $venvPython)) {
        if (!$Python) {
            $candidates = @(
                (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
                (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
                (Join-Path $env:LOCALAPPDATA "Programs\Python\Python314\python.exe")
            )
            $Python = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
            if (!$Python) { $Python = (Get-Command python.exe -ErrorAction Stop).Source }
        }
        & $Python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
        if ($LASTEXITCODE -ne 0) { throw "Python 3.12+ is required. Supply -Python with its full executable path." }
        & $Python -m venv (Join-Path $backendDir ".venv")
        if ($LASTEXITCODE -ne 0) { throw "Could not create the Python virtual environment." }
    }
    & $venvPython -m pip install -r (Join-Path $backendDir "requirements.txt") -r (Join-Path $backendDir "requirements-inference.txt")
    if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }
    $mediaRequirements = Join-Path $backendDir "requirements-media.txt"
    if (Test-Path -LiteralPath $mediaRequirements) {
        & $venvPython -m pip install -r $mediaRequirements
        if ($LASTEXITCODE -ne 0) { throw "Media dependency installation failed." }
    }

    Push-Location $frontendDir
    try {
        $npmEntry = Join-Path (Split-Path $node -Parent) "node_modules\npm\bin\npm-cli.js"
        $npmCommand = if (Test-Path -LiteralPath "package-lock.json") { "ci" } else { "install" }
        if (Test-Path -LiteralPath $npmEntry) {
            & $node $npmEntry $npmCommand
        } else {
            & npm.cmd $npmCommand
        }
        if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed." }
    } finally {
        Pop-Location
    }
}

if (!(Test-Path -LiteralPath $venvPython) -or !(Test-Path -LiteralPath $viteEntry)) {
    throw "Dependencies are missing. Run .\scripts\start-dev.ps1 -Install first."
}
& $venvPython -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)"
if ($LASTEXITCODE -ne 0) { throw "The existing backend virtual environment requires Python 3.12+." }
# Keep backend/.env and inherited application settings intact. Never force
# SQLite, an empty Redis URL, demo mode, administrator credentials or AI settings.
Push-Location $backendDir
try {
    & $venvPython -c "from app.config import Settings; from sqlalchemy.engine import make_url; s=Settings(); raise SystemExit(0 if make_url(s.database_url).get_backend_name()=='mysql' and s.redis_url.startswith(('redis://','rediss://')) else 2)"
    if ($LASTEXITCODE -ne 0) { throw "Configure host MySQL DATABASE_URL and REDIS_URL in backend/.env (default ports: 13308 and 16380)." }
} finally { Pop-Location }

New-Item -ItemType Directory -Path $runtimeDir, $logDir -Force | Out-Null

try {
    $api = Start-Process -FilePath $venvPython -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", ([string]$ApiPort)) -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "api.out.log") -RedirectStandardError (Join-Path $logDir "api.err.log")
    $startedProcesses += $api
    Wait-Endpoint "http://127.0.0.1:$ApiPort/api/health" $api

    [Environment]::SetEnvironmentVariable("AGRISCAN_API_TARGET", "http://127.0.0.1:$ApiPort", "Process")
    $apiTargetChanged = $true
    $web = Start-Process -FilePath $node -ArgumentList @("`"$viteEntry`"", "--host", "127.0.0.1", "--port", ([string]$WebPort), "--strictPort") -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "frontend.out.log") -RedirectStandardError (Join-Path $logDir "frontend.err.log")
    $startedProcesses += $web
    Wait-Endpoint "http://127.0.0.1:$WebPort" $web

    $processRecords = @($startedProcesses | ForEach-Object {
        @{ pid = $_.Id; startedAt = $_.StartTime.ToUniversalTime().ToString("o") }
    })
    @{ projectRoot = $projectRoot; processes = $processRecords } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $pidFile -Encoding UTF8
    Write-Host ""
    $health = Invoke-RestMethod "http://127.0.0.1:$ApiPort/api/health"
    if ($health.database -ne "connected" -or $health.redis -ne "connected" -or $health.status -ne "ok") {
        throw "The API is reachable but MySQL/Redis are not healthy. Check backend/.env and logs."
    }
    Write-Host "AgriScan host frontend/API started; Docker runs MySQL and Redis only."
    Write-Host "Health: status=$($health.status); database=$($health.database); Redis=$($health.redis); model=$($health.model)"
    if ($health.model -eq "ready") { Write-Host "Image classification: ready (verified by /api/health)." }
    else { Write-Warning "Image classification is not ready; samples require a selected crop and remain pending." }
    $mysqlBinding = @(& $docker compose @composeOptions port mysql 3306) | Select-Object -First 1
    if ($LASTEXITCODE -ne 0) { throw "Could not read the MySQL host port." }
    $redisBinding = @(& $docker compose @composeOptions port redis 6379) | Select-Object -First 1
    if ($LASTEXITCODE -ne 0) { throw "Could not read the Redis host port." }
    Write-Host "MySQL: $mysqlBinding"
    Write-Host "Redis: $redisBinding"
    Write-Host "Config: backend/.env (application), root .env (database containers)"
    Write-Host "Web:   http://127.0.0.1:$WebPort"
    Write-Host "Admin: http://127.0.0.1:$WebPort/#admin/overview"
    Write-Host "API:   http://127.0.0.1:$ApiPort/docs"
    Write-Host "Logs:  $logDir"
    Write-Host "Stop:  .\scripts\stop-dev.ps1 (preserves database volumes and local uploads)"
    Write-Host "Frontend supports hot reload. Restart this script after backend changes."
} catch {
    foreach ($process in $startedProcesses) {
        $process.Refresh()
        if (!$process.HasExited) { Stop-Process -InputObject $process -Force -ErrorAction SilentlyContinue }
    }
    if (Test-Path -LiteralPath $pidFile) { Remove-Item -LiteralPath $pidFile }
    throw
}
finally {
    if ($apiTargetChanged) { [Environment]::SetEnvironmentVariable("AGRISCAN_API_TARGET", $previousApiTarget, "Process") }
}
