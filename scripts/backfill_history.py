"""回補近十年的每月估值快照。

官方的單日查詢端點一次給全市場，所以每個月只要抓一天（該月最後一個交易日），
十年約 120 個月 × 3 支端點，對官方站台負擔很小。

輸出：docs/data/history/<西元年>.json
    {"2026-08": {"d": "2026-08-28",
                 "s": {"2330": [pe, pb, dy, price]}}}
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import markets as M
import sources as S
from util import DATA_DIR, last_business_day, log, month_key, read_json, rnd, write_json

HIST_DIR = DATA_DIR / "history"


def month_snapshot(y: int, m: int) -> dict | None:
    """抓某月最後一個交易日的全市場估值。遇到假日往前退，最多退 7 天。"""
    for back in range(8):
        d = last_business_day(y, m) - timedelta(days=back)
        if d > date.today():
            continue

        listed = M.norm_daily_listed(S.fetch_daily("listed", d))
        if not listed:
            continue  # 該日無資料（假日或休市），再往前退一天

        otc_pe = M.norm_daily_otc_pe(S.fetch_daily("otc_pe", d))
        # 上櫃的每日收盤行情 php 端點會忽略日期參數、一律回當天的價格，
        # 存進歷史會變成「每個月都是今天的股價」，所以上櫃歷史不放價格。
        # 本益比、淨值比、殖利率的端點則確實依日期回傳，是可信的。

        stocks: dict[str, list] = {}
        for code, v in listed.items():
            if len(code) == 4 and code.isdigit():
                stocks[code] = [rnd(v.get("pe")), rnd(v.get("pb")), rnd(v.get("dy")), rnd(v.get("price"))]
        for code, v in otc_pe.items():
            if len(code) == 4 and code.isdigit():
                stocks[code] = [rnd(v.get("pe")), rnd(v.get("pb")), rnd(v.get("dy")), None]

        log(f"  {y}-{m:02d} ({d})：上市 {len(listed)}、上櫃 {len(otc_pe)}，合計 {len(stocks)} 檔")
        return {"d": d.isoformat(), "s": stocks}

    log(f"  {y}-{m:02d}：找不到有資料的交易日")
    return None


def main() -> None:
    years = int(os.environ.get("BACKFILL_YEARS") or 10)
    only = (os.environ.get("BACKFILL_START_YEAR") or "").strip()
    today = date.today()

    year_range = [int(only)] if only.isdigit() else list(range(today.year - years + 1, today.year + 1))
    log(f"回補年度：{year_range[0]}–{year_range[-1]}")

    for y in year_range:
        path = HIST_DIR / f"{y}.json"
        store = read_json(path, {}) or {}
        changed = False
        for m in range(1, 13):
            if y == today.year and m > today.month:
                break
            key = month_key(y, m)
            # 已有的月份就跳過；當月要重抓以取得最新值
            if key in store and not (y == today.year and m == today.month):
                continue
            snap = month_snapshot(y, m)
            if snap:
                store[key] = snap
                changed = True
        if changed:
            write_json(path, dict(sorted(store.items())))
            log(f"{y} 年：共 {len(store)} 個月")
        else:
            log(f"{y} 年：無新增")


if __name__ == "__main__":
    main()
