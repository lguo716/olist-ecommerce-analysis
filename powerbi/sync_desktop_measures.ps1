param([int]$Port = 63246)
$ErrorActionPreference = 'Stop'
Add-Type -Path 'D:\ATools\bin\Microsoft.PowerBI.Amo.Core.dll'
Add-Type -Path 'D:\ATools\bin\Microsoft.PowerBI.Tabular.dll'
$source = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'Olist.SemanticModel\model.bim') -Raw | ConvertFrom-Json
$server = New-Object Microsoft.AnalysisServices.Tabular.Server
$server.Connect("localhost:$Port")
try {
    $model = $server.Databases[0].Model
    # Remove the two temporary parser artifacts, never the actual report measures.
    foreach ($name in @('VAR CustomerOrders', 'VAR PreviousMonthGMV')) {
        $obsolete = $model.Tables.Find('Metrics').Measures.Find($name)
        if ($null -ne $obsolete) { $model.Tables.Find('Metrics').Measures.Remove($obsolete) }
    }
    foreach ($tableSource in $source.model.tables) {
        $table = $model.Tables.Find($tableSource.name)
        if ($null -eq $table) { throw "Missing table: $($tableSource.name)" }
        foreach ($measureSource in $tableSource.measures) {
            $measure = $table.Measures.Find($measureSource.name)
            if ($null -eq $measure) {
                $measure = New-Object Microsoft.AnalysisServices.Tabular.Measure
                $measure.Name = $measureSource.name
                $table.Measures.Add($measure)
            }
            $measure.Expression = $measureSource.expression
            $measure.FormatString = $measureSource.formatString
            $measure.DisplayFolder = $measureSource.displayFolder
        }
    }
    $model.SaveChanges()
    Write-Output 'All dashboard measures synchronized.'
} finally { $server.Disconnect() }
