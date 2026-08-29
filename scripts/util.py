"""共用工具：HTTP 抓取（含重試）、民國/西元日期轉換、數值解析、JSON 讀寫。"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

_SESSION: requests.Session | None = None


def session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": UA,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            }
        )
        _SESSION = s
    return _SESSION


class FetchError(RuntimeError):
    pass


class Throttled(FetchError):
    """官方站台的流量保護頁。等一下再試就會過。"""


# 站台的流量保護會回一頁 HTML 而不是 HTTP 429，只能靠內容辨識。
_THROTTLE_MARKERS = (
    "因為安全性考量",
    "無法呈現",
    "Access Denied",
    "請稍後再試",
)

# 每個主機的最小請求間隔（秒）。證交所的 OpenAPI 對連續請求特別敏感，
# 連打二十幾個端點就會被擋，所以刻意放慢。
_MIN_INTERVAL = {
    "openapi.twse.com.tw": 4.0,
    "www.twse.com.tw": 1.5,
    "www.tpex.org.tw": 1.0,
}
_last_hit: dict[str, float] = {}


def _wait_turn(url: str) -> None:
    host = url.split("/")[2] if "//" in url else url
    gap = _MIN_INTERVAL.get(host, 0.8)
    prev = _last_hit.get(host)
    if prev is not None:
        wait = gap - (time.monotonic() - prev)
        if wait > 0:
            time.sleep(wait)
    _last_hit[host] = time.monotonic()


def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    tries: int = 5,
    timeout: int = 45,
    referer: str | None = None,
) -> Any:
    """抓 JSON。被流量保護擋下時退避重試；仍失敗則丟 FetchError。"""
    headers = {"Referer": referer} if referer else {}
    last: Exception | None = None
    for attempt in range(tries):
        if attempt:
            # 被擋下時等久一點，讓對方的計數器歸零
            time.sleep(min(90, 8 * 2 ** (attempt - 1)) + random.random() * 3)
        _wait_turn(url)
        try:
            r = session().get(url, params=params, timeout=timeout, headers=headers)
        except requests.RequestException as exc:
            last = exc
            continue

        text = r.text.strip()
        if r.status_code == 200 and text[:1] in ("[", "{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                last = exc
                continue
        if any(m in text for m in _THROTTLE_MARKERS):
            last = Throttled(f"流量保護：{url}")
            continue
        if r.status_code in (403, 404):
            raise FetchError(f"HTTP {r.status_code}: {url}")
        last = FetchError(f"HTTP {r.status_code} / 非 JSON：{url}")
    raise FetchError(f"{url} 重試 {tries} 次仍失敗：{last}")


def rows_from_fields(payload: Any) -> list[dict[str, Any]]:
    """把證交所 {fields, data} 或 {tables:[{fields, data}]} 轉成 list of dict。

    有多張表時，挑欄位含「證券代號」且資料列最多的那一張（個股表）。
    """
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []

    candidates: list[tuple[list, list]] = []
    if payload.get("fields") and payload.get("data"):
        candidates.append((payload["fields"], payload["data"]))
    for t in payload.get("tables", []) or []:
        if t.get("fields") and t.get("data"):
            candidates.append((t["fields"], t["data"]))
    if not candidates:
        return []

    def score(c: tuple[list, list]) -> tuple[int, int]:
        fields = [str(f) for f in c[0]]
        has_code = any("證券代號" in f or "股票代號" in f or f == "代號" for f in fields)
        return (1 if has_code else 0, len(c[1]))

    fields, data = max(candidates, key=score)
    names = [str(f) for f in fields]
    out = []
    for row in data:
        if isinstance(row, dict):
            out.append(row)
        elif isinstance(row, list):
            out.append({names[i]: v for i, v in enumerate(row) if i < len(names)})
    return out


def try_json(url: str, **kw: Any) -> Any | None:
    """抓 JSON，失敗回 None（給「可有可無」的來源用）。"""
    try:
        return get_json(url, **kw)
    except Exception as exc:  # noqa: BLE001
        print(f"  [skip] {url} -> {exc}")
        return None


# ---------------------------------------------------------------- 日期處理

def roc_to_date(s: str) -> date | None:
    """'1150828' / '115/08/28' -> date(2026, 8, 28)"""
    if not s:
        return None
    s = s.strip().replace("/", "").replace("-", "")
    if not s.isdigit() or len(s) not in (6, 7):
        return None
    y = int(s[:-4]) + 1911
    m, d = int(s[-4:-2]), int(s[-2:])
    try:
        return date(y, m, d)
    except ValueError:
        return None


def roc_ym(s: str) -> tuple[int, int] | None:
    """'11507' -> (2026, 7)"""
    if not s or not s.strip().isdigit():
        return None
    s = s.strip()
    if len(s) not in (5, 6):
        return None
    return int(s[:-2]) + 1911, int(s[-2:])


def to_roc(d: date) -> str:
    return f"{d.year - 1911:03d}{d.month:02d}{d.day:02d}"


def month_key(y: int, m: int) -> str:
    return f"{y:04d}-{m:02d}"


def add_months(y: int, m: int, delta: int) -> tuple[int, int]:
    idx = y * 12 + (m - 1) + delta
    return idx // 12, idx % 12 + 1


def last_business_day(y: int, m: int) -> date:
    """該月最後一個平日（週末往前推）。台股國定假日由呼叫端往前退。"""
    nxt = date(y + (m == 12), (m % 12) + 1, 1)
    d = nxt - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


# ---------------------------------------------------------------- 數值處理

_BAD = {"", "-", "--", "---", "N/A", "n/a", "NA", "null", "None", "不適用", "無"}


def num(v: Any) -> float | None:
    """把開放資料裡的字串轉成 float；無效值回 None。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return None if isinstance(v, bool) else float(v)
    s = str(v).strip().replace(",", "").replace("%", "").replace("+", "")
    if s in _BAD:
        return None
    # 括號代表負數：(1,234) -> -1234
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        f = float(s)
    except ValueError:
        return None
    return None if f != f else f  # 濾掉 NaN


def pos(v: Any) -> float | None:
    """只接受正數（本益比、股價營收比為負或零時無意義）。"""
    f = num(v)
    return f if f is not None and f > 0 else None


def rnd(v: float | None, digits: int = 2) -> float | None:
    return None if v is None else round(v, digits)


def pct_change(new: float | None, old: float | None) -> float | None:
    """成長率(%)。基期為負或零時不計算，避免出現無意義的數字。"""
    if new is None or old is None or old <= 0:
        return None
    return (new - old) / old * 100.0


# ---------------------------------------------------------------- JSON I/O

def write_json(path: Path, obj: Any, *, compact: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    kw: dict[str, Any] = {"ensure_ascii": False, "sort_keys": False}
    if compact:
        kw["separators"] = (",", ":")
    else:
        kw["indent"] = 1
    tmp.write_text(json.dumps(obj, **kw), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def now_taipei() -> datetime:
    return datetime.utcnow() + timedelta(hours=8)


def log(msg: str) -> None:
    print(f"[{now_taipei():%H:%M:%S}] {msg}", flush=True)
