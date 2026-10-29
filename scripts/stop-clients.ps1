$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$recordFile = Join-Path $projectRoot '.runtime/client-processes.json'
if (!(Test-Path -LiteralPath $recordFile)) {Write-Host 'No recorded APP/admin session.'; return}
$record = Get-Content -LiteralPath $recordFile -Raw | ConvertFrom-Json
if ($record.projectRoot -ne $projectRoot) {throw 'Process record does not belong to this checkout.'}
foreach ($entry in $record.processes) {
    $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    if (!$process) {continue}
    if ([Math]::Abs(($process.StartTime.ToUniversalTime() - [DateTime]::Parse($entry.startedAt).ToUniversalTime()).TotalSeconds) -gt 1) {Write-Warning "PID $($entry.pid) has been reused; preserved."; continue}
    # Uvicorn's Windows launcher may own a child Python process; stop only its verified AgriScan child.
    Get-CimInstance Win32_Process -Filter "ParentProcessId = $($entry.pid)" | Where-Object {$_.CommandLine -match 'uvicorn app.main:app'} | ForEach-Object {Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue}
    Stop-Process -InputObject $process -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $recordFile
Write-Host 'Stopped recorded APP/admin processes. Database containers and reused API are preserved.'
