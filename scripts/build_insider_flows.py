"""Collect insider buy/sell flow data and build compact site JSON.

Outputs docs/data/insider_flows.json.
Values are in board lots (張). Positive values are insider buys; negative
values are insider sells / declared transfers. Current-only OpenAPI snapshots
accumulate history from the first successful run.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from util import DATA_DIR, get_json, log, num, read_json, roc_to_date, rows_from_fields, write_json

OUT = DATA_DIR / "insider_flows.json"

SOURCES = [
    {"name": "twse_transfer", "kind": "transfer", "market": "listed", "url": "https://openapi.twse.com.tw/v1/opendata/t187ap12_L"},
    {"name": "tpex_transfer", "kind": "transfer", "market": "otc", "url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap12_O"},
    {"name": "esb_transfer", "kind": "transfer", "market": "esb", "url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap12_R", "optional": True},
    {"name": "twse_holding", "kind": "holding", "market": "listed", "url": "https://openapi.twse.com.tw/v1/opendata/t187ap11_L", "optional": True},
    {"name": "tpex_holding", "kind": "holding", "market": "otc", "url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap11_O", "optional": True},
    {"name": "esb_holding", "kind": "holding", "market": "esb", "url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap11_R", "optional": True},
]

WINDOWS = {"d1": 1, "d5": 5, "d10": 10, "d30": 30}
KEEP_DAYS = 420
TW = timezone(timedelta(hours=8))


def clean_code(v: Any) -> str | None:
    m = re.search(r"\d{4}", str(v or ""))
    return m.group(0) if m else None


def pick(row: dict[str, Any], *needles: str) -> Any:
    for k, v in row.items():
        text = re.sub(r"\s+", "", str(k))
        if all(n in text for n in needles):
            return v
    return None


def row_date(row: dict[str, Any]) -> date | None:
    for needles in (("出表", "日期"), ("申報", "日期"), ("資料", "日期"), ("日期",)):
        v = pick(row, *needles)
        if v:
            parsed = roc_to_date(str(v))
            if parsed:
                return parsed
    return None


def row_month(row: dict[str, Any]) -> date | None:
    v = pick(row, "資料", "年月") or pick(row, "年月")
    s = re.sub(r"\D", "", str(v or ""))
    if len(s) not in (5, 6):
        return None
    try:
        y = int(s[:-2]) + 1911
        m = int(s[-2:])
        if not 1 <= m <= 12:
            return None
        nxt = date(y + (m == 12), 1 if m == 12 else m + 1, 1)
        return nxt - timedelta(days=1)
    except ValueError:
        return None


def lots(value: Any) -> float:
    v = num(value)
    if v is None:
        return 0.0
    return round(v / 1000.0, 3)


def transfer_lots(row: dict[str, Any]) -> float:
    candidates: list[Any] = []
    for k, v in row.items():
        key = re.sub(r"\s+", "", str(k))
        if "最大" in key or "每日" in key or "轉讓後" in key or "保留運用" in key:
            continue
        if "轉讓股數" in key or ("預定" in key and "轉讓" in key):
            candidates.append(v)
    if candidates:
        return max((lots(v) for v in candidates), default=0.0)
    return lots(pick(row, "轉讓", "股數"))


def holding_buy_sell(row: dict[str, Any]) -> tuple[float, float]:
    buy = 0.0
    sell = 0.0
    for k, v in row.items():
        key = re.sub(r"\s+", "", str(k))
        if any(skip in key for skip in ("私募", "信託", "設質", "解質", "目前", "上月", "月底", "累計")):
            continue
        val = lots(v)
        if not val:
            continue
        is_market = any(x in key for x in ("集中", "市場", "買進", "賣出"))
        if "增加" in key or "買進" in key:
            if is_market or "本月" in key:
                buy += val
        elif "減少" in key or "賣出" in key:
            if is_market or "本月" in key:
                sell += val
    return round(buy, 3), round(sell, 3)


def normalize_source(src: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        payload = get_json(src["url"], tries=2)
    except Exception as exc:  # noqa: BLE001
        if src.get("optional"):
            log(f"  跳過 {src['name']}: {exc}")
            return []
        raise
    rows = rows_from_fields(payload)
    out: list[dict[str, Any]] = []
    for row in rows:
        code = clean_code(pick(row, "公司", "代號") or pick(row, "股票", "代號") or pick(row, "代號") or pick(row, "Code"))
        if not code:
            continue
        if src["kind"] == "transfer":
            d = row_date(row)
            sell = transfer_lots(row)
            buy = 0.0
        else:
            d = row_month(row)
            buy, sell = holding_buy_sell(row)
        if not d or (not buy and not sell):
            continue
        out.append({"date": d.isoformat(), "code": code, "market": src["market"], "source": src["kind"], "buy": buy, "sell": sell})
    log(f"  {src['name']}：{len(out)} 筆可用事件")
    return out


def load_existing() -> dict[str, dict[str, dict[str, Any]]]:
    old = read_json(OUT, {})
    records: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for code, obj in (old.get("stocks") or {}).items():
        for item in obj.get("series") or []:
            if not isinstance(item, list) or len(item) < 4:
                continue
            d, buy, sell, net = item[:4]
            source = item[4] if len(item) > 4 else "legacy"
            records[code][f"{d}|{source}"] = {"date": d, "code": code, "source": source, "buy": float(buy or 0), "sell": float(abs(sell or 0)), "net": float(net or 0)}
    return records


def prune(records: dict[str, dict[str, dict[str, Any]]], anchor: date) -> None:
    cutoff = anchor - timedelta(days=KEEP_DAYS)
    for code in list(records):
        records[code] = {k: v for k, v in records[code].items() if datetime.strptime(v["date"], "%Y-%m-%d").date() >= cutoff}
        if not records[code]:
            del records[code]


def build_output(records: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    all_dates = [v["date"] for per_code in records.values() for v in per_code.values()]
    anchor = max((datetime.strptime(d, "%Y-%m-%d").date() for d in all_dates), default=date.today())
    prune(records, anchor)
    stocks: dict[str, Any] = {}
    for code, per_code in sorted(records.items()):
        series = []
        for rec in sorted(per_code.values(), key=lambda x: (x["date"], x["source"])):
            buy = round(float(rec.get("buy") or 0), 3)
            sell = round(float(rec.get("sell") or 0), 3)
            net = round(buy - sell, 3)
            if buy or sell:
                series.append([rec["date"], buy, sell, net, rec.get("source", "")])
        if not series:
            continue
        summary: dict[str, float | None] = {}
        for key, days in WINDOWS.items():
            start = anchor - timedelta(days=days - 1)
            net = 0.0
            for d, buy, sell, *_ in series:
                day = datetime.strptime(d, "%Y-%m-%d").date()
                if start <= day <= anchor:
                    net += float(buy or 0) - float(sell or 0)
            summary[key] = round(net, 3) if abs(net) >= 0.001 else 0.0
        stocks[code] = {"summary": summary, "series": series[-180:]}
    return {
        "asOf": anchor.isoformat(),
        "updatedAt": datetime.now(TW).isoformat(timespec="seconds"),
        "unit": "張",
        "note": "紅色為內部人市場買進；綠色向下為內部人賣出/持股轉讓。OpenAPI 若只提供最新快照，歷史自本站開始累積。",
        "stocks": stocks,
    }


def main() -> int:
    records = load_existing()
    for src in SOURCES:
        for ev in normalize_source(src):
            key = f"{ev['date']}|{ev['source']}"
            prev = records[ev["code"]].get(key)
            if prev:
                prev["buy"] = round(float(prev.get("buy") or 0) + ev["buy"], 3)
                prev["sell"] = round(float(prev.get("sell") or 0) + ev["sell"], 3)
                prev["net"] = round(float(prev["buy"]) - float(prev["sell"]), 3)
            else:
                ev["net"] = round(ev["buy"] - ev["sell"], 3)
                records[ev["code"]][key] = ev
    out = build_output(records)
    write_json(OUT, out)
    log(f"完成：{len(out['stocks'])} 檔，asOf={out['asOf']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
