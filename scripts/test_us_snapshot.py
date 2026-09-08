"""build_us_snapshot 的離線測試。

用假的 SEC 回應（形狀照 data.sec.gov 實測結果）跑完整條流程，
驗證 TTM 的兩條算法、年增率、估值比率，以及「資料不齊就留白」的行為。

    python test_us_snapshot.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import build_us_snapshot as B
import us_sources as U

FAKE_TICKERS = {
    1045810: {"ticker": "NVDA", "name": "NVIDIA CORP"},
    320193:  {"ticker": "AAPL", "name": "Apple Inc."},
    2098:    {"ticker": "ACU",  "name": "ACME UNITED CORP"},
    999001:  {"ticker": "PART", "name": "PARTIAL DATA CO"},   # 只有單季 → TTM 應留白
    999002:  {"ticker": "LOSS", "name": "LOSSMAKER INC"},     # 虧損 → 本益比應留白
    999003:  {"ticker": "EMPTY", "name": "NO FUNDAMENTALS"},  # 什麼都沒有 → 不進表
    999004:  {"ticker": "NOSH", "name": "NO SHARE COUNT CO"}, # 沒股數 → 市值退用報價來源的
}

P = B.periods()
QS = P["quarters"]
CUR, PREV = P["cur"], P["same_q_ly"]
Q4 = next((q for q in QS if q[1] == 4), None)


def _series(per_cik: dict[int, list[float | None]]) -> dict:
    """把 {cik: [最近季, 次近季, ...]} 轉成 {期間: {cik: 值}}。"""
    out = {q: {} for q in QS}
    for cik, vals in per_cik.items():
        for q, v in zip(QS, vals):
            if v is not None:
                out[q][cik] = v
    return out


def _drop_q4(series: dict) -> dict:
    """把第四季挖掉 —— 這才是 SEC 季度框的真實樣子。"""
    return {q: ({} if q == Q4 else vals) for q, vals in series.items()}


# NVDA 四季齊全 → 走「直接相加」
# AAPL 缺第四季 → 走「年報錨定」
REV = _series({
    1045810: [46_000e6, 44_000e6, 39_000e6, 35_000e6, 30_000e6],
    320193:  [94_000e6, None,     90_000e6, 124_000e6, 85_000e6],
    2098:    [54e6, 52e6, 50e6, 48e6, 50e6],
    999001:  [10e6, None, None, None, 9e6],
    999002:  [5e6, 5e6, 5e6, 5e6, 4e6],
    999004:  [8e6, 8e6, 8e6, 8e6, 7e6],
})
NET = _series({
    1045810: [26_000e6, 25_000e6, 22_000e6, 19_000e6, 16_000e6],
    320193:  [23_000e6, None,     23_000e6, 36_000e6, 21_000e6],
    2098:    [4e6, 3.8e6, 3.5e6, 3.2e6, 3.4e6],
    999001:  [1e6, None, None, None, 0.9e6],
    999002:  [-2e6, -2e6, -2e6, -2e6, -1e6],
    999004:  [1e6, 1e6, 1e6, 1e6, 0.8e6],
})
GP = _series({
    1045810: [34_000e6, 33_000e6, 29_000e6, 26_000e6, 22_000e6],
    2098:    [20e6, 19e6, 18e6, 17e6, 18e6],
})
EPS = _series({
    1045810: [1.05, 1.01, 0.89, 0.78, 0.65],
    320193:  [1.55, None, 1.53, 2.40, 1.40],
    2098:    [1.10, 1.05, 0.96, 0.88, 0.93],
    999002:  [-0.40, -0.40, -0.40, -0.40, -0.20],
    999004:  [0.50, 0.50, 0.50, 0.50, 0.40],
})
EQ = _series({1045810: [90_000e6] * 5, 320193: [60_000e6] * 5, 2098: [120e6] * 5,
              999002: [20e6] * 5, 999004: [50e6] * 5})
SH = _series({1045810: [24_400e6] * 5, 320193: [14_800e6] * 5, 2098: [3.9e6] * 5,
              999002: [10e6] * 5})   # 999004 故意沒有股數

# 年報（CY{fy}）。AAPL 的 TTM 要靠它 + 本季 − 去年同季 湊出來。
AAPL_FY_REV, AAPL_FY_NET, AAPL_FY_EPS = 400_000e6, 100_000e6, 6.60
ANNUAL = {
    "rev": {320193: AAPL_FY_REV, 999004: 30e6, 999002: 19e6},
    "net": {320193: AAPL_FY_NET, 999004: 3.5e6, 999002: -7.5e6},
    "eps": {320193: AAPL_FY_EPS, 999004: 1.8, 999002: -1.5},
    "gp":  {320193: 180_000e6},
}

QUOTES = {
    "NVDA": {"p": 180.0, "cap": 4_000e9},
    "AAPL": {"p": 250.0, "cap": 3_700e9},
    "ACU":  {"p": 40.0, "cap": 156e6},
    "LOSS": {"p": 3.0, "cap": 30e6},
    "NOSH": {"p": 12.0, "cap": 240e6},   # 沒有 SEC 股數，市值只能用這個
}


def install_fakes() -> None:
    U.sec_tickers = lambda: dict(FAKE_TICKERS)
    U.revenue_frame = lambda ccp: {}
    U.frame = lambda *a, **k: {}
    U.QUOTE_PROVIDERS = {
        "nasdaq": lambda tickers: {t: QUOTES[t] for t in tickers if t in QUOTES},
        "none": lambda tickers: {},
    }

    def fake_collect():
        data = {"rev": _drop_q4(REV), "net": _drop_q4(NET), "gp": _drop_q4(GP),
                "eps": _drop_q4(EPS), "eq": EQ, "sh": SH, "annual": ANNUAL}
        # NVDA 要維持「四季齊全」，所以把它的第四季補回去
        for key, src in (("rev", REV), ("net", NET), ("gp", GP), ("eps", EPS)):
            if Q4 and 1045810 in src[Q4]:
                data[key][Q4] = {1045810: src[Q4][1045810]}
        return data, P

    B.collect = fake_collect
    B.U = U


def check(name: str, cond: bool, detail: str = "") -> bool:
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  — {detail}" if detail else ""))
    return cond


def main() -> int:
    install_fakes()
    out = Path("/tmp/us_test_out")
    B.OUT_DIR = out
    B.build("nasdaq")

    rows = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    market = json.loads((out / "market.json").read_text(encoding="utf-8"))
    by = {r["c"]: r for r in rows}
    ok = True

    print("\n--- 期間設定 ---")
    ok &= check("直接相加用的是連續四季", len(set(P["consecutive"])) == 4)
    ok &= check("年報年度早於基準季", P["fy"] <= CUR[0])
    ok &= check("去年同季與基準季同一個季別", PREV[1] == CUR[1] and PREV[0] == CUR[0] - 1)

    print("\n--- 進表與排除 ---")
    ok &= check("完全沒有基本面的公司不進表", "EMPTY" not in by)
    ok &= check("有基本面的都在",
                {"NVDA", "AAPL", "ACU", "PART", "LOSS", "NOSH"} <= set(by))
    ok &= check("依市值由大到小排序",
                [r["cap"] or 0 for r in rows] == sorted([r["cap"] or 0 for r in rows],
                                                        reverse=True))

    print("\n--- TTM 算法一：四季直接相加 ---")
    nvda = by["NVDA"]
    eps_ttm = 1.05 + 1.01 + 0.89 + 0.78
    ok &= check("EPS 為最近四季加總", abs(nvda["fin"]["eps"] - round(eps_ttm, 2)) < 0.01,
                f"{nvda['fin']['eps']} vs {round(eps_ttm, 2)}")
    ok &= check("本益比 = 股價 / TTM EPS",
                abs(nvda["pe"] - round(180.0 / eps_ttm, 2)) < 0.05, f"pe={nvda['pe']}")
    cap = 180.0 * 24_400e6
    ok &= check("市值 = 股價 × SEC 申報股數（不是報價來源給的）", nvda["cap"] == round(cap))
    rev_ttm = (46_000 + 44_000 + 39_000 + 35_000) * 1e6
    ok &= check("股價營收比 = 市值 / TTM 營收",
                abs(nvda["ps"] - round(cap / rev_ttm, 2)) < 0.05, f"ps={nvda['ps']}")
    ok &= check("淨值比 = 市值 / 股東權益",
                abs(nvda["pb"] - round(cap / 90_000e6, 2)) < 0.05, f"pb={nvda['pb']}")
    ok &= check("毛利率 = TTM 毛利 / TTM 營收",
                abs(nvda["fin"]["gpm"] - round((34_000 + 33_000 + 29_000 + 26_000) /
                                               (46_000 + 44_000 + 39_000 + 35_000) * 100, 1)) < 0.2,
                f"{nvda['fin']['gpm']}%")

    print("\n--- TTM 算法二：年報錨定（第四季缺席時的正常情況） ---")
    aapl = by["AAPL"]
    want_eps = AAPL_FY_EPS + 1.55 - 1.40
    ok &= check("缺第四季仍算得出 EPS", aapl["fin"].get("eps") is not None)
    ok &= check("EPS = 年報 + 本季 − 去年同季",
                abs(aapl["fin"]["eps"] - round(want_eps, 2)) < 0.01,
                f"{aapl['fin'].get('eps')} vs {round(want_eps, 2)}")
    want_rev = AAPL_FY_REV + 94_000e6 - 85_000e6
    want_cap = 250.0 * 14_800e6
    ok &= check("股價營收比也用年報錨定的 TTM 營收",
                abs(aapl["ps"] - round(want_cap / want_rev, 2)) < 0.05, f"ps={aapl['ps']}")
    ok &= check("淨利率用年報錨定的 TTM",
                abs(aapl["fin"]["npm"] - round((AAPL_FY_NET + 23_000e6 - 21_000e6) /
                                               want_rev * 100, 1)) < 0.2,
                f"{aapl['fin'].get('npm')}%")

    print("\n--- 成長率 ---")
    ok &= check("季營收年增率 = 最近季 vs 去年同期",
                abs(nvda["fin"]["rev_yoy"] - round((46_000 - 30_000) / 30_000 * 100, 1)) < 0.1,
                f"{nvda['fin']['rev_yoy']}%")
    ok &= check("季淨利年增率",
                abs(nvda["fin"]["net_yoy"] - round((26_000 - 16_000) / 16_000 * 100, 1)) < 0.1,
                f"{nvda['fin']['net_yoy']}%")

    print("\n--- 市值來源 ---")
    nosh = by["NOSH"]
    ok &= check("沒有 SEC 股數時，市值退用報價來源給的",
                nosh["cap"] == round(240e6), f"cap={nosh['cap']}")
    ok &= check("退用的市值一樣能算股價營收比", nosh.get("ps") is not None)

    print("\n--- 留白行為（寧可空白也不要給錯的數字） ---")
    part = by["PART"]
    ok &= check("兩條算法都湊不齊就不給 TTM 營收 → 股價營收比留白", part.get("ps") is None)
    ok &= check("沒有報價 → 市值留白", part.get("cap") is None)
    loss = by["LOSS"]
    ok &= check("EPS 為負 → 本益比留白", loss.get("pe") is None, f"eps={loss['fin'].get('eps')}")
    ok &= check("虧損公司仍看得到股價營收比", loss.get("ps") is not None)
    ok &= check("fin 裡不留 None", all(v is not None for r in rows for v in r["fin"].values()))
    ok &= check("絕對營收金額沒有外流到前端", all("rev" not in r["fin"] for r in rows))

    print("\n--- meta / market ---")
    ok &= check("meta.total 與列數一致", meta["total"] == len(rows))
    ok &= check("meta 記錄報價來源", meta["priceSource"] == "nasdaq")
    ok &= check("meta.withPrice 等於實際有股價的檔數",
                meta["withPrice"] == sum(1 for r in rows if r.get("p")),
                str(meta["withPrice"]))
    ok &= check("市場中位數本益比有值", market["markets"]["us"]["pe"] is not None,
                str(market["markets"]["us"]["pe"]))
    ok &= check("市值加權本益比有值", market["markets"]["us"]["peWeighted"] is not None)

    print("\n--- Nasdaq 清單的解析 ---")
    payload = {"data": {"rows": [
        {"symbol": "NVDA", "lastsale": "$230.36", "marketCap": "5,551,676,000,000"},
        {"symbol": "BRK/B", "lastsale": "$512.00", "marketCap": "1,100,000,000,000"},
        {"symbol": "ZZZZ", "lastsale": "$0.00", "marketCap": "0.00"},
        {"symbol": "NOCAP", "lastsale": "$7.25", "marketCap": "N/A"},
    ]}}
    U.try_json = lambda *a, **k: payload
    got = U.quotes_nasdaq()
    ok &= check("價格字串的 $ 與逗號有處理掉", got.get("NVDA", {}).get("p") == 230.36)
    ok &= check("市值字串的逗號有處理掉", got.get("NVDA", {}).get("cap") == 5_551_676_000_000)
    ok &= check("Nasdaq 的 BRK/B 也對得上 SEC 的 BRK-B", "BRK-B" in got)
    ok &= check("價格為 0 的不收", "ZZZZ" not in got)
    ok &= check("沒有市值仍收，市值留白",
                got.get("NOCAP", {}).get("p") == 7.25 and got["NOCAP"]["cap"] is None)

    print("\n--- --no-prices 模式 ---")
    B.build("none")
    rows2 = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    meta2 = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    ok &= check("不抓報價時所有估值比率留空",
                all(r.get("pe") is None and r.get("ps") is None and r.get("pb") is None
                    for r in rows2))
    ok &= check("不抓報價時 EPS 與成長率仍在",
                any(r["fin"].get("eps") for r in rows2) and
                any(r["fin"].get("rev_yoy") for r in rows2))
    ok &= check("meta 標記 priceSource=none", meta2["priceSource"] == "none")

    print("\n" + ("全部通過" if ok else "有測試失敗"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
