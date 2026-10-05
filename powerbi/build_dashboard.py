"""Build the four-page PBIR report and its reusable semantic model.

The initial model comes from the user's PBIX. Generated files are editable
Power BI project sources, not rendered substitutes for a Power BI report.
"""
from pathlib import Path
import json
import re
import shutil
import uuid

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / 'Olist.Report'
PAGES = REPORT / 'definition/pages'
MODEL = ROOT / 'Olist.SemanticModel/model.bim'
SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


model = json.loads(MODEL.read_text(encoding='utf-8-sig'))
# Strip engine-generated state so the sources contain only authored metadata.
def clean(value):
    if isinstance(value, dict):
        for key in list(value):
            if key.endswith('Time') or key in {'createdTimestamp', 'lastUpdate', 'lastSchemaUpdate', 'lastProcessed', 'attributeHierarchy', 'variations', 'state'}:
                value.pop(key, None)
            else:
                clean(value[key])
    elif isinstance(value, list):
        for item in value:
            clean(item)
clean(model)
model['model']['tables'] = [t for t in model['model']['tables'] if t['name'] != 'Metrics' and not t['name'].startswith(('LocalDateTable_', 'DateTableTemplate_'))]
tables = {t['name']: t for t in model['model']['tables']}
model['model']['relationships'] = [r for r in model['model'].get('relationships', []) if r['fromTable'] in tables and r['toTable'] in tables]
for table in tables.values():
    table['columns'] = [c for c in table['columns'] if c.get('type') != 'rowNumber']
    table.pop('hierarchies', None) if table['name'] != 'Date' else None
    for partition in table.get('partitions', []):
        partition.pop('state', None)
        source = partition['source']
        if source['type'] == 'm':
            if isinstance(source['expression'], list):
                source['expression'] = '\n'.join(source['expression'])
            source['expression'] = source['expression'].replace('Encoding=936', 'Encoding=65001').replace('QuoteStyle.None', 'QuoteStyle.Csv')
            source['expression'] = source['expression'].replace('{"review_score", Int64.Type}', '{"review_score", type number}')
    for column in table['columns']:
        if column['name'] == 'review_score':
            column['dataType'] = 'double'
            column['formatString'] = '0.00'
        if column['name'].endswith(('_rate', '_growth')) or column['name'] == 'retention_rate':
            column['formatString'] = '0.00%'
        elif column.get('dataType') == 'double':
            column['formatString'] = '#,0.00'
        elif column.get('dataType') == 'dateTime':
            column['formatString'] = 'yyyy-MM-dd'
        column.pop('state', None)

tables['Date']['columns'][0]['isKey'] = True
for column in tables['Date']['columns']:
    if column['name'] == 'Year Month':
        column['sortByColumn'] = 'Year Month Sort'
    if column['name'] == 'Month':
        column['sortByColumn'] = 'Month Number'
tables['Metrics'] = {'name': 'Metrics', 'columns': [{'name': 'Placeholder', 'dataType': 'string', 'type': 'calculatedTableColumn', 'isHidden': True, 'sourceColumn': '[Placeholder]'}], 'partitions': [{'name': 'Metrics', 'mode': 'import', 'source': {'type': 'calculated', 'expression': 'DATATABLE ( "Placeholder", STRING, { { "" } } )'}}], 'measures': []}
model['model']['tables'].append(tables['Metrics'])


def measure(name, expression, fmt='#,0', table='Metrics'):
    target = tables[table]
    target.setdefault('measures', [])
    target['measures'] = [m for m in target['measures'] if m['name'] != name]
    target['measures'].append({'name': name, 'expression': expression.strip(), 'formatString': fmt, 'displayFolder': '经营分析' if table == 'Metrics' else '看板度量'})
    return (table, name, 'measure')


dax = (ROOT / 'measures.dax').read_text(encoding='utf-8-sig')
dax = re.sub(r'//[^\n]*', '', dax)
blocks = re.split(r'\n\s*\n(?=[A-Za-z0-9][^\n=]+ =\s*\n)', '\n' + dax)
for block in blocks:
    if '=' not in block:
        continue
    name, expression = block.strip().split('=', 1)
    name = name.strip()
    if name in {'Delivery Status Label', 'Seller Late Risk Band'}:
        table = 'powerbi_orders' if name == 'Delivery Status Label' else 'seller_scorecard'
        tables[table]['columns'] = [c for c in tables[table]['columns'] if c['name'] != name]
        tables[table]['columns'].append({'type': 'calculated', 'name': name, 'dataType': 'string', 'expression': expression.strip()})
    else:
        fmt = '0.00%' if name.endswith(('Rate', '%')) else '#,0.00' if any(x in name for x in ['GMV', 'Freight', 'Value', 'Average']) else '#,0'
        measure(name, expression, fmt)

measure('Top 10 Item GMV', 'IF ( RANKX ( ALLSELECTED ( powerbi_order_items[category] ), [Item GMV], , DESC, DENSE ) <= 10, [Item GMV] )', '#,0.00')
measure('RFM Customers', 'COUNTROWS ( powerbi_customers )')
measure('RFM Value', 'SUM ( powerbi_customers[monetary] )', '#,0.00')
measure('Customer Frequency Count', 'COUNTROWS ( powerbi_customers )')
measure('Category Orders', 'SUM ( category_performance[orders] )', table='category_performance')
measure('Category GMV', 'SUM ( category_performance[revenue] )', '#,0.00', 'category_performance')
for name, col, fmt in [('Category Score','average_review_score','0.00'),('Category Low Rate','low_review_rate','0.00%'),('Category Late Rate','late_delivery_rate','0.00%'),('Category Freight Rate','freight_to_revenue_rate','0.00%')]:
    measure(name, f'AVERAGE ( category_performance[{col}] )', fmt, 'category_performance')
for name, col, fmt in [('Seller GMV','revenue','#,0.00'),('Seller Orders','orders','#,0'),('Seller Score','average_review_score','0.00'),('Seller Low Rate','low_review_rate','0.00%'),('Seller Late Rate','late_delivery_rate','0.00%')]:
    measure(name, f'SUM ( seller_scorecard[{col}] )' if col in {'revenue','orders'} else f'AVERAGE ( seller_scorecard[{col}] )', fmt, 'seller_scorecard')
for name, col, fmt in [('Growth','revenue_growth','0.00%'),('Score Change','review_score_change','0.00'),('Growth Orders','orders','#,0')]:
    measure(name, f'MAX ( category_growth_quality[{col}] )', fmt, 'category_growth_quality')
measure('Retention', 'DIVIDE ( SUM ( cohort_retention_tidy[active_customers] ), SUM ( cohort_retention_tidy[cohort_size] ) )', '0.00%', 'cohort_retention_tidy')
measure('Retention Cell Color', '''VAR Rate = [Retention]
RETURN SWITCH ( TRUE (), ISBLANK ( Rate ), BLANK (), SELECTEDVALUE ( cohort_retention_tidy[cohort_index] ) = 0, "#DBEAFE", Rate = 0, "#F8FAFC", Rate < 0.003, "#DBEAFE", Rate < 0.005, "#93C5FD", "#3B82F6" )''', '', 'cohort_retention_tidy')
for c in tables['cohort_retention_tidy']['columns']:
    if c['name'] == 'cohort_month':
        c['formatString'] = 'yyyy-MM'
measure('Delivery 90D Rate', 'DIVIDE ( SUM ( repurchase_by_first_delivery[repeat_90d_customers] ), SUM ( repurchase_by_first_delivery[customers] ) )', '0.00%', 'repurchase_by_first_delivery')
measure('Review 90D Rate', 'DIVIDE ( SUM ( repurchase_by_first_review[repeat_90d_customers] ), SUM ( repurchase_by_first_review[customers] ) )', '0.00%', 'repurchase_by_first_review')
measure('New Customers Monthly', 'SUM ( monthly_metrics[new_customers] )', table='monthly_metrics')
measure('Returning Customers Monthly', 'SUM ( monthly_metrics[returning_customers] )', table='monthly_metrics')
measure('Item Weight Kg', 'AVERAGE ( powerbi_order_items[product_weight_g] ) / 1000', '0.00')
measure('Item Volume Litres', 'AVERAGE ( powerbi_order_items[product_volume_cm3] ) / 1000', '0.00')
measure('Item Freight', 'AVERAGE ( powerbi_order_items[freight_value] )', '0.00')
measure('Delivery Group Orders', '''CALCULATE ( [Delivered Orders], NOT ISBLANK ( powerbi_orders[is_late] ), NOT ISBLANK ( powerbi_orders[review_score] ) )''')
measure('Delivery Group Score', 'CALCULATE ( [Average Review Score], NOT ISBLANK ( powerbi_orders[is_late] ) )', '0.00')
measure('Delivery Group Low Rate', 'CALCULATE ( [Low-review Rate], NOT ISBLANK ( powerbi_orders[is_late] ) )', '0.00%')

# Keep the original lineage so the cache can be restored, but authored metadata
# controls the relationships and calculations after loading.
write(MODEL, model)


def lit(value):
    if isinstance(value, bool):
        value = str(value).lower()
    elif isinstance(value, str):
        value = "'" + value.replace("'", "''") + "'"
    else:
        value = str(value) + 'D'
    return {'expr': {'Literal': {'Value': value}}}


def color(value):
    return {'solid': {'color': lit(value)}}


def col(table, name):
    return (table, name, 'column')


def met(name, table='Metrics'):
    return (table, name, 'measure')


def field(spec, alias=False):
    table, name, kind = spec[:3]
    source = {'Source': 's'} if alias else {'Entity': table}
    return {'Measure' if kind == 'measure' else 'Column': {'Expression': {'SourceRef': source}, 'Property': name}}


def filter_in(spec, values):
    return {'name': uuid.uuid4().hex[:20], 'field': field(spec), 'type': 'Categorical', 'filter': {'Version': 2, 'From': [{'Name': 's', 'Entity': spec[0], 'Type': 0}], 'Where': [{'Condition': {'In': {'Expressions': [field(spec, True)], 'Values': [[v] for v in values]}}}]}}


def filter_ge(spec, value):
    return {'name': uuid.uuid4().hex[:20], 'field': field(spec), 'type': 'Advanced', 'filter': {'Version': 2, 'From': [{'Name': 's', 'Entity': spec[0], 'Type': 0}], 'Where': [{'Condition': {'Comparison': {'ComparisonKind': 2, 'Left': field(spec, True), 'Right': {'Literal': {'Value': str(value) + 'L'}}}}}]}}


def boolean_filter(table, name, value=True):
    return filter_in(col(table, name), [{'Literal': {'Value': str(value).lower()}}])


def page(name, title, subtitle, filters=None):
    identifier = name
    write(PAGES / identifier / 'page.json', {'$schema': SCHEMA + 'page/2.1.0/schema.json', 'name': identifier, 'displayName': title, 'displayOption': 'FitToPage', 'height': 900, 'width': 1600, 'objects': {'background': [{'properties': {'color': color('#F1F5F9'), 'transparency': lit(0)}}]}, **({'filterConfig': {'filters': filters}} if filters else {})})
    text(identifier, 'heading', title, 24, 6, 1552, 54, 24, '#0F172A', True)
    text(identifier, 'subtitle', subtitle, 24, 59, 1552, 34, 11, '#475569')
    return identifier


def visual(page_id, key, typ, title, pos, roles=None, filters=None, objects=None, sort=None):
    x,y,w,h = pos
    content = {'$schema': SCHEMA+'visualContainer/2.9.0/schema.json', 'name': key, 'position': {'x':x,'y':y,'z':0,'height':h,'width':w,'tabOrder':0}, 'visual': {'visualType':typ, 'drillFilterOtherVisuals':True, 'visualContainerObjects': {'title':[{'properties':{'show':lit(bool(title)), 'text':lit(title), 'fontSize':lit(12), 'fontFamily':lit('Microsoft YaHei'), 'fontColor':color('#0F172A')}}], 'subTitle':[{'properties':{'show':lit(False)}}], 'background':[{'properties':{'show':lit(True),'color':color('#FFFFFF'),'transparency':lit(0)}}], 'border':[{'properties':{'show':lit(False)}}]}}}
    if roles:
        query_state={}
        for role, specs in roles.items():
            query_state[role]={'projections':[{'field':field(s), 'queryRef':s[0]+'.'+s[1], 'nativeQueryRef':s[1], 'displayName':s[3] if len(s)>3 else s[1]} for s in specs]}
        content['visual']['query']={'queryState':query_state}
        if sort:
            content['visual']['query']['sortDefinition']={'sort':[{'field':field(sort[0]),'direction':sort[1]}], 'isDefaultSort':True}
    if objects:
        content['visual']['objects']=objects
    if typ == 'clusteredBarChart':
        content['visual'].setdefault('objects', {})['categoryAxis'] = [{'properties':{'preferredCategoryWidth':lit(16),'fontSize':lit(9)}}]
    if typ == 'clusteredColumnChart':
        content['visual'].setdefault('objects', {})['categoryAxis'] = [{'properties':{'show':lit(True),'fontSize':lit(9),'preferredCategoryWidth':lit(16)}}]
    if filters:
        copied = json.loads(json.dumps(filters))
        for f in copied:
            f['name'] = uuid.uuid4().hex[:20]
        content['filterConfig']={'filters':copied}
    write(PAGES / page_id / 'visuals' / key / 'visual.json', content)
    return content


def text(p, key, content, x,y,w,h,size=12,fg='#334155',bold=False):
    obj=visual(p,key,'textbox','',(x,y,w,h))
    obj['visual']['objects']={'general':[{'properties':{'paragraphs':[{'textRuns':[{'value':content,'textStyle':{'fontFamily':'Microsoft YaHei','fontSize':f'{size}pt','color':fg,'fontWeight':'bold' if bold else 'normal'}}]}]}}]}
    obj['visual']['visualContainerObjects']['background'][0]['properties']['transparency']=lit(100)
    write(PAGES / p / 'visuals' / key / 'visual.json', obj)


def card(p,key,name,label,pos):
    return visual(p,key,'card',label,pos,{'Values':[(*met(name),label)]},objects={'labels':[{'properties':{'fontSize':lit(25),'labelDisplayUnits':lit(1),'color':color('#1D4ED8')}}], 'categoryLabels':[{'properties':{'show':lit(False)}}]})


def dropdown(p,key,spec,title,pos):
    visual(p,key,'slicer',title,pos,{'Values':[spec]},objects={'data':[{'properties':{'mode':lit('Dropdown')}}], 'header':[{'properties':{'show':lit(False)}}], 'selection':[{'properties':{'singleSelect':lit(False)}}]})


def matrix(p,key,title,pos,rows,values,filters=None,columns=None,sort=None):
    roles={'Rows':rows,'Values':values}
    if columns:
        roles['Columns']=columns
    obj={'grid':[{'properties':{'textSize':lit(10)}}], 'rowHeaders':[{'properties':{'fontSize':lit(10)}}], 'columnHeaders':[{'properties':{'fontSize':lit(10)}}], 'values':[{'properties':{'fontSize':lit(10)}}], 'subTotals':[{'properties':{'rowSubtotals':lit(False),'columnSubtotals':lit(False)}}]}
    if len(rows)>1:
        obj['subTotals'][0]['properties']['rowSubtotals']=lit(True)
        obj['rowHeaders'][0]['properties']['showExpandCollapseButtons']=lit(True)
    if columns:
        obj['values'].append({'selector':{'metadata':'cohort_retention_tidy.Retention','data':[{'dataViewWildcard':{'matchingOption':1}}]},'properties':{'backColor':{'solid':{'color':{'expr':field(met('Retention Cell Color','cohort_retention_tidy'))}}}}})
    visual(p,key,'pivotTable',title,pos,roles,filters,obj,sort)


ids=[]
p=page('business_overview','01 经营总览','成交商品金额（BRL） · 页面默认为2017-01至2018-08完整月份 · 日期/州/状态筛选作用于经营明细', [boolean_filter('Date','Is Complete Core Month')]); ids.append(p)
dropdown(p,'date_slicer',col('Date','Year Month'),'月份',(24,98,490,68))
dropdown(p,'state_slicer',col('powerbi_orders','customer_state'),'顾客州',(530,98,490,68))
dropdown(p,'status_slicer',col('powerbi_orders','order_status'),'订单状态',(1036,98,540,68))
for i,(name,label) in enumerate([('Delivered GMV','成交额 BRL'),('Delivered Orders','成交订单'),('Average Order Value','客单价 BRL'),('Purchasing Customers','购买顾客'),('Repeat Customer Rate','窗口内复购率'),('On-time Delivery Rate','准时送达率')]):
    card(p,'kpi_'+str(i),name,label,(24+i*260,178,248,112))
visual(p,'monthly_combo','lineClusteredColumnComboChart','月度经营趋势：成交额与成交订单',(24,306,1024,288),{'Category':[col('Date','Year Month')],'Y':[met('Delivered GMV')],'Y2':[met('Delivered Orders')]},objects={'valueAxis':[{'properties':{'secShow':lit(True),'showAxisTitle':lit(True),'titleText':lit('成交额 BRL'),'secShowAxisTitle':lit(True),'secTitleText':lit('成交订单')}}], 'legend':[{'properties':{'show':lit(True)}}]},sort=(col('Date','Year Month'),'Ascending'))
visual(p,'top_categories','clusteredBarChart','Top 10 品类成交额（商品金额）',(1064,306,512,288),{'Category':[col('powerbi_order_items','category')],'Y':[met('Top 10 Item GMV')]},sort=(met('Top 10 Item GMV'),'Descending'))
matrix(p,'state_metrics','州级经营与质量（展开州可下钻城市）',(24,610,1024,246),[(*col('powerbi_orders','customer_state'),'州'),(*col('powerbi_orders','customer_city'),'城市')],[(*met('Delivered Orders'),'成交订单'),(*met('Delivered GMV'),'成交额'),(*met('Average Order Value'),'客单价'),(*met('Late Delivery Rate'),'延迟率'),(*met('Low-review Rate'),'低评分率')],sort=(met('Delivered GMV'),'Descending'))
text(p,'takeaway','解读线索\n2017-11为完整月成交额峰值。\n2018年1—8月较上年同期增长141.13%。\n增长需要同时查看订单量与客单价。',1080,622,476,200,15)
text(p,'footnote','全窗口验收：99,441总订单 / 96,478成交订单 / 13,221,498.11 BRL。清除页面“完整月份”筛选后可核对。',24,859,1552,36,10)

p=page('customer_repurchase','02 用户与复购','固定历史观察窗口：参考日期2018-08-30 · 90天指标仅纳入完整可观察顾客 · 各汇总图按自身分组解释'); ids.append(p)
for i,(name,label) in enumerate([('Purchasing Customers','成交顾客'),('Repeat Customer Rate','总体复购率'),('Eligible 90D Customers','90天可观察顾客'),('90D Repeat Rate','90天复购率')]):
    card(p,'user_kpi_'+str(i),name,label,(24+i*392,104,376,110))
visual(p,'rfm_people','clusteredBarChart','RFM分层人数',(24,230,500,242),{'Category':[col('powerbi_customers','segment')],'Y':[met('RFM Customers')]},sort=(met('RFM Customers'),'Descending'))
visual(p,'rfm_value','clusteredBarChart','RFM分层累计金额 BRL',(540,230,500,242),{'Category':[col('powerbi_customers','segment')],'Y':[met('RFM Value')]},sort=(met('RFM Value'),'Descending'))
visual(p,'frequency','clusteredColumnChart','购买频次分布',(1056,230,520,242),{'Category':[col('powerbi_customers','frequency')],'Y':[met('Customer Frequency Count')]},sort=(col('powerbi_customers','frequency'),'Ascending'))
cohort_filters=[filter_ge(col('cohort_retention_tidy','cohort_month'),0)]
# The matrix retains all observable cells. Visual limits are explicit filters.
date_filter=filter_in(col('cohort_retention_tidy','cohort_month'),[{'Literal':{'Value':f"datetime'{year}-{month:02d}-01T00:00:00'"}} for year,month in [(2017,m) for m in range(1,13)]+[(2018,m) for m in range(1,9)]])
matrix(p,'cohort','首购同期群：当月复购留存（0月=100%，空白=尚不可观察）',(24,488,896,344),[(*col('cohort_retention_tidy','cohort_month'),'首购月')],[(*met('Retention','cohort_retention_tidy'),'留存率')],[date_filter],columns=[col('cohort_retention_tidy','cohort_index')])
visual(p,'monthly_users','lineChart','完整月份：新客与复购顾客人数',(936,488,640,146),{'Category':[col('monthly_metrics','purchase_month')],'Y':[(*met('New Customers Monthly','monthly_metrics'),'新客'),(*met('Returning Customers Monthly','monthly_metrics'),'复购顾客')]},[boolean_filter('monthly_metrics','is_complete_core_month')],sort=(col('monthly_metrics','purchase_month'),'Ascending'))
visual(p,'first_delivery','clusteredColumnChart','首单配送与90天复购',(936,650,312,182),{'Category':[col('repurchase_by_first_delivery','first_delivery_status')],'Y':[met('Delivery 90D Rate','repurchase_by_first_delivery')]})
visual(p,'first_review','clusteredColumnChart','首单评分与90天复购',(1264,650,312,182),{'Category':[col('repurchase_by_first_review','first_review_group')],'Y':[met('Review 90D Rate','repurchase_by_first_review')]})
text(p,'user_note','总体复购2,801 / 93,358 = 3.00%；90天复购1,718 / 75,563 = 2.27%；加权次月留存约0.4827%。',24,849,1552,37,11)

p=page('delivery_satisfaction','03 物流与满意度','成交订单 · 配送对比同时要求配送判断与评分完整 · 延迟为实际送达晚于预计时间 · 低评分为1—2分'); ids.append(p)
for i,(name,label) in enumerate([('On-time Delivery Rate','准时送达率'),('Average Delivery Days','平均履约天数'),('Average Review Score','平均评分'),('Low-review Rate','低评分率')]):
    card(p,'delivery_kpi_'+str(i),name,label,(24+i*392,104,376,110))
deliveryfilter=[filter_in(col('powerbi_orders','Delivery Status Label'),[{'Literal':{'Value':"'准时'"}},{'Literal':{'Value':"'延迟'"}}])]
colors=[{'selector':{'data':[{'dataViewWildcard':{'matchingOption':1}}]},'properties':{'fill':color('#2563EB')}}]
for key,title,m,x in [('group_score','准时与延迟：平均评分','Delivery Group Score',24),('group_low','准时与延迟：低评分率','Delivery Group Low Rate',544)]:
    series_colors=[{'selector':{'data':[{'scopeId':{'Comparison':{'ComparisonKind':0,'Left':field(col('powerbi_orders','Delivery Status Label')),'Right':{'Literal':{'Value':"'"+label+"'"}}}}}]},'properties':{'fill':color(hexcolor)}} for label,hexcolor in [('延迟','#DC2626'),('准时','#2563EB')]]
    visual(p,key,'clusteredColumnChart',title,(x,230,504,238),{'Category':[col('powerbi_orders','Delivery Status Label')],'Y':[met(m)]},deliveryfilter,objects={'labels':[{'properties':{'show':lit(True)}}], 'dataPoint':series_colors})
text(p,'effect','全窗口基准\n延迟订单低评分率53.99%\n准时订单低评分率9.19%\n差44.80个百分点 / 约5.88倍\n延迟组平均评分低1.73分',1080,236,476,228,15)
matrix(p,'state_quality','州级履约与评分（成交≥300单）',(24,484,730,342),[(*col('powerbi_orders','customer_state'),'州')],[(*met('Delivered Orders'),'订单数'),(*met('Late Delivery Rate'),'延迟率'),(*met('Low-review Rate'),'低评分率'),(*met('Average Delivery Days'),'履约天数')],[filter_ge(met('Delivered Orders'),300)],sort=(met('Late Delivery Rate'),'Descending'))
matrix(p,'seller_attention','商家关注清单（成交≥30单；历史全窗口）',(770,484,806,342),[(*col('seller_scorecard','seller_id'),'商家')],[(*met('Seller Orders','seller_scorecard'),'订单数'),(*met('Seller GMV','seller_scorecard'),'成交额'),(*met('Seller Score','seller_scorecard'),'评分'),(*met('Seller Low Rate','seller_scorecard'),'低评分率'),(*met('Seller Late Rate','seller_scorecard'),'延迟率')],[boolean_filter('seller_scorecard','reliable_sample')],sort=(met('Seller Low Rate','seller_scorecard'),'Descending'))
text(p,'delivery_note','评分差95%置信区间[-1.7657, -1.6899]；Mann–Whitney与Spearman检验p<1e-300；用于定位关联和治理优先级。',24,843,1552,40,11)

p=page('category_seller','04 品类与商家','品类成交额按商品行price汇总 · 品类≥300单 / 商家≥30单 · 同期增长比较：2017与2018年1—8月各≥100单'); ids.append(p)
matrix(p,'category_matrix','品类规模、质量与运费（可靠样本）',(24,106,1552,242),[col('category_performance','category')],[(*met('Category GMV','category_performance'),'成交额 BRL'),(*met('Category Orders','category_performance'),'订单数'),(*met('Category Score','category_performance'),'评分'),(*met('Category Low Rate','category_performance'),'低评分率'),(*met('Category Late Rate','category_performance'),'延迟率'),(*met('Category Freight Rate','category_performance'),'运费/成交额')],[boolean_filter('category_performance','reliable_sample')])
visual(p,'growth_scatter','scatterChart','品类同期增长与评分变化',(24,364,754,242),{'Category':[col('category_growth_quality','category')],'X':[met('Growth','category_growth_quality')],'Y':[met('Score Change','category_growth_quality')],'Size':[met('Growth Orders','category_growth_quality')]},[boolean_filter('category_growth_quality','comparable_sample')])
visual(p,'seller_scatter','scatterChart','商家成交额与评分（点大小=订单量）',(794,364,782,242),{'Category':[col('seller_scorecard','seller_id')],'X':[met('Seller GMV','seller_scorecard')],'Y':[met('Seller Score','seller_scorecard')],'Size':[met('Seller Orders','seller_scorecard')],'Series':[col('seller_scorecard','Seller Late Risk Band')]},[boolean_filter('seller_scorecard','reliable_sample')])
visual(p,'weight_scatter','scatterChart','商品重量与平均运费（按商品聚合）',(24,622,754,224),{'Category':[col('powerbi_order_items','product_id')],'X':[met('Item Weight Kg')],'Y':[met('Item Freight')],'Tooltips':[met('Item Volume Litres')]},[boolean_filter('powerbi_order_items','is_delivered')])
visual(p,'volume_scatter','scatterChart','商品体积与平均运费（按商品聚合）',(794,622,782,224),{'Category':[col('powerbi_order_items','product_id')],'X':[met('Item Volume Litres')],'Y':[met('Item Freight')],'Tooltips':[met('Item Weight Kg')]},[boolean_filter('powerbi_order_items','is_delivered')])
text(p,'category_note','关注baby、stationery、electronics、watches_gifts等增长伴质量压力品类；多商家订单评分需结合订单和地区下钻解释。',24,853,1552,34,11)

write(PAGES/'pages.json',{'$schema':SCHEMA+'pagesMetadata/1.1.0/schema.json','pageOrder':ids,'activePageName':ids[0]})
for old_id in ('e197d89c55c25a40e343', 'ff89eea880494794aadb'):
    source = PAGES / old_id
    if source.exists():
        target = ROOT / 'backups' / ('original_page_' + old_id)
        if not target.exists():
            shutil.move(str(source), str(target))
theme_path = REPORT/'StaticResources/RegisteredResources/Olist_Portfolio4722957240780504.json'
theme = json.loads(theme_path.read_text(encoding='utf-8-sig'))
theme['name'] = 'Olist_Portfolio4722957240780504.json'
for item in theme['visualStyles']['*']['*']['title']:
    if 'color' in item:
        item['fontColor'] = item.pop('color')
write(theme_path, theme)
print('Built four report pages:', ', '.join(ids))
print('Semantic model:', len(tables), 'tables;',sum(len(t.get('measures',[])) for t in tables.values()),'measures')
