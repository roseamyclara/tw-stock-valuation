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
    python build_us_snapshot.py                # 含報價（Stooq）
    python build_us_snapshot.py --no-prices    # 只用 SEC 官方資料
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

# 需要幾季：最近 4 季算 TTM，再往前 1 季（去年同期）算年增率 → 共 5 季
QUARTERS_BACK = 5


def recent_quarters(n: int) -> list[tuple[int, int]]:
    """回傳最近 n 個「已經有人報完」的日曆季，新到舊。

    財報有落後，最近一季通常還沒填滿，所以從兩季前開始往回數。
    """
    today = date.today()
    y, q = today.year, (today.month - 1) // 3 + 1
    for _ in range(2):  # 退兩季，避開還沒報完的期間
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    out = []
    for _ in range(n):
        out.append((y, q))
        q -= 1
        if q == 0:
            y, q = y - 1, 4
    return out


def ccp(y: int, q: int, *, instant: bool = False) -> str:
    return f"CY{y}Q{q}I" if instant else f"CY{y}Q{q}"


def collect() -> tuple[dict, list[tuple[int, int]]]:
    """把需要的科目一次抓齊，回傳 {科目: {期間: {cik: 值}}}。"""
    qs = recent_quarters(QUARTERS_BACK)
    log(f"期間：{'、'.join(f'{y}Q{q}' for y, q in qs)}")

    data: dict[str, dict[tuple[int, int], dict[int, float]]] = {
        "rev": {}, "net": {}, "gp": {}, "eps": {}, "eq": {}, "sh": {},
    }
    for y, q in qs:
        period, inst = ccp(y, q), ccp(y, q, instant=True)
        data["rev"][(y, q)] = U.revenue_frame(period)
        data["net"][(y, q)] = U.frame("NetIncomeLoss", "USD", period)
        data["gp"][(y, q)] = U.frame("GrossProfit", "USD", period)
        data["eps"][(y, q)] = U.frame("EarningsPerShareDiluted", "USD-per-shares", period)
        data["eq"][(y, q)] = U.frame("StockholdersEquity", "USD", inst)
        data["sh"][(y, q)] = U.frame("EntityCommonStockSharesOutstanding", "shares", inst,
                                     tax="dei")
    return data, qs


def ttm(series: dict[tuple[int, int], dict[int, float]], qs: list[tuple[int, int]],
        cik: int) -> float | None:
    """最近四季加總。缺任何一季就不給值 —— 寧可留白也不要給半年當一年。"""
    vals = []
    for key in qs[:4]:
        v = series.get(key, {}).get(cik)
        if v is None:
            return None
        vals.append(v)
    return sum(vals)


def latest(series: dict[tuple[int, int], dict[int, float]], qs: list[tuple[int, int]],
           cik: int) -> float | None:
    for key in qs:
        v = series.get(key, {}).get(cik)
        if v is not None:
            return v
    return None


def build(no_prices: bool) -> None:
    tickers = U.sec_tickers()
    log(f"SEC 代號對照表：{len(tickers)} 家")

    data, qs = collect()
    cur, prev = qs[0], qs[4]  # 最近一季 vs 去年同期

    rows = []
    for cik, info in tickers.items():
        rev_ttm = ttm(data["rev"], qs, cik)
        net_ttm = ttm(data["net"], qs, cik)
        eps_ttm = ttm(data["eps"], qs, cik)
        gp_ttm = ttm(data["gp"], qs, cik)
        equity = latest(data["eq"], qs, cik)
        shares = latest(data["sh"], qs, cik)

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
    prices: dict[str, float] = {}
    if not no_prices:
        provider = U.PRICE_PROVIDERS["stooq"]
        log(f"抓報價（{len(rows)} 檔）…")
        prices = provider([r["c"] for r in rows])
        log(f"抓到報價：{len(prices)} 檔")

    for r in rows:
        p = prices.get(r["c"])
        r["p"] = rnd(p)
        shares, equity, fin = r.pop("shares"), r.pop("equity"), r["fin"]
        cap = p * shares if p and shares else None
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
        "withPrice": len(prices),
        "withPE": len(pes),
        "withPS": len(pss),
        "priceSource": "none" if no_prices else "stooq",
        "counts": {"us": len(rows)},
    }

    for r in rows:
        r["fin"] = {k: v for k, v in r["fin"].items() if v is not None}
        r.pop("cik", None)

    write_json(OUT_DIR / "latest.json", rows)
    write_json(OUT_DIR / "market.json", market)
    write_json(OUT_DIR / "meta.json", meta)
    log(f"完成：{len(rows)} 檔，有本益比 {len(pes)}、有股價營收比 {len(pss)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-prices", action="store_true",
                    help="不抓報價，只用 SEC 官方資料（估值比率會留空）")
    args = ap.parse_args()
    build(args.no_prices)
    return 0


if __name__ == "__main__":
    sys.exit(main())
