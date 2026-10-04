"""Supplement operating indicators with iXBRL note disclosures.

Why this exists:
- Some issuers (for example TSMC) do not present contract liabilities as a
  separate line on the face of the balance sheet.
- The amount is instead disclosed in the notes and tagged in the filed iXBRL.
- Customer temporary receipts / customer advances are economically useful lead
  indicators but are NOT contract liabilities, so they are stored separately.

This script downloads the official MOPS iXBRL filing, reads facts whose context
instant matches the requested quarter-end date, and classifies note rows by
their visible disclosure labels. Missing values remain null.

It is intentionally resumable: rows store notesChecked/notesCheckedAt so a
bounded number of filings can be processed on each scheduled run without
hammering MOPS.
"""
from __future__ import annotations

import argparse
import io
import re
import time
import zipfile
from datetime import date
from typing import Any

import requests
from bs4 import BeautifulSoup

from build_operating_leads import (
    DATA_DIR,
    LATEST_OUT,
    build_latest,
    latest_completed_period,
    load_docs,
    now_taipei,
    period_key,
    periods_for,
    read_json,
    save_docs,
    write_json,
)
from util import log

MOPSOV = "https://mopsov.twse.com.tw"
DOWNLOAD_URL = (
    MOPSOV
    + "/server-java/FileDownLoad"
    + "?functionName=t164sb01&step=9"
    + "&co_id={code}&year={year}&season={quarter}&report_id={report_id}"
)
REQUEST_GAP = 1.0
UA = "tw-stock-valuation/note-disclosures (+https://roseamyclara.github.io/tw-stock-valuation/)"

CUSTOMER_RECEIPT_FIELDS = (
    "customerReceiptsCurrent",
    "customerReceiptsNoncurrent",
    "customerReceiptsTotal",
)


def canon(value: Any) -> str:
    return (
        re.sub(r"\s+", "", str(value or ""))
        .replace("－", "-")
        .replace("–", "-")
        .replace("—", "-")
        .replace("（", "(")
        .replace("）", ")")
        .lower()
    )


def attr_ci(tag, name: str) -> Any:
    wanted = name.lower()
    for key, value in (tag.attrs or {}).items():
        if str(key).lower() == wanted:
            return value
    return None


def quarter_end(period: str) -> str:
    match = re.fullmatch(r"(\d{4})Q([1-4])", period)
    if not match:
        raise ValueError(period)
    year, quarter = int(match.group(1)), int(match.group(2))
    month_day = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[quarter]
    return f"{year}-{month_day}"


def numeric_text(value: Any) -> float | None:
    s = re.sub(r"\s+", "", str(value or ""))
    if not s or s in {"-", "--", "—", "–", "n/a", "N/A"}:
        return None
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    s = s.replace(",", "").replace("$", "").replace("NT$", "")
    s = re.sub(r"[^0-9.\-]", "", s)
    if not s or s in {"-", ".", "-."}:
        return None
    try:
        out = float(s)
    except ValueError:
        return None
    return -out if negative and out > 0 else out


def ix_fact_value(tag) -> int | None:
    nil = str(attr_ci(tag, "xsi:nil") or attr_ci(tag, "nil") or "").lower()
    if nil in {"true", "1"}:
        return None

    raw = numeric_text("".join(tag.stripped_strings))
    if raw is None:
        return None

    try:
        scale = int(attr_ci(tag, "scale") or 0)
    except (TypeError, ValueError):
        scale = 0

    sign = str(attr_ci(tag, "sign") or "")
    if sign.strip() == "-" and raw > 0:
        raw = -raw

    return int(round(raw * (10**scale)))


def is_context(tag) -> bool:
    name = str(getattr(tag, "name", "") or "").lower()
    return name == "context" or name.endswith(":context")


def is_instant(tag) -> bool:
    name = str(getattr(tag, "name", "") or "").lower()
    return name == "instant" or name.endswith(":instant")


def is_ix_number(tag) -> bool:
    name = str(getattr(tag, "name", "") or "").lower()
    return name == "nonfraction" or name.endswith(":nonfraction")


def context_instants(soup: BeautifulSoup) -> dict[str, str]:
    out: dict[str, str] = {}
    for ctx in soup.find_all(is_context):
        context_id = str(attr_ci(ctx, "id") or "").strip()
        if not context_id:
            continue
        instant = ctx.find(is_instant)
        if instant:
            value = " ".join(instant.stripped_strings).strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                out[context_id] = value
    return out


def previous_context(table) -> str:
    """Small nearby text window used to identify note section headings."""
    parts: list[str] = []
    node = table
    for _ in range(12):
        node = node.find_previous(
            ["p", "h1", "h2", "h3", "h4", "h5", "strong", "b", "div", "span"]
        )
        if node is None:
            break
        text = " ".join(node.stripped_strings).strip()
        # Large wrapper divs contain whole pages and create false positives.
        if not text or len(text) > 220:
            continue
        if text not in parts:
            parts.append(text)
        if len(" ".join(parts)) > 600:
            break
    return " ".join(parts)


def is_contract_text(text: str) -> bool:
    c = canon(text)
    return "合約負債" in c or "contractliabilit" in c


def is_customer_receipt_text(text: str) -> bool:
    c = canon(text)
    chinese = (
        ("客戶" in c and ("暫收" in c or "預收" in c))
        or "暫收客戶款" in c
        or "預收客戶款" in c
    )
    english = any(
        phrase in c
        for phrase in (
            "temporaryreceiptsfromcustomer",
            "temporaryreceiptsfromcustomers",
            "customeradvances",
            "advancesfromcustomer",
            "advancesfromcustomers",
            "customerdeposits",
        )
    )
    return chinese or english


def liquidity(text: str) -> str | None:
    c = canon(text)
    if "非流動" in c or "noncurrent" in c or "non-current" in c:
        return "noncurrent"
    if (
        "流動" in c
        or "currentportion" in c
        or "currentliabilit" in c
    ):
        return "current"
    return None


def unique_target_value(row, instants: dict[str, str], target_date: str) -> int | None:
    values: set[int] = set()
    for fact in row.find_all(is_ix_number):
        context_ref = str(
            attr_ci(fact, "contextref") or attr_ci(fact, "contextRef") or ""
        ).strip()
        if instants.get(context_ref) != target_date:
            continue
        value = ix_fact_value(fact)
        if value is not None:
            values.add(value)
    if len(values) == 1:
        return next(iter(values))
    # Ambiguous rows are deliberately ignored instead of guessing.
    return None


def merge_value(out: dict[str, int | None], key: str, value: int | None) -> None:
    if value is None:
        return
    old = out.get(key)
    if old is None:
        out[key] = value
    elif old != value:
        # Multiple documents/tables disagreeing is a hard ambiguity; remove it.
        out[key] = None


def parse_ixbrl_html(html: str, period: str) -> dict[str, int | None]:
    soup = BeautifulSoup(html, "html.parser")
    instants = context_instants(soup)
    target = quarter_end(period)

    out: dict[str, int | None] = {
        "contractCurrent": None,
        "contractNoncurrent": None,
        "contractTotal": None,
        "customerReceiptsCurrent": None,
        "customerReceiptsNoncurrent": None,
        "customerReceiptsTotal": None,
    }

    for table in soup.find_all("table"):
        context = previous_context(table)
        context_contract = is_contract_text(context)
        context_customer = is_customer_receipt_text(context)

        for row in table.find_all("tr"):
            row_text = " ".join(row.stripped_strings)
            facts = row.find_all(is_ix_number)
            if not facts:
                continue

            value = unique_target_value(row, instants, target)
            if value is None:
                continue

            fact_names = " ".join(str(attr_ci(f, "name") or "") for f in facts)
            direct_contract = is_contract_text(row_text) or is_contract_text(fact_names)
            direct_customer = (
                is_customer_receipt_text(row_text)
                or is_customer_receipt_text(fact_names)
            )

            # Contract-liability note row.
            if direct_contract or (
                context_contract
                and any(x in canon(row_text) for x in ("流動", "current", "合計", "total"))
            ):
                liq = liquidity(row_text + " " + fact_names)
                if liq == "current":
                    merge_value(out, "contractCurrent", value)
                elif liq == "noncurrent":
                    merge_value(out, "contractNoncurrent", value)
                else:
                    merge_value(out, "contractTotal", value)
                continue

            # Customer temporary receipts / customer advances.
            # Rows such as "Current portion" rely on the immediately preceding
            # note-section heading to establish that they belong to customer receipts.
            if direct_customer or (
                context_customer
                and any(
                    token in canon(row_text)
                    for token in ("流動", "current", "非流動", "noncurrent", "合計", "total")
                )
            ):
                liq = liquidity(row_text + " " + fact_names)
                if liq == "current":
                    merge_value(out, "customerReceiptsCurrent", value)
                elif liq == "noncurrent":
                    merge_value(out, "customerReceiptsNoncurrent", value)
                else:
                    merge_value(out, "customerReceiptsTotal", value)

    if (
        out["contractTotal"] is None
        and out["contractCurrent"] is not None
        and out["contractNoncurrent"] is not None
    ):
        out["contractTotal"] = (
            out["contractCurrent"] + out["contractNoncurrent"]
        )

    if (
        out["customerReceiptsTotal"] is None
        and out["customerReceiptsCurrent"] is not None
        and out["customerReceiptsNoncurrent"] is not None
    ):
        out["customerReceiptsTotal"] = (
            out["customerReceiptsCurrent"]
            + out["customerReceiptsNoncurrent"]
        )

    return out


def ixbrl_documents(content: bytes) -> list[str]:
    blobs: list[bytes] = []
    if content[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for name in archive.namelist():
                lower = name.lower()
                if lower.endswith((".html", ".htm", ".xhtml")):
                    blobs.append(archive.read(name))
    else:
        blobs = [content]

    docs: list[str] = []
    for blob in blobs:
        if b"ix:nonFraction" not in blob and b"ix:nonfraction" not in blob.lower():
            continue
        try:
            docs.append(blob.decode("utf-8"))
        except UnicodeDecodeError:
            docs.append(blob.decode("utf-8", errors="ignore"))
    return docs


class NoteClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": UA,
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
            }
        )
        self.last_hit = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self.last_hit
        if elapsed < REQUEST_GAP:
            time.sleep(REQUEST_GAP - elapsed)
        self.last_hit = time.monotonic()

    def download(self, code: str, period: str) -> tuple[bytes, str]:
        year, quarter = period.split("Q")
        last_error: Exception | None = None

        for report_id in ("C", "A"):
            url = DOWNLOAD_URL.format(
                code=code,
                year=year,
                quarter=quarter,
                report_id=report_id,
            )
            for attempt in range(3):
                if attempt:
                    time.sleep(1.5 * attempt)
                self.wait()
                try:
                    response = self.session.get(
                        url,
                        timeout=60,
                        allow_redirects=True,
                        headers={
                            "Referer": f"{MOPSOV}/mops/web/t203sb01",
                            "Accept": "text/html,application/xhtml+xml,application/zip,*/*;q=0.8",
                        },
                    )
                    response.raise_for_status()
                    content = response.content
                    if content[:2] == b"PK" or b"ix:nonFraction" in content or b"ix:nonfraction" in content.lower():
                        return content, report_id
                    last_error = RuntimeError("官方回傳內容不是 iXBRL/ZIP")
                except requests.RequestException as exc:
                    last_error = exc

        raise RuntimeError(f"{code} {period} iXBRL 下載失敗：{last_error}")


def parse_report(content: bytes, period: str) -> dict[str, int | None]:
    docs = ixbrl_documents(content)
    if not docs:
        raise ValueError("檔案內找不到 iXBRL 文件")

    merged: dict[str, int | None] = {
        "contractCurrent": None,
        "contractNoncurrent": None,
        "contractTotal": None,
        "customerReceiptsCurrent": None,
        "customerReceiptsNoncurrent": None,
        "customerReceiptsTotal": None,
    }
    for doc in docs:
        parsed = parse_ixbrl_html(doc, period)
        for key, value in parsed.items():
            merge_value(merged, key, value)
    return merged


def apply_disclosures(
    row: dict[str, Any],
    parsed: dict[str, int | None],
    report_id: str,
) -> None:
    status = row.setdefault("status", {})

    for key in ("contractCurrent", "contractNoncurrent", "contractTotal"):
        note_value = parsed.get(key)
        row[f"{key}Note"] = note_value

        if row.get(key) is not None:
            row.setdefault(f"{key}Source", "balance_sheet")
        elif note_value is not None:
            row[key] = note_value
            row[f"{key}Source"] = "ixbrl_notes"
            status[key] = "reported_in_notes"

    for key in CUSTOMER_RECEIPT_FIELDS:
        row[key] = parsed.get(key)
        status[key] = (
            "reported_in_notes" if parsed.get(key) is not None else "not_disclosed"
        )

    row["notesChecked"] = True
    row["notesCheckedAt"] = now_taipei().isoformat(timespec="seconds")
    row["notesReportType"] = "consolidated" if report_id == "C" else "standalone"
    row["notesSource"] = "mops_ixbrl"


def refresh_operating_latest(
    meta: dict[str, dict[str, Any]],
    codes: list[str],
) -> None:
    all_codes = sorted(meta)
    docs = load_docs(all_codes)
    write_json(
        LATEST_OUT,
        build_latest(meta, docs),
        compact=True,
    )


def period_candidates(args, latest_period: tuple[int, int]) -> list[str]:
    if args.years > 0:
        return periods_for(args.years, latest_period)
    return [period_key(*latest_period)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--codes",
        default="",
        help="只處理指定股票，逗號分隔；留空表示全市場漸進處理",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=0,
        help="回補附註歷史年數；0 表示只檢查最新已完成財報季",
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=150,
        help="本次最多下載幾份 iXBRL 財報，避免對官方站台過度請求",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="即使 notesChecked 已存在仍重新檢查",
    )
    parser.add_argument(
        "--require-tsmc",
        action="store_true",
        help="若包含 2330，要求 2026Q2 台積電附註基準資料必須抓到",
    )
    args = parser.parse_args()

    latest_rows = read_json(DATA_DIR / "latest.json", []) or []
    meta = {
        str(row.get("c")): row
        for row in latest_rows
        if len(str(row.get("c") or "")) == 4
        and str(row.get("c") or "").isdigit()
    }
    if not meta:
        raise SystemExit("latest.json 沒有股票母體")

    if args.codes:
        selected = {x.strip() for x in args.codes.split(",") if x.strip()}
        codes = [code for code in sorted(meta) if code in selected]
    else:
        codes = sorted(meta)

    latest_period = latest_completed_period(now_taipei().date())
    periods = period_candidates(args, latest_period)
    docs = load_docs(codes)
    client = NoteClient()

    jobs: list[tuple[str, str]] = []
    for code in codes:
        doc = docs.setdefault(code, {})
        pmap = doc.setdefault("periods", {})
        for period in periods:
            row = pmap.setdefault(period, {})
            if row.get("notesChecked") and not args.refresh:
                continue
            jobs.append((code, period))

    # TSMC first so the known "contract liability only in notes" case is always
    # validated before the general market queue.
    jobs.sort(
        key=lambda item: (
            item[0] != "2330",
            (docs.get(item[0], {}).get("periods", {}).get(item[1], {}).get("contractCurrent") is not None),
            item[0],
            item[1],
        )
    )

    if args.max_requests > 0:
        jobs = jobs[: args.max_requests]

    log(f"iXBRL 附註：本次 {len(jobs)} 份（期間 {periods[0]}～{periods[-1]}）")

    processed = 0
    for code, period in jobs:
        row = docs[code].setdefault("periods", {}).setdefault(period, {})
        try:
            content, report_id = client.download(code, period)
            parsed = parse_report(content, period)
            apply_disclosures(row, parsed, report_id)
            processed += 1
            if code == "2330":
                log(
                    f"2330 {period}: 合約負債={parsed.get('contractCurrent') or parsed.get('contractTotal')} "
                    f"暫收客戶款={parsed.get('customerReceiptsTotal')}"
                )
        except Exception as exc:  # noqa: BLE001
            row["notesChecked"] = True
            row["notesCheckedAt"] = now_taipei().isoformat(timespec="seconds")
            row["notesStatus"] = "unavailable"
            row["notesError"] = str(exc)[:240]
            log(f"[附註略過] {code} {period}: {exc}")

    save_docs(codes, meta, docs)

    # Rebuild latest summary from the entire universe, not only touched codes.
    all_docs = load_docs(sorted(meta))
    write_json(
        LATEST_OUT,
        build_latest(meta, all_docs),
        compact=True,
    )

    if args.require_tsmc and "2330" in meta:
        tsmc = load_docs(["2330"]).get("2330", {})
        q2 = (tsmc.get("periods") or {}).get("2026Q2", {})
        contract = q2.get("contractCurrent")
        receipts = q2.get("customerReceiptsTotal")
        expected_contract = 55_852_048_000
        expected_receipts = 234_225_146_000

        errors = []
        if contract is None or abs(contract - expected_contract) > 20_000_000:
            errors.append(
                f"2330 2026Q2 合約負債 {contract}，預期約 {expected_contract}"
            )
        if receipts is None or abs(receipts - expected_receipts) > 20_000_000:
            errors.append(
                f"2330 2026Q2 暫收客戶款 {receipts}，預期約 {expected_receipts}"
            )
        if errors:
            raise ValueError("台積電附註驗證失敗：\n" + "\n".join(errors))

    log(f"iXBRL 附註完成：{processed}/{len(jobs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
