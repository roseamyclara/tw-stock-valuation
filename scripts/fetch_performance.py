"""使用證交所與櫃買的整批每日行情回補，不逐檔請求；可中斷續傳。"""
import argparse
from datetime import date, timedelta
from util import DATA_DIR, get_json, read_json, write_json, num, FetchError, log
from fetch_prices import _payload_rows, TPEX_OTC
from build_performance import targets

TWSE = 'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={day}&type=ALLBUT0999&response=json'


def parse(payload, market):
    result = {}
    if market == 'listed':
        tables = [t for t in payload.get('tables', []) if '收盤價' in t.get('fields', [])]
        if not tables: return result
        table = tables[-1]; fields = table['fields']
        indexes = [fields.index(f) for f in ['證券代號', '收盤價', '最高價', '最低價']]
        rows = table.get('data', [])
    else:
        rows = _payload_rows(payload); indexes = [0, 2, 5, 6]
    for row in rows:
        if len(row) <= max(indexes): continue
        code = str(row[indexes[0]]).strip()
        if len(code) != 4 or not code.isdigit(): continue
        values = [num(row[i]) for i in indexes[1:]]
        if all(v is not None and v > 0 for v in values) and values[2] <= values[0] <= values[1]:
            result[code] = values
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backfill', action='store_true')
    parser.add_argument('--max-requests', type=int, default=80)
    args = parser.parse_args()
    prices = read_json(DATA_DIR / 'prices.json', {})
    if not prices.get('dates'): return 0
    asof = date.fromisoformat(prices['dates'][-1])
    path = DATA_DIR / 'performance_history.json'
    cache = read_json(path, {})
    wanted = {asof - timedelta(days=i) for i in range(370 if args.backfill else 7)}
    for target in targets(asof).values():
        wanted.update(target - timedelta(days=i) for i in range(15))
    requests = 0
    # Cache even non-trading dates; never cache HTTP/network errors as empty data.
    try:
        for day in sorted(wanted, reverse=True):
            if day.weekday() >= 5: continue
            key = day.isoformat()
            for market in ['listed', 'otc']:
                if market in cache.get(key, {}): continue
                if requests >= args.max_requests: return 0
                url = TWSE.format(day=day.strftime('%Y%m%d')) if market == 'listed' else TPEX_OTC.format(
                    roc=f'{day.year-1911}/{day.month:02}/{day.day:02}')
                requests += 1
                payload = get_json(url, tries=1)
                cache.setdefault(key, {})[market] = parse(payload, market)
                write_json(path, cache)
                log(f'{key} {market}: {len(cache[key][market])}')
    except FetchError:
        log('行情來源暫時無法使用，停止請求；下次由快取接續。')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
