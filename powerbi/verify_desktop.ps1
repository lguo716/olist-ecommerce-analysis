param([int]$Port = 63246)
$ErrorActionPreference = 'Stop'
Add-Type -Path 'D:\ATools\bin\Microsoft.PowerBI.AdomdClient.dll'
$connection = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$Port")
$connection.Open()
try {
    $queries = [ordered]@{
        platform = 'EVALUATE ROW("orders",[Total Orders],"delivered",[Delivered Orders],"gmv",[Delivered GMV],"aov",[Average Order Value],"customers",[Purchasing Customers],"repeat",[Repeat Customers],"repeat_rate",[Repeat Customer Rate],"on_time",[On-time Delivered Orders],"known_delivery",[Known Delivery Orders],"on_time_rate",[On-time Delivery Rate],"low_reviews",[Low-review Orders],"rated",[Rated Delivered Orders],"low_rate",[Low-review Rate],"eligible90",[Eligible 90D Customers],"repeat90",[90D Repeat Customers],"repeat90rate",[90D Repeat Rate])'
        delivery = 'EVALUATE SUMMARIZECOLUMNS(powerbi_orders[Delivery Status Label],"orders",[Delivery Group Orders],"score",[Delivery Group Score],"low_rate",[Delivery Group Low Rate])'
        core = 'EVALUATE CALCULATETABLE(ROW("gmv",[Delivered GMV],"delivered",[Delivered Orders],"repeat",[Repeat Customers],"repeat_rate",[Repeat Customer Rate]), ''Date''[Is Complete Core Month] = TRUE())'
        model = 'EVALUATE ROW("items",COUNTROWS(powerbi_order_items),"customer_rows",COUNTROWS(powerbi_customers),"item_gmv",[Item GMV],"rfm_value",[RFM Customer Value])'
        ba_core = 'EVALUATE CALCULATETABLE(ROW("gmv",[Delivered GMV],"delivered",[Delivered Orders],"customers",[Purchasing Customers],"repeat",[Repeat Customers]), ''Date''[Is Complete Core Month] = TRUE(), powerbi_orders[customer_state] = "BA")'
        november = 'EVALUATE CALCULATETABLE(ROW("gmv",[Delivered GMV],"delivered",[Delivered Orders]), ''Date''[Year Month] = "2017-11")'
        canceled = 'EVALUATE CALCULATETABLE(ROW("orders",[Total Orders],"delivered",COALESCE([Delivered Orders],0),"gmv",COALESCE([Delivered GMV],0),"repeat",COALESCE([Repeat Customers],0)),powerbi_orders[order_status]="canceled")'
        cohorts = 'EVALUATE ROW("groups",DISTINCTCOUNT(cohort_retention_tidy[cohort_month]),"m0_customers",CALCULATE(SUM(cohort_retention_tidy[active_customers]),cohort_retention_tidy[cohort_index]=0),"m0_min",CALCULATE(MIN(cohort_retention_tidy[retention_rate]),cohort_retention_tidy[cohort_index]=0),"m1_active",CALCULATE(SUM(cohort_retention_tidy[active_customers]),cohort_retention_tidy[cohort_index]=1),"m1_base",CALCULATE(SUM(cohort_retention_tidy[cohort_size]),cohort_retention_tidy[cohort_index]=1),"m2_active",CALCULATE(SUM(cohort_retention_tidy[active_customers]),cohort_retention_tidy[cohort_index]=2),"m2_base",CALCULATE(SUM(cohort_retention_tidy[cohort_size]),cohort_retention_tidy[cohort_index]=2))'
        mom = 'EVALUATE ROW("jan",CALCULATE([GMV MoM %],''Date''[Year Month]="2017-01"),"sep",CALCULATE([GMV MoM %],''Date''[Year Month]="2018-09"),"total",[GMV MoM %])'
    }
    $output = [ordered]@{}
    foreach ($entry in $queries.GetEnumerator()) {
        $command = $connection.CreateCommand()
        $command.CommandText = $entry.Value
        $reader = $command.ExecuteReader()
        $rows = @()
        while ($reader.Read()) {
            $row = [ordered]@{}
            for ($i=0; $i -lt $reader.FieldCount; $i++) { $row[$reader.GetName($i)] = if ($reader.IsDBNull($i)) { $null } else { $reader.GetValue($i) } }
            $rows += [pscustomobject]$row
        }
        $reader.Close()
        $output[$entry.Key] = $rows
    }
    $checks = @()
    function Assert-Value($Group, $Field, $Expected, $Tolerance = 0.000001) {
        $actual = $output[$Group][0].PSObject.Properties["[$Field]"].Value
        $passed = if ($null -eq $Expected) { $null -eq $actual } else { $null -ne $actual -and [Math]::Abs([double]$actual - [double]$Expected) -le $Tolerance }
        $script:checks += [pscustomobject]@{check="$Group.$Field";actual=$actual;expected=$Expected;passed=$passed}
        if (-not $passed) { throw "Check failed: $Group.$Field; actual=$actual expected=$Expected" }
    }
    foreach ($entry in @{orders=99441;delivered=96478;gmv=13221498.11;aov=(13221498.11/96478);customers=93358;repeat=2801;repeat_rate=(2801/93358);on_time=88644;known_delivery=96470;on_time_rate=(88644/96470);low_reviews=12237;rated=95832;low_rate=(12237/95832);eligible90=75563;repeat90=1718;repeat90rate=(1718/75563)}.GetEnumerator()) { Assert-Value 'platform' $entry.Key $entry.Value 0.01 }
    foreach ($entry in @{items=112650;customer_rows=93358;item_gmv=13221498.11;rfm_value=13221498.11}.GetEnumerator()) { Assert-Value 'model' $entry.Key $entry.Value 0.01 }
    foreach ($entry in @{gmv=13181027.13;delivered=96211;repeat=2789}.GetEnumerator()) { Assert-Value 'core' $entry.Key $entry.Value 0.01 }
    foreach ($entry in @{gmv=493339.26;delivered=3253;customers=3155;repeat=88}.GetEnumerator()) { Assert-Value 'ba_core' $entry.Key $entry.Value 0.01 }
    Assert-Value 'november' 'gmv' 987765.37 0.01
    Assert-Value 'november' 'delivered' 7289
    foreach ($entry in @{orders=625;delivered=0;gmv=0;repeat=0}.GetEnumerator()) { Assert-Value 'canceled' $entry.Key $entry.Value }
    foreach ($entry in @{groups=23;m0_customers=93358;m0_min=1;m1_active=421;m1_base=87214;m2_active=273;m2_base=81265}.GetEnumerator()) { Assert-Value 'cohorts' $entry.Key $entry.Value }
    foreach ($field in @('jan','sep','total')) { Assert-Value 'mom' $field $null }
    foreach ($row in $output.delivery) {
        $late = $row.'powerbi_orders[Delivery Status Label]' -eq '延迟'
        $expectedN = if ($late) {7661} else {88163}
        $expectedScore = if ($late) {2.5665056781} else {4.2942920121}
        $expectedLow = if ($late) {4136/7661} else {8100/88163}
        if ($row.'[orders]' -ne $expectedN -or [Math]::Abs($row.'[score]'-$expectedScore) -gt 0.000001 -or [Math]::Abs($row.'[low_rate]'-$expectedLow) -gt 0.000001) { throw 'Delivery group check failed' }
        $checks += [pscustomobject]@{check="delivery.$($row.'powerbi_orders[Delivery Status Label]')";passed=$true}
    }
    $output['checks'] = $checks
    $output['status'] = 'PASS'
    $output['checked_at'] = (Get-Date).ToString('s')
    $json = $output | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'desktop_verification.json'), $json, [System.Text.UTF8Encoding]::new($false))
    Write-Output $json
} finally { $connection.Close() }
