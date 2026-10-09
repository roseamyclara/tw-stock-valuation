"""合併官方月份 CSV 與 OpenAPI；逐檔選最新月份，保留尚未申報的公司。

OpenAPI 是整批月報，申報期間可能仍停在上月。MOPS 提供的靜態 CSV
按市場、月份下載，每次只讀最近兩期，不逐家公司爬查詢頁。
"""
from __future__ import annotations

import csv
import io
import time
from collections import Counter
from datetime import date

import requests

import markets as M
import sources as S
from util import (FetchError, _wait_turn, add_months, log, month_key,
                  now_taipei, roc_ym, session)

MARKET_PATH = {"listed": "sii", "otc": "otc", "esb": "rotc"}


def monthly_url(market: str, year: int, month: int) -> str:
    return (f"https://mopsov.twse.com.tw/nas/t21/{MARKET_PATH[market]}/"
            f"t21sc03_{year - 1911}_{month}.csv")


def parse_csv(content: bytes, expected: tuple[int, int]) -> list[dict]:
    for encoding in ("utf-8-sig", "cp950"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise FetchError("月營收 CSV 編碼無法辨識")
    reader = csv.DictReader(io.StringIO(text))
    required = {"公司代號", "資料年月", "營業收入-當月營收"}
    if not required.issubset(reader.fieldnames or []):
        raise FetchError("月營收 CSV 欄位不符（可能是 HTML 保護頁）")
    rows = list(reader)
    if not rows or any(roc_ym(r.get("資料年月")) != expected for r in rows):
        raise FetchError("月營收 CSV 為空或資料月份不符")
    return rows


def fetch_month(market: str, year: int, month: int) -> list[dict]:
    url = monthly_url(market, year, month)
    for attempt in range(2):
        try:
            if attempt:
                time.sleep(2)
            _wait_turn(url)
            response = session().get(url, timeout=25)
            # 月初尚未產生，或來源拒絕存取，不反覆重試。
            if response.status_code in (403, 404):
                raise FetchError(f"HTTP {response.status_code}: {url}")
            response.raise_for_status()
            return parse_csv(response.content, (year, month))
        except requests.RequestException as exc:
            if attempt:
                raise FetchError(f"{url}: {exc}") from exc
    raise FetchError(url)


def merge_latest(*datasets: dict[str, dict], today: date) -> dict[str, dict]:
    """月份優先、再比出表日期；相同日期採後面的來源以接收更正。"""
    out = {}
    for records in datasets:
        for code, rec in records.items():
            period = roc_ym(rec.get("ym"))
            if not period or period >= (today.year, today.month) or rec.get("month") is None:
                continue
            old = out.get(code)
            rank = (period, rec.get("publishedAt") or "")
            old_rank = (roc_ym(old["ym"]), old.get("publishedAt") or "") if old else None
            if old_rank is None or rank >= old_rank:
                out[code] = dict(rec)
    return out


def fetch_revenue(market: str, previous: dict[str, dict], *, today: date | None = None):
    today = today or now_taipei().date()
    target = add_months(today.year, today.month, -1)
    sources = []
    candidates = [previous]
    raw = S.fetch(f"{market}_revenue")
    api = M.norm_revenue(raw)
    api_url = S.DATASETS[f"{market}_revenue"][0]
    for rec in api.values():
        rec["source"] = api_url
    candidates.append(api)
    sources.append({"url": api_url, "rows": len(api), "status": "ok" if api else "unavailable"})
    # 前一期仍可能有更正；尚未公告本期的公司仍保留前一期。
    for year, month in (add_months(*target, -1), target):
        url = monthly_url(market, year, month)
        try:
            records = M.norm_revenue(fetch_month(market, year, month))
            if not records:
                raise FetchError("沒有有效的營收列")
            for rec in records.values():
                rec["source"] = url
            candidates.append(records)
            sources.append({"url": url, "rows": len(records), "status": "ok"})
        except FetchError as exc:
            log(f"  [warn] {market} 月營收 CSV：{exc}")
            sources.append({"url": url, "rows": 0, "status": "unavailable", "error": str(exc)})
    result = merge_latest(*candidates, today=today)
    periods = Counter(month_key(*roc_ym(rec["ym"])) for rec in result.values())
    current = periods.get(month_key(*target), 0)
    status = {"targetMonth": month_key(*target), "months": dict(sorted(periods.items())),
              "currentMonthCount": current, "olderMonthCount": len(result) - current,
              "checkedAt": now_taipei().isoformat(timespec="seconds") + "+08:00",
              "sources": sources}
    log(f"  {market} 營收月份：{dict(periods)}；本期 {current} 筆")
    if not current:
        print(f"::warning::{market} 尚未取得 {month_key(*target)} 營收；保留可用舊期，請檢查來源")
    return result, status
