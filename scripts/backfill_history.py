"""回補近十年的每月估值快照。

官方每日查詢端點一次給全市場，所以每個月只需要抓一天（該月最後一個交易日），
十年約 120 次請求 × 市場數，對官方站台負擔很小。

輸出：docs/data/history/<西元年>.json
    {"2026-08": {"d": "2026-08-28",
                 "s": {"2330": [pe, pb, dy, price], ...}}}
"""
from __future__ import annotations

import os
from datetime import date, timedelta

from util import (
    DATA_DIR,
    FetchError,
    get_json,
    last_business_day,
    log,
    month_key,
    num,
    pos,
    read_json,
    rnd,
    to_roc,
    write_json,
)

HIST_DIR = DATA_DIR / "history"

TWSE_PE = "https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?date={ymd}&selectType=ALL&response=json"
TWSE_PX = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={ymd}&type=ALLBUT0999&response=json"
TPEX_PE = "https://www.tpex.org.tw/www/zh-tw/afterTrading/peQry?date={roc}&response=json"
TPEX_PX = "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date={roc}&response=json"


def _rows(payload) -> tuple[list[str], list[list]]:
    """把官方各種回傳格式攤平成 (欄位名, 資料列)。"""
    if not isinstance(payload, dict):
        return [], payload if isinstance(payload, list) else []
    if payload.get("stat") not in (None, "OK") and "tables" not in payload:
        return [], []
    # 新版 TPEx / TWSE：tables[]
    for t in payload.get("tables", []) or []:
        data = t.get("data") or []
        if len(data) > 50:  # 個股表才會有幾百列
            return [str(f) for f in (t.get("fields") or [])], data
    # 舊版 TWSE：頂層 fields + data
    if payload.get("data"):
        return [str(f) for f in (payload.get("fields") or [])], payload["data"]
    for key in ("data5", "data4", "data3", "data2", "data1", "aaData"):
        if payload.get(key):
            return [str(f) for f in (payload.get("fields") or [])], payload[key]
    return [], []


def _col(fields: list[str], *needles: str) -> int | None:
    for i, f in enumerate(fields):
        for n in needles:
            if n in f:
                return i
    return None


def fetch_valuation(url: str) -> dict[str, list]:
    """抓單日全市場的本益比／淨值比／殖利率。"""
    try:
        payload = get_json(url, tries=3, pause=1.2)
    except FetchError as exc:
        log(f"    {exc}")
        return {}
    fields, data = _rows(payload)
    if not data:
        return {}
    ci = _col(fields, "代號") or 0
    c_dy = _col(fields, "殖利率")
    c_pe = _col(fields, "本益比")
    c_pb = _col(fields, "淨值比")
    out = {}
    for row in data:
        if not row or len(row) <= ci:
            continue
        code = str(row[ci]).strip().strip('="')
        if not (len(code) == 4 and code.isdigit()):
            continue
        out[code] = [
            pos(row[c_pe]) if c_pe is not None and len(row) > c_pe else None,
            pos(row[c_pb]) if c_pb is not None and len(row) > c_pb else None,
            num(row[c_dy]) if c_dy is not None and len(row) > c_dy else None,
        ]
    return out


def fetch_prices(url: str) -> dict[str, float]:
    try:
        payload = get_json(url, tries=3, pause=1.2)
    except FetchError as exc:
        log(f"    {exc}")
        return {}
    fields, data = _rows(payload)
    if not data:
        return {}
    ci = _col(fields, "代號") or 0
    cp = _col(fields, "收盤價", "收盤")
    if cp is None:
        return {}
    out = {}
    for row in data:
        if not row or len(row) <= max(ci, cp):
            continue
        code = str(row[ci]).strip().strip('="')
        if not (len(code) == 4 and code.isdigit()):
            continue
        p = num(row[cp])
        if p:
            out[code] = p
    return out


def month_snapshot(y: int, m: int) -> dict | None:
    """抓某個月最後一個交易日的全市場估值。遇到假日往前退最多 6 天。"""
    for back in range(7):
        d = last_business_day(y, m) - timedelta(days=back)
        if d > date.today():
            continue
        ymd = d.strftime("%Y%m%d")
        roc = to_roc(d)
        roc_slash = f"{roc[:3]}/{roc[3:5]}/{roc[5:]}"

        val = fetch_valuation(TWSE_PE.format(ymd=ymd))
        if not val:
            continue  # 該日無資料（假日），往前退一天

        px = fetch_prices(TWSE_PX.format(ymd=ymd))
        otc_val = fetch_valuation(TPEX_PE.format(roc=roc_slash))
        otc_px = fetch_prices(TPEX_PX.format(roc=roc_slash))

        stocks: dict[str, list] = {}
        for code, v in {**val, **otc_val}.items():
            price = px.get(code) or otc_px.get(code)
            stocks[code] = [
                rnd(v[0]), rnd(v[1]), rnd(v[2]), rnd(price),
            ]
        log(f"  {y}-{m:02d} ({d}): 上市 {len(val)}、上櫃 {len(otc_val)}，合計 {len(stocks)} 檔")
        return {"d": d.isoformat(), "s": stocks}
    log(f"  {y}-{m:02d}: 找不到有資料的交易日")
    return None


def main() -> None:
    years = int(os.environ.get("BACKFILL_YEARS") or 10)
    only = os.environ.get("BACKFILL_START_YEAR") or ""
    today = date.today()

    if only.strip().isdigit():
        year_range = [int(only)]
    else:
        year_range = list(range(today.year - years + 1, today.year + 1))

    for y in year_range:
        path = HIST_DIR / f"{y}.json"
        store = read_json(path, {}) or {}
        changed = False
        for m in range(1, 13):
            if y == today.year and m > today.month:
                break
            key = month_key(y, m)
            # 已有資料就跳過（除了當月，當月要更新到最新）
            if key in store and not (y == today.year and m == today.month):
                continue
            snap = month_snapshot(y, m)
            if snap:
                store[key] = snap
                changed = True
        if changed:
            write_json(path, dict(sorted(store.items())))
            log(f"{y} 年：寫入 {len(store)} 個月")
        else:
            log(f"{y} 年：無新增")


if __name__ == "__main__":
    main()
