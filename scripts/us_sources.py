"""美股資料來源：SEC EDGAR 的 XBRL frames API，加上可抽換的報價來源。

為什麼用 frames 而不是 companyfacts：
    companyfacts 一家一支 API，五千多家要打五千多次；
    frames 是「一個會計科目 × 一個期間 → 全市場」，一次拿回一整欄，
    抓完整份快照只要二十幾次請求。

SEC 的規矩（https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data）：
    - User-Agent 必須帶得到人的聯絡方式，不能用瀏覽器字串
    - 每秒最多 10 次請求（util._MIN_INTERVAL 已設成 0.2 秒 = 每秒 5 次）
"""
from __future__ import annotations

import csv
import io
import os
from typing import Any

from util import FetchError, _wait_turn, get_json, log, session, try_json

SEC_CONTACT = os.environ.get("SEC_CONTACT", "tw-stock-valuation contact@example.com")
SEC_HEADERS = {"User-Agent": SEC_CONTACT, "Accept-Encoding": "gzip, deflate"}

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FRAMES = "https://data.sec.gov/api/xbrl/frames/{tax}/{tag}/{uom}/{ccp}.json"

# 同一個「營收」在不同公司會用不同科目名，依序試，先命中的算數。
# 括號內是 2025Q2 實測的涵蓋家數，可以看出為什麼一定要 fallback。
REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",  # 2,555
    "Revenues",                                             # 1,926
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
)


def sec_tickers() -> dict[int, dict[str, str]]:
    """cik -> {ticker, name}。同一家有多個代號時取第一個。"""
    payload = get_json(TICKERS_URL, headers=SEC_HEADERS)
    out: dict[int, dict[str, str]] = {}
    for row in payload.values():
        cik = int(row["cik_str"])
        if cik in out:
            continue
        out[cik] = {"ticker": str(row["ticker"]).strip().upper(),
                    "name": str(row["title"]).strip()}
    return out


def frame(tag: str, uom: str, ccp: str, *, tax: str = "us-gaap") -> dict[int, float]:
    """抓一個科目一個期間的全市場數字，回 cik -> val。抓不到回空的。"""
    url = FRAMES.format(tax=tax, tag=tag, uom=uom, ccp=ccp)
    payload = try_json(url, headers=SEC_HEADERS, tries=3)
    if not payload or "data" not in payload:
        return {}
    out: dict[int, float] = {}
    for row in payload["data"]:
        try:
            out[int(row["cik"])] = float(row["val"])
        except (KeyError, TypeError, ValueError):
            continue
    log(f"  frames {tax}/{tag} {ccp}: {len(out)} 家")
    return out


def revenue_frame(ccp: str) -> dict[int, float]:
    """營收：多個科目取聯集，先命中的優先。"""
    merged: dict[int, float] = {}
    for tag in REVENUE_TAGS:
        got = frame(tag, "USD", ccp)
        for cik, val in got.items():
            merged.setdefault(cik, val)
    return merged


# ------------------------------------------------------------------ 報價

# Nasdaq 自家頁面在用的上市股票清單端點。一次請求就拿回三個交易所的
# 收盤價與市值 —— 先前用 Stooq 逐檔抓，四千多次請求會被對方整批擋掉，
# 實測 4812 檔一檔都沒抓到。這裡改成整批，全程只打一次。
NASDAQ_SCREENER = (
    "https://api.nasdaq.com/api/screener/stocks"
    "?tableonly=true&limit=25000&download=true"
)


def _money(text: Any) -> float | None:
    """把 "$230.36"、"5,551,676,000,000" 這種字串轉成數字，非正數當沒有。"""
    if text is None:
        return None
    s = str(text).replace("$", "").replace(",", "").strip()
    if not s or s in {"N/A", "--", "0", "0.00"}:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v > 0 else None


def quotes_nasdaq(_tickers: list[str] | None = None) -> dict[str, dict[str, float | None]]:
    """ticker -> {"p": 收盤價, "cap": 市值}。抓不到就回空的。

    非官方端點，但它是 nasdaq.com 自己的個股清單頁在用的，資料是前一個
    交易日收盤。多股別的代號 Nasdaq 寫成 BRK/B、SEC 寫成 BRK-B，兩種都建索引。
    未在三大交易所掛牌（OTC）的公司這裡本來就沒有，會留白。
    """
    payload = try_json(NASDAQ_SCREENER, tries=3, headers={"Accept": "application/json"})
    rows = ((payload or {}).get("data") or {}).get("rows") or []
    out: dict[str, dict[str, float | None]] = {}
    for row in rows:
        sym = str(row.get("symbol") or "").strip().upper()
        price = _money(row.get("lastsale"))
        if not sym or price is None:
            continue
        rec = {"p": price, "cap": _money(row.get("marketCap"))}
        out[sym] = rec
        if "/" in sym:
            out.setdefault(sym.replace("/", "-"), rec)
    log(f"  Nasdaq 清單 {len(rows)} 檔，可用報價 {len(out)} 檔")
    return out


# Stooq 一檔一個請求，只適合小批。留著當備援，但預設不用。
STOOQ_MAX = 600


def quotes_stooq(tickers: list[str]) -> dict[str, dict[str, float | None]]:
    """Stooq 的免費日線 CSV。逐檔抓且會被限流，所以只取前 STOOQ_MAX 檔。"""
    out: dict[str, dict[str, float | None]] = {}
    s = session()
    picked = tickers[:STOOQ_MAX]
    for i, t in enumerate(picked, 1):
        url = f"https://stooq.com/q/d/l/?s={t.lower()}.us&i=d"
        try:
            _wait_turn(url)
            r = s.get(url, timeout=30)
            if r.status_code != 200 or not r.text.startswith("Date"):
                continue
            rows = list(csv.DictReader(io.StringIO(r.text)))
            if not rows:
                continue
            close = rows[-1].get("Close")
            if close and close != "N/D":
                out[t] = {"p": float(close), "cap": None}
        except Exception:  # noqa: BLE001
            continue
        if i % 100 == 0:
            log(f"  報價 {i}/{len(picked)}，成功 {len(out)}")
    return out


QUOTE_PROVIDERS = {
    "nasdaq": quotes_nasdaq,
    "stooq": quotes_stooq,
    "none": lambda tickers: {},
}
