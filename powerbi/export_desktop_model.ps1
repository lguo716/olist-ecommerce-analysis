param([int]$Port = 62942)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$modelDir = Join-Path $projectRoot 'Olist.SemanticModel'
New-Item -ItemType Directory -Path (Join-Path $modelDir '.pbi') -Force | Out-Null
Add-Type -Path 'D:\ATools\bin\Microsoft.PowerBI.Amo.Core.dll'
Add-Type -Path 'D:\ATools\bin\Microsoft.PowerBI.Tabular.dll'
$server = New-Object Microsoft.AnalysisServices.Tabular.Server
$server.Connect("localhost:$Port")
try {
    $database = $server.Databases[0]
    $json = [Microsoft.AnalysisServices.Tabular.JsonSerializer]::SerializeDatabase($database)
    [System.IO.File]::WriteAllText((Join-Path $modelDir 'model.bim'), $json, [System.Text.UTF8Encoding]::new($false))
    $backupFile = Join-Path $modelDir '.pbi\cache.abf'
    $xml = '<Backup xmlns="http://schemas.microsoft.com/analysisservices/2003/engine"><Object><DatabaseID>' + $database.ID + '</DatabaseID></Object><File>' + $backupFile + '</File><AllowOverwrite>true</AllowOverwrite><ApplyCompression>true</ApplyCompression></Backup>'
    $result = $server.Execute($xml)
    foreach ($item in $result) { foreach ($message in $item.Messages) { Write-Output $message.Description } }
    $database.Model.Relationships | Select-Object Name,FromTable,FromColumn,ToTable,ToColumn,CrossFilteringBehavior | Format-Table
    Get-Item -LiteralPath (Join-Path $modelDir 'model.bim'),$backupFile | Select-Object Name,Length
} finally { $server.Disconnect() }
