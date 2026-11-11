param([Parameter(Mandatory=$true)][string]$InputDocx,[Parameter(Mandatory=$true)][string]$OutputPdf)
$ErrorActionPreference='Stop'
$wordInstance=$null
$openedDocument=$null
try {
    $wordInstance=New-Object -ComObject Word.Application
    $wordInstance.Visible=$false
    $wordInstance.DisplayAlerts=0
    $wordInstance.AutomationSecurity=3
    $openedDocument=$wordInstance.Documents.Open($InputDocx,$false,$true,$false)
    $openedDocument.Repaginate()
    $openedDocument.ExportAsFixedFormat($OutputPdf,17)
    $pageTotal=$openedDocument.ComputeStatistics(2)
    Write-Output ('Native Word PDF rendered. Pages: '+$pageTotal)
} finally {
    if ($null -ne $openedDocument) {$openedDocument.Close(0);[void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($openedDocument)}
    if ($null -ne $wordInstance) {$wordInstance.Quit();[void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($wordInstance)}
}
