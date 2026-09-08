"""產生美股快照：TTM 本益比、股價營收比、淨值比、季度成長率。

輸出：
    docs/data/us/latest.json   個股最新指標
    docs/data/us/meta.json     資料日期、筆數、來源涵蓋狀況
    docs/data/us/market.json   全市場加總估值

跟台股版的差別（不是偷懶，是制度不同）：
    - 美國公司不公布月營收，只有季報，所以沒有「月營收年增率」，
      改用「季營收年增率」。
    - 殖利率要自己從股利推，SEC 的 XBRL 裡股利科目很雜，v1 先不做。
    - frames API 的季度框只收「會計季與日曆季對齊」的公司，
      九月結算那種非日曆年度的公司會被漏掉，這是方法本身的限制。

用法：
    python build_us_snapshot.py                # 含報價（Nasdaq 整批清單）
    python build_us_snapshot.py --no-prices    # 只用 SEC 官方資料
    python build_us_snapshot.py --prices stooq # 改用 Stooq（逐檔，只取前幾百檔）
    SEC_CONTACT="你的名字 you@example.com" python build_us_snapshot.py
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from statistics import median

import us_sources as U
from util import DATA_DIR, log, now_taipei, pct_change, rnd, write_json

OUT_DIR = DATA_DIR / "us"

# SEC 的季度資料框（CY2025Q4 這種）在第四季幾乎是空的 —— 多數公司不單獨
# 申報第四季，數字併在年報裡。因此「最近四季相加」在一年裡的多數時間都算不出
# TTM（實測 4812 家只有 170 家有 EPS）。改成以年報為錨：
#     TTM = 上一個完整年度 + 今年至今 − 去年同期至今
# 四季都齊全時仍優先用直接相加，那個最精確。


def anchor_quarter() -> tuple[int, int]:
    """最近一個「大家都報完了」的日曆季。財報有落後，所以從兩季前算起。"""
    today = date.today()
    y, q = today.year, (today.month - 1) // 3 + 1
    for _ in range(2):
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return y, q


def back(y: int, q: int, n: int) -> tuple[int, int]:
    """往前數 n 季。"""
    total = y * 4 + (q - 1) - n
    return total // 4, total % 4 + 1


def periods(cur: tuple[int, int] | None = None) -> dict:
    """算出這次要抓哪些期間，以及 TTM 的兩條算法各需要哪幾季。"""
    y, k = cur or anchor_quarter()
    consecutive = [back(y, k, i) for i in range(4)]          # 直接相加用
    if k == 4:
        # 第四季本身就是一個完整年度，年報直接就是 TTM
        ytd_cur: list[tuple[int, int]] = []
        ytd_prev: list[tuple[int, int]] = []
        fy = y
    else:
        ytd_cur = [(y, i) for i in range(1, k + 1)]
        ytd_prev = [(y - 1, i) for i in range(1, k + 1)]
        fy = y - 1
    same_q_ly = (y - 1, k)
    quarters = sorted(
        set(consecutive + ytd_cur + ytd_prev + [same_q_ly, (y - 1, 4)]),
        reverse=True,
    )
    return {
        "cur": (y, k),
        "same_q_ly": same_q_ly,
        "consecutive": consecutive,
        "ytd_cur": ytd_cur,
        "ytd_prev": ytd_prev,
        "fy": fy,
        "quarters": quarters,
    }


def ccp(y: int, q: int, *, instant: bool = False) -> str:
    return f"CY{y}Q{q}I" if instant else f"CY{y}Q{q}"


# 年報用的科目（都是期間型；股東權益與股數是時點型，用不到年報）
ANNUAL_TAGS = {
    "net": ("NetIncomeLoss", "USD"),
    "gp": ("GrossProfit", "USD"),
    "eps": ("EarningsPerShareDiluted", "USD-per-shares"),
}


def collect() -> tuple[dict, dict]:
    """把需要的科目一次抓齊，回傳 {科目: {期間: {cik: 值}}} 與期間設定。"""
    P = periods()
    log(f"基準季：{P['cur'][0]}Q{P['cur'][1]}；"
        f"季度框：{'、'.join(f'{y}Q{q}' for y, q in P['quarters'])}；年報：CY{P['fy']}")

    data: dict[str, dict] = {"rev": {}, "net": {}, "gp": {}, "eps": {}, "eq": {}, "sh": {}}
    for y, q in P["quarters"]:
        period, inst = ccp(y, q), ccp(y, q, instant=True)
        data["rev"][(y, q)] = U.revenue_frame(period)
        data["net"][(y, q)] = U.frame("NetIncomeLoss", "USD", period)
        data["gp"][(y, q)] = U.frame("GrossProfit", "USD", period)
        data["eps"][(y, q)] = U.frame("EarningsPerShareDiluted", "USD-per-shares", period)
        data["eq"][(y, q)] = U.frame("StockholdersEquity", "USD", inst)
        data["sh"][(y, q)] = U.frame("EntityCommonStockSharesOutstanding", "shares", inst,
                                     tax="dei")

    fy = f"CY{P['fy']}"
    annual = {"rev": U.revenue_frame(fy)}
    for key, (tag, uom) in ANNUAL_TAGS.items():
        annual[key] = U.frame(tag, uom, fy)
    data["annual"] = annual
    return data, P


def ttm(series: dict[tuple[int, int], dict[int, float]], P: dict, cik: int,
        annual: dict[int, float] | None = None) -> float | None:
    """近四季合計。先試直接相加，不齊再用年報錨定；兩條都湊不齊就留白。"""
    vals = [series.get(key, {}).get(cik) for key in P["consecutive"]]
    if all(v is not None for v in vals):
        return sum(vals)

    if annual is None:
        return None
    total = annual.get(cik)
    if total is None:
        return None
    for key in P["ytd_cur"]:
        v = series.get(key, {}).get(cik)
        if v is None:
            return None
        total += v
    for key in P["ytd_prev"]:
        v = series.get(key, {}).get(cik)
        if v is None:
            return None
        total -= v
    return total


def latest(series: dict[tuple[int, int], dict[int, float]], P: dict,
           cik: int) -> float | None:
    for key in P["quarters"]:
        v = series.get(key, {}).get(cik)
        if v is not None:
            return v
    return None


def build(source: str = "nasdaq") -> None:
    tickers = U.sec_tickers()
    log(f"SEC 代號對照表：{len(tickers)} 家")

    data, P = collect()
    cur, prev = P["cur"], P["same_q_ly"]
    ann = data["annual"]

    rows = []
    for cik, info in tickers.items():
        rev_ttm = ttm(data["rev"], P, cik, ann["rev"])
        net_ttm = ttm(data["net"], P, cik, ann["net"])
        eps_ttm = ttm(data["eps"], P, cik, ann["eps"])
        gp_ttm = ttm(data["gp"], P, cik, ann["gp"])
        equity = latest(data["eq"], P, cik)
        shares = latest(data["sh"], P, cik)

        rev_q = data["rev"].get(cur, {}).get(cik)
        rev_q_ly = data["rev"].get(prev, {}).get(cik)
        net_q = data["net"].get(cur, {}).get(cik)
        net_q_ly = data["net"].get(prev, {}).get(cik)

        # 一點基本面都沒有的才不進表。只有單季數字、湊不齊 TTM 的仍然列出來 ——
        # 跟台股版興櫃沒有本益比一樣，該留白的留白，但公司還是看得到。
        if all(v is None for v in (rev_ttm, net_ttm, eps_ttm, rev_q, net_q)):
            continue

        rows.append({
            "c": info["ticker"],
            "n": info["name"],
            "m": "us",
            "cik": cik,
            "shares": shares,
            "equity": equity,
            "fin": {
                "y": cur[0], "q": cur[1],
                "eps": rnd(eps_ttm),
                "rev": rev_ttm,
                "net": net_ttm,
                "gpm": rnd(gp_ttm / rev_ttm * 100, 1) if gp_ttm and rev_ttm else None,
                "npm": rnd(net_ttm / rev_ttm * 100, 1) if net_ttm and rev_ttm else None,
                "rev_yoy": rnd(pct_change(rev_q, rev_q_ly), 1),
                "net_yoy": rnd(pct_change(net_q, net_q_ly), 1),
            },
        })
    log(f"有基本面的公司：{len(rows)}")

    # ---- 報價 ----
    quotes: dict[str, dict] = {}
    if source != "none":
        log(f"抓報價（來源 {source}）…")
        quotes = U.QUOTE_PROVIDERS[source]([r["c"] for r in rows]) or {}
        hit = sum(1 for r in rows if r["c"] in quotes)
        log(f"對得上的報價：{hit}/{len(rows)} 檔")
        if hit == 0:
            log("  警告：一檔都沒對上，估值比率會全部留白")

    for r in rows:
        q = quotes.get(r["c"]) or {}
        p = q.get("p")
        r["p"] = rnd(p)
        shares, equity, fin = r.pop("shares"), r.pop("equity"), r["fin"]
        # 市值優先用「股價 × SEC 申報股數」，跟財報同源；沒有股數才退而用
        # 報價來源自己給的市值。
        cap = p * shares if p and shares else q.get("cap")
        r["cap"] = round(cap) if cap else None
        r["pe"] = rnd(p / fin["eps"]) if p and fin["eps"] and fin["eps"] > 0 else None
        r["ps"] = rnd(cap / fin["rev"]) if cap and fin["rev"] and fin["rev"] > 0 else None
        r["pb"] = rnd(cap / equity) if cap and equity and equity > 0 else None
        fin["rev"] = None  # 絕對金額不上前端，省檔案大小

    rows.sort(key=lambda r: -(r["cap"] or 0))

    # ---- 市場加總 ----
    pes = [r["pe"] for r in rows if r["pe"]]
    pss = [r["ps"] for r in rows if r["ps"]]
    caps = [r["cap"] for r in rows if r["cap"]]
    with_price = sum(1 for r in rows if r["p"])
    total_cap = sum(caps)
    total_net = sum(r["fin"]["net"] for r in rows if r["fin"]["net"] and r["cap"])
    market = {
        "asOf": date.today().isoformat(),
        "markets": {
            "us": {
                "label": "美股",
                "count": len(rows),
                "cap": total_cap or None,
                "pe": rnd(median(pes)) if pes else None,
                "ps": rnd(median(pss)) if pss else None,
                "peWeighted": rnd(total_cap / total_net) if total_cap and total_net > 0 else None,
                "withPE": len(pes),
                "withPS": len(pss),
            }
        },
    }

    meta = {
        "asOf": date.today().isoformat(),
        "updatedAt": now_taipei().strftime("%Y-%m-%dT%H:%M:%S"),
        "quarter": f"{cur[0]}Q{cur[1]}",
        "total": len(rows),
        "withPrice": with_price,
        "withPE": len(pes),
        "withPS": len(pss),
        "priceSource": source,
        "counts": {"us": len(rows)},
    }

    for r in rows:
        r["fin"] = {k: v for k, v in r["fin"].items() if v is not None}
        r.pop("cik", None)

    write_json(OUT_DIR / "latest.json", rows)
    write_json(OUT_DIR / "market.json", market)
    write_json(OUT_DIR / "meta.json", meta)
    log(f"完成：{len(rows)} 檔，有報價 {with_price}、有本益比 {len(pes)}、"
        f"有股價營收比 {len(pss)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", default="nasdaq", choices=sorted(U.QUOTE_PROVIDERS),
                    help="報價來源（預設 nasdaq，整批一次抓完）")
    ap.add_argument("--no-prices", action="store_true",
                    help="不抓報價，只用 SEC 官方資料（估值比率會留空）")
    args = ap.parse_args()
    build("none" if args.no_prices else args.prices)
    return 0


if __name__ == "__main__":
    sys.exit(main())
