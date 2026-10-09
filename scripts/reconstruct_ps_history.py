"""以官方歷史股數、未還原股價及完整 12 月營收重建 P/S。

2013 起合併月營收 CSV；2012 使用 2013 報表的去年同月比較值。
歷史申報可能事後更正，故為事後重建，不宣稱是當時可得的回測資料。
"""
from __future__ import annotations
import argparse
import calendar
import csv
import hashlib
import io
import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse
import requests
from util import DATA_DIR, ROOT, num, read_json, write_json

DEST = DATA_DIR / 'ps_reconstructed'
CACHE = ROOT / '.ps_backfill_cache'
MARKETS = {'listed': 'sii', 'otc': 'otc', 'esb': 'rotc'}
LOCKS = {h: threading.Lock() for h in ['www.twse.com.tw', 'www.tpex.org.tw', 'mopsov.twse.com.tw']}
LAST = {}


def shift(ym, delta):
    y, m = map(int, ym.split('-')); n = y * 12 + m - 1 + delta
    return f'{n // 12:04d}-{n % 12 + 1:02d}'


def months(start, end):
    while start <= end:
        yield start
        start = shift(start, 1)


def fetch(url):
    path = CACHE / (hashlib.sha256(url.encode()).hexdigest() + '.txt')
    if path.exists():
        return path.read_text()
    host = urlparse(url).hostname
    for attempt in range(3):
        with LOCKS[host]:
            time.sleep(max(0, 1.0 - (time.monotonic() - LAST.get(host, 0))))
            LAST[host] = time.monotonic()
            r = requests.get(url, timeout=35)
        if r.status_code in (403, 404):
            raise ValueError(f'HTTP {r.status_code}: {url}')
        if r.status_code == 200:
            try: text = r.content.decode('utf-8-sig')
            except UnicodeDecodeError: text = r.content.decode('cp950')
            if text.lstrip().startswith(('{', '[', 'TITLE,', '出表日期,')):
                CACHE.mkdir(exist_ok=True)
                path.write_text(text)
                return text
        time.sleep(2 ** attempt)
    raise ValueError(f'無有效資料: {url}')


def stock_code(s):
    s = str(s).strip().strip('="')
    return s if len(s) == 4 and s.isdigit() else None


def valid_number(v, positive=False):
    v = num(v)
    return v if v is not None and math.isfinite(v) and (v > 0 if positive else v >= 0) else None


def parse_revenue(text, ym):
    y, m = map(int, ym.split('-'))
    rows = list(csv.DictReader(io.StringIO(text.lstrip('\ufeff'))))
    if not rows or '營業收入-當月營收' not in rows[0]:
        raise ValueError('月營收欄位不符')
    out = {}
    for row in rows:
        if row.get('資料年月') != f'{y-1911}/{m}':
            raise ValueError('月營收日期不符')
        code = stock_code(row.get('公司代號', ''))
        if code:
            out[code] = [valid_number(row.get('營業收入-當月營收')),
                         valid_number(row.get('營業收入-去年當月營收'))]
    return out


def revenue_job(task):
    market, ym = task; y, m = map(int, ym.split('-'))
    url = f'https://mopsov.twse.com.tw/nas/t21/{MARKETS[market]}/t21sc03_{y-1911}_{m}.csv'
    try: return market, ym, parse_revenue(fetch(url), ym), None
    except Exception as e: return market, ym, {}, str(e)


def json_rows(payload, day, required):
    """來源日期必須吻合；拒絕忽略歷史日期而回傳今天資料的端點。"""
    output = {}
    for t in payload.get('tables', [payload]):
        fields = [re.sub(r'\s+', '', f) for f in t.get('fields', [])]
        if not all(f in fields for f in required):
            continue
        d = t.get('date', payload.get('date', ''))
        roc = f'{day.year-1911}/{day.month:02d}/{day.day:02d}'
        if d not in (day.strftime('%Y%m%d'), roc, day.isoformat()):
            raise ValueError(f'行情日期不符：要求 {day}，收到 {d}')
        for row in t.get('data', []):
            code = stock_code(row[fields.index(required[0])])
            if code:
                output[code] = {f: row[fields.index(f)] for f in required[1:]}
    return output


def esb_rows(text, day):
    rows = list(csv.reader(io.StringIO(text)))
    expected = f'日期:{day.year-1911}年{day.month:02d}月{day.day:02d}日'
    if not any(r[:2] == ['DATADATE', expected] for r in rows):
        raise ValueError('興櫃行情日期不符')
    header = next((r[1:] for r in rows if r and r[0] == 'HEADER'), [])
    if not all(f in header for f in ['證券代號', '日均價', '發行股數']):
        raise ValueError('興櫃行情欄位不符')
    result = {}
    for row in rows:
        if not row or row[0] != 'BODY': continue
        r = dict(zip(header, row[1:])); code = stock_code(r['證券代號'])
        p, s = valid_number(r['日均價'], True), valid_number(r['發行股數'], True)
        if code and p and s: result[code] = [p, s, 'esb']
    return result


def valuation_job(ym):
    y, m = map(int, ym.split('-')); end = date(y, m, calendar.monthrange(y, m)[1])
    errors = []; sources = {}; stocks = {}; day = None
    for back in range(15):
        d = end - timedelta(days=back)
        if d.month != m or d.weekday() > 4: continue
        u = f'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={d:%Y%m%d}&type=ALLBUT0999&response=json'
        try:
            p = json_rows(json.loads(fetch(u)), d, ['證券代號', '收盤價'])
        except Exception as e:
            errors.append(str(e)); continue
        if p: day = d; sources['listedPrice'] = u; break
    if day is None: return ym, None, errors + ['找不到交易日']
    u = f'https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?date={day:%Y%m%d}&selectType=ALLBUT0999&response=json'
    try:
        q = json_rows(json.loads(fetch(u)), day, ['證券代號', '發行股數'])
        for code in p.keys() & q.keys():
            price, shares = valid_number(p[code]['收盤價'], True), valid_number(q[code]['發行股數'], True)
            if price and shares: stocks[code] = [price, shares, 'listed']
        sources['listedShares'] = u
    except Exception as e: errors.append(str(e))
    u = f'https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?l=zh-tw&d={day.year-1911:03d}/{day.month:02d}/{day.day:02d}&se=EW'
    try:
        q = json_rows(json.loads(fetch(u)), day, ['代號', '收盤', '發行股數'])
        for code, row in q.items():
            price, shares = valid_number(row['收盤'], True), valid_number(row['發行股數'], True)
            if price and shares: stocks[code] = [price, shares, 'otc']
        sources['otc'] = u
    except Exception as e: errors.append(str(e))
    u = f'https://www.tpex.org.tw/www/zh-tw/emerging/dailyDl?name=EMdes010.{day:%Y%m%d}-C.csv'
    try:
        stocks.update(esb_rows(fetch(u), day)); sources['esb'] = u
    except Exception as e: errors.append(str(e))
    return ym, {'d': day.isoformat(), 'sources': sources, 's': stocks}, errors


def revenue_series(reports):
    """跨轉板合併相同代號；2012 僅用 2013 表內同口徑比較值。"""
    result = {}; conflicts = set()
    for market, ym, rows in reports:
        for code, pair in rows.items():
            for period, amount in [(ym, pair[0])] + ([(shift(ym, -12), pair[1])] if ym.startswith('2013-') else []):
                if amount is None: continue
                key = (code, period)
                if key in conflicts: continue
                if key in result and result[key] != amount:
                    conflicts.add(key); result.pop(key)
                else: result[key] = amount
    return result


def reconstruct(ym, valuation, revenue):
    last = shift(ym, -1); periods = list(months(shift(last, -11), last)); out = {}
    for code, (price, shares, market) in valuation['s'].items():
        vals = [revenue.get((code, p)) for p in periods]
        if any(v is None for v in vals): continue
        ttm = sum(vals) * 1000
        if ttm <= 0: continue
        ratio = price * shares / ttm
        if math.isfinite(ratio) and ratio > 0:
            out[code] = [round(ratio, 4), price, shares, ttm, market]
    return {'d': valuation['d'], 'revenueMonth': last, 'sources': valuation['sources'], 's': out}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--start', default='2013-01'); ap.add_argument('--end', default=shift(min(read_json(DATA_DIR / 'ps_history.json', {}) or {date.today().strftime('%Y-%m'): {}}), -1))
    args = ap.parse_args()
    if args.start < '2013-01' or args.start > args.end: ap.error('支援 2013 年起的相容合併營收')
    # 至少取得 2013 全年比較欄，供 2012 的完整 TTM。
    start_rev = max('2013-01', shift(args.start, -12)); end_rev = max('2013-12', shift(args.end, -1))
    jobs = [(m, ym) for ym in months(start_rev, end_rev) for m in MARKETS]
    reports = []; errors = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, (m, ym, rows, err) in enumerate(pool.map(revenue_job, jobs)):
            reports.append((m, ym, rows))
            if err: errors.append({'market': m, 'month': ym, 'error': err})
            if i % 30 == 0: print(f'營收 {i+1}/{len(jobs)}', flush=True)
    revenue = revenue_series(reports)
    stores = {}; summary = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for ym, valuation, errs in pool.map(valuation_job, months(args.start, args.end)):
            errors.extend({'month': ym, 'error': e} for e in errs)
            if not valuation: continue
            row = reconstruct(ym, valuation, revenue)
            if row['s']:
                y = ym[:4]
                if y not in stores: stores[y] = read_json(DEST / f'{y}.json', {}) or {}
                # Only replace a month if coverage does not regress after source failures.
                old = stores[y].get(ym)
                if old and len(old['s']) > len(row['s']): continue
                stores[y][ym] = row
                write_json(DEST / f'{y}.json', dict(sorted(stores[y].items())))
            counts = {m: sum(v[4] == m for v in row['s'].values()) for m in MARKETS}
            summary.append({'month': ym, **counts}); print(ym, counts, '8102', row['s'].get('8102'), flush=True)
    write_json(DEST / 'coverage.json', {'method': 'historical-shares-unadjusted-price-12-month-revenue', 'revenuePolicy': 'previous-month; complete 12 months; revised filings, not point-in-time', 'months': summary, 'errors': errors}, compact=False)
    if not summary: raise SystemExit('沒有可重建資料')

if __name__ == '__main__': main()
