$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$target = Join-Path $projectRoot 'data\raw'
$baseUrl = 'https://raw.githubusercontent.com/olist/work-at-olist-data/master/datasets'

$files = @(
    'olist_customers_dataset.csv',
    'olist_geolocation_dataset.csv',
    'olist_order_items_dataset.csv',
    'olist_order_payments_dataset.csv',
    'olist_order_reviews_dataset.csv',
    'olist_orders_dataset.csv',
    'olist_products_dataset.csv',
    'olist_sellers_dataset.csv',
    'product_category_name_translation.csv'
)

New-Item -ItemType Directory -Force -Path $target | Out-Null

foreach ($file in $files) {
    $destination = Join-Path $target $file
    Write-Host "Downloading $file"
    Invoke-WebRequest -Uri "$baseUrl/$file" -OutFile $destination
}

Write-Host "Downloaded $($files.Count) files to $target"

