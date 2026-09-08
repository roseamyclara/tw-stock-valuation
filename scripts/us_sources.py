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

from util import FetchError, get_json, log, session, try_json

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

def prices_stooq(tickers: list[str]) -> dict[str, float]:
    """Stooq 的免費日線 CSV。一次一檔，所以只對有基本面的個股抓。

    這是全流程唯一的非官方來源 —— SEC 不發布報價，美國交易所也沒有免費的
    整批收盤檔。若要維持「全部資料都來自官方」，用 --no-prices 跑，
    本益比／股價營收比／淨值比會留空，但 EPS、營收年增、利潤率仍然有。
    """
    out: dict[str, float] = {}
    s = session()
    for i, t in enumerate(tickers, 1):
        url = f"https://stooq.com/q/d/l/?s={t.lower()}.us&i=d"
        try:
            r = s.get(url, timeout=30)
            if r.status_code != 200 or not r.text.startswith("Date"):
                continue
            rows = list(csv.DictReader(io.StringIO(r.text)))
            if not rows:
                continue
            close = rows[-1].get("Close")
            if close and close != "N/D":
                out[t] = float(close)
        except Exception:  # noqa: BLE001
            continue
        if i % 250 == 0:
            log(f"  報價 {i}/{len(tickers)} …")
    return out


PRICE_PROVIDERS = {
    "stooq": prices_stooq,
    "none": lambda tickers: {},
}
