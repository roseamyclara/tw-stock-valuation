"""第二輪探測：找出「上市」資料在 GitHub Actions 上可用的替代路徑。

已知：openapi.twse.com.tw 會擋機房 IP（回安全性攔截頁），
      但 www.twse.com.tw 的盤後端點可用，TPEx 的 OpenAPI 也完全可用。
這裡驗證三件事：
  1. TPEx 的 OpenAPI 是否也代管了上市（_L）的公開資訊觀測站資料集
  2. 證交所自家還有沒有其他可用主機／路徑
  3. MI_INDEX 究竟回了哪幾張表，個股表在第幾張
"""
from __future__ import annotations

import json

import requests
from util import session

TPEX = "https://www.tpex.org.tw/openapi/v1"
TWSE_RWD = "https://www.twse.com.tw/rwd/zh"

# 1. TPEx 是否代管上市資料集
TPEX_L = [
    f"{TPEX}/mopsfin_t187ap05_L",       # 上市月營收
    f"{TPEX}/mopsfin_t187ap03_L",       # 上市公司基本資料（含股數）
    f"{TPEX}/mopsfin_t187ap06_L_ci",    # 上市綜合損益表
    f"{TPEX}/t187ap05_L",
    f"{TPEX}/t187ap03_L",
    f"{TPEX}/t187ap06_L_ci",
    f"{TPEX}/mopsfin_t187ap06_R_ci",    # 興櫃損益表（第一輪失敗，再試一次）
    f"{TPEX}/t187ap06_R_ci",
    f"{TPEX}/t187ap03_R",
]

# 2. 證交所的其他主機／路徑
TWSE_ALT = [
    "https://mopsfin.twse.com.tw/opendata/t187ap05_L",
    "https://mops.twse.com.tw/opendata/t187ap05_L",
    f"{TWSE_RWD}/opendata/t187ap05_L",
    "https://www.twse.com.tw/opendata/t187ap05_L",
    "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",   # 對照組
]

# 3. 上市每日收盤 / 股數
TWSE_DAILY = [
    f"{TWSE_RWD}/afterTrading/MI_INDEX?date=20260828&type=ALLBUT0999&response=json",
    f"{TWSE_RWD}/afterTrading/STOCK_DAY_ALL?response=json",
    f"{TWSE_RWD}/afterTrading/BWIBBU_d?date=20260828&selectType=ALL&response=json",
]

HEADER_SETS = {
    "default": {},
    "with-referer": {"Referer": "https://openapi.twse.com.tw/"},
    "plain-ua": {"User-Agent": "python-requests/2.32"},
}


def show(url: str, headers: dict | None = None) -> str:
    try:
        r = session().get(url, timeout=45, headers=headers or {})
    except requests.RequestException as exc:
        return f"ERR {str(exc)[:100]}"
    body = r.text.strip()
    if r.status_code != 200:
        return f"HTTP {r.status_code}"
    if not body.startswith(("[", "{")):
        return f"非 JSON（{len(body)} bytes）：{body[:90]}"
    try:
        data = json.loads(body)
    except ValueError:
        return "JSON 解析失敗"
    if isinstance(data, list):
        if not data:
            return "空陣列"
        keys = list(data[0].keys()) if isinstance(data[0], dict) else []
        return f"{len(data)} 筆｜欄位 {keys[:14]}｜樣本 {json.dumps(data[0], ensure_ascii=False)[:220]}"
    return f"dict｜keys {list(data.keys())[:12]}"


def main() -> None:
    out = ["# 第二輪探測：上市資料替代路徑", ""]

    out += ["## 1. TPEx OpenAPI 是否代管上市／興櫃資料集", ""]
    for u in TPEX_L:
        out.append(f"- `{u}`\n  - {show(u)}")
    out.append("")

    out += ["## 2. 證交所其他主機／路徑（含標頭實驗）", ""]
    for u in TWSE_ALT:
        for name, h in HEADER_SETS.items():
            out.append(f"- `{u}` [{name}]\n  - {show(u, h)}")
    out.append("")

    out += ["## 3. 證交所每日盤後端點的表格結構", ""]
    for u in TWSE_DAILY:
        out.append(f"### `{u}`")
        try:
            r = session().get(u, timeout=45)
            data = r.json()
        except Exception as exc:  # noqa: BLE001
            out.append(f"- 失敗：{str(exc)[:120]}")
            continue
        if isinstance(data, list):
            out.append(f"- 陣列 {len(data)} 筆，欄位 {list(data[0].keys()) if data and isinstance(data[0], dict) else []}")
            continue
        out.append(f"- 頂層 keys：{list(data.keys())[:12]}  stat={data.get('stat')}")
        for i, t in enumerate(data.get("tables", []) or []):
            fields = t.get("fields") or []
            rows = t.get("data") or []
            out.append(f"  - 表 {i}：{len(rows)} 列｜title={str(t.get('title'))[:40]}｜欄位 {fields[:16]}")
            if rows:
                out.append(f"    - 樣本 {json.dumps(rows[0], ensure_ascii=False)[:200]}")
        if data.get("fields"):
            out.append(f"  - 頂層 fields：{data['fields'][:16]}")
            if data.get("data"):
                out.append(f"    - 樣本 {json.dumps(data['data'][0], ensure_ascii=False)[:200]}")
        out.append("")

    report = "\n".join(out)
    print(report)
    with open("probe2-report.md", "w", encoding="utf-8") as fh:
        fh.write(report)


if __name__ == "__main__":
    main()
