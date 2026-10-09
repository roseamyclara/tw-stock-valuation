"""保存當時的 P/S 月末快照；不以現在營收倒算歷史估值。"""
from __future__ import annotations

import math
from datetime import date

from util import DATA_DIR, read_json, write_json

PS_HISTORY = DATA_DIR / "ps_history.json"


def record_snapshot(store: dict, rows: list[dict], as_of: str, updated_at: str) -> bool:
    """當月取最近交易日，同日取較晚建置的快照；缺值保留為空。"""
    try:
        day = date.fromisoformat(as_of)
    except (TypeError, ValueError):
        return False
    if day.isoformat() != as_of:
        return False
    key = day.strftime("%Y-%m")
    previous = store.get(key)
    if previous and (previous["asOf"], previous.get("updatedAt", "")) > (as_of, updated_at):
        return False
    stocks = {}
    for row in rows:
        code, value = row.get("c", ""), row.get("ps")
        if not (len(code) == 4 and code.isdigit()):
            continue
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            value = None
        stocks[code] = {"v": value, "basis": row.get("ps_basis") or "無",
                        "revenueMonth": (row.get("rev") or {}).get("ym")}
    if not stocks or not any(s["v"] is not None for s in stocks.values()):
        return False
    store[key] = {"asOf": as_of, "updatedAt": updated_at, "stocks": stocks}
    return True


def update_ps_history(rows: list[dict], day: date, updated_at: str) -> None:
    store = read_json(PS_HISTORY, {}) or {}
    if record_snapshot(store, rows, day.isoformat(), updated_at):
        write_json(PS_HISTORY, dict(sorted(store.items())))


def stock_series(store: dict, code: str) -> list[dict]:
    result = []
    for month, snapshot in sorted(store.items()):
        value = snapshot.get("stocks", {}).get(code, {})
        result.append({"ym": month, "d": snapshot["asOf"], "v": value.get("v"),
                       "basis": value.get("basis", "無"), "revenueMonth": value.get("revenueMonth")})
    return result


def load_reconstructed() -> dict:
    """載入官方歷史重建值；與當時保存的快照分開保存，便於追溯。"""
    result = {}
    for path in sorted((DATA_DIR / 'ps_reconstructed').glob('[0-9][0-9][0-9][0-9].json')):
        for month, snap in (read_json(path, {}) or {}).items():
            result[month] = {
                'asOf': snap['d'],
                'stocks': {code: {'v': vals[0], 'basis': '歷史重建',
                                 'revenueMonth': snap['revenueMonth'], 'market': vals[4]}
                           for code, vals in snap['s'].items()}}
    return result


def merge_history(reconstructed: dict, snapshots: dict) -> dict:
    result = {ym: {'asOf': s['asOf'], 'stocks': dict(s['stocks'])} for ym, s in reconstructed.items()}
    # 原快照整月優先，避免混入另一交易日的數值。
    result.update(snapshots)
    return dict(sorted(result.items()))
