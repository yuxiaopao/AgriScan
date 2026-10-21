$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pidFile = Join-Path $projectRoot ".runtime\dev-processes.json"

if (!(Test-Path -LiteralPath $pidFile)) {
    Write-Host "No AgriScan development session is recorded."
    exit 0
}

$session = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
if ($session.projectRoot -ne $projectRoot) {
    throw "The recorded session belongs to a different project directory."
}

function Stop-ChildProcesses([int]$ParentProcessId) {
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $ParentProcessId" -ErrorAction Stop)
    foreach ($child in $children) {
        Stop-ChildProcesses $child.ProcessId
        Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

foreach ($record in $session.processes) {
    $process = Get-Process -Id $record.pid -ErrorAction SilentlyContinue
    if (!$process) { continue }
    # PowerShell 7 may deserialize ISO timestamps directly to DateTime.
    # Parsing that value again as a string loses fractional seconds.
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
        Write-Warning "PID $($record.pid) has been reused; that process was left running."
        continue
    }
    Stop-ChildProcesses $process.Id
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $pidFile
Write-Host "AgriScan development servers stopped. Local database, uploads and logs were preserved."
