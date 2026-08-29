"""台灣官方開放資料來源清單。

只使用證交所（TWSE）與櫃買中心（TPEx）公開發布、供程式取用的端點。
公開資訊觀測站（MOPS）的網頁在 robots.txt 中被禁止爬取，本專案不使用。

端點都經過實地探測（見 reports/probe-report.md、reports/probe2-report.md）：

  上市  www.twse.com.tw   BWIBBU_d 一支就同時給收盤價、本益比、淨值比、殖利率
        openapi.twse.com.tw  月營收、公司基本資料（股數）、綜合損益表
        ※ openapi 主機對連續請求敏感，util 已針對它設 4 秒最小間隔並偵測流量保護頁

  上櫃  www.tpex.org.tw   報價（含股本）、本益比、公司基本資料、月營收、損益表（五種業別）

  興櫃  www.tpex.org.tw   報價、公司基本資料、月營收
        ※ 官方未發布興櫃的綜合損益表，因此興櫃沒有獲利成長率
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from util import ROOT, FetchError, get_json, log, rows_from_fields, to_roc

TWSE_API = "https://openapi.twse.com.tw/v1"
TWSE_WEB = "https://www.twse.com.tw/rwd/zh"
TPEX = "https://www.tpex.org.tw/openapi/v1"

CACHE = ROOT / ".endpoint_cache.json"

DATASETS: dict[str, list[str]] = {
    # ---- 上市 ----
    "listed_profile": [f"{TWSE_API}/opendata/t187ap03_L"],
    "listed_revenue": [f"{TWSE_API}/opendata/t187ap05_L"],
    "listed_income_ci": [f"{TWSE_API}/opendata/t187ap06_L_ci"],
    "listed_income_basi": [f"{TWSE_API}/opendata/t187ap06_L_basi"],
    "listed_income_bd": [f"{TWSE_API}/opendata/t187ap06_L_bd"],
    "listed_income_fh": [f"{TWSE_API}/opendata/t187ap06_L_fh"],
    "listed_income_ins": [f"{TWSE_API}/opendata/t187ap06_L_ins"],
    # ---- 上櫃 ----
    "otc_quotes": [f"{TPEX}/tpex_mainboard_daily_close_quotes"],
    "otc_pe": [f"{TPEX}/tpex_mainboard_peratio_analysis"],
    "otc_profile": [f"{TPEX}/mopsfin_t187ap03_O"],
    "otc_revenue": [f"{TPEX}/mopsfin_t187ap05_O"],
    "otc_income_ci": [f"{TPEX}/mopsfin_t187ap06_O_ci"],
    "otc_income_basi": [f"{TPEX}/mopsfin_t187ap06_O_basi"],
    "otc_income_bd": [f"{TPEX}/mopsfin_t187ap06_O_bd"],
    "otc_income_fh": [f"{TPEX}/mopsfin_t187ap06_O_fh"],
    "otc_income_ins": [f"{TPEX}/mopsfin_t187ap06_O_ins"],
    # ---- 興櫃 ----
    "esb_quotes": [f"{TPEX}/tpex_esb_latest_statistics"],
    "esb_profile": [f"{TPEX}/mopsfin_t187ap03_R"],
    "esb_revenue": [f"{TPEX}/t187ap05_R"],
}

# 單日全市場查詢（最新快照與歷史回補共用）
DAILY = {
    # 證券代號 / 證券名稱 / 收盤價 / 殖利率(%) / 股利年度 / 本益比 / 股價淨值比 / 財報年季
    "listed": TWSE_WEB + "/afterTrading/BWIBBU_d?date={ymd}&selectType=ALL&response=json",
    # 股票代號 / 公司名稱 / 本益比 / 每股股利 / 股利年度 / 殖利率(%) / 股價淨值比 / 財報年季
    "otc_pe": "https://www.tpex.org.tw/web/stock/aftertrading/peratio_analysis/"
              "pera_result.php?l=zh-tw&d={roc}&response=json",
    # 代號 / 名稱 / 收盤 / … / 發行股數 / …
    "otc_px": "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/"
              "stk_quote_result.php?l=zh-tw&d={roc}",
}


def _cache() -> dict[str, str]:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cache(c: dict[str, str]) -> None:
    CACHE.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")


def fetch(name: str, *, required: bool = False) -> list[dict[str, Any]]:
    """抓資料集，回傳 list of dict。全部候選都失敗時回 []（或丟例外）。"""
    candidates = DATASETS.get(name)
    if not candidates:
        raise KeyError(f"unknown dataset: {name}")

    cache = _cache()
    order = list(candidates)
    if cache.get(name) in order:
        order.remove(cache[name])
        order.insert(0, cache[name])

    errors = []
    for url in order:
        try:
            rows = rows_from_fields(get_json(url))
        except FetchError as exc:
            errors.append(str(exc))
            continue
        if rows:
            if cache.get(name) != url:
                cache[name] = url
                _save_cache(cache)
            log(f"  {name}: {len(rows)} 筆")
            return rows
        errors.append(f"空資料：{url}")

    msg = f"{name} 取得失敗\n    " + "\n    ".join(errors)
    if required:
        raise FetchError(msg)
    log(f"  [warn] {msg}")
    return []


def fetch_daily(kind: str, day: date) -> list[dict[str, Any]]:
    """抓某一天的全市場資料。假日或無資料時回 []。"""
    roc = to_roc(day)
    url = DAILY[kind].format(ymd=day.strftime("%Y%m%d"), roc=f"{roc[:3]}/{roc[3:5]}/{roc[5:]}")
    try:
        return rows_from_fields(get_json(url, tries=3))
    except FetchError as exc:
        log(f"    {kind} {day}: {exc}")
        return []


def latest_trading_day(kind: str = "listed", back: int = 10) -> tuple[date | None, list[dict]]:
    """從今天往回找最近一個有資料的交易日。"""
    d = date.today()
    for _ in range(back):
        if d.weekday() < 5:
            rows = fetch_daily(kind, d)
            if rows:
                return d, rows
        d -= timedelta(days=1)
    return None, []


def fetch_income(market: str) -> list[dict[str, Any]]:
    """綜合損益表分成一般業／金控／保險／證券／銀行五張表，合併回傳。"""
    rows: list[dict[str, Any]] = []
    for kind in ("ci", "basi", "bd", "fh", "ins"):
        key = f"{market}_income_{kind}"
        if key in DATASETS:
            rows.extend(fetch(key))
    return rows
