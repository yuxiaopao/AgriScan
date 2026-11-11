$ErrorActionPreference = 'Stop'
$toolchainRoot = 'E:\AgriScan\.runtime\android-toolchain'
$folder = 'E:\AgriScan\.runtime\mobile-cancel-final-20261029\apk'
$env:JAVA_HOME = Join-Path $toolchainRoot 'jdk/jdk-21.0.12.1+1'
$signer = Join-Path $toolchainRoot 'android-sdk/build-tools/36.0.0/apksigner.bat'
$aapt = Join-Path $toolchainRoot 'android-sdk/build-tools/36.0.0/aapt.exe'
$apk = Join-Path $folder 'agriscan-test-1.0.4-code5.apk'
& $signer verify --verbose --print-certs $apk *> (Join-Path $folder 'new-signature.txt')
if ($LASTEXITCODE -ne 0) { throw 'New APK signature verification failed.' }
& $signer verify --verbose --print-certs 'E:\AgriScan\.runtime\server-latest-20261029\apk\agriscan-test-1.0.3-code4.apk' *> (Join-Path $folder 'previous-signature.txt')
if ($LASTEXITCODE -ne 0) { throw 'Previous APK signature verification failed.' }
& $aapt dump badging $apk *> (Join-Path $folder 'manifest-badging.txt')
if ($LASTEXITCODE -ne 0) { throw 'Manifest badging inspection failed.' }
& $aapt dump xmltree $apk 'AndroidManifest.xml' *> (Join-Path $folder 'manifest-tree.txt')
if ($LASTEXITCODE -ne 0) { throw 'Manifest XML inspection failed.' }
& 'E:\AgriScan\backend\.venv\Scripts\python.exe' 'E:\AgriScan\.runtime\mobile-cancel-final-20261029\verify-mobile.py'
if ($LASTEXITCODE -ne 0) { throw 'Final APK verification failed.' }
