"""收集每日收盤價，供漲幅排行使用。

輸出 docs/data/prices.json：
    {"dates": ["2026-07-01", ...],           # 由舊到新的交易日
     "p": {"2330": [1180.0, null, 1195.0]}}  # 與 dates 等長，缺值為 null

各市場的來源與限制（見 reports/probe2-report.md 的實測）：
  上市  BWIBBU_d          吃日期，含收盤價，可回補
  上櫃  stk_wn1430        吃日期，含收盤價，可回補
  興櫃  沒有整批的歷史端點；每次更新存當天均價，另可由報價表的「前一日均價」
        補回前一個交易日。因此興櫃的中長天期漲幅要等資料累積。
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from util import DATA_DIR, FetchError, get_json, log, num, read_json, to_roc, write_json

PRICES = DATA_DIR / "prices.json"
KEEP_DAYS = 70          # 保留的交易日數；30 日漲幅需要 31 個交易日
BACKFILL_DAYS = 50      # 回補時往前找幾個日曆日

TWSE_BWIBBU = ("https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d"
               "?date={ymd}&selectType=ALL&response=json")
TPEX_OTC = ("https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/"
            "stk_wn1430_result.php?l=zh-tw&d={roc}&se=EW")
TPEX_ESB = "https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics"


def _payload_rows(payload) -> list:
    """把回傳攤平成資料列（這兩支端點都沒有 fields，只能用位置取值）。"""
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("aaData", "data"):
        if isinstance(payload.get(key), list):
            return payload[key]
    best: list = []
    for t in payload.get("tables", []) or []:
        rows = t.get("data") or []
        if len(rows) > len(best):
            best = rows
    return best


def _closes(rows: list, code_i: int, close_i: int) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in rows:
        if not isinstance(r, list) or len(r) <= max(code_i, close_i):
            continue
        code = str(r[code_i]).strip().strip('="')
        if not (len(code) == 4 and code.isdigit()):
            continue          # 濾掉 ETF、權證、債券
        p = num(r[close_i])
        if p and p > 0:
            out[code] = p
    return out


def listed_closes(d: date) -> dict[str, float]:
    """上市：[證券代號, 證券名稱, 收盤價, 殖利率, 股利年度, 本益比, 股價淨值比, 財報年季]"""
    try:
        rows = _payload_rows(get_json(TWSE_BWIBBU.format(ymd=d.strftime("%Y%m%d")), tries=3))
    except FetchError as exc:
        log(f"    上市 {d}: {exc}")
        return {}
    return _closes(rows, 0, 2)


def otc_closes(d: date) -> dict[str, float]:
    """上櫃：[代號, 名稱, 收盤, 漲跌, 開盤, 最高, 最低, 成交股數, …]"""
    roc = to_roc(d)
    url = TPEX_OTC.format(roc=f"{roc[:3]}/{roc[3:5]}/{roc[5:]}")
    try:
        rows = _payload_rows(get_json(url, tries=3))
    except FetchError as exc:
        log(f"    上櫃 {d}: {exc}")
        return {}
    return _closes(rows, 0, 2)


def esb_closes_today() -> tuple[dict[str, float], dict[str, float]]:
    """興櫃：回傳 (當日均價, 前一交易日均價)。沒有整批歷史端點，只能這樣取。"""
    try:
        rows = get_json(TPEX_ESB, tries=3)
    except FetchError as exc:
        log(f"    興櫃: {exc}")
        return {}, {}
    today: dict[str, float] = {}
    prev: dict[str, float] = {}
    for r in rows if isinstance(rows, list) else []:
        code = str(r.get("SecuritiesCompanyCode", "")).strip()
        if not (len(code) == 4 and code.isdigit()):
            continue
        p = num(r.get("Average")) or num(r.get("LatestPrice"))
        q = num(r.get("PreviousAveragePrice"))
        if p and p > 0:
            today[code] = p
        if q and q > 0:
            prev[code] = q
    return today, prev


def load() -> dict:
    d = read_json(PRICES, None)
    if not isinstance(d, dict) or "dates" not in d:
        return {"dates": [], "p": {}}
    return d


def put(store: dict, day: str, closes: dict[str, float]) -> None:
    """把某一天的收盤價寫進 store（自動對齊各檔的陣列長度）。"""
    if not closes:
        return
    dates = store["dates"]
    if day in dates:
        i = dates.index(day)
    else:
        dates.append(day)
        dates.sort()
        i = dates.index(day)
        for arr in store["p"].values():
            arr.insert(i, None)
    n = len(dates)
    for code, price in closes.items():
        arr = store["p"].setdefault(code, [None] * n)
        while len(arr) < n:
            arr.append(None)
        arr[i] = price


def trim(store: dict, keep: int) -> None:
    dates = store["dates"]
    if len(dates) <= keep:
        return
    cut = len(dates) - keep
    store["dates"] = dates[cut:]
    for code in list(store["p"]):
        arr = store["p"][code][cut:]
        if any(v is not None for v in arr):
            store["p"][code] = arr
        else:
            del store["p"][code]


def main() -> int:
    backfill = "--backfill" in sys.argv
    store = load()
    have = set(store["dates"])
    log(f"現有交易日 {len(have)} 天")

    days = [date.today() - timedelta(days=i) for i in range(BACKFILL_DAYS if backfill else 5)]
    days = [d for d in days if d.weekday() < 5]
    days.sort()

    added = 0
    for d in days:
        key = d.isoformat()
        if key in have:
            continue
        lc = listed_closes(d)
        if not lc:
            continue          # 非交易日
        oc = otc_closes(d)
        put(store, key, {**lc, **oc})
        added += 1
        log(f"  {key}：上市 {len(lc)}、上櫃 {len(oc)}")

    # 興櫃只能取當天與前一交易日
    esb_today, esb_prev = esb_closes_today()
    if esb_today:
        dates = store["dates"]
        latest = dates[-1] if dates else date.today().isoformat()
        put(store, latest, esb_today)
        if esb_prev and len(dates) >= 2:
            put(store, dates[-2], esb_prev)
        log(f"  興櫃：當日 {len(esb_today)}、前一日 {len(esb_prev)}")

    trim(store, KEEP_DAYS)
    write_json(PRICES, store)
    log(f"完成：{len(store['dates'])} 個交易日、{len(store['p'])} 檔，新增 {added} 天")
    return 0


if __name__ == "__main__":
    sys.exit(main())
