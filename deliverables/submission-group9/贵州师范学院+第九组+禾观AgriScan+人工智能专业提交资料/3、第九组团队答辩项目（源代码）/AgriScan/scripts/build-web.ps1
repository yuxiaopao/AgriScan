param(
  [Parameter(Mandatory = $true)][string]$OutDir,
  [string]$ReleaseVersion = '1.0.4'
)
$ErrorActionPreference = 'Stop'
$env:VITE_WEB_BASE = '/agriscan/workspace/'
$env:VITE_API_PREFIX = '/agriscan'
$env:VITE_ADMIN_URL = '/agriscan/admin/'
$env:VITE_RELEASE_VERSION = $ReleaseVersion
& npm.cmd --prefix (Join-Path $PSScriptRoot '../frontend') run build -- --outDir $OutDir
if ($LASTEXITCODE -ne 0) {throw 'Web production build failed.'}
