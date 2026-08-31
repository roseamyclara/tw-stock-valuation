# 第三輪探測：每日收盤價端點

近日 = 2026-08-28，20 個交易日前 = 2026-08-03

判準：兩個日期回傳的指紋**必須不同**，才代表這支端點真的吃日期參數。

## `otc_A_stk_wn1430`
`https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?l=zh-tw&d={roc}&se=EW`
- 近日：OK，1013 列
- 過去：OK，1012 列
- 判定：**吃日期 ✓**
- 近日樣本：`[["00411A", "主動統一前沿科技", "9.84", "+0.02", "9.90", "9.90", "9.82", "26,083,000", "257,466,900", "2,960", "9.83", "163", "9.84", "147", "701,076,000", "9,999.95", "0.01"], ["00679B", "元大美債20年", "25.85", "-0.19", "25.92", "25.92", "25.81", "12,614,000", "326,218,1`
- 過去樣本：`[["00679B", "元大美債20年", "26.42", "-0.26", "26.34", "26.43", "26.31", "33,947,000", "895,409,240", "3,126", "26.42", "639", "26.43", "1,013", "6,357,192,000", "9,999.95", "0.01"], ["00687B", "國泰20年美債", "27.51", "-0.22", "27.45", "27.51", "27.38", "35,058,000", "`

## `otc_B_stk_quote`
`https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&d={roc}`
- 近日：OK，10713 列
- 過去：OK，10713 列
- 判定：**忽略日期 ✗（兩次結果相同）**
- 近日樣本：`[["00411A", "主動統一前沿科技", "9.61", "-0.23 ", "9.64", "9.64", "9.51", "9.57", "30,048,195", "287,667,213", "5,403", "9.60", "1459", "9.61", "2968", "677,576,000", "9.61", "9999.95", "0.01"], ["006201", "元大富櫃50", "44.32", "-0.07 ", "44.20", "44.39", "43.33", "43.99`
- 過去樣本：`[["00411A", "主動統一前沿科技", "9.61", "-0.23 ", "9.64", "9.64", "9.51", "9.57", "30,048,195", "287,667,213", "5,403", "9.60", "1459", "9.61", "2968", "677,576,000", "9.61", "9999.95", "0.01"], ["006201", "元大富櫃50", "44.32", "-0.07 ", "44.20", "44.39", "43.33", "43.99`

## `otc_C_www_otc`
`https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date={roc}&type=EW&response=json`
- 近日：OK，1013 列
- 過去：OK，1012 列
- 判定：**吃日期 ✓**
- 近日樣本：`[["00411A", "主動統一前沿科技", "9.84", "+0.02", "9.90", "9.90", "9.82", "26,083,000", "257,466,900", "2,960", "9.83", "163", "9.84", "147", "701,076,000", "9,999.95", "0.01"], ["00679B", "元大美債20年", "25.85", "-0.19", "25.92", "25.92", "25.81", "12,614,000", "326,218,1`
- 過去樣本：`[["00679B", "元大美債20年", "26.42", "-0.26", "26.34", "26.43", "26.31", "33,947,000", "895,409,240", "3,126", "26.42", "639", "26.43", "1,013", "6,357,192,000", "9,999.95", "0.01"], ["00687B", "國泰20年美債", "27.51", "-0.22", "27.45", "27.51", "27.38", "35,058,000", "`

## `otc_D_dailyQuotes`
`https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={roc}&type=EW&response=json`
- 近日：OK，10657 列
- 過去：OK，10199 列
- 判定：**吃日期 ✓**
- 近日樣本：`[["00411A", "主動統一前沿科技", "9.84", "+0.02", "9.90", "9.90", "9.82", "9.87", "26,235,417", "258,968,980", "3,502", "9.83", "163", "9.84", "147", "701,076,000", "9.84", "9999.95", "0.01"], ["006201", "元大富櫃50", "44.39", "+0.25", "44.35", "44.70", "44.04", "44.34", "`
- 過去樣本：`[["006201", "元大富櫃50", "39.88", "+1.81", "38.30", "40.19", "38.30", "39.77", "659,766", "26,240,241", "347", "39.86", "2", "39.88", "4", "23,446,000", "39.88", "43.86", "35.90"], ["00679B", "元大美債20年", "26.42", "-0.26 ", "26.34", "26.43", "26.31", "26.38", "34,0`

## `otc_E_otcQuote`
`https://www.tpex.org.tw/www/zh-tw/afterTrading/otcQuote?date={roc}&response=json`
- 近日：非 JSON：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>404 - è­å¸æ«æª¯，0 列
- 過去：非 JSON：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>404 - è­å¸æ«æª¯，0 列

## `otc_F_api`
`https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes`
- 近日：OK，10713 列
- 過去：OK，10713 列
- 判定：**忽略日期 ✗（兩次結果相同）**
- 近日樣本：`[{"Date": "1150831", "SecuritiesCompanyCode": "00411A", "CompanyName": "主動統一前沿科技", "Close": "9.61", "Change": "-0.23 ", "Open": "9.64", "High": "9.64", "Low": "9.51", "Average": "9.57", "TradingShares": "30048195", "TransactionAmount": "287667213", "Transactio`
- 過去樣本：`[{"Date": "1150831", "SecuritiesCompanyCode": "00411A", "CompanyName": "主動統一前沿科技", "Close": "9.61", "Change": "-0.23 ", "Open": "9.64", "High": "9.64", "Low": "9.51", "Average": "9.57", "TradingShares": "30048195", "TransactionAmount": "287667213", "Transactio`

## `esb_A_emdaily`
`https://www.tpex.org.tw/web/emergingstock/aftertrading/daily_close_quotes/emdaily_result.php?l=zh-tw&d={roc}`
- 近日：非 JSON：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>404 - è­å¸æ«æª¯，0 列
- 過去：非 JSON：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>404 - è­å¸æ«æª¯，0 列

## `esb_B_www_daily`
`https://www.tpex.org.tw/www/zh-tw/emerging/dailyQuotes?date={roc}&response=json`
- 近日：非 JSON：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>404 - è­å¸æ«æª¯，0 列
- 過去：非 JSON：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>404 - è­å¸æ«æª¯，0 列

## `esb_C_www_stat`
`https://www.tpex.org.tw/www/zh-tw/emerging/statistics?date={roc}&response=json`
- 近日：非 JSON：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>404 - è­å¸æ«æª¯，0 列
- 過去：非 JSON：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>404 - è­å¸æ«æª¯，0 列

## `esb_D_peQry`
`https://www.tpex.org.tw/www/zh-tw/emerging/peQry?date={roc}&response=json`
- 近日：非 JSON：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>404 - è­å¸æ«æª¯，0 列
- 過去：非 JSON：<!DOCTYPE html><html lang="zh-Hant-tw"><head><title>404 - è­å¸æ«æª¯，0 列

## `esb_E_api`
`https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics`
- 近日：OK，364 列
- 過去：OK，364 列
- 判定：**忽略日期 ✗（兩次結果相同）**
- 近日樣本：`[{"Date": "1150831", "Time": "163004", "SecuritiesCompanyCode": "1260", "CompanyName": "富味鄉", "PreviousAveragePrice": "30.25", "BuyingPrice": "29.4", "BuyingQuantity": "3000", "SellingPrice": "30.6", "SellingQuantity": "2998", "Highest": "30.6", "Lowest": "29.`
- 過去樣本：`[{"Date": "1150831", "Time": "163004", "SecuritiesCompanyCode": "1260", "CompanyName": "富味鄉", "PreviousAveragePrice": "30.25", "BuyingPrice": "29.4", "BuyingQuantity": "3000", "SellingPrice": "30.6", "SellingQuantity": "2998", "Highest": "30.6", "Lowest": "29.`

## `listed_bwibbu`
`https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?date={ymd}&selectType=ALL&response=json`
- 近日：OK，1081 列
- 過去：OK，1082 列
- 判定：**吃日期 ✓**
- 近日樣本：`[["1101", "台泥", "24.30", "3.29", 114, "-", "0.79", "115/2"], ["1102", "亞泥", "34.55", "6.66", 114, "9.54", "0.66", "115/2"]]`
- 過去樣本：`[["1101", "台泥", "23.80", "3.36", 114, "-", "0.76", "115/1"], ["1102", "亞泥", "32.70", "7.03", 114, "10.97", "0.65", "115/1"]]`

## `listed_mi`
`https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={ymd}&type=ALLBUT0999&response=json`
- 近日：OK，1377 列
- 過去：OK，1377 列
- 判定：**吃日期 ✓**
- 近日樣本：`[["00400A", "主動國泰動能高息", "41,461,478", "7,417", "621,924,604", "14.96", "15.05", "14.91", "15.00", "<p style= color:red>+</p>", "0.19", "15.00", "80", "15.01", "176", "0.00"], ["00401A", "主動摩根台灣鑫收", "3,028,373", "698", "41,696,359", "13.74", "13.80", "13.71", "`
- 過去樣本：`[["00400A", "主動國泰動能高息", "54,905,455", "7,524", "725,130,876", "12.93", "13.37", "12.93", "13.25", "<p style= color:red>+</p>", "0.31", "13.24", "152", "13.25", "981", "0.00"], ["00401A", "主動摩根台灣鑫收", "9,538,199", "852", "121,445,500", "12.55", "12.83", "12.47",`
