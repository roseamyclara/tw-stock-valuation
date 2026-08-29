# 第二輪探測：上市資料替代路徑

## 1. TPEx OpenAPI 是否代管上市／興櫃資料集

- `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_L`
  - 非 JSON（23902 bytes）：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>è­å¸æ«æª¯è²·è³£ä¸­å¿</title><meta 
- `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_L`
  - 非 JSON（23902 bytes）：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>è­å¸æ«æª¯è²·è³£ä¸­å¿</title><meta 
- `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_L_ci`
  - 非 JSON（23902 bytes）：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>è­å¸æ«æª¯è²·è³£ä¸­å¿</title><meta 
- `https://www.tpex.org.tw/openapi/v1/t187ap05_L`
  - 非 JSON（23902 bytes）：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>è­å¸æ«æª¯è²·è³£ä¸­å¿</title><meta 
- `https://www.tpex.org.tw/openapi/v1/t187ap03_L`
  - 非 JSON（23902 bytes）：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>è­å¸æ«æª¯è²·è³£ä¸­å¿</title><meta 
- `https://www.tpex.org.tw/openapi/v1/t187ap06_L_ci`
  - 非 JSON（23902 bytes）：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>è­å¸æ«æª¯è²·è³£ä¸­å¿</title><meta 
- `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_R_ci`
  - 非 JSON（23902 bytes）：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>è­å¸æ«æª¯è²·è³£ä¸­å¿</title><meta 
- `https://www.tpex.org.tw/openapi/v1/t187ap06_R_ci`
  - 非 JSON（23902 bytes）：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>è­å¸æ«æª¯è²·è³£ä¸­å¿</title><meta 
- `https://www.tpex.org.tw/openapi/v1/t187ap03_R`
  - 非 JSON（23902 bytes）：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>è­å¸æ«æª¯è²·è³£ä¸­å¿</title><meta 

## 2. 證交所其他主機／路徑（含標頭實驗）

- `https://mopsfin.twse.com.tw/opendata/t187ap05_L` [default]
  - HTTP 404
- `https://mopsfin.twse.com.tw/opendata/t187ap05_L` [with-referer]
  - HTTP 404
- `https://mopsfin.twse.com.tw/opendata/t187ap05_L` [plain-ua]
  - HTTP 404
- `https://mops.twse.com.tw/opendata/t187ap05_L` [default]
  - HTTP 404
- `https://mops.twse.com.tw/opendata/t187ap05_L` [with-referer]
  - HTTP 404
- `https://mops.twse.com.tw/opendata/t187ap05_L` [plain-ua]
  - 非 JSON（686 bytes）：<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
</head>

- `https://www.twse.com.tw/rwd/zh/opendata/t187ap05_L` [default]
  - 非 JSON（747 bytes）：<!DOCTYPE html>
<html lang="zh-Hant-tw">
<head>

<meta charset="utf-8">
<meta name="viewpo
- `https://www.twse.com.tw/rwd/zh/opendata/t187ap05_L` [with-referer]
  - 非 JSON（747 bytes）：<!DOCTYPE html>
<html lang="zh-Hant-tw">
<head>

<meta charset="utf-8">
<meta name="viewpo
- `https://www.twse.com.tw/rwd/zh/opendata/t187ap05_L` [plain-ua]
  - 非 JSON（747 bytes）：<!DOCTYPE html>
<html lang="zh-Hant-tw">
<head>

<meta charset="utf-8">
<meta name="viewpo
- `https://www.twse.com.tw/opendata/t187ap05_L` [default]
  - 非 JSON（747 bytes）：<!DOCTYPE html>
<html lang="zh-Hant-tw">
<head>

<meta charset="utf-8">
<meta name="viewpo
- `https://www.twse.com.tw/opendata/t187ap05_L` [with-referer]
  - 非 JSON（747 bytes）：<!DOCTYPE html>
<html lang="zh-Hant-tw">
<head>

<meta charset="utf-8">
<meta name="viewpo
- `https://www.twse.com.tw/opendata/t187ap05_L` [plain-ua]
  - 非 JSON（747 bytes）：<!DOCTYPE html>
<html lang="zh-Hant-tw">
<head>

<meta charset="utf-8">
<meta name="viewpo
- `https://openapi.twse.com.tw/v1/opendata/t187ap05_L` [default]
  - 1085 筆｜欄位 ['出表日期', '資料年月', '公司代號', '公司名稱', '產業別', '營業收入-當月營收', '營業收入-上月營收', '營業收入-去年當月營收', '營業收入-上月比較增減(%)', '營業收入-去年同月增減(%)', '累計營業收入-當月累計營收', '累計營業收入-去年累計營收', '累計營業收入-前期比較增減(%)', '備註']｜樣本 {"出表日期": "1150817", "資料年月": "11507", "公司代號": "1101", "公司名稱": "台泥", "產業別": "水泥工業", "營業收入-當月營收": "13744103", "營業收入-上月營收": "13382706", "營業收入-去年當月營收": "13535929", "營業收入-上月比較增減(%)": "2.70047776585692", "營業收入-去年同月增減(%)": "1.53
- `https://openapi.twse.com.tw/v1/opendata/t187ap05_L` [with-referer]
  - 1085 筆｜欄位 ['出表日期', '資料年月', '公司代號', '公司名稱', '產業別', '營業收入-當月營收', '營業收入-上月營收', '營業收入-去年當月營收', '營業收入-上月比較增減(%)', '營業收入-去年同月增減(%)', '累計營業收入-當月累計營收', '累計營業收入-去年累計營收', '累計營業收入-前期比較增減(%)', '備註']｜樣本 {"出表日期": "1150817", "資料年月": "11507", "公司代號": "1101", "公司名稱": "台泥", "產業別": "水泥工業", "營業收入-當月營收": "13744103", "營業收入-上月營收": "13382706", "營業收入-去年當月營收": "13535929", "營業收入-上月比較增減(%)": "2.70047776585692", "營業收入-去年同月增減(%)": "1.53
- `https://openapi.twse.com.tw/v1/opendata/t187ap05_L` [plain-ua]
  - 1085 筆｜欄位 ['出表日期', '資料年月', '公司代號', '公司名稱', '產業別', '營業收入-當月營收', '營業收入-上月營收', '營業收入-去年當月營收', '營業收入-上月比較增減(%)', '營業收入-去年同月增減(%)', '累計營業收入-當月累計營收', '累計營業收入-去年累計營收', '累計營業收入-前期比較增減(%)', '備註']｜樣本 {"出表日期": "1150817", "資料年月": "11507", "公司代號": "1101", "公司名稱": "台泥", "產業別": "水泥工業", "營業收入-當月營收": "13744103", "營業收入-上月營收": "13382706", "營業收入-去年當月營收": "13535929", "營業收入-上月比較增減(%)": "2.70047776585692", "營業收入-去年同月增減(%)": "1.53

## 3. 證交所每日盤後端點的表格結構

### `https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20260828&type=ALLBUT0999&response=json`
- 頂層 keys：['tables', 'type', 'params', 'stat', 'date']  stat=OK
  - 表 0：56 列｜title=115年08月28日 價格指數(臺灣證券交易所)｜欄位 ['指數', '收盤指數', '漲跌(+/-)', '漲跌點數', '漲跌百分比(%)', '特殊處理註記']
    - 樣本 ["寶島股價指數", "51,394.02", "<p style ='color:red'>+</p>", "389.55", "0.76", ""]
  - 表 1：48 列｜title=價格指數(跨市場)｜欄位 ['指數', '收盤指數', '漲跌(+/-)', '漲跌點數', '漲跌百分比(%)', '特殊處理註記']
    - 樣本 ["臺灣生技指數", "4,613.61", "<p style ='color:green'>-</p>", "40.87", "-0.88", ""]
  - 表 2：37 列｜title=價格指數(臺灣指數公司)｜欄位 ['指數', '收盤指數', '漲跌(+/-)', '漲跌點數', '漲跌百分比(%)', '特殊處理註記']
    - 樣本 ["金融類日報酬兩倍指數", "107,623.38", "<p style ='color:red'>+</p>", "3,335.61", "3.20", ""]
  - 表 3：47 列｜title=報酬指數(臺灣證券交易所)｜欄位 ['報酬指數', '收盤指數', '漲跌(+/-)', '漲跌點數', '漲跌百分比(%)', '特殊處理註記']
    - 樣本 ["寶島股價報酬指數", "79,830.76", "<p style ='color:red'>+</p>", "611.45", "0.77", ""]
  - 表 4：49 列｜title=報酬指數(跨市場)｜欄位 ['報酬指數', '收盤指數', '漲跌(+/-)', '漲跌點數', '漲跌百分比(%)', '特殊處理註記']
    - 樣本 ["臺灣生技報酬指數", "5,419.44", "<p style ='color:green'>-</p>", "48.00", "-0.88", ""]
  - 表 5：36 列｜title=報酬指數(臺灣指數公司)｜欄位 ['報酬指數', '收盤指數', '漲跌(+/-)', '漲跌點數', '漲跌百分比(%)', '特殊處理註記']
    - 樣本 ["漲升股利150報酬指數", "33,761.07", "<p style ='color:red'>+</p>", "355.73", "1.06", ""]
  - 表 6：17 列｜title=115年08月28日 大盤統計資訊｜欄位 ['成交統計', '成交金額(元)', '成交股數(股)', '成交筆數']
    - 樣本 ["1.一般股票", "1,006,613,934,315", "5,189,414,229", "4,155,179"]
  - 表 7：5 列｜title=漲跌證券數合計｜欄位 ['類型', '整體市場', '股票']
    - 樣本 ["上漲(漲停)", "7,456(227)", "361(19)"]
  - 表 8：1377 列｜title=115年08月28日 每日收盤行情(全部(不含權證、牛熊證、可展延牛熊證))｜欄位 ['證券代號', '證券名稱', '成交股數', '成交筆數', '成交金額', '開盤價', '最高價', '最低價', '收盤價', '漲跌(+/-)', '漲跌價差', '最後揭示買價', '最後揭示買量', '最後揭示賣價', '最後揭示賣量', '本益比']
    - 樣本 ["00400A", "主動國泰動能高息", "41,461,478", "7,417", "621,924,604", "14.96", "15.05", "14.91", "15.00", "<p style= color:red>+</p>", "0.19", "15.00", "80", "15.01", "176", "0.00"]
  - 表 9：0 列｜title=None｜欄位 []

### `https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json`
- 失敗：Expecting value: line 1 column 1 (char 0)
### `https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?date=20260828&selectType=ALL&response=json`
- 頂層 keys：['stat', 'date', 'title', 'fields', 'data', 'selectType', 'total']  stat=OK
  - 頂層 fields：['證券代號', '證券名稱', '收盤價', '殖利率(%)', '股利年度', '本益比', '股價淨值比', '財報年/季']
    - 樣本 ["1101", "台泥", "24.30", "3.29", 114, "-", "0.79", "115/2"]
