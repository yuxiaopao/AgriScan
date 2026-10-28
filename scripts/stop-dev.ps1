param(
    [Alias("LegacyOnly")]
    [switch]$NativeOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pidFile = Join-Path $projectRoot ".runtime\dev-processes.json"
$composeFile = Join-Path $projectRoot "docker-compose.yml"

function Stop-VerifiedProcessTree([System.Diagnostics.Process]$Process) {
    $parentStartedAt = $Process.StartTime.ToUniversalTime()
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($Process.Id)" -ErrorAction Stop)
    foreach ($child in $children) {
        $childProcess = Get-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
        # A stale parent PID can appear on unrelated old processes; leave them alone.
        if ($childProcess -and $childProcess.StartTime.ToUniversalTime() -ge $parentStartedAt) {
            Stop-VerifiedProcessTree $childProcess
        }
    }
    # A Process object identifies the validated process, rather than a freshly reused PID.
    Stop-Process -InputObject $Process -Force -ErrorAction SilentlyContinue
}

if (Test-Path -LiteralPath $pidFile) {
    $session = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    if (!$session.projectRoot -or [IO.Path]::GetFullPath([string]$session.projectRoot).TrimEnd('\') -ne $projectRoot.TrimEnd('\')) {
        throw "The recorded native session belongs to another project. No process was stopped."
    }
    foreach ($record in $session.processes) {
        $recordedId = 0
        if (![int]::TryParse([string]$record.pid, [ref]$recordedId) -or $recordedId -le 0 -or $recordedId -eq $PID) {
            throw "The recorded native session contains an invalid process ID. No further process was stopped."
        }
        $process = Get-Process -Id $recordedId -ErrorAction SilentlyContinue
        if (!$process) { continue }
        # PowerShell 7 can deserialize ISO timestamps to DateTime; reparsing that
        # DateTime as a string would lose fractional seconds and break PID verification.
        $expectedStart = if ($record.startedAt -is [DateTime]) {
            $record.startedAt.ToUniversalTime()
        } else {
            [DateTime]::Parse(
                [string]$record.startedAt,
                [Globalization.CultureInfo]::InvariantCulture,
                [Globalization.DateTimeStyles]::RoundtripKind
            ).ToUniversalTime()
        }
        if ($process.StartTime.ToUniversalTime().Ticks -ne $expectedStart.Ticks) {
            Write-Warning "PID $recordedId has been reused; that process was left running."
            continue
        }
        Stop-VerifiedProcessTree $process
    }
    Remove-Item -LiteralPath $pidFile
    Write-Host "The recorded native development session was stopped. Database files and local uploads were preserved."
} elseif ($NativeOnly) {
    return
}

if ($NativeOnly) { return }

$docker = (Get-Command docker -ErrorAction SilentlyContinue).Source
if (!$docker) {
    throw "Docker was not found. The recorded native session was checked, but Compose services could not be stopped."
}
& $docker compose -p agriscan --project-directory $projectRoot -f $composeFile stop mysql redis
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose could not stop all services. Data volumes were not removed."
}
Write-Host "AgriScan host servers and Docker MySQL/Redis stopped. Database volumes and local uploads were preserved."
