"""Publication gate shared by main collection and daily note backfill."""
from build_operating_leads import load_docs, validate_4563, change, read_json, LATEST_OUT


def validate_tsmc(doc, *, require_yoy=False):
    row = doc.get("periods", {}).get("2026Q2", {})
    expected = {
        "contractCurrent": 55_852_048_000,
        "customerReceiptsCurrent": 141_853_142_000,
        "customerReceiptsNoncurrent": 92_372_004_000,
        "customerReceiptsTotal": 234_225_146_000,
    }
    for key, value in expected.items():
        actual = row.get(key)
        if actual is None or abs(actual - value) > 20_000_000:
            raise ValueError(f"2330 2026Q2 {key}: {actual}, expected {value}")
    if row.get("data_source") != "notes" or row.get("contractCurrentSource") != "notes":
        raise ValueError("2330 2026Q2 合約負債必須來自 notes")
    if not row.get("notesChecked") or row.get("notesParserVersion") != 2:
        raise ValueError("2330 2026Q2 必須完成新版附註解析")

    if require_yoy:
        prior = doc.get("periods", {}).get("2025Q2", {})
        amount = prior.get("contractCurrent")
        if amount is None or abs(amount - 56_799_375_000) > 20_000_000:
            raise ValueError(f"2330 2025Q2 合約負債缺漏或錯誤：{amount}")
        if prior.get("contractCurrentSource") != "notes":
            raise ValueError("2330 2025Q2 必須有附註來源")
        result = change(doc["periods"], "2026Q2", "contractCurrent")
        if result is None or result["yoy"] is None or abs(result["yoy"] + 1.67) > 0.01:
            raise ValueError(f"2330 2026Q2 YoY 錯誤：{result}")


def validate(docs):
    validate_tsmc(docs.get("2330", {}), require_yoy=True)
    validate_4563(docs, require_benchmark=True)
    row = docs.get("4563", {}).get("periods", {}).get("2026Q2", {})
    if row.get("data_source") != "balance_sheet":
        raise ValueError("4563 2026Q2 必須保留主表來源 balance_sheet")


if __name__ == "__main__":
    validate(load_docs(["2330", "4563"]))
    summary = read_json(LATEST_OUT, {}).get("stocks", {}).get("2330", {})
    docs = load_docs(["2330"])
    period = summary.get("contractCurrentPeriod")
    expected = change(docs["2330"]["periods"], period, "contractCurrent")
    if period is None or expected is None or summary.get("contractCurrentChange") != expected:
        raise ValueError("首頁摘要與台積電歷史資料不一致")
    if period == "2026Q2" and expected.get("yoy") != -1.67:
        raise ValueError("首頁摘要缺少台積電 2026Q2 YoY")
    print("2330 去年同期、YoY、首頁摘要與 4563 主表驗證通過")
