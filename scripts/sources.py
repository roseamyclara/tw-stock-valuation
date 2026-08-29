"""台灣官方開放資料來源清單。

只使用證交所（TWSE）與櫃買中心（TPEx）公開發布、供程式取用的 OpenAPI 端點。
公開資訊觀測站（MOPS）的網頁在 robots.txt 中被禁止爬取，本專案不使用。

有些端點名稱官方文件標示不一致，因此以「候選清單」方式撰寫：
依序嘗試，命中即記錄到 .endpoint_cache.json，下次直接走已知可用的那一個。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from util import ROOT, FetchError, get_json, log

TWSE = "https://openapi.twse.com.tw/v1"
TPEX = "https://www.tpex.org.tw/openapi/v1"

CACHE = ROOT / ".endpoint_cache.json"

# ---------------------------------------------------------------------------
# 資料集候選清單。第一個是最可能正確的名稱。
# ---------------------------------------------------------------------------
DATASETS: dict[str, list[str]] = {
    # ---- 上市（已實測可用）----
    "listed_profile": [f"{TWSE}/opendata/t187ap03_L"],
    "listed_pe": [f"{TWSE}/exchangeReport/BWIBBU_ALL"],
    "listed_price": [f"{TWSE}/exchangeReport/STOCK_DAY_ALL"],
    "listed_revenue": [f"{TWSE}/opendata/t187ap05_L"],
    # ---- 上市綜合損益表（依業別分五張表）----
    "listed_income_ci": [f"{TWSE}/opendata/t187ap06_L_ci"],
    "listed_income_basi": [f"{TWSE}/opendata/t187ap06_L_basi"],
    "listed_income_bd": [f"{TWSE}/opendata/t187ap06_L_bd"],
    "listed_income_fh": [f"{TWSE}/opendata/t187ap06_L_fh"],
    "listed_income_ins": [f"{TWSE}/opendata/t187ap06_L_ins"],
    # ---- 上櫃（前兩個已實測可用）----
    "otc_quotes": [f"{TPEX}/tpex_mainboard_daily_close_quotes"],
    "otc_pe": [f"{TPEX}/tpex_mainboard_peratio_analysis"],
    "otc_profile": [
        f"{TPEX}/mopsfin_t187ap03_O",
        f"{TPEX}/tpex_mainboard_company_profile",
        f"{TWSE}/opendata/t187ap03_O",
    ],
    "otc_revenue": [
        f"{TPEX}/mopsfin_t187ap05_O",
        f"{TPEX}/tpex_mainboard_monthly_sales",
        f"{TPEX}/t187ap05_O",
        f"{TWSE}/opendata/t187ap05_O",
    ],
    "otc_income_ci": [
        f"{TPEX}/mopsfin_t187ap06_O_ci",
        f"{TPEX}/t187ap06_O_ci",
        f"{TWSE}/opendata/t187ap06_O_ci",
    ],
    "otc_income_basi": [f"{TPEX}/mopsfin_t187ap06_O_basi"],
    "otc_income_bd": [f"{TPEX}/mopsfin_t187ap06_O_bd"],
    "otc_income_fh": [f"{TPEX}/mopsfin_t187ap06_O_fh"],
    "otc_income_ins": [f"{TPEX}/mopsfin_t187ap06_O_ins"],
    # ---- 興櫃（第一個已實測可用）----
    "esb_quotes": [f"{TPEX}/tpex_esb_latest_statistics"],
    "esb_profile": [
        f"{TPEX}/mopsfin_t187ap03_R",
        f"{TPEX}/tpex_esb_company_profile",
        f"{TWSE}/opendata/t187ap03_R",
    ],
    "esb_revenue": [
        f"{TPEX}/mopsfin_t187ap05_R",
        f"{TPEX}/t187ap05_R",
        f"{TWSE}/opendata/t187ap05_R",
    ],
    "esb_income_ci": [
        f"{TPEX}/mopsfin_t187ap06_R_ci",
        f"{TWSE}/opendata/t187ap06_R_ci",
    ],
    "esb_income_basi": [f"{TPEX}/mopsfin_t187ap06_R_basi"],
    "esb_income_bd": [f"{TPEX}/mopsfin_t187ap06_R_bd"],
    "esb_income_fh": [f"{TPEX}/mopsfin_t187ap06_R_fh"],
    "esb_income_ins": [f"{TPEX}/mopsfin_t187ap06_R_ins"],
}

# 歷史查詢端點（帶日期參數，供回補使用）
HISTORY: dict[str, list[str]] = {
    # 上市：個股日本益比、殖利率及股價淨值比（單日全市場）
    "listed_pe_day": [
        "https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?date={ymd}&selectType=ALL&response=json",
        "https://www.twse.com.tw/exchangeReport/BWIBBU_d?date={ymd}&selectType=ALL&response=json",
    ],
    # 上市：每日收盤行情（全部）
    "listed_price_day": [
        "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={ymd}&type=ALLBUT0999&response=json",
        "https://www.twse.com.tw/exchangeReport/MI_INDEX?date={ymd}&type=ALLBUT0999&response=json",
    ],
    # 上櫃：本益比、殖利率、股價淨值比（單日全市場）
    "otc_pe_day": [
        "https://www.tpex.org.tw/www/zh-tw/afterTrading/peQry?date={roc_slash}&response=json",
        "https://www.tpex.org.tw/web/stock/aftertrading/peratio_analysis/pera_result.php?l=zh-tw&d={roc_slash}&response=json",
    ],
    # 上櫃：每日收盤行情
    "otc_price_day": [
        "https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date={roc_slash}&response=json",
        "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&d={roc_slash}",
    ],
    # 興櫃：每日成交資訊
    "esb_price_day": [
        "https://www.tpex.org.tw/www/zh-tw/emerging/historical?date={roc_slash}&response=json",
        "https://www.tpex.org.tw/web/emergingstock/historical/daily/EMdaily_result.php?l=zh-tw&d={roc_slash}",
    ],
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
    """依候選順序抓取資料集，回傳 list of dict。全部失敗時回 []（或丟例外）。"""
    candidates = DATASETS.get(name)
    if not candidates:
        raise KeyError(f"unknown dataset: {name}")

    cache = _cache()
    order = list(candidates)
    if cache.get(name) in order:  # 已知可用的排到最前面
        order.remove(cache[name])
        order.insert(0, cache[name])

    errors = []
    for url in order:
        try:
            data = get_json(url)
        except FetchError as exc:
            errors.append(str(exc))
            continue
        if isinstance(data, dict):  # 有些端點包一層
            for key in ("data", "aaData", "records", "result"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        if isinstance(data, list) and data:
            if cache.get(name) != url:
                cache[name] = url
                _save_cache(cache)
            log(f"  {name}: {len(data)} 筆  <- {url}")
            return data
        errors.append(f"unexpected shape: {url}")

    msg = f"{name}: 所有候選端點皆失敗\n    " + "\n    ".join(errors)
    if required:
        raise FetchError(msg)
    log(f"  [warn] {msg}")
    return []


def fetch_income(market: str) -> list[dict[str, Any]]:
    """綜合損益表分成一般業/金控/保險/證券/銀行五張表，合併回傳。"""
    rows: list[dict[str, Any]] = []
    for kind in ("ci", "basi", "bd", "fh", "ins"):
        rows.extend(fetch(f"{market}_income_{kind}"))
    return rows
