# 台股估值與成長率追蹤

台灣股市 **上市／上櫃／興櫃** 三個板塊的估值與成長指標，每交易日自動更新，
以 GitHub Pages 呈現。

網站：<https://roseamyclara.github.io/tw-stock-valuation/>

## 指標

| 指標 | 說明 |
|---|---|
| **P/E** 本益比 | 上市取自證交所、上櫃取自櫃買中心的官方計算值；興櫃自行以股價 ÷ 近四季 EPS 計算 |
| **P/S** 股價營收比 | 自行計算：市值 ÷ 近十二個月營收。官方未提供此欄位 |
| **P/B** 股價淨值比、殖利率 | 上市／上櫃取自官方 |
| **月營收年增率** | 最新月份營收與去年同月比較 |
| **累計營收年增率** | 本年度累計營收與去年同期累計比較 |
| **獲利成長率** | 最新一季累計的營業利益、稅後淨利、EPS 與去年同期比較 |

市場層級的 P/E 與 P/S 由成分股加總計算（總市值 ÷ 總淨利、總市值 ÷ 總營收），
三個板塊口徑一致，也不受個股極端值影響。

## 資料來源

全部來自政府公開的官方開放資料，免申請、免金鑰：

- **臺灣證券交易所 OpenAPI** — <https://openapi.twse.com.tw/>
- **證券櫃檯買賣中心 OpenAPI** — <https://www.tpex.org.tw/openapi/>

公開資訊觀測站（MOPS）的網頁在 `robots.txt` 中禁止爬取，本專案不使用，
所有資料一律走官方發布的 OpenAPI 端點。

## 運作方式

```
GitHub Actions (排程)
    │
    ├─ scripts/build_snapshot.py    每交易日：抓最新報價、本益比、月營收、損益表
    ├─ scripts/rebuild_history.py   每月：重建各年度歷史與個股頁資料
    └─ scripts/backfill_history.py  手動：回補近十年歷史（初次建置用）
    │
    └──> docs/data/*.json ──> docs/index.html（GitHub Pages 靜態網站）
```

網站本身是純靜態頁面，直接讀取 repo 內的 JSON，不需要後端。

## 本機執行

```bash
pip install -r requirements.txt
cd scripts && python build_snapshot.py
python -m http.server -d ../docs 8000   # 開 http://localhost:8000
```

## 注意事項

- 上櫃與興櫃的股數以「股本 ÷ 面額 10 元」回推。少數面額非 10 元的個股，
  市值與 P/S 會有偏差。
- 年度中計算 P/S 時，「去年全年營收」在歷史資料尚未累積前為推估值，
  網站上會標示為「估算」。
- 本專案僅整理公開資料，不構成任何投資建議。
