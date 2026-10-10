"""Apply explicitly reviewed, dated negative-earnings evidence to historical display rows."""
from datetime import date
from decimal import Decimal
import re


def confirmed_negative(record, snapshot_date):
    """Fail closed: dates, consecutive quarters, sources and both negative sums required."""
    try:
        snapshot = date.fromisoformat(snapshot_date)
        if snapshot_date not in record['snapshotDates']:
            return False
        boundary = record['nextAnnouncement']
        if not boundary['source'].startswith('https://') or snapshot >= date.fromisoformat(boundary['date']):
            return False
        quarters = record['quarters']
        if len(quarters) != 4:
            return False
        indexes, eps, earnings = [], Decimal(0), Decimal(0)
        for row in quarters:
            match = re.fullmatch(r'(\d{4})Q([1-4])', row['period'])
            if not match or not row['source'].startswith('https://'):
                return False
            if date.fromisoformat(row['announcedOn']) >= snapshot:
                return False  # 同日沒有公告時間，不猜測盤前或盤後。
            indexes.append(int(match[1]) * 4 + int(match[2]) - 1)
            eps += Decimal(str(row['eps']))
            earnings += Decimal(str(row['netIncomeBillionTwd']))
        # 公告數字有四捨五入：四季每項各保留兩位小數，誤差上限 0.02。
        return (indexes == list(range(indexes[0], indexes[0] + 4))
                and eps.is_finite() and earnings.is_finite()
                and eps < Decimal('-0.02') and earnings < Decimal('-0.02'))
    except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError):
        return False


def with_pe_evidence(values, code, snapshot_date, evidence):
    """Keep source values untouched; only append a display reason for reviewed snapshots."""
    result = list(values)
    if len(result) != 4 or result[0] is not None:
        return result
    # 沒有任何其他估值欄位的整筆缺漏，不能僅憑財報補成有效歷史點。
    if all(value is None for value in result[1:]):
        return result
    for record in evidence.get(code, []):
        if confirmed_negative(record, snapshot_date):
            return result + ['negative_eps']
    return result
