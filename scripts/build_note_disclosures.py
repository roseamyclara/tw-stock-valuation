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
import pymupdf
from urllib.parse import urlencode, urljoin

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
IXBRL_URL = MOPSOV + "/server-java/t164sb01"
# Legacy download form retained only as a last acquisition fallback.
DOWNLOAD_URL = (
    MOPSOV
    + "/server-java/FileDownLoad"
    + "?functionName=t164sb01&step=9"
    + "&co_id={code}&year={year}&season={quarter}&report_id={report_id}"
)
REQUEST_GAP = 1.0
UA = "tw-stock-valuation/note-disclosures (+https://roseamyclara.github.io/tw-stock-valuation/)"
BOOK_QUERY = MOPSOV + "/mops/web/ajax_t57sb01_q1"
BOOK_PAGE = MOPSOV + "/mops/web/t57sb01_q1"
DOC_DOWNLOAD = "https://doc.twse.com.tw/server-java/t57sb01"

_PDF_HREF_RE = re.compile(r"""href=["'](/pdf/[^"']+\.pdf)["']""", re.I)
_DOC_FILENAME_RE = re.compile(
    r"(?P<filename>(?P<year>\d{4})(?P<quarter>0[1-4])_"
    r"(?P<code>\d{4,6})_(?P<type>AI1|AIA|AE1)\.pdf)",
    re.I,
)

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


_RAW_ATTR_RE = re.compile(r"""([\w:-]+)\s*=\s*["']([^"']*)["']""", re.I)
_RAW_CONTEXT_RE = re.compile(
    r'<xbrli:context\b(?P<attrs>[^>]*)>(?P<body>.*?)</xbrli:context>',
    re.I | re.S,
)
_RAW_INSTANT_RE = re.compile(r'<xbrli:instant>([^<]+)</xbrli:instant>', re.I)
_RAW_FACT_RE = re.compile(
    r'<ix:nonfraction\b(?P<attrs>[^>]*)>(?P<body>.*?)</ix:nonfraction>'
    r'|<ix:nonfraction\b(?P<selfattrs>[^>]*)/>',
    re.I | re.S,
)
_RAW_TAG_RE = re.compile(r'<[^>]+>', re.S)


def raw_attrs(value: str) -> dict[str, str]:
    return {key.lower(): val for key, val in _RAW_ATTR_RE.findall(value)}


def decode_ixbrl_bytes(blob: bytes) -> str:
    """Decode MOPS bytes from content, because the declared charset is unreliable."""
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return blob.decode("big5hkscs", errors="replace")


def regex_context_instants(document: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in _RAW_CONTEXT_RE.finditer(document):
        attrs = raw_attrs(match.group("attrs"))
        context_id = attrs.get("id")
        instant = _RAW_INSTANT_RE.search(match.group("body"))
        if not context_id or not instant:
            continue
        value = instant.group(1).strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            out[context_id] = value
    return out


def raw_fact_value(body: str | None, attrs: dict[str, str]) -> int | None:
    if body is None:
        return None
    if (attrs.get("xsi:nil") or attrs.get("nil") or "").lower() in {"true", "1"}:
        return None
    value = numeric_text(_RAW_TAG_RE.sub("", body))
    if value is None:
        return None
    try:
        scale = int(attrs.get("scale") or 0)
    except ValueError:
        scale = 0
    if attrs.get("sign") == "-" and value > 0:
        value = -value
    return int(round(value * (10 ** scale)))


def parse_ixbrl_facts_regex(document: str, period: str) -> dict[str, int | None]:
    """Regex-first extraction avoids HTML tree repair dropping inline-XBRL facts."""
    instants = regex_context_instants(document)
    target = quarter_end(period)
    out = empty_note_values()

    for match in _RAW_FACT_RE.finditer(document):
        attrs = raw_attrs(match.group("attrs") or match.group("selfattrs") or "")
        if instants.get(attrs.get("contextref", "")) != target:
            continue

        concept = attrs.get("name", "")
        local = canon(concept.split(":")[-1])
        value = raw_fact_value(match.group("body"), attrs)
        if value is None:
            continue

        # For generic note concepts (e.g. ContractLiabilities), the visible
        # row label immediately BEFORE the fact tells whether it is current.
        # Never inspect the following row: that can contain an unrelated
        # non-current customer-receipt fact and contaminate classification.
        around = document[max(0, match.start() - 500): match.start()]
        around_text = canon(_RAW_TAG_RE.sub(" ", around))

        if "contractliabilit" in local:
            is_noncurrent = (
                "noncurrent" in local
                or "非流動負債" in around_text
                or "noncurrentliabilit" in around_text
            )
            is_current = (
                not is_noncurrent
                and (
                    "currentcontractliabilit" in local
                    or "contractliabilitiescurrent" in local
                    or "流動負債" in around_text
                    or "currentliabilit" in around_text
                )
            )
            if is_noncurrent:
                merge_value(out, "contractNoncurrent", value)
            elif is_current:
                merge_value(out, "contractCurrent", value)
            else:
                merge_value(out, "contractTotal", value)
            continue

        is_customer_receipt = any(
            token in local
            for token in (
                "temporaryreceiptsfromcustomer",
                "temporaryreceiptsfromcustomers",
                "customeradvances",
                "advancesfromcustomer",
                "advancesfromcustomers",
            )
        )
        if is_customer_receipt:
            is_noncurrent = "noncurrent" in local
            is_current = not is_noncurrent and "current" in local
            if is_noncurrent:
                merge_value(out, "customerReceiptsNoncurrent", value)
            elif is_current:
                merge_value(out, "customerReceiptsCurrent", value)
            else:
                merge_value(out, "customerReceiptsTotal", value)

    if (
        out["contractTotal"] is None
        and out["contractCurrent"] is not None
        and out["contractNoncurrent"] is not None
    ):
        out["contractTotal"] = out["contractCurrent"] + out["contractNoncurrent"]
    if (
        out["customerReceiptsTotal"] is None
        and out["customerReceiptsCurrent"] is not None
        and out["customerReceiptsNoncurrent"] is not None
    ):
        out["customerReceiptsTotal"] = (
            out["customerReceiptsCurrent"] + out["customerReceiptsNoncurrent"]
        )
    return out


def debug_raw_ixbrl_facts(document: str, period: str) -> list[str]:
    instants = regex_context_instants(document)
    target = quarter_end(period)
    target_refs = {ref for ref, value in instants.items() if value == target}
    lines = [
        f"raw-debug {period}: contexts={len(instants)} targetRefs={len(target_refs)}"
    ]
    candidates: list[str] = []
    for match in _RAW_FACT_RE.finditer(document):
        attrs = raw_attrs(match.group("attrs") or match.group("selfattrs") or "")
        name = attrs.get("name", "")
        local = canon(name.split(":")[-1])
        if not any(
            token in local
            for token in ("contract", "liabil", "temporary", "receipt", "customer", "advance")
        ):
            continue
        cref = attrs.get("contextref", "")
        value = raw_fact_value(match.group("body"), attrs)
        candidates.append(
            f"{name} context={cref} instant={instants.get(cref)} value={value}"
        )
        if len(candidates) >= 40:
            break
    lines.extend(candidates or ["raw-debug: no matching concept names"])
    return lines


def parse_ixbrl_html_dom(html: str, period: str) -> dict[str, int | None]:
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
        section_kind: str | None = (
            "customer" if context_customer else "contract" if context_contract else None
        )

        for row in table.find_all("tr"):
            row_text = " ".join(row.stripped_strings)

            # Some iXBRL renderers put the note-section heading in a table row
            # immediately before the numeric rows. Track that section even if
            # the heading row itself has no ix:nonFraction facts.
            if is_customer_receipt_text(row_text):
                section_kind = "customer"
            elif is_contract_text(row_text) and not is_customer_receipt_text(row_text):
                section_kind = "contract"

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

            row_contract_context = context_contract or section_kind == "contract"
            row_customer_context = context_customer or section_kind == "customer"

            # Contract-liability note row.
            if direct_contract or (
                row_contract_context
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
                row_customer_context
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


def parse_ixbrl_html(html: str, period: str) -> dict[str, int | None]:
    """Use raw facts first; visible-table parsing only fills remaining gaps."""
    primary = parse_ixbrl_facts_regex(html, period)
    fallback = parse_ixbrl_html_dom(html, period)
    for key, value in fallback.items():
        if primary.get(key) is None and value is not None:
            primary[key] = value

    if (
        primary["contractTotal"] is None
        and primary["contractCurrent"] is not None
        and primary["contractNoncurrent"] is not None
    ):
        primary["contractTotal"] = (
            primary["contractCurrent"] + primary["contractNoncurrent"]
        )
    if (
        primary["customerReceiptsTotal"] is None
        and primary["customerReceiptsCurrent"] is not None
        and primary["customerReceiptsNoncurrent"] is not None
    ):
        primary["customerReceiptsTotal"] = (
            primary["customerReceiptsCurrent"]
            + primary["customerReceiptsNoncurrent"]
        )
    return primary


def debug_ixbrl_html(html: str, period: str) -> list[str]:
    """Compact diagnostics for one real filing; avoids dumping the document."""
    soup = BeautifulSoup(html, "html.parser")
    instants = context_instants(soup)
    target = quarter_end(period)
    target_refs = {ref for ref, instant in instants.items() if instant == target}
    facts = soup.find_all(is_ix_number)
    target_facts = [
        fact
        for fact in facts
        if str(attr_ci(fact, "contextref") or "").strip() in target_refs
    ]

    lines = [
        (
            f"debug {period}: contexts={len(instants)} "
            f"targetRefs={len(target_refs)} facts={len(facts)} "
            f"targetFacts={len(target_facts)} tables={len(soup.find_all('table'))}"
        )
    ]

    keys = ("合約負債", "contract liabil", "暫收客戶", "temporary receipt", "customer")
    found_rows = 0
    for row in soup.find_all("tr"):
        text_value = " ".join(row.stripped_strings)
        low = text_value.lower()
        if not any(key.lower() in low for key in keys):
            continue
        row_facts = row.find_all(is_ix_number)
        details = []
        for fact in row_facts[:8]:
            details.append(
                (
                    str(attr_ci(fact, "name") or "?"),
                    str(attr_ci(fact, "contextref") or "?"),
                    "".join(fact.stripped_strings)[:80],
                    str(attr_ci(fact, "scale") or "0"),
                )
            )
        lines.append(
            f"row[{found_rows}] {text_value[:700]} facts={details}"
        )
        found_rows += 1
        if found_rows >= 12:
            break

    if found_rows == 0:
        full_text = " ".join(soup.stripped_strings)
        low = full_text.lower()
        for key in keys:
            idx = low.find(key.lower())
            if idx >= 0:
                lines.append(
                    f"text-snippet {key}: {full_text[max(0, idx-220):idx+700]}"
                )
    return lines


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
        docs.append(decode_ixbrl_bytes(blob))
    return docs



def empty_note_values() -> dict[str, int | None]:
    return {
        "contractCurrent": None,
        "contractNoncurrent": None,
        "contractTotal": None,
        "customerReceiptsCurrent": None,
        "customerReceiptsNoncurrent": None,
        "customerReceiptsTotal": None,
    }


def note_values_present(values: dict[str, int | None]) -> bool:
    return any(value is not None for value in values.values())


def split_period_for_pdf(period: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{4})Q([1-4])", period)
    if not match:
        raise ValueError(period)
    return int(match.group(1)), int(match.group(2))


def roc_period_label(period: str) -> tuple[int, str]:
    year, quarter = split_period_for_pdf(period)
    label = {1: "第一季", 2: "第二季", 3: "第三季", 4: "第四季"}[quarter]
    return year - 1911, label


def report_filename_from_book_html(html: str, code: str, period: str) -> str | None:
    roc_year, quarter_label = roc_period_label(period)
    soup = BeautifulSoup(html, "html.parser")
    wanted_period = canon(f"{roc_year}年{quarter_label}")

    for row in soup.find_all("tr"):
        text_value = " ".join(row.stripped_strings)
        key = canon(text_value)
        if code not in key or wanted_period not in key:
            continue
        if "ifrss合併財報" not in key and "合併財務報告" not in key:
            continue
        if "英文" in key or "english" in key:
            continue
        match = re.search(r"([A-Za-z0-9_.-]+\.pdf)", str(row), flags=re.I)
        if match:
            return match.group(1)

    for row in soup.find_all("tr"):
        text_value = " ".join(row.stripped_strings)
        key = canon(text_value)
        if code not in key or wanted_period not in key or "英文" in key:
            continue
        matches = re.findall(r"([A-Za-z0-9_.-]+\.pdf)", str(row), flags=re.I)
        preferred = [filename for filename in matches if "_A11" in filename.upper()]
        if len(preferred) == 1:
            return preferred[0]
    return None


def pdf_amount_multiplier(text: str) -> int:
    compact = canon(text)
    if "百萬元" in compact:
        return 1_000_000
    if "仟元" in compact or "千元" in compact:
        return 1_000
    raise ValueError("財報 PDF 找不到明確的仟元／千元金額單位")


def first_money_after_label(text: str, label_start: int, window: int = 420) -> int | None:
    chunk = text[label_start : label_start + window]
    match = re.search(r"(?<!\d)(\d{1,3}(?:,\d{3})+)(?!\d)", chunk)
    if not match:
        return None
    return int(match.group(1).replace(",", ""))



def parse_pdf_note_text(text: str, period: str) -> dict[str, int | None]:
    multiplier = pdf_amount_multiplier(text)
    out = empty_note_values()
    lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in text.replace("\u3000", " ").splitlines()
        if line.strip()
    ]

    for index, line in enumerate(lines):
        if not is_contract_text(line):
            continue
        block = " ".join(lines[index : index + 4])
        label_start = block.find("合約負債")
        if label_start < 0:
            label_start = block.lower().find("contract liabil")
        if label_start < 0:
            continue
        raw = first_money_after_label(block, label_start)
        if raw is None:
            continue
        value = raw * multiplier
        liq = liquidity(block)
        if liq == "noncurrent":
            merge_value(out, "contractNoncurrent", value)
        elif liq == "current":
            merge_value(out, "contractCurrent", value)
        else:
            merge_value(out, "contractTotal", value)

    # PDF text extraction often splits "暫收客戶款" and its table across
    # several lines. Find the section with a sliding window instead of
    # requiring the whole heading to survive on one extracted line.
    customer_starts: list[int] = []
    for index in range(len(lines)):
        heading_window = " ".join(lines[index : index + 3])
        if is_customer_receipt_text(heading_window):
            customer_starts.append(index)

    for index in customer_starts:
        section = lines[index : index + 60]
        for offset, row_text in enumerate(section):
            # A new Chinese-numbered subsection such as （四） ends （三）.
            # Do not stop on Arabic-numbered explanatory bullets like (1).
            if (
                offset > 3
                and re.match(r"^[（(][一二三四五六七八九十]+[）)]", row_text)
                and not is_customer_receipt_text(
                    " ".join(section[offset : offset + 3])
                )
            ):
                break

            liq = liquidity(row_text)
            if liq not in {"current", "noncurrent"}:
                continue

            # Keep classification tied to the label line, but allow the number
            # to land one or two lines later after PDF table extraction.
            amount_block = " ".join(section[offset : offset + 3])
            raw = first_money_after_label(
                amount_block, 0, window=len(amount_block)
            )
            if raw is None:
                continue
            key = (
                "customerReceiptsNoncurrent"
                if liq == "noncurrent"
                else "customerReceiptsCurrent"
            )
            merge_value(out, key, raw * multiplier)

        if (
            out["customerReceiptsCurrent"] is None
            and out["customerReceiptsNoncurrent"] is None
        ):
            # Some issuers disclose only a total immediately after the heading.
            block = " ".join(section[:8])
            raw = first_money_after_label(block, 0, window=len(block))
            if raw is not None:
                merge_value(out, "customerReceiptsTotal", raw * multiplier)

    if (
        out["contractTotal"] is None
        and out["contractCurrent"] is not None
        and out["contractNoncurrent"] is not None
    ):
        out["contractTotal"] = out["contractCurrent"] + out["contractNoncurrent"]
    elif (
        out["contractTotal"] is None
        and out["contractCurrent"] is not None
        and out["contractNoncurrent"] is None
    ):
        if any(
            is_contract_text(line) and liquidity(line) == "current"
            for line in lines
        ):
            out["contractTotal"] = out["contractCurrent"]

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


def parse_pdf_report(content: bytes, period: str) -> dict[str, int | None]:
    if not content.startswith(b"%PDF"):
        raise ValueError("官方電子書下載內容不是 PDF")

    document = pymupdf.open(stream=content, filetype="pdf")
    unit_pages: list[str] = []
    note_pages: list[str] = []
    for page in document:
        try:
            value = page.get_text("text") or ""
        except Exception:  # noqa: BLE001
            value = ""
        if not value:
            continue
        if (
            len(unit_pages) < 3
            and ("仟元" in value or "千元" in value or "百萬元" in value)
        ):
            unit_pages.append(value)
        if is_contract_text(value) or is_customer_receipt_text(value):
            note_pages.append(value)

        # Most disclosures put contract balances and customer receipts on the
        # same note page. Once both labels are found and unit evidence exists,
        # no reason remains to scan the rest of a 100+ page report.
        combined_notes = "\n".join(note_pages)
        if (
            unit_pages
            and is_contract_text(combined_notes)
            and is_customer_receipt_text(combined_notes)
        ):
            break

    document.close()
    if not note_pages:
        raise ValueError("財報 PDF 文字層找不到合約負債或客戶暫收／預收附註")

    return parse_pdf_note_text(
        "\n".join(unit_pages + note_pages),
        period,
    )


def select_quarter_pdf_filename(html: str, code: str, period: str) -> str | None:
    year, quarter = split_period_for_pdf(period)
    candidates: list[tuple[int, str]] = []
    rank = {"AI1": 0, "AIA": 1, "AE1": 2}
    for match in _DOC_FILENAME_RE.finditer(html):
        if (
            match.group("year") != str(year)
            or int(match.group("quarter")) != quarter
            or match.group("code") != code
        ):
            continue
        typecode = match.group("type").upper()
        candidates.append((rank.get(typecode, 99), match.group("filename")))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


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

    def financial_report_pdf(self, code: str, period: str) -> tuple[bytes, str]:
        """Download the official quarterly PDF through doc.twse.com.tw."""
        year, _quarter = split_period_for_pdf(period)
        listing_params = {
            "step": "1",
            "colorchg": "1",
            "co_id": code,
            "year": str(year - 1911),
            "mtype": "A",
        }

        last_error: Exception | None = None
        listing_html = ""
        listing_url = DOC_DOWNLOAD
        for attempt in range(3):
            if attempt:
                time.sleep(1.5 ** attempt)
            self.wait()
            try:
                response = self.session.get(
                    DOC_DOWNLOAD,
                    params=listing_params,
                    timeout=60,
                    headers={
                        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                        "Referer": "https://doc.twse.com.tw/",
                    },
                )
                response.raise_for_status()
                listing_url = response.url
                listing_html = response.content.decode("big5", errors="replace")
                filename = select_quarter_pdf_filename(listing_html, code, period)
                if filename:
                    break
                last_error = ValueError(
                    f"{code} {period} 官方文件索引找不到季度財報"
                )
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
        else:
            raise RuntimeError(
                f"{code} {period} 財報索引失敗：{last_error}"
            )

        filename = select_quarter_pdf_filename(listing_html, code, period)
        if not filename:
            raise ValueError(f"{code} {period} 找不到 AI1/AIA/AE1 財報 PDF")

        # Official endpoint returns a short HTML launcher first. The actual
        # session-bound PDF lives at the /pdf/ URL inside that response.
        form = {
            "step": "9",
            "kind": "A",
            "co_id": code,
            "filename": filename,
            "colorchg": "1",
            "DEBUG": "",
            "SKEY1": "",
            "SKEY2": "",
            "YEAR": "",
            "MDATE": "",
            "TYPE": "",
        }
        self.wait()
        launch = self.session.post(
            DOC_DOWNLOAD,
            data=form,
            timeout=60,
            headers={
                "Accept": "text/html,*/*;q=0.8",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://doc.twse.com.tw",
                "Referer": listing_url,
            },
        )
        launch.raise_for_status()
        launch_html = launch.content.decode("big5", errors="replace")
        href = _PDF_HREF_RE.search(launch_html)
        if not href:
            raise ValueError(
                f"{code} {period} step=9 沒有回傳暫時 PDF 連結"
            )

        pdf_url = urljoin("https://doc.twse.com.tw", href.group(1))
        self.wait()
        pdf = self.session.get(
            pdf_url,
            timeout=120,
            allow_redirects=True,
            headers={
                "Accept": "application/pdf,*/*;q=0.8",
                "Referer": listing_url,
            },
        )
        pdf.raise_for_status()
        if not pdf.content.startswith(b"%PDF"):
            raise ValueError(f"{code} {period} 官方下載結果不是 PDF")
        return pdf.content, filename


    def download(self, code: str, period: str) -> tuple[bytes, str]:
        """Fetch the complete official inline-XBRL filing, consolidated first."""
        year, quarter_text = period.split("Q")
        quarter = int(quarter_text)
        last_error: Exception | None = None

        for report_id in ("C", "A"):
            params = {
                "step": "1",
                "CO_ID": code,
                "SYEAR": year,
                "SSEASON": str(quarter),
                "REPORT_ID": report_id,
            }
            for attempt in range(3):
                if attempt:
                    time.sleep(1.5 * attempt)
                self.wait()
                try:
                    response = self.session.get(
                        IXBRL_URL,
                        params=params,
                        timeout=60,
                        allow_redirects=True,
                        headers={
                            "Referer": f"{MOPSOV}/mops/web/t203sb01",
                            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                        },
                    )
                    response.raise_for_status()
                    content = response.content
                    decoded = decode_ixbrl_bytes(content)
                    if "檔案不存在" in decoded:
                        break
                    if re.search(r"<ix:nonfraction\b", decoded, re.I):
                        return content, report_id
                    last_error = RuntimeError(
                        "官方 t164sb01 回傳內容不是完整 iXBRL"
                    )
                except requests.RequestException as exc:
                    last_error = exc

        # Old download contract is kept only as a compatibility fallback.
        for report_id in ("C", "A"):
            url = DOWNLOAD_URL.format(
                code=code,
                year=year,
                quarter=quarter,
                report_id=report_id,
            )
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
                decoded = decode_ixbrl_bytes(content)
                if content[:2] == b"PK" or re.search(
                    r"<ix:nonfraction\b", decoded, re.I
                ):
                    return content, report_id
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

        if (
            merged.get("contractCurrent") is None
            or merged.get("customerReceiptsTotal") is None
        ):
            visible_text = BeautifulSoup(doc, "html.parser").get_text("\n")
            if is_contract_text(visible_text) or is_customer_receipt_text(visible_text):
                try:
                    visible_values = parse_pdf_note_text(visible_text, period)
                except ValueError:
                    visible_values = empty_note_values()
                for key, value in visible_values.items():
                    if merged.get(key) is None and value is not None:
                        merged[key] = value
    return merged


def apply_disclosures(
    row: dict[str, Any],
    parsed: dict[str, int | None],
    report_id: str,
    source: str = "mops_ixbrl",
    *,
    complete: bool = True,
) -> None:
    """Merge note values while distinguishing 'not disclosed' from 'not scanned yet'."""
    status = row.setdefault("status", {})

    for key in ("contractCurrent", "contractNoncurrent", "contractTotal"):
        note_value = parsed.get(key)
        row[f"{key}Note"] = note_value

        if row.get(key) is not None:
            row.setdefault(f"{key}Source", "balance_sheet")
        elif note_value is not None:
            row[key] = note_value
            row[f"{key}Source"] = (
                "pdf_notes" if source == "mops_pdf_notes" else "ixbrl_notes"
            )
            status[key] = "reported_in_notes"

    for key in CUSTOMER_RECEIPT_FIELDS:
        value = parsed.get(key)
        if value is not None:
            row[key] = value
            status[key] = "reported_in_notes"
        elif complete:
            row[key] = None
            status[key] = "not_disclosed"
        else:
            # Do not turn a bounded PDF queue into a false "does not exist".
            row.setdefault(key, None)
            status[key] = "pending_pdf"

    row["notesCheckedAt"] = now_taipei().isoformat(timespec="seconds")
    row["notesReportType"] = "consolidated" if report_id == "C" else "standalone"
    row["notesSource"] = source
    row["notesChecked"] = bool(complete)
    if complete:
        row.pop("notesStatus", None)
    else:
        row["notesStatus"] = "pdf_pending"

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
        "--max-pdf",
        type=int,
        default=12,
        help="本次最多下載幾份大型 PDF 附註；0 表示不限",
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
            (
                docs.get(item[0], {})
                .get("periods", {})
                .get(item[1], {})
                .get("contractCurrent")
                is not None
            ),
            -(meta.get(item[0], {}).get("cap") or 0),
            item[0],
            item[1],
        )
    )

    if args.max_requests > 0:
        jobs = jobs[: args.max_requests]

    log(f"財報附註：本次 {len(jobs)} 份（期間 {periods[0]}～{periods[-1]}）")

    processed = 0
    pdf_attempts = 0
    for code, period in jobs:
        row = docs[code].setdefault("periods", {}).setdefault(period, {})
        try:
            content, report_id = client.download(code, period)
            parsed = parse_report(content, period)
            source = "mops_ixbrl"

            needs_pdf = (
                parsed.get("contractCurrent") is None
                or parsed.get("customerReceiptsTotal") is None
            )
            complete = not needs_pdf

            if needs_pdf and (args.max_pdf <= 0 or pdf_attempts < args.max_pdf):
                pdf_attempts += 1
                try:
                    pdf_content, pdf_filename = client.financial_report_pdf(
                        code, period
                    )
                    pdf_values = parse_pdf_report(pdf_content, period)
                    for key, value in pdf_values.items():
                        if parsed.get(key) is None and value is not None:
                            parsed[key] = value
                    source = (
                        "mops_pdf_notes"
                        if note_values_present(pdf_values)
                        else "mops_ixbrl"
                    )
                    row["notesPdfFilename"] = pdf_filename
                    row.pop("notesPdfError", None)
                    complete = True
                except Exception as pdf_exc:  # noqa: BLE001
                    row["notesPdfError"] = str(pdf_exc)[:240]
                    row["notesStatus"] = "pdf_retry"
                    complete = False

            elif needs_pdf:
                # This filing stays in the queue for the next scheduled run.
                row["notesStatus"] = "pdf_pending"
                complete = False

            apply_disclosures(
                row,
                parsed,
                report_id,
                source,
                complete=complete,
            )
            processed += 1
            if code == "2330":
                log(
                    f"2330 {period}: 合約負債="
                    f"{parsed.get('contractCurrent') or parsed.get('contractTotal')} "
                    f"暫收客戶款={parsed.get('customerReceiptsTotal')} "
                    f"source={source} pdf={row.get('notesPdfFilename')} "
                    f"pdfError={row.get('notesPdfError')}"
                )
        except Exception as exc:  # noqa: BLE001
            # Network / upstream failures must be retried later, not frozen as
            # a permanent 'unavailable' disclosure.
            row["notesChecked"] = False
            row["notesCheckedAt"] = now_taipei().isoformat(timespec="seconds")
            row["notesStatus"] = "retry"
            row["notesError"] = str(exc)[:240]
            log(f"[附註待重試] {code} {period}: {exc}")

    log(
        f"附註批次：iXBRL {processed}/{len(jobs)}，"
        f"PDF {pdf_attempts}/{args.max_pdf if args.max_pdf > 0 else '不限'}"
    )

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

    log(f"財報附註完成：{processed}/{len(jobs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
