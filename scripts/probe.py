"""端點探測：實際打過每一個候選網址，回報可用性與欄位結構。

在 GitHub Actions 上跑一次即可定案（Actions 的機房 IP 不會被 WAF 擋）。
輸出 probe-report.md，方便直接看結果。
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import requests
from sources import DATASETS, HISTORY
from util import session, to_roc


def describe(payload) -> tuple[int, list[str], str]:
    """回傳 (筆數, 欄位名, 首筆樣本)。"""
    data = payload
    if isinstance(data, dict):
        for key in ("data", "aaData", "records", "result", "tables"):
            if isinstance(data.get(key), list) and data[key]:
                inner = data[key]
                if key == "tables" and isinstance(inner[0], dict):
                    t = inner[0]
                    fields = t.get("fields") or t.get("title") or []
                    rows = t.get("data") or []
                    return len(rows), list(fields), json.dumps(
                        rows[0] if rows else [], ensure_ascii=False
                    )[:400]
                data = inner
                break
        else:
            return 1, list(data.keys())[:40], json.dumps(data, ensure_ascii=False)[:400]
    if isinstance(data, list) and data:
        first = data[0]
        keys = list(first.keys()) if isinstance(first, dict) else []
        return len(data), keys, json.dumps(first, ensure_ascii=False)[:400]
    return 0, [], ""


def probe(url: str) -> dict:
    try:
        r = session().get(url, timeout=45)
    except requests.RequestException as exc:
        return {"ok": False, "status": "ERR", "note": str(exc)[:160]}
    if r.status_code != 200:
        return {"ok": False, "status": r.status_code, "note": r.text[:120].replace("\n", " ")}
    try:
        payload = r.json()
    except ValueError:
        return {"ok": False, "status": 200, "note": "not JSON: " + r.text[:120].replace("\n", " ")}
    n, keys, sample = describe(payload)
    return {"ok": n > 0, "status": 200, "rows": n, "keys": keys, "sample": sample}


def catalogue() -> list[str]:
    """把 TWSE / TPEx 的 OpenAPI 規格整份 dump 出來，看清楚到底有哪些資料集。"""
    out: list[str] = ["## 官方端點目錄", ""]
    specs = [
        ("TWSE", "https://openapi.twse.com.tw/v1/swagger.json"),
        ("TPEx", "https://www.tpex.org.tw/openapi/swagger.json"),
        ("TPEx-alt", "https://www.tpex.org.tw/openapi/v1/swagger.json"),
    ]
    for label, url in specs:
        out.append(f"### {label} — `{url}`")
        try:
            r = session().get(url, timeout=60)
            if r.status_code != 200:
                out += [f"- FAIL status {r.status_code}", ""]
                continue
            spec = r.json()
        except Exception as exc:  # noqa: BLE001
            out += [f"- ERR {str(exc)[:160]}", ""]
            continue
        paths = spec.get("paths", {})
        out.append(f"- 共 {len(paths)} 個端點")
        for p, ops in sorted(paths.items()):
            summary = ""
            for method in ("get", "post"):
                if method in ops:
                    summary = ops[method].get("summary") or ops[method].get("description") or ""
                    break
            out.append(f"  - `{p}` — {str(summary)[:90]}")
        out.append("")
    return out


def main() -> None:
    lines = ["# 端點探測報告", ""]

    lines += catalogue()

    lines += ["## 最新快照端點", ""]
    for name, candidates in DATASETS.items():
        lines.append(f"### `{name}`")
        for url in candidates:
            res = probe(url)
            mark = "OK  " if res["ok"] else "FAIL"
            head = f"- **{mark}** `{url}` — status {res['status']}"
            if res["ok"]:
                head += f", {res['rows']} 筆"
            lines.append(head)
            if res["ok"]:
                lines.append(f"  - 欄位：`{'`, `'.join(res['keys'])}`")
                lines.append(f"  - 樣本：`{res['sample']}`")
                break  # 命中就不試下一個候選
            elif res.get("note"):
                lines.append(f"  - {res['note']}")
        lines.append("")

    # 歷史端點：拿最近一個平日測
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    ymd = d.strftime("%Y%m%d")
    roc = to_roc(d)
    roc_slash = f"{roc[:3]}/{roc[3:5]}/{roc[5:]}"

    lines += [f"## 歷史查詢端點（測試日期 {d}）", ""]
    for name, candidates in HISTORY.items():
        lines.append(f"### `{name}`")
        for tpl in candidates:
            url = tpl.format(ymd=ymd, roc=roc, roc_slash=roc_slash)
            res = probe(url)
            mark = "OK  " if res["ok"] else "FAIL"
            head = f"- **{mark}** `{url}` — status {res['status']}"
            if res["ok"]:
                head += f", {res['rows']} 筆"
            lines.append(head)
            if res["ok"]:
                lines.append(f"  - 欄位：`{'`, `'.join(str(k) for k in res['keys'])}`")
                lines.append(f"  - 樣本：`{res['sample']}`")
                break
            elif res.get("note"):
                lines.append(f"  - {res['note']}")
        lines.append("")

    # 這些端點官方只給「最新一期」。測試看看能不能用查詢參數取得歷史期別，
    # 這決定了「獲利成長率」在第一天就能算，還是要等下一季財報才補得齊。
    lines += ["## 歷史期別參數測試（損益表／月營收）", ""]
    param_tests = [
        f"{DATASETS['listed_income_ci'][0]}?年度=114&季別=2",
        f"{DATASETS['listed_income_ci'][0]}?year=114&season=2",
        f"{DATASETS['listed_income_ci'][0]}/114/2",
        f"{DATASETS['listed_revenue'][0]}?資料年月=11407",
        f"{DATASETS['listed_revenue'][0]}?date=11407",
    ]
    for url in param_tests:
        res = probe(url)
        mark = "OK  " if res["ok"] else "FAIL"
        lines.append(f"- **{mark}** `{url}` — status {res['status']}")
        if res["ok"]:
            lines.append(f"  - 樣本：`{res['sample']}`")
    lines.append("")

    report = "\n".join(lines)
    print(report)
    with open("probe-report.md", "w", encoding="utf-8") as fh:
        fh.write(report)


if __name__ == "__main__":
    main()
