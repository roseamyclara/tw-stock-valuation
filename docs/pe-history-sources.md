# 負 EPS 的歷年本益比顯示

有明確負值依據的歷史期間，以 0 的水平虛線表示；hover 顯示「該期間本益比為負，無資料」。0 僅供圖表定位，並非有效估值，不加入市場平均或中位數。

月快照格式保持前四欄 `[pe, pb, dy, price]` 不變，可選第五欄 `"negative_eps"` 表示已確認原因。重建個股檔後是 `[ym, pe, pb, dy, price, reason]`。正常 P/E 優先，未確認的 null 維持原有濾除處理。前端亦支援明確的負 P/E 數值。

資料正規化只在來源提供負 P/E 數值時保留 `peReason`，每日快照、回補與個股重建均會傳遞此原因。

## 嚴格判定與歷史資料範圍

現有歷史檔只保存正值或 null，沒有保存 EPS 或空值原因。現行官方端點通常以空白或 N/A 表示不適用，這項程式修改**不會自動把這些空值認定為負 EPS**。採嚴格判定：日期或原因無法確認的舊資料保留原樣，不按一般公告時程推估，也不因功能上線而批次補 0。日後只有取得與各歷史交易日期對應、可驗證的近四季 EPS 或明確負值原因資料，才能標記該期間。

[證交所計算說明](https://www.twse.com.tw/zh/trading/historical/bwibbu-day.html)指出，EPS 為 0 或負數皆不計算本益比，財報未申報或未齊全也可能不計算。因此不得把所有 null、N/A 或 0 一律標為負 EPS；也不得拿最新 EPS、單季 EPS 或年度累計 EPS 回填所有歷史月份。

## 測試

- `node --test scripts/test_pe_chart.cjs`
- 在 `scripts` 目錄執行 `python -m unittest test_pe_history test_ps_history test_revenue`
