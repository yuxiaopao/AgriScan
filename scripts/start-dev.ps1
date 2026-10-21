param(
    [switch]$Install,
    [string]$Python
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
$previousEnvironment = @{}

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
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
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
    & $venvPython -m pip install -r (Join-Path $backendDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed." }

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
Assert-FreePort 8000
Assert-FreePort 5173
New-Item -ItemType Directory -Path $runtimeDir, $logDir -Force | Out-Null

$demoEnvironment = @{
    DEMO_MODE = "true"
    DATABASE_URL = "sqlite:///./data/agriscan.db"
    REDIS_URL = ""
    UPLOAD_DIR = "./uploads"
    JWT_SECRET = "local-demo-change-this-secret-before-production-2026"
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "admin12345"
    CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
}

try {
    foreach ($name in $demoEnvironment.Keys) {
        $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, $demoEnvironment[$name], "Process")
    }
    $api = Start-Process -FilePath $venvPython -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") -WorkingDirectory $backendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "api.out.log") -RedirectStandardError (Join-Path $logDir "api.err.log")
    $startedProcesses += $api
    Wait-Endpoint "http://127.0.0.1:8000/api/health" $api

    $web = Start-Process -FilePath $node -ArgumentList @("`"$viteEntry`"", "--host", "127.0.0.1", "--port", "5173", "--strictPort") -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "frontend.out.log") -RedirectStandardError (Join-Path $logDir "frontend.err.log")
    $startedProcesses += $web
    Wait-Endpoint "http://127.0.0.1:5173" $web

    $processRecords = @($startedProcesses | ForEach-Object {
        @{ pid = $_.Id; startedAt = $_.StartTime.ToUniversalTime().ToString("o") }
    })
    @{ projectRoot = $projectRoot; processes = $processRecords } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $pidFile -Encoding UTF8
    Write-Host ""
    $modelState = (Invoke-RestMethod "http://127.0.0.1:8000/api/health").model
    Write-Host "AgriScan local demo is ready (SQLite; Redis disabled; model: $modelState)."
    Write-Host "Web:   http://127.0.0.1:5173"
    Write-Host "API:   http://127.0.0.1:8000/docs"
    Write-Host "Logs:  $logDir"
    Write-Host "Stop:  .\scripts\stop-dev.ps1"
    Write-Host "Frontend supports hot reload. Restart this script after backend changes."
} catch {
    foreach ($process in $startedProcesses) {
        $process.Refresh()
        if (!$process.HasExited) { Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue }
    }
    throw
} finally {
    foreach ($name in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], "Process")
    }
}
