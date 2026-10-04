"""Build quarterly operating lead indicators for all Taiwan stocks.

Official source:
    公開資訊觀測站－財務比較 E 點通 (https://mopsfin.twse.com.tw/)

Outputs:
    docs/data/operating/<code>.json
    docs/data/operating_latest.json

The previous contract-liabilities collector read a single MOPS company page and
assumed the first numeric column represented the requested current period. This
replacement instead:
1. asks the official comparison service for an explicit reporting period,
2. verifies the returned yearseason,
3. maps columns by company identity,
4. keeps current/non-current contract liabilities separate,
5. treats missing values as null, never zero,
6. obtains revenue from the official quarterly comparison series.

All monetary values are normalized to TWD.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import time
from datetime import date
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup

from util import DATA_DIR, log, now_taipei, read_json, write_json

BASE = "https://mopsfin.twse.com.tw"
OUT_DIR = DATA_DIR / "operating"
LATEST_OUT = DATA_DIR / "operating_latest.json"
BATCH_SIZE = 10
REQUEST_GAP = 0.65
UA = "tw-stock-valuation/operating-leads (+https://roseamyclara.github.io/tw-stock-valuation/)"

MISSING = {"", "-", "--", "---", "—", "–", "N/A", "NA", "null", "None", "不適用", "無"}
FINANCIAL_HINTS = ("金融", "銀行", "保險", "證券", "金控", "票券")

CURRENT_NAMES = {"合約負債-流動", "合約負債流動"}
NONCURRENT_NAMES = {"合約負債-非流動", "合約負債非流動"}
TOTAL_NAMES = {"合約負債", "合約負債合計"}
INVENTORY_NAMES = {"存貨", "存貨合計", "存貨淨額", "存貨-淨額"}


def clean(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).replace("\u3000", "")


def canonical(value: Any) -> str:
    return (
        clean(value)
        .replace("－", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("─", "-")
        .replace("，", "")
        .replace(",", "")
        .replace("：", ":")
        .replace("(", "")
        .replace(")", "")
        .replace("（", "")
        .replace("）", "")
        .lower()
    )


def account_label(value: Any) -> str:
    s = canonical(value)
    return re.sub(r"^\d{3,6}[:：.、-]?", "", s)


def parse_number(value: Any) -> float | None:
    if value is None:
        return None
    s = clean(value).replace(",", "")
    if s in MISSING:
        return None
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        n = float(s)
    except ValueError:
        return None
    return n if math.isfinite(n) else None


def unit_multiplier(label: str) -> int:
    text = clean(label).replace("仟", "千")
    if "百萬元" in text:
        return 1_000_000
    if "千元" in text:
        return 1_000
    if "新台幣元" in text or "新臺幣元" in text:
        return 1
    raise ValueError(f"無法辨識金額單位：{label!r}")


def pct(new: float | int | None, old: float | int | None) -> float | None:
    if new is None or old is None or old == 0:
        return None
    return round((float(new) - float(old)) / abs(float(old)) * 100.0, 2)


def period_key(year: int, quarter: int) -> str:
    return f"{year}Q{quarter}"


def split_period(period: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{4})Q([1-4])", period)
    if not match:
        raise ValueError(period)
    return int(match.group(1)), int(match.group(2))


def previous_quarter(period: str) -> str:
    year, quarter = split_period(period)
    quarter -= 1
    if quarter == 0:
        year, quarter = year - 1, 4
    return period_key(year, quarter)


def previous_year(period: str) -> str:
    year, quarter = split_period(period)
    return period_key(year - 1, quarter)


def latest_completed_period(today: date) -> tuple[int, int]:
    """Conservative filing cutoffs, so scheduled runs do not request a future report."""
    month_day = (today.month, today.day)
    if month_day < (3, 31):
        return today.year - 1, 3
    if month_day < (5, 15):
        return today.year - 1, 4
    if month_day < (8, 14):
        return today.year, 1
    if month_day < (11, 14):
        return today.year, 2
    return today.year, 3


def periods_for(years: int, latest: tuple[int, int]) -> list[str]:
    last_year, last_quarter = latest
    first_year = last_year - max(1, years) + 1
    out: list[str] = []
    for year in range(first_year, last_year + 1):
        for quarter in range(1, 5):
            if year == last_year and quarter > last_quarter:
                break
            out.append(period_key(year, quarter))
    return out


def chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class Http:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": UA,
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
            }
        )
        self.last_hit = 0.0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self.last_hit
        if elapsed < REQUEST_GAP:
            time.sleep(REQUEST_GAP - elapsed)
        self.last_hit = time.monotonic()

    def post(self, path: str, fields: list[tuple[str, str]], tries: int = 4) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(tries):
            if attempt:
                time.sleep(min(20.0, 2.0**attempt))
            self._wait()
            try:
                response = self.session.post(
                    BASE + path,
                    data=fields,
                    timeout=45,
                    headers={
                        "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
                        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                        "Origin": BASE,
                        "Referer": BASE + "/",
                        "X-Requested-With": "XMLHttpRequest",
                    },
                )
                if response.status_code == 200:
                    return response
                last_error = RuntimeError(f"HTTP {response.status_code}")
            except requests.RequestException as exc:
                last_error = exc
        raise RuntimeError(f"{path} 重試後仍失敗：{last_error}")


def display_name(code: str, meta: dict[str, dict[str, Any]]) -> str:
    return f"{code} {meta[code].get('n') or ''}".strip()


def common_fields(metric: str, unit: str) -> list[tuple[str, str]]:
    return [
        ("compareItem", metric),
        ("ylabel", unit),
        ("quarter", "true"),
        ("revenue", "true"),
        ("ys", "0"),
        ("qnumber", ""),
        ("bcodeAvg", "false"),
        ("companyAvg", "false"),
    ]


def expand_table(table) -> list[list[str]]:
    """Expand HTML rowspan/colspan into a rectangular text grid."""
    rows = table.find_all("tr")
    grid: list[list[str]] = []
    carry: dict[tuple[int, int], tuple[int, str]] = {}

    for row_index, tr in enumerate(rows):
        row: list[str] = []
        col_index = 0

        def flush_carry() -> None:
            nonlocal col_index
            while (row_index, col_index) in carry:
                remaining, value = carry.pop((row_index, col_index))
                row.append(value)
                if remaining > 1:
                    carry[(row_index + 1, col_index)] = (remaining - 1, value)
                col_index += 1

        flush_carry()
        for cell in tr.find_all(["th", "td"], recursive=False):
            flush_carry()
            value = " ".join(cell.stripped_strings)
            rowspan = max(1, int(cell.get("rowspan", 1) or 1))
            colspan = max(1, int(cell.get("colspan", 1) or 1))
            for offset in range(colspan):
                row.append(value)
                if rowspan > 1:
                    carry[(row_index + 1, col_index + offset)] = (rowspan - 1, value)
            col_index += colspan
        flush_carry()
        grid.append(row)

    width = max((len(row) for row in grid), default=0)
    return [row + [""] * (width - len(row)) for row in grid]


def code_in_text(text: str, codes: set[str]) -> str | None:
    value = re.sub(r"\s+", " ", text).strip()
    for code in codes:
        if re.search(rf"(^|[^0-9A-Za-z]){re.escape(code)}([^0-9A-Za-z]|$)", value):
            return code
    return None


def parse_balance_sheet(
    html: str, requested_period: str, codes: set[str]
) -> dict[str, dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    marker = soup.select_one('input[name="yearseason"]')
    returned = (marker.get("value") or "").strip() if marker else ""
    expected = requested_period.replace("Q", "")
    returned_normalized = returned.upper().replace("Q", "")
    if returned_normalized != expected:
        raise ValueError(
            f"期別不符：要求 {requested_period}，官方回傳 {returned or 'unknown'}"
        )

    multiplier = unit_multiplier(" ".join(soup.stripped_strings))
    out = {
        code: {
            "contractCurrent": None,
            "contractNoncurrent": None,
            "contractTotal": None,
            "inventory": None,
            "status": {
                "contractCurrent": "not_separately_disclosed",
                "contractNoncurrent": "not_separately_disclosed",
                "contractTotal": "not_separately_disclosed",
                "inventory": "not_separately_disclosed",
            },
            "companyReturned": False,
        }
        for code in codes
    }

    def assign(code: str, key: str, raw: str) -> None:
        value = parse_number(raw)
        if value is None:
            out[code]["status"][key] = "missing"
            return
        out[code][key] = int(round(value * multiplier))
        out[code]["status"][key] = "reported"

    def field_from_cells(cells: list[str]) -> str | None:
        for raw_label in cells:
            label = account_label(raw_label)
            if label in CURRENT_NAMES:
                return "contractCurrent"
            if label in NONCURRENT_NAMES:
                return "contractNoncurrent"
            if label in TOTAL_NAMES:
                return "contractTotal"
            if label in INVENTORY_NAMES:
                return "inventory"
        return None

    # The live E-Point balance sheet uses two synchronized HTML tables:
    # a frozen left table containing account names and a scrollable right table
    # containing company headers + values. Their row indices are aligned.
    tables = soup.find_all("table")
    grids = [expand_table(table) for table in tables]

    label_grids: list[list[list[str]]] = []
    value_grids: list[tuple[list[list[str]], dict[int, str]]] = []
    for grid in grids:
        if not grid:
            continue
        account_hits = sum(1 for row in grid if field_from_cells(row[:3]) is not None)
        if account_hits:
            label_grids.append(grid)

        columns: dict[int, str] = {}
        for row in grid[:6]:
            for col_index, cell in enumerate(row):
                code = code_in_text(cell, codes)
                if code:
                    columns[col_index] = code
        if columns:
            value_grids.append((grid, columns))

    used_split_pair = False
    for label_grid in label_grids:
        for value_grid, columns in value_grids:
            # Real Mopsfin split tables have equal row counts. Tolerate one
            # decorative row difference but never align unrelated tables.
            if abs(len(label_grid) - len(value_grid)) > 1:
                continue
            limit = min(len(label_grid), len(value_grid))
            matched_fields = 0
            for row_index in range(limit):
                key = field_from_cells(label_grid[row_index][:3])
                if key is None:
                    continue
                matched_fields += 1
                value_row = value_grid[row_index]
                for col_index, code in columns.items():
                    if col_index < len(value_row):
                        assign(code, key, value_row[col_index])
                        out[code]["companyReturned"] = True
            if matched_fields:
                used_split_pair = True
                break
        if used_split_pair:
            break

    # Fallback for the conventional single-table layout used by some
    # responses and by our parser fixtures.
    for grid in grids:
        if not grid:
            continue

        columns: dict[int, str] = {}
        header_end = -1
        for row_index, row in enumerate(grid[:12]):
            matched = False
            for col_index, cell in enumerate(row):
                code = code_in_text(cell, codes)
                if code:
                    columns[col_index] = code
                    matched = True
            if matched:
                header_end = row_index

        if not columns:
            continue

        for code in columns.values():
            out[code]["companyReturned"] = True

        first_value_column = min(columns)
        for row in grid[header_end + 1 :]:
            if not row:
                continue
            # Mopsfin may put an account code (e.g. 2130) before the account
            # name. Search every descriptive column before the first company
            # value instead of assuming the label is row[0].
            key = field_from_cells(row[:first_value_column])
            if key is None:
                continue
            for col_index, code in columns.items():
                if col_index < len(row):
                    assign(code, key, row[col_index])

    for item in out.values():
        status = item["status"]
        if (
            status["contractTotal"] != "reported"
            and status["contractCurrent"] == "reported"
            and status["contractNoncurrent"] == "reported"
        ):
            item["contractTotal"] = item["contractCurrent"] + item["contractNoncurrent"]
            status["contractTotal"] = "calculated"

    return out


def fetch_balance_sheet(
    http: Http,
    period: str,
    batch: list[str],
    meta: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    fields = common_fields("BalanceSheet", "新台幣仟元")
    fields = [
        (key, period.replace("Q", "") if key == "ys" else value)
        for key, value in fields
    ]
    fields.extend(("companyId", display_name(code, meta)) for code in batch)
    response = http.post("/compare/report", fields)
    return parse_balance_sheet(response.text, period, set(batch))


def normalize_identity(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def parse_revenue_payload(
    payload: dict[str, Any], batch: list[str]
) -> dict[str, dict[str, int | None]]:
    periods = [str(value) for value in payload.get("xaxisList") or []]
    multiplier = unit_multiplier(str(payload.get("ylabel") or "新台幣仟元"))

    checked = [str(value) for value in payload.get("checkedNameList") or []]
    shown = [str(value) for value in payload.get("showNameList") or []]
    displayed = [str(value) for value in payload.get("displayCompanyId") or []]

    aliases: dict[str, set[str]] = {code: {normalize_identity(code)} for code in batch}
    batch_set = set(batch)
    for index, raw in enumerate(checked):
        code = code_in_text(raw, batch_set)
        if code is None:
            continue
        for values in (checked, shown, displayed):
            if index < len(values) and values[index]:
                aliases[code].add(normalize_identity(values[index]))

    result: dict[str, dict[str, int | None]] = {code: {} for code in batch}
    claimed: set[str] = set()
    for series in payload.get("graphData") or []:
        label = normalize_identity(series.get("label"))
        candidates = [
            code
            for code in batch
            if code not in claimed
            and (
                label in aliases[code]
                or label == code.lower()
                or re.search(
                    rf"(^|[^0-9a-z]){re.escape(code.lower())}([^0-9a-z]|$)",
                    label,
                )
            )
        ]
        if len(candidates) != 1:
            continue

        code = candidates[0]
        claimed.add(code)
        for point in series.get("data") or []:
            if not isinstance(point, list) or len(point) < 2:
                continue
            try:
                index = int(point[0])
            except (TypeError, ValueError):
                continue
            if index < 0 or index >= len(periods):
                continue
            value = parse_number(point[1])
            result[code][periods[index]] = (
                None if value is None else int(round(value * multiplier))
            )
    return result


def fetch_revenue(
    http: Http, batch: list[str], meta: dict[str, dict[str, Any]]
) -> dict[str, dict[str, int | None]]:
    fields = common_fields("OperatingRevenue", "新台幣仟元")
    fields.extend(("companyId", display_name(code, meta)) for code in batch)
    response = http.post("/compare/data", fields)
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise ValueError("營收端點未回傳 JSON") from exc
    return parse_revenue_payload(payload, batch)


def load_docs(codes: list[str]) -> dict[str, dict[str, Any]]:
    return {
        code: read_json(OUT_DIR / f"{code}.json", {}) or {}
        for code in codes
    }


def ensure_doc(
    doc: dict[str, Any], code: str, meta: dict[str, dict[str, Any]]
) -> None:
    stock = meta[code]
    doc.update(
        {
            "c": code,
            "n": stock.get("n"),
            "m": stock.get("m"),
            "i": stock.get("i"),
            "unit": "TWD",
        }
    )
    doc.setdefault("periods", {})


def save_docs(
    codes: list[str],
    meta: dict[str, dict[str, Any]],
    docs: dict[str, dict[str, Any]],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for code in codes:
        ensure_doc(docs.setdefault(code, {}), code, meta)
        docs[code]["periods"] = dict(sorted(docs[code]["periods"].items()))
        write_json(OUT_DIR / f"{code}.json", docs[code])


def merge_balance_sheet(
    docs: dict[str, dict[str, Any]],
    meta: dict[str, dict[str, Any]],
    period: str,
    parsed: dict[str, dict[str, Any]],
) -> None:
    for code, item in parsed.items():
        if not item.get("companyReturned"):
            continue
        ensure_doc(docs.setdefault(code, {}), code, meta)
        row = docs[code]["periods"].setdefault(period, {})
        for key in (
            "contractCurrent",
            "contractNoncurrent",
            "contractTotal",
            "inventory",
        ):
            row[key] = item.get(key)
        row["balanceSheetBasis"] = "financial_statement"
        status = row.setdefault("status", {})
        status.update(item.get("status") or {})

        industry = str(meta[code].get("i") or "")
        if (
            any(hint in industry for hint in FINANCIAL_HINTS)
            and status.get("inventory") == "not_separately_disclosed"
        ):
            status["inventory"] = "not_applicable"


def merge_revenue(
    docs: dict[str, dict[str, Any]],
    meta: dict[str, dict[str, Any]],
    revenue: dict[str, dict[str, int | None]],
    allowed_periods: set[str],
) -> None:
    for code, series in revenue.items():
        ensure_doc(docs.setdefault(code, {}), code, meta)
        for period, value in series.items():
            if period not in allowed_periods:
                continue
            row = docs[code]["periods"].setdefault(period, {})
            row["revenue"] = value
            row["revenueBasis"] = "mopsfin_quarterly"
            row.setdefault("status", {})["revenue"] = (
                "reported" if value is not None else "missing"
            )


def newest(periods: dict[str, dict[str, Any]], key: str) -> str | None:
    candidates = [
        period
        for period, row in periods.items()
        if row.get(key) is not None
    ]
    return max(candidates) if candidates else None


def change(
    periods: dict[str, dict[str, Any]], period: str | None, key: str
) -> dict[str, float | None] | None:
    if period is None:
        return None
    current = (periods.get(period) or {}).get(key)
    return {
        "qoq": pct(
            current,
            (periods.get(previous_quarter(period)) or {}).get(key),
        ),
        "yoy": pct(
            current,
            (periods.get(previous_year(period)) or {}).get(key),
        ),
    }


def build_latest(
    meta: dict[str, dict[str, Any]], docs: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    stocks: dict[str, Any] = {}
    for code, stock in meta.items():
        periods = (docs.get(code) or {}).get("periods") or {}
        contract_period = newest(periods, "contractCurrent")
        total_period = newest(periods, "contractTotal")
        inventory_period = newest(periods, "inventory")
        revenue_period = newest(periods, "revenue")

        stocks[code] = {
            "n": stock.get("n"),
            "m": stock.get("m"),
            "i": stock.get("i"),
            "contractCurrentPeriod": contract_period,
            "contractCurrent": (
                (periods.get(contract_period) or {}).get("contractCurrent")
                if contract_period
                else None
            ),
            "contractCurrentChange": change(
                periods, contract_period, "contractCurrent"
            ),
            "contractTotalPeriod": total_period,
            "contractTotal": (
                (periods.get(total_period) or {}).get("contractTotal")
                if total_period
                else None
            ),
            "contractTotalChange": change(
                periods, total_period, "contractTotal"
            ),
            "inventoryPeriod": inventory_period,
            "inventory": (
                (periods.get(inventory_period) or {}).get("inventory")
                if inventory_period
                else None
            ),
            "inventoryChange": change(
                periods, inventory_period, "inventory"
            ),
            "revenuePeriod": revenue_period,
            "revenue": (
                (periods.get(revenue_period) or {}).get("revenue")
                if revenue_period
                else None
            ),
            "revenueChange": change(
                periods, revenue_period, "revenue"
            ),
        }

    return {
        "updatedAt": now_taipei().isoformat(timespec="seconds"),
        "unit": "TWD",
        "source": {
            "name": "公開資訊觀測站－財務比較 E 點通",
            "url": BASE + "/",
        },
        "notes": {
            "contract": (
                "預設使用合約負債－流動；總合約負債只在公司明列總額，"
                "或流動與非流動皆有明確數值時提供。"
            ),
            "missing": (
                "null 代表未單獨揭露、不適用或該期沒有資料，不會改寫為 0。"
            ),
            "revenue": (
                "營收採 E 點通 quarterly 口徑。上市櫃通常為單季；"
                "興櫃依申報頻率可能只出現在 Q2/Q4，因此前端只比較實際回傳期別。"
            ),
        },
        "stocks": stocks,
    }


def validate_4563(
    docs: dict[str, dict[str, Any]], *, require_benchmark: bool = False
) -> None:
    """Regression guard for the contract-liability values known to have been wrong before."""
    periods = ((docs.get("4563") or {}).get("periods") or {})
    checks = {
        ("2026Q2", "contractCurrent"): (145_000_000, 5_000_000),
        ("2026Q2", "inventory"): (1_382_000_000, 8_000_000),
        ("2026Q1", "contractCurrent"): (181_000_000, 5_000_000),
        ("2026Q1", "inventory"): (1_403_000_000, 8_000_000),
    }
    errors: list[str] = []
    for (period, key), (expected, tolerance) in checks.items():
        actual = (periods.get(period) or {}).get(key)
        if actual is None:
            if require_benchmark:
                errors.append(f"4563 {period} {key}: 未抓到資料")
            continue
        if abs(actual - expected) > tolerance:
            errors.append(
                f"4563 {period} {key}: {actual:,}，預期約 {expected:,}"
            )
    if errors:
        raise ValueError(
            "4563 基準驗證失敗，拒絕發布：\n" + "\n".join(errors)
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="完整回補最近幾年，預設 5 年",
    )
    parser.add_argument(
        "--latest-only",
        action="store_true",
        help="只更新最近已完成財報季的資產負債表；營收趨勢仍會刷新",
    )
    parser.add_argument(
        "--codes",
        default="",
        help="除錯用：逗號分隔股票代號",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=0,
        help="除錯用：每期最多處理幾批；0 表示不限",
    )
    args = parser.parse_args()

    latest = read_json(DATA_DIR / "latest.json", []) or []
    meta = {
        str(row.get("c")): row
        for row in latest
        if len(str(row.get("c") or "")) == 4
        and str(row.get("c") or "").isdigit()
    }
    if args.codes:
        selected = {
            value.strip()
            for value in args.codes.split(",")
            if value.strip()
        }
        meta = {
            code: row
            for code, row in meta.items()
            if code in selected
        }
    if not meta:
        raise SystemExit("latest.json 沒有可用股票母體")

    codes = sorted(meta)
    docs = load_docs(codes)
    http = Http()

    latest_period = latest_completed_period(now_taipei().date())
    all_periods = periods_for(max(1, args.years), latest_period)
    balance_sheet_periods = (
        [period_key(*latest_period)]
        if args.latest_only
        else all_periods
    )
    allowed_periods = set(all_periods)

    log(f"營收趨勢：{len(codes)} 檔")
    for batch_index, batch in enumerate(
        chunks(codes, BATCH_SIZE), start=1
    ):
        if args.max_batches and batch_index > args.max_batches:
            break
        try:
            merge_revenue(
                docs,
                meta,
                fetch_revenue(http, batch, meta),
                allowed_periods,
            )
        except Exception as exc:  # noqa: BLE001
            log(f"[營收批次略過] #{batch_index} {batch}: {exc}")

    for period in balance_sheet_periods:
        log(f"資產負債表 {period}：{len(codes)} 檔")
        for batch_index, batch in enumerate(
            chunks(codes, BATCH_SIZE), start=1
        ):
            if args.max_batches and batch_index > args.max_batches:
                break
            try:
                parsed = fetch_balance_sheet(
                    http, period, batch, meta
                )
                merge_balance_sheet(
                    docs, meta, period, parsed
                )
            except Exception as exc:  # noqa: BLE001
                log(
                    f"[BS批次略過] {period} "
                    f"#{batch_index} {batch}: {exc}"
                )
        save_docs(codes, meta, docs)

    validate_4563(
        docs,
        require_benchmark=(
            "4563" in meta
            and "2026Q1" in allowed_periods
            and "2026Q2" in allowed_periods
        ),
    )
    save_docs(codes, meta, docs)
    write_json(
        LATEST_OUT,
        build_latest(meta, docs),
        compact=True,
    )
    log(f"完成：{len(meta)} 檔；輸出 {LATEST_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
