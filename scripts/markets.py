"""三個市場（上市／上櫃／興櫃）的欄位對應與正規化。

各交易所的欄位命名不一致，這裡把它們統一成同一組內部欄位：
    code, name, industry, price, shares, pe, pb, dy
以及月營收與損益表的正規化結果。
"""
from __future__ import annotations

from typing import Any, Iterable

from util import num, pos

# 面額。台股絕大多數為 10 元；用股本回推股數時使用。
PAR_VALUE = 10.0

MARKETS = ("listed", "otc", "esb")

MARKET_LABEL = {"listed": "上市", "otc": "上櫃", "esb": "興櫃"}


def _first(row: dict, *keys: str) -> Any:
    for k in keys:
        if k in row and str(row[k]).strip() not in ("", "-"):
            return row[k]
    return None


def index_by_code(rows: Iterable[dict], *code_keys: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        code = _first(r, *code_keys)
        if code:
            out[str(code).strip()] = r
    return out


# ---------------------------------------------------------------- 名單／股數

def norm_profile_listed(rows: list[dict]) -> dict[str, dict]:
    """上市：t187ap03_L"""
    out = {}
    for r in rows:
        code = str(r.get("公司代號", "")).strip()
        if not code:
            continue
        shares = num(r.get("已發行普通股數或TDR原股發行股數")) or num(
            r.get("已發行普通股數或TDR原發行股數")
        )
        # 沒有股數欄位時，用實收資本額 / 面額回推
        if not shares:
            cap = num(r.get("實收資本額"))
            shares = cap / PAR_VALUE if cap else None
        out[code] = {
            "code": code,
            "name": str(r.get("公司簡稱") or r.get("公司名稱") or "").strip(),
            "shares": shares,
        }
    return out


def norm_profile_from_capital(rows: list[dict], code_key: str, name_key: str, cap_key: str) -> dict[str, dict]:
    """上櫃／興櫃：用股本欄位回推股數。"""
    out = {}
    for r in rows:
        code = str(r.get(code_key, "")).strip()
        if not code:
            continue
        cap = num(r.get(cap_key))
        out[code] = {
            "code": code,
            "name": str(r.get(name_key) or "").strip(),
            "shares": cap / PAR_VALUE if cap else None,
        }
    return out


# ---------------------------------------------------------------- 估值

def norm_valuation_listed(rows: list[dict]) -> dict[str, dict]:
    """上市：BWIBBU_ALL"""
    return {
        str(r.get("Code", "")).strip(): {
            "pe": pos(r.get("PEratio")),
            "pb": pos(r.get("PBratio")),
            "dy": num(r.get("DividendYield")),
        }
        for r in rows
        if str(r.get("Code", "")).strip()
    }


def norm_valuation_otc(rows: list[dict]) -> dict[str, dict]:
    """上櫃：tpex_mainboard_peratio_analysis"""
    return {
        str(r.get("SecuritiesCompanyCode", "")).strip(): {
            "pe": pos(r.get("PriceEarningRatio")),
            "pb": pos(r.get("PriceBookRatio")),
            "dy": num(r.get("YieldRatio")),
        }
        for r in rows
        if str(r.get("SecuritiesCompanyCode", "")).strip()
    }


# ---------------------------------------------------------------- 價格

def norm_price_listed(rows: list[dict]) -> dict[str, float]:
    out = {}
    for r in rows:
        code = str(r.get("Code", "")).strip()
        p = num(r.get("ClosingPrice"))
        if code and p:
            out[code] = p
    return out


def norm_price_otc(rows: list[dict]) -> dict[str, float]:
    out = {}
    for r in rows:
        code = str(r.get("SecuritiesCompanyCode", "")).strip()
        p = num(r.get("Close")) or num(r.get("Average"))
        if code and p:
            out[code] = p
    return out


def norm_price_esb(rows: list[dict]) -> dict[str, float]:
    """興櫃沒有收盤價概念，用當日均價；無均價時退回最新成交價。"""
    out = {}
    for r in rows:
        code = str(r.get("SecuritiesCompanyCode", "")).strip()
        p = num(r.get("Average")) or num(r.get("LatestPrice")) or num(r.get("PreviousAveragePrice"))
        if code and p:
            out[code] = p
    return out


# ---------------------------------------------------------------- 月營收

REV_KEYS = {
    "code": ("公司代號", "CompanyCode", "SecuritiesCompanyCode"),
    "name": ("公司名稱", "CompanyName"),
    "industry": ("產業別", "Industry"),
    "ym": ("資料年月", "DataYearMonth", "YearMonth"),
    "month": ("營業收入-當月營收", "CurrentMonthRevenue", "當月營收"),
    "last_month": ("營業收入-上月營收", "LastMonthRevenue"),
    "last_year_month": ("營業收入-去年當月營收", "SameMonthLastYearRevenue"),
    "mom": ("營業收入-上月比較增減(%)", "MoMChange"),
    "yoy": ("營業收入-去年同月增減(%)", "YoYChange"),
    "cum": ("累計營業收入-當月累計營收", "CumulativeRevenue"),
    "cum_ly": ("累計營業收入-去年累計營收", "CumulativeRevenueLastYear"),
    "cum_yoy": ("累計營業收入-前期比較增減(%)", "CumulativeYoYChange"),
}


def norm_revenue(rows: list[dict]) -> dict[str, dict]:
    """月營收正規化。上市／上櫃／興櫃的欄位名相同（皆源自公開資訊觀測站格式）。"""
    out: dict[str, dict] = {}
    for r in rows:
        code = str(_first(r, *REV_KEYS["code"]) or "").strip()
        if not code:
            continue
        rec = {
            "ym": str(_first(r, *REV_KEYS["ym"]) or "").strip(),
            "industry": str(_first(r, *REV_KEYS["industry"]) or "").strip() or None,
            "name": str(_first(r, *REV_KEYS["name"]) or "").strip() or None,
            "month": num(_first(r, *REV_KEYS["month"])),
            "last_year_month": num(_first(r, *REV_KEYS["last_year_month"])),
            "mom": num(_first(r, *REV_KEYS["mom"])),
            "yoy": num(_first(r, *REV_KEYS["yoy"])),
            "cum": num(_first(r, *REV_KEYS["cum"])),
            "cum_ly": num(_first(r, *REV_KEYS["cum_ly"])),
            "cum_yoy": num(_first(r, *REV_KEYS["cum_yoy"])),
        }
        out[code] = rec
    return out


# ---------------------------------------------------------------- 損益表

INC_KEYS = {
    "code": ("公司代號", "CompanyCode", "SecuritiesCompanyCode"),
    "year": ("年度", "Year"),
    "quarter": ("季別", "Quarter", "Season"),
    "revenue": ("營業收入", "營業收入合計", "收入合計", "淨收益"),
    "gross": ("營業毛利（毛損）淨額", "營業毛利（毛損）", "營業毛利"),
    "op": ("營業利益（損失）", "營業利益"),
    "pretax": ("稅前淨利（淨損）", "繼續營業單位稅前淨利（淨損）", "稅前淨利"),
    "net": ("淨利（淨損）歸屬於母公司業主", "本期淨利（淨損）", "本期稅後淨利（淨損）"),
    "eps": ("基本每股盈餘（元）", "基本每股盈餘"),
}


def norm_income(rows: list[dict]) -> dict[str, dict]:
    """綜合損益表正規化。數字為「本年度累計至該季」。

    金融、保險、證券業的欄位名與一般業不同，這裡用候選清單一併吸收。
    """
    out: dict[str, dict] = {}
    for r in rows:
        code = str(_first(r, *INC_KEYS["code"]) or "").strip()
        if not code:
            continue
        year = num(_first(r, *INC_KEYS["year"]))
        quarter = num(_first(r, *INC_KEYS["quarter"]))
        rec = {
            "year": int(year) if year else None,   # 民國年
            "quarter": int(quarter) if quarter else None,
            "revenue": num(_first(r, *INC_KEYS["revenue"])),
            "gross": num(_first(r, *INC_KEYS["gross"])),
            "op": num(_first(r, *INC_KEYS["op"])),
            "pretax": num(_first(r, *INC_KEYS["pretax"])),
            "net": num(_first(r, *INC_KEYS["net"])),
            "eps": num(_first(r, *INC_KEYS["eps"])),
        }
        prev = out.get(code)
        # 同一家公司若出現多筆，保留較新的期別
        if prev and (prev["year"], prev["quarter"]) >= (rec["year"] or 0, rec["quarter"] or 0):
            continue
        out[code] = rec
    return out
