$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime] > $null
[Windows.Storage.Streams.IRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime] > $null
[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime] > $null
[Windows.Graphics.Imaging.SoftwareBitmap,Windows.Graphics.Imaging,ContentType=WindowsRuntime] > $null
[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] > $null
[Windows.Media.Ocr.OcrResult,Windows.Foundation,ContentType=WindowsRuntime] > $null
$asTaskMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1
function Await-Value($operation, $resultType) {
    $netTask = $asTaskMethod.MakeGenericMethod($resultType).Invoke($null,@($operation))
    $netTask.Wait()
    return $netTask.Result
}
$imagePath = $args[0]
$outputPath = 'E:\AgriScan\.runtime\smtp-20261029\credentials.json'
$file = Await-Value ([Windows.Storage.StorageFile]::GetFileFromPathAsync($imagePath)) ([Windows.Storage.StorageFile])
$stream = Await-Value ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await-Value ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await-Value ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) { throw 'Local OCR engine is unavailable.' }
$result = Await-Value ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
if ($args.Count -gt 1 -and $args[1] -eq '--diagnose-positions') {
    $positions = @($result.Lines | ForEach-Object {$_.Words} | Where-Object {$_.Text -match '[a-z]{16}'} | ForEach-Object { @{x=$_.BoundingRect.X;y=$_.BoundingRect.Y;length=$_.Text.Length} })
    @{width=$bitmap.PixelWidth;height=$bitmap.PixelHeight;candidate_positions=$positions} | ConvertTo-Json -Compress
    exit 0
}
$passwordLine = ($result.Lines | ForEach-Object {$_.Text} | Where-Object {$_ -match 'smtp.password'}) -join ' '
$passwordMatches = [regex]::Matches($result.Text,'(?<![A-Za-z])[a-z]{16}(?![A-Za-z])')
$passwordMatch = if ($passwordMatches.Count -eq 1) {$passwordMatches[0]} else {[regex]::Match($passwordLine,'(?<![A-Za-z])[a-z]{16}(?![A-Za-z])')}
$emailMatch = [regex]::Match($result.Text,'[0-9]{5,12}@qq\.com')
if (!$passwordMatch.Success) {
    Write-Output ('{"status":"ocr_incomplete","password_found":'+$passwordMatch.Success.ToString().ToLowerInvariant()+',"email_found":'+$emailMatch.Success.ToString().ToLowerInvariant()+',"candidate_count":'+$passwordMatches.Count+'}')
    throw 'SMTP fields could not be read reliably; no credential was printed or saved.'
}
$emailValue = if ($emailMatch.Success) {$emailMatch.Value} else {'2018372151@qq.com'}
$privateData = @{smtp_host='smtp.qq.com';smtp_port=465;smtp_security='ssl';smtp_username=$emailValue;smtp_from=$emailValue;smtp_password=$passwordMatch.Value}
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($outputPath)) > $null
[IO.File]::WriteAllText($outputPath,($privateData | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
$acl = Get-Acl -LiteralPath $outputPath
$acl.SetAccessRuleProtection($true,$false)
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$rule = [Security.AccessControl.FileSystemAccessRule]::new($identity,'FullControl','Allow')
$acl.AddAccessRule($rule)
Set-Acl -LiteralPath $outputPath -AclObject $acl
$stream.Dispose()
$bitmap.Dispose()
Write-Output '{"status":"read_privately","password_length":16,"credentials_printed":false}'
