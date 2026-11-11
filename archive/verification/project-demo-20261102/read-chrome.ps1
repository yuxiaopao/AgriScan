Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$chrome = Get-Process chrome | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $chrome) { throw 'Chrome window is not open.' }
$root = [System.Windows.Automation.AutomationElement]::FromHandle($chrome.MainWindowHandle)
$nodes = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
$out = foreach ($node in $nodes) {
    $c = $node.Current
    if ($c.Name -and -not $c.IsOffscreen) {
        [pscustomobject]@{Name=$c.Name;Type=$c.ControlType.ProgrammaticName;Rect=$c.BoundingRectangle.ToString();Enabled=$c.IsEnabled}
    }
}
$out | ConvertTo-Json -Depth 3
