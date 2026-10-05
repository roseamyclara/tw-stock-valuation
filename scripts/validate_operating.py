"""Publication gate shared by main collection and daily note backfill."""
from build_operating_leads import load_docs, validate_4563


def validate_tsmc(doc):
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


def validate(docs):
    validate_tsmc(docs.get("2330", {}))
    validate_4563(docs, require_benchmark=True)
    row = docs.get("4563", {}).get("periods", {}).get("2026Q2", {})
    if row.get("data_source") != "balance_sheet":
        raise ValueError("4563 2026Q2 必須保留主表來源 balance_sheet")


if __name__ == "__main__":
    validate(load_docs(["2330", "4563"]))
    print("2330 附註與 4563 主表驗證通過")
