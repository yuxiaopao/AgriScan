param(
    [switch]$Release,
    [switch]$AllowLocalHttp,
    [string]$ApiBaseUrl = ''
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$mobileRoot = Join-Path $projectRoot 'mobile'
$androidRoot = Join-Path $mobileRoot 'android'
$toolchainRoot = Join-Path $projectRoot '.runtime/android-toolchain'
$environmentNames = @('JAVA_HOME', 'ANDROID_HOME', 'ANDROID_SDK_ROOT', 'ANDROID_USER_HOME', 'GRADLE_USER_HOME', 'PATH', 'AGRISCAN_DEV_HTTP', 'VITE_API_BASE_URL')
$priorEnvironment = @{}
foreach ($name in $environmentNames) { $priorEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }

try {
    # Prefer the project-local toolchain without changing the system's Java or SDK settings.
    $localJdk = Get-ChildItem -LiteralPath (Join-Path $toolchainRoot 'jdk') -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin/java.exe') } |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($localJdk) {
        $env:JAVA_HOME = $localJdk.FullName
        $env:PATH = (Join-Path $localJdk.FullName 'bin') + [IO.Path]::PathSeparator + $env:PATH
        $env:GRADLE_USER_HOME = Join-Path $toolchainRoot 'gradle-cache'
        $env:ANDROID_USER_HOME = Join-Path $toolchainRoot 'android-user'
    }
    $localSdk = Join-Path $toolchainRoot 'android-sdk'
    if (Test-Path -LiteralPath (Join-Path $localSdk 'cmdline-tools/latest/bin/sdkmanager.bat')) {
        $env:ANDROID_HOME = $localSdk
        $env:ANDROID_SDK_ROOT = $localSdk
        $env:PATH = (Join-Path $localSdk 'platform-tools') + [IO.Path]::PathSeparator + $env:PATH
    }

    if ($Release -and $AllowLocalHttp) { throw 'Release builds require HTTPS. Remove -AllowLocalHttp.' }
    if (!$ApiBaseUrl) { $ApiBaseUrl = $env:VITE_API_BASE_URL }
    if (!$ApiBaseUrl) { $ApiBaseUrl = 'https://flowly-ai.top/agriscan' }
    $apiUri = $null
    if (![Uri]::TryCreate($ApiBaseUrl, [UriKind]::Absolute, [ref]$apiUri) -or $apiUri.Scheme -notin @('https', 'http') -or $apiUri.UserInfo -or $apiUri.Query -or $apiUri.Fragment) {
        throw 'ApiBaseUrl must be an absolute HTTPS service address without credentials, query parameters or a fragment.'
    }
    if (!$AllowLocalHttp -and $apiUri.Scheme -ne 'https') { throw 'HTTPS is required unless -AllowLocalHttp is explicitly selected for a debug build.' }
    $env:VITE_API_BASE_URL = $ApiBaseUrl.TrimEnd('/')
    if ($env:VITE_API_BASE_URL.EndsWith('/api', [StringComparison]::Ordinal)) { $env:VITE_API_BASE_URL = $env:VITE_API_BASE_URL.Substring(0, $env:VITE_API_BASE_URL.Length - 4) }
    if (!(Test-Path -LiteralPath (Join-Path $mobileRoot 'node_modules/@capacitor/cli'))) { throw 'Run npm.cmd ci in mobile/ first.' }
    if (!(Get-Command java.exe -ErrorAction SilentlyContinue)) { throw 'Install JDK 21 or configure JAVA_HOME before building Android.' }
    $javaInfo = & java.exe -version 2>&1 | Out-String
    if ($javaInfo -notmatch 'version "(\d+)') { throw 'Could not read the Java version.' }
    if ([int]$Matches[1] -lt 21) { throw 'Capacitor 8 requires JDK 21 or newer; configure JAVA_HOME and PATH, or use .runtime/android-toolchain.' }
    $sdkRoot = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { $env:ANDROID_SDK_ROOT }
    if (!$sdkRoot -or !(Test-Path -LiteralPath (Join-Path $sdkRoot 'platforms/android-36/android.jar'))) {
        throw 'Install Android SDK platform 36 and build-tools 36.0.0, then configure ANDROID_HOME.'
    }
    if (!(Test-Path -LiteralPath $androidRoot)) { throw 'Android project is missing. Run npm.cmd run android:add in mobile/.' }

    $env:AGRISCAN_DEV_HTTP = if ($AllowLocalHttp) { '1' } else { '0' }
    Push-Location $mobileRoot
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Mobile build failed.' }
        & npx.cmd cap sync android
        if ($LASTEXITCODE -ne 0) { throw 'Capacitor synchronization failed.' }
    } finally { Pop-Location }

    Push-Location $androidRoot
    try {
        $task = if ($Release) { ':app:assembleRelease' } else { ':app:assembleDebug' }
        & .\gradlew.bat $task --no-daemon
        if ($LASTEXITCODE -ne 0) { throw 'Android build failed. Check Android SDK and Gradle diagnostics above.' }
    } finally { Pop-Location }
    $relative = if ($Release) { 'app/build/outputs/apk/release/app-release-unsigned.apk' } else { 'app/build/outputs/apk/debug/app-debug.apk' }
    $apk = Join-Path $androidRoot $relative
    if (!(Test-Path -LiteralPath $apk)) { throw 'Gradle completed but the expected APK was not found.' }
    $apkHash = (Get-FileHash -LiteralPath $apk -Algorithm SHA256).Hash.ToLowerInvariant()
    "$apkHash  $([IO.Path]::GetFileName($apk))" | Set-Content -LiteralPath "$apk.sha256" -Encoding ascii
    Write-Host "APK: $apk"
    Write-Host "Default API: $env:VITE_API_BASE_URL"
    Write-Host "SHA256: $apkHash"
    if ($Release) { Write-Host 'Sign the release APK with your own Android keystore before distribution.' }
} finally {
    foreach ($name in $environmentNames) {
        if ($null -eq $priorEnvironment[$name]) {
            Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue
        } else {
            [Environment]::SetEnvironmentVariable($name, $priorEnvironment[$name], 'Process')
        }
    }
}
