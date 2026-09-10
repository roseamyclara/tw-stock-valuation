"""集保戶股權分散表：算出「400 張以上股東」的持股比例與月增減。

資料來源
    臺灣集中保管結算所開放資料「集保戶股權分散表」
    https://opendata.tdcc.com.tw/getOD.ashx?id=1-5
    每週五結算、隔週一公布，CSV 欄位為
        資料日期,證券代號,持股分級,人數,股數,占集保庫存數比例%

持股分級（實測 2026-09-04 全表驗證過邊界）
     1: 1-999          2: 1,000-5,000      3: 5,001-10,000
     4: 10,001-15,000  5: 15,001-20,000    6: 20,001-30,000
     7: 30,001-40,000  8: 40,001-50,000    9: 50,001-100,000
    10: 100,001-200,000                   11: 200,001-400,000
    12: 400,001-600,000                   13: 600,001-800,000
    14: 800,001-1,000,000                 15: 1,000,001 以上
    16: 差異數調整（券商庫存與集保庫存的對帳差額，不是真的股東）
    17: 合計

    一張 = 1,000 股，所以「大於 400 張」= 400,000 股以上 = 級距 12~15。
    級距 12 的下界是 400,001 股，剛好就是「大於」400 張，不含整數 400 張。

分母用級距 17 的合計（集保庫存數），跟集保自己的「占集保庫存數比例%」一致。
不是除以發行股數 —— 未存入集保的股票（例如部分實體保管）不在這份資料裡。

輸出
    docs/data/tdcc_history.json  滾動保留最近 KEEP_WEEKS 週的原始比例，供計算增減
    docs/data/tdcc.json          前端用：最新一週的比例，以及與四週前的差（百分點）
"""
from __future__ import annotations

import csv
import io
import sys
from datetime import date, datetime

from util import DATA_DIR, FetchError, log, session, write_json, read_json

URL = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"

# 「大於 400 張」的級距
BIG_LEVELS = ("12", "13", "14", "15")
TOTAL_LEVEL = "17"

# 保留幾週的歷史。要算「四週前」至少得留 5 筆，多留一些讓漏抓一兩週也不會斷。
KEEP_WEEKS = 13
# 「上個月」定義為四週前那一週
LOOKBACK = 4


def fetch_csv(*, tries: int = 4, timeout: int = 120) -> str:
    """抓回整份 CSV（約 2.4 MB）。集保沒有流量保護，單純重試即可。"""
    last: Exception | None = None
    for attempt in range(tries):
        try:
            r = session().get(URL, timeout=timeout)
            if r.status_code == 200 and "證券代號" in r.text[:200]:
                return r.text
            last = FetchError(f"HTTP {r.status_code} / 非預期內容")
        except Exception as exc:  # noqa: BLE001 - 網路層什麼都可能丟
            last = exc
        log(f"集保資料抓取失敗（第 {attempt + 1} 次）：{last}")
    raise FetchError(f"{URL} 重試 {tries} 次仍失敗：{last}")


def parse(text: str) -> tuple[str, dict[str, float]]:
    """CSV → (資料日期 YYYY-MM-DD, {證券代號: 400 張以上占集保庫存比例%})。

    代號欄位是靠右補空白的六碼字串（"2330  "），一定要 strip。
    """
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header or "證券代號" not in ",".join(header):
        raise FetchError("集保 CSV 缺表頭")

    day = ""
    big: dict[str, float] = {}
    total: dict[str, float] = {}
    for row in reader:
        if len(row) < 5:
            continue
        d, code, level, _people, shares = (c.strip() for c in row[:5])
        if not code:
            continue
        if not day:
            day = d
        try:
            sh = float(shares)
        except ValueError:
            continue
        if level in BIG_LEVELS:
            big[code] = big.get(code, 0.0) + sh
        elif level == TOTAL_LEVEL:
            total[code] = sh

    out: dict[str, float] = {}
    for code, tot in total.items():
        if tot <= 0:
            continue
        out[code] = round(big.get(code, 0.0) / tot * 100, 2)

    if not out:
        raise FetchError("集保 CSV 解析後沒有任何有效資料")
    return _fmt_day(day), out


def _fmt_day(s: str) -> str:
    try:
        return datetime.strptime(s, "%Y%m%d").date().isoformat()
    except ValueError:
        return date.today().isoformat()


def merge_history(hist: dict, day: str, ratios: dict[str, float]) -> dict:
    """把這一週併進滾動歷史；同一個資料日期重跑不會重複塞。

    結構：{"dates": [舊 → 新], "r": {代號: [對應每個日期的比例, 缺值為 null]}}
    """
    dates: list[str] = list(hist.get("dates") or [])
    r: dict[str, list] = {k: list(v) for k, v in (hist.get("r") or {}).items()}

    if day in dates:
        i = dates.index(day)
    else:
        dates.append(day)
        dates.sort()
        i = dates.index(day)
        for v in r.values():
            v.insert(i, None)

    for code, vals in r.items():
        # 補齊長度，避免歷史檔曾經缺欄
        while len(vals) < len(dates):
            vals.append(None)
        vals[i] = ratios.get(code)

    for code, val in ratios.items():
        if code not in r:
            row: list = [None] * len(dates)
            row[i] = val
            r[code] = row

    # 只留最近 KEEP_WEEKS 週
    if len(dates) > KEEP_WEEKS:
        cut = len(dates) - KEEP_WEEKS
        dates = dates[cut:]
        r = {k: v[cut:] for k, v in r.items()}

    # 期間內全部沒資料的代號就丟掉（下市、改代號）
    r = {k: v for k, v in r.items() if any(x is not None for x in v)}
    return {"dates": dates, "r": r}


def build_front(hist: dict) -> dict:
    """前端用：最新比例 + 與四週前的差（百分點）。

    {"date": "2026-09-04", "base": "2026-08-07", "d": {"2330": [87.51, 0.42]}}
    沒有基期時第二個值是 null，前端顯示「—」。
    """
    dates: list[str] = hist["dates"]
    if not dates:
        return {"date": None, "base": None, "d": {}}
    last = len(dates) - 1
    bi = last - LOOKBACK
    base = dates[bi] if bi >= 0 else None

    d: dict[str, list] = {}
    for code, vals in hist["r"].items():
        cur = vals[last]
        if cur is None:
            continue
        prev = vals[bi] if bi >= 0 else None
        chg = round(cur - prev, 2) if prev is not None else None
        d[code] = [cur, chg]
    return {"date": dates[last], "base": base, "d": d}


def main() -> int:
    log("抓集保戶股權分散表…")
    day, ratios = parse(fetch_csv())
    log(f"資料日期 {day}，解析到 {len(ratios)} 檔證券")

    # 只留我們追蹤的個股，把 ETF、權證、受益證券濾掉
    rows = read_json(DATA_DIR / "latest.json", []) or []
    codes = {r["c"] for r in rows if r.get("c")}
    if codes:
        ratios = {k: v for k, v in ratios.items() if k in codes}
    log(f"對上追蹤清單後剩 {len(ratios)} 檔")

    hist_path = DATA_DIR / "tdcc_history.json"
    hist = merge_history(read_json(hist_path, {}) or {}, day, ratios)
    write_json(hist_path, hist)

    front = build_front(hist)
    write_json(DATA_DIR / "tdcc.json", front)

    with_chg = sum(1 for v in front["d"].values() if v[1] is not None)
    log(f"歷史 {len(hist['dates'])} 週；輸出 {len(front['d'])} 檔，"
        f"其中 {with_chg} 檔有月增減（基期 {front['base'] or '尚未累積'}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
