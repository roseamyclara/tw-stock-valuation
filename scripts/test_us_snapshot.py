"""build_us_snapshot 的離線測試。

用假的 SEC 回應（形狀照 data.sec.gov 實測結果）跑完整條流程，
驗證 TTM 加總、年增率、估值比率、以及「資料不齊就留白」的行為。

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
    999001:  {"ticker": "PART", "name": "PARTIAL DATA CO"},   # 只有 3 季 → TTM 應留白
    999002:  {"ticker": "LOSS", "name": "LOSSMAKER INC"},     # 虧損 → 本益比應留白
    999003:  {"ticker": "EMPTY", "name": "NO FUNDAMENTALS"},  # 什麼都沒有 → 不進表
}

QS = B.recent_quarters(B.QUARTERS_BACK)
CUR, PREV = QS[0], QS[4]


def _series(per_cik: dict[int, list[float | None]]) -> dict:
    """把 {cik: [最近季, 次近季, ...]} 轉成 {期間: {cik: 值}}。"""
    out = {q: {} for q in QS}
    for cik, vals in per_cik.items():
        for q, v in zip(QS, vals):
            if v is not None:
                out[q][cik] = v
    return out


REV = _series({
    1045810: [46_000e6, 44_000e6, 39_000e6, 35_000e6, 30_000e6],
    320193:  [94_000e6, 95_000e6, 90_000e6, 124_000e6, 85_000e6],
    2098:    [54e6, 52e6, 50e6, 48e6, 50e6],
    999001:  [10e6, 10e6, 10e6, None, 9e6],          # 缺第 4 季
    999002:  [5e6, 5e6, 5e6, 5e6, 4e6],
})
NET = _series({
    1045810: [26_000e6, 25_000e6, 22_000e6, 19_000e6, 16_000e6],
    320193:  [23_000e6, 24_000e6, 23_000e6, 36_000e6, 21_000e6],
    2098:    [4e6, 3.8e6, 3.5e6, 3.2e6, 3.4e6],
    999001:  [1e6, 1e6, 1e6, None, 0.9e6],
    999002:  [-2e6, -2e6, -2e6, -2e6, -1e6],
})
GP = _series({
    1045810: [34_000e6, 33_000e6, 29_000e6, 26_000e6, 22_000e6],
    2098:    [20e6, 19e6, 18e6, 17e6, 18e6],
})
EPS = _series({
    1045810: [1.05, 1.01, 0.89, 0.78, 0.65],
    320193:  [1.55, 1.60, 1.53, 2.40, 1.40],
    2098:    [1.10, 1.05, 0.96, 0.88, 0.93],
    999002:  [-0.40, -0.40, -0.40, -0.40, -0.20],
})
EQ = _series({1045810: [90_000e6] * 5, 320193: [60_000e6] * 5, 2098: [120e6] * 5,
              999002: [20e6] * 5})
SH = _series({1045810: [24_400e6] * 5, 320193: [14_800e6] * 5, 2098: [3.9e6] * 5,
              999002: [10e6] * 5})

PRICES = {"NVDA": 180.0, "AAPL": 250.0, "ACU": 40.0, "LOSS": 3.0}


def install_fakes() -> None:
    U.sec_tickers = lambda: dict(FAKE_TICKERS)
    U.revenue_frame = lambda ccp: {}
    U.frame = lambda *a, **k: {}
    U.PRICE_PROVIDERS = {"stooq": lambda tickers: {t: PRICES[t] for t in tickers if t in PRICES},
                         "none": lambda tickers: {}}

    def fake_collect():
        return {"rev": REV, "net": NET, "gp": GP, "eps": EPS, "eq": EQ, "sh": SH}, QS

    B.collect = fake_collect
    B.U = U


def check(name: str, cond: bool, detail: str = "") -> bool:
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"  — {detail}" if detail else ""))
    return cond


def main() -> int:
    install_fakes()
    out = Path("/tmp/us_test_out")
    B.OUT_DIR = out
    B.build(no_prices=False)

    rows = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    market = json.loads((out / "market.json").read_text(encoding="utf-8"))
    by = {r["c"]: r for r in rows}
    ok = True

    print("\n--- 進表與排除 ---")
    ok &= check("完全沒有基本面的公司不進表", "EMPTY" not in by)
    ok &= check("有基本面的都在", {"NVDA", "AAPL", "ACU", "PART", "LOSS"} <= set(by))
    ok &= check("依市值由大到小排序",
                [r["cap"] or 0 for r in rows] == sorted([r["cap"] or 0 for r in rows], reverse=True))

    print("\n--- TTM 與比率 ---")
    nvda = by["NVDA"]
    eps_ttm = 1.05 + 1.01 + 0.89 + 0.78
    ok &= check("EPS 為最近四季加總", abs(nvda["fin"]["eps"] - round(eps_ttm, 2)) < 0.01,
                f"{nvda['fin']['eps']} vs {round(eps_ttm, 2)}")
    ok &= check("本益比 = 股價 / TTM EPS",
                abs(nvda["pe"] - round(180.0 / eps_ttm, 2)) < 0.05, f"pe={nvda['pe']}")
    cap = 180.0 * 24_400e6
    ok &= check("市值 = 股價 × 流通股數", nvda["cap"] == round(cap))
    rev_ttm = (46_000 + 44_000 + 39_000 + 35_000) * 1e6
    ok &= check("股價營收比 = 市值 / TTM 營收",
                abs(nvda["ps"] - round(cap / rev_ttm, 2)) < 0.05, f"ps={nvda['ps']}")
    ok &= check("淨值比 = 市值 / 股東權益",
                abs(nvda["pb"] - round(cap / 90_000e6, 2)) < 0.05, f"pb={nvda['pb']}")

    print("\n--- 成長率 ---")
    ok &= check("季營收年增率 = 最近季 vs 去年同期",
                abs(nvda["fin"]["rev_yoy"] - round((46_000 - 30_000) / 30_000 * 100, 1)) < 0.1,
                f"{nvda['fin']['rev_yoy']}%")
    ok &= check("季淨利年增率",
                abs(nvda["fin"]["net_yoy"] - round((26_000 - 16_000) / 16_000 * 100, 1)) < 0.1,
                f"{nvda['fin']['net_yoy']}%")
    ok &= check("毛利率 = TTM 毛利 / TTM 營收",
                abs(nvda["fin"]["gpm"] - round((34_000 + 33_000 + 29_000 + 26_000) /
                                               (46_000 + 44_000 + 39_000 + 35_000) * 100, 1)) < 0.2,
                f"{nvda['fin']['gpm']}%")

    print("\n--- 留白行為（寧可空白也不要給錯的數字） ---")
    part = by["PART"]
    ok &= check("缺一季就不給 TTM 營收 → 股價營收比留白", part.get("ps") is None)
    ok &= check("沒有報價 → 市值留白", part.get("cap") is None)
    loss = by["LOSS"]
    ok &= check("EPS 為負 → 本益比留白", loss.get("pe") is None, f"eps={loss['fin'].get('eps')}")
    ok &= check("虧損公司仍看得到股價營收比", loss.get("ps") is not None)
    ok &= check("fin 裡不留 None", all(v is not None for r in rows for v in r["fin"].values()))
    ok &= check("絕對營收金額沒有外流到前端",
                all("rev" not in r["fin"] for r in rows))

    print("\n--- meta / market ---")
    ok &= check("meta.total 與列數一致", meta["total"] == len(rows))
    ok &= check("meta 記錄報價來源", meta["priceSource"] == "stooq")
    ok &= check("市場中位數本益比有值", market["markets"]["us"]["pe"] is not None,
                str(market["markets"]["us"]["pe"]))
    ok &= check("市值加權本益比有值", market["markets"]["us"]["peWeighted"] is not None)

    print("\n--- --no-prices 模式 ---")
    B.build(no_prices=True)
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
