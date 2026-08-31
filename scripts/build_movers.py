"""算漲幅排行與「最近在漲什麼族群」。

讀 prices.json（每日收盤價）、latest.json（名稱／市場）、tags.json（業務標籤），
輸出 docs/data/movers.json：

    {"asOf": "2026-08-28",
     "periods": {
       "d1": {"days": 1, "from": "2026-08-27",
              "markets": {"listed": [ {c,n,r,p,t}, ... ], "otc": [...], "esb": [...]},
              "groups": [ {tag, n, med, top:[代號]}, ... ]}}}

族群用「中位數」排名而不是平均：一檔飆股就能把平均拉起來，中位數要多數成員
一起漲才會高，比較接近「這個族群在動」的直覺。
"""
from __future__ import annotations

import sys
from collections import defaultdict
from statistics import median

from util import DATA_DIR, log, read_json, rnd, write_json

PERIODS = {"d1": 1, "d5": 5, "d10": 10, "d30": 30}
TOP_N = 40          # 每個市場列出的檔數
MIN_GROUP = 3       # 族群至少要有幾檔才納入排名
TOP_GROUPS = 25


def main() -> int:
    prices = read_json(DATA_DIR / "prices.json", None)
    rows = read_json(DATA_DIR / "latest.json", [])
    tags = read_json(DATA_DIR / "tags.json", {}) or {}
    if not prices or not prices.get("dates") or not rows:
        log("缺少 prices.json 或 latest.json，跳過")
        return 0

    dates = prices["dates"]
    px = prices["p"]
    meta = {r["c"]: r for r in rows}
    log(f"價格資料 {len(dates)} 個交易日、{len(px)} 檔")

    def price_at(code: str, idx: int) -> float | None:
        """取第 idx 個交易日的收盤價；當天沒有就往前找最多 3 天（停牌／無成交）。"""
        arr = px.get(code)
        if not arr or idx < 0 or idx >= len(arr):
            return None
        for j in range(idx, max(-1, idx - 4), -1):
            if arr[j] is not None:
                return arr[j]
        return None

    out: dict = {"asOf": dates[-1], "tradingDays": len(dates), "periods": {}}
    last = len(dates) - 1

    for key, n in PERIODS.items():
        base_i = last - n
        if base_i < 0:
            log(f"{key}：資料只有 {len(dates)} 天，不足 {n + 1} 天，略過")
            continue

        returns: dict[str, float] = {}
        for code in meta:
            now = price_at(code, last)
            then = price_at(code, base_i)
            if now and then and then > 0:
                returns[code] = (now / then - 1) * 100

        markets: dict[str, list] = {}
        for m in ("listed", "otc", "esb"):
            sel = [(c, r) for c, r in returns.items() if meta[c]["m"] == m]
            sel.sort(key=lambda x: -x[1])
            markets[m] = [
                {
                    "c": c,
                    "n": meta[c]["n"],
                    "r": rnd(r),
                    "p": meta[c].get("p"),
                    "t": tags.get(c, [])[:3],
                    "i": meta[c].get("i"),
                }
                for c, r in sel[:TOP_N]
            ]

        # 族群：把每個標籤底下所有有報酬率的成員聚在一起
        by_tag: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for code, r in returns.items():
            for t in tags.get(code, []):
                by_tag[t].append((code, r))
        groups = []
        for tag, members in by_tag.items():
            if len(members) < MIN_GROUP:
                continue
            vals = [r for _, r in members]
            members.sort(key=lambda x: -x[1])
            groups.append({
                "tag": tag,
                "n": len(members),
                "med": rnd(median(vals)),
                "top": [c for c, _ in members[:3]],
            })
        groups.sort(key=lambda g: -(g["med"] or 0))

        out["periods"][key] = {
            "days": n,
            "from": dates[base_i],
            "counts": {m: sum(1 for c in returns if meta[c]["m"] == m) for m in ("listed", "otc", "esb")},
            "markets": markets,
            "groups": groups[:TOP_GROUPS],
            "groupsWeak": groups[-TOP_GROUPS:][::-1] if len(groups) > TOP_GROUPS else [],
        }
        log(f"{key}（{dates[base_i]} → {dates[last]}）：{len(returns)} 檔、{len(groups)} 個族群")

    write_json(DATA_DIR / "movers.json", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
