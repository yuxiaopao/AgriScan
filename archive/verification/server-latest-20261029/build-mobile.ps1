$ErrorActionPreference = 'Stop'
$taskRoot = 'E:\AgriScan'
$buildRoot = Join-Path $taskRoot '.runtime/server-latest-20261029/mobile'
$outputRoot = Join-Path $taskRoot '.runtime/server-latest-20261029/apk'
$toolchainRoot = Join-Path $taskRoot '.runtime/android-toolchain'
$jdkRoot = Join-Path $toolchainRoot 'jdk/jdk-21.0.12.1+1'
$sdkRoot = Join-Path $toolchainRoot 'android-sdk'
$keystore = Join-Path $toolchainRoot 'android-user/debug.keystore'
foreach ($file in @((Join-Path $jdkRoot 'bin/java.exe'), (Join-Path $sdkRoot 'platforms/android-36/android.jar'), $keystore)) {
    if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw 'Existing project toolchain or debug signing material is missing; refusing to replace it.' }
}
New-Item -ItemType Directory -Force -Path $outputRoot | Out-Null
$originalKeystoreHash = (Get-FileHash -LiteralPath $keystore -Algorithm SHA256).Hash.ToLowerInvariant()
$inputs = @{}
foreach ($relative in @('src/App.tsx','src/api.ts','src/components.tsx','capacitor.config.ts','android/app/build.gradle')) {
    $inputs[$relative] = (Get-FileHash -LiteralPath (Join-Path $buildRoot $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
}
$names = @('JAVA_HOME','ANDROID_HOME','ANDROID_SDK_ROOT','ANDROID_USER_HOME','GRADLE_USER_HOME','PATH','AGRISCAN_DEV_HTTP','VITE_API_BASE_URL')
$prior = @{}
foreach ($name in $names) { $prior[$name] = [Environment]::GetEnvironmentVariable($name,'Process') }
try {
    $env:JAVA_HOME = $jdkRoot
    $env:ANDROID_HOME = $sdkRoot
    $env:ANDROID_SDK_ROOT = $sdkRoot
    $env:ANDROID_USER_HOME = Join-Path $toolchainRoot 'android-user'
    $env:GRADLE_USER_HOME = Join-Path $toolchainRoot 'gradle-cache'
    $env:PATH = (Join-Path $jdkRoot 'bin') + [IO.Path]::PathSeparator + $env:PATH
    $env:AGRISCAN_DEV_HTTP = '0'
    $env:VITE_API_BASE_URL = 'https://agriscan.ming-ai.top/agriscan'
    Push-Location $buildRoot
    try {
        & npm.cmd run build *> (Join-Path $outputRoot 'npm-build.log')
        if ($LASTEXITCODE -ne 0) { throw 'Mobile build failed; inspect .runtime/server-latest-20261029/apk/npm-build.log.' }
        Write-Host 'Mobile snapshot build passed.'
        & npx.cmd --no-install cap sync android *> (Join-Path $outputRoot 'capacitor-sync.log')
        if ($LASTEXITCODE -ne 0) { throw 'Capacitor sync failed; inspect .runtime/server-latest-20261029/apk/capacitor-sync.log.' }
        Write-Host 'Capacitor sync passed.'
    } finally { Pop-Location }
    Push-Location (Join-Path $buildRoot 'android')
    try {
        & .\gradlew.bat :app:assembleDebug --no-daemon --console=plain *> (Join-Path $outputRoot 'gradle-build.log')
        if ($LASTEXITCODE -ne 0) { throw 'Android packaging failed; inspect .runtime/server-latest-20261029/apk/gradle-build.log.' }
        Write-Host 'Gradle assembleDebug passed.'
    } finally { Pop-Location }
    if ((Get-FileHash -LiteralPath $keystore -Algorithm SHA256).Hash.ToLowerInvariant() -ne $originalKeystoreHash) { throw 'Existing debug keystore changed; refusing artifact.' }
    foreach ($relative in $inputs.Keys) {
        if ((Get-FileHash -LiteralPath (Join-Path $buildRoot $relative) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $inputs[$relative]) { throw "Input changed during packaging: $relative" }
    }
    $apk = Join-Path $outputRoot 'agriscan-test-1.0.3-code4.apk'
    Copy-Item -LiteralPath (Join-Path $buildRoot 'android/app/build/outputs/apk/debug/app-debug.apk') -Destination $apk
    $hash = (Get-FileHash -LiteralPath $apk -Algorithm SHA256).Hash.ToLowerInvariant()
    $report = @{status='built';apk=$apk;sha256=$hash;size_bytes=(Get-Item -LiteralPath $apk).Length;version='1.0.3';version_code=4;default_api=$env:VITE_API_BASE_URL;keystore_sha256=$originalKeystoreHash;keystore_unchanged=$true;source_inputs=$inputs;source_inputs_unchanged=$true;source_snapshot=$buildRoot;native_runtime_tested=$false}
    $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $outputRoot 'build.json') -Encoding utf8
    Write-Host "APK built: $apk"
    Write-Host "SHA256: $hash"
} finally {
    foreach ($name in $names) {
        if ($null -eq $prior[$name]) { Remove-Item -LiteralPath "Env:$name" -ErrorAction SilentlyContinue }
        else { [Environment]::SetEnvironmentVariable($name,$prior[$name],'Process') }
    }
}
