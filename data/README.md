# 数据目录

## raw

应包含下列原始文件：

- `olist_customers_dataset.csv`
- `olist_geolocation_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_order_reviews_dataset.csv`
- `olist_orders_dataset.csv`
- `olist_products_dataset.csv`
- `olist_sellers_dataset.csv`
- `product_category_name_translation.csv`

可以运行 `src/download_data.ps1` 从 Olist 官方 GitHub 仓库重新下载。原始数据不提交到当前代码仓库。

## processed

由 `src/run_analysis.py` 自动生成，包括订单级分析底表、月度指标、用户分层、同期群、商家、品类、地区和 Power BI 数据表。

