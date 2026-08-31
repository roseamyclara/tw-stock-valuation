"""第三輪探測：找「單日全市場收盤價」且真的吃日期參數的端點。

漲幅排行需要過去約 30 個交易日的每日收盤價。
已知：上市的 BWIBBU_d 支援日期且含收盤價；
      上櫃的 stk_quote_result.php 會忽略日期、一律回當天；
      興櫃的 www/zh-tw/emerging/historical 需要個股代號，不能整批。
這裡把候選端點各打「今天」與「20 個交易日前」兩次，比對回傳是否真的不同 ——
只有兩次結果不同，才代表它真的吃日期。
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import requests
from util import session, to_roc

TPEX = "https://www.tpex.org.tw"
TWSE = "https://www.twse.com.tw/rwd/zh"

CANDIDATES = {
    # ---- 上櫃 ----
    "otc_A_stk_wn1430": TPEX + "/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?l=zh-tw&d={roc}&se=EW",
    "otc_B_stk_quote": TPEX + "/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&d={roc}",
    "otc_C_www_otc": TPEX + "/www/zh-tw/afterTrading/otc?date={roc}&type=EW&response=json",
    "otc_D_dailyQuotes": TPEX + "/www/zh-tw/afterTrading/dailyQuotes?date={roc}&type=EW&response=json",
    "otc_E_otcQuote": TPEX + "/www/zh-tw/afterTrading/otcQuote?date={roc}&response=json",
    "otc_F_api": TPEX + "/openapi/v1/tpex_mainboard_daily_close_quotes",   # 對照組，應該不吃日期
    # ---- 興櫃 ----
    "esb_A_emdaily": TPEX + "/web/emergingstock/aftertrading/daily_close_quotes/emdaily_result.php?l=zh-tw&d={roc}",
    "esb_B_www_daily": TPEX + "/www/zh-tw/emerging/dailyQuotes?date={roc}&response=json",
    "esb_C_www_stat": TPEX + "/www/zh-tw/emerging/statistics?date={roc}&response=json",
    "esb_D_peQry": TPEX + "/www/zh-tw/emerging/peQry?date={roc}&response=json",
    "esb_E_api": TPEX + "/openapi/v1/tpex_esb_latest_statistics",          # 對照組
    # ---- 上市（已知可用，當基準）----
    "listed_bwibbu": TWSE + "/afterTrading/BWIBBU_d?date={ymd}&selectType=ALL&response=json",
    "listed_mi": TWSE + "/afterTrading/MI_INDEX?date={ymd}&type=ALLBUT0999&response=json",
}


def business_days_back(n: int) -> date:
    d = date.today() - timedelta(days=1)
    cnt = 0
    while cnt < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            cnt += 1
    return d


def fmt(url: str, d: date) -> str:
    roc = to_roc(d)
    return url.format(ymd=d.strftime("%Y%m%d"), roc=f"{roc[:3]}/{roc[3:5]}/{roc[5:]}")


def grab(url: str) -> tuple[str, int, str]:
    """回傳 (狀態說明, 資料列數, 前兩列的指紋)。"""
    try:
        r = session().get(url, timeout=45)
    except requests.RequestException as exc:
        return f"ERR {str(exc)[:70]}", 0, ""
    if r.status_code != 200:
        return f"HTTP {r.status_code}", 0, ""
    body = r.text.strip()
    if body[:1] not in ("[", "{"):
        return f"非 JSON：{body[:70]}", 0, ""
    try:
        data = r.json()
    except ValueError:
        return "JSON 解析失敗", 0, ""

    rows = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        if isinstance(data.get("aaData"), list):
            rows = data["aaData"]
        elif isinstance(data.get("data"), list):
            rows = data["data"]
        else:
            for t in data.get("tables", []) or []:
                if isinstance(t.get("data"), list) and len(t["data"]) > len(rows):
                    rows = t["data"]
    if not rows:
        keys = list(data.keys())[:8] if isinstance(data, dict) else []
        return f"沒有資料列（keys={keys}）", 0, ""
    return "OK", len(rows), json.dumps(rows[:2], ensure_ascii=False)[:260]


def main() -> None:
    today_d = business_days_back(1)
    past_d = business_days_back(20)
    out = [f"# 第三輪探測：每日收盤價端點", "",
           f"近日 = {today_d}，20 個交易日前 = {past_d}", "",
           "判準：兩個日期回傳的指紋**必須不同**，才代表這支端點真的吃日期參數。", ""]

    for name, tpl in CANDIDATES.items():
        out.append(f"## `{name}`")
        out.append(f"`{tpl}`")
        s1, n1, f1 = grab(fmt(tpl, today_d))
        s2, n2, f2 = grab(fmt(tpl, past_d))
        out.append(f"- 近日：{s1}，{n1} 列")
        out.append(f"- 過去：{s2}，{n2} 列")
        if n1 and n2:
            verdict = "**吃日期 ✓**" if f1 != f2 else "**忽略日期 ✗（兩次結果相同）**"
            out.append(f"- 判定：{verdict}")
            out.append(f"- 近日樣本：`{f1}`")
            out.append(f"- 過去樣本：`{f2}`")
        out.append("")

    report = "\n".join(out)
    print(report)
    with open("probe3-report.md", "w", encoding="utf-8") as fh:
        fh.write(report)


if __name__ == "__main__":
    main()
