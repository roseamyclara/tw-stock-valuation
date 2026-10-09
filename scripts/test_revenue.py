import csv
import io
import unittest
import tempfile
from pathlib import Path
import json
import build_snapshot
from datetime import date
from unittest.mock import patch

import markets
import revenue
from util import FetchError, roc_ym

TODAY = date(2026, 10, 9)


def raw(code='8102', ym='115/9', amount='41991', published='115/10/09'):
    return {'公司代號': code, '資料年月': ym, '出表日期': published,
            '營業收入-當月營收': amount, '營業收入-上月營收': '35243',
            '營業收入-去年當月營收': '31146',
            '營業收入-上月比較增減(%)': '19.14706466532361',
            '營業收入-去年同月增減(%)': '34.81988056251204',
            '累計營業收入-當月累計營收': '346091',
            '累計營業收入-去年累計營收': '327006',
            '累計營業收入-前期比較增減(%)': '5.836284349522638'}


class RevenueTests(unittest.TestCase):
    def test_period_formats_and_invalid_months(self):
        for value in ('11509', '115/9', '115/09', '2026-09', '202609'):
            self.assertEqual(roc_ym(value), (2026, 9))
        for value in ('11500', '11513', '115/99', '', None, 'bad'):
            self.assertIsNone(roc_ym(value))

    def test_official_8102_values(self):
        rec = markets.norm_revenue([raw()])['8102']
        self.assertEqual(rec['ym'], '11509')
        self.assertEqual(rec['month'], 41991)
        self.assertEqual(round(rec['yoy'], 2), 34.82)
        self.assertEqual(round(rec['mom'], 2), 19.15)
        self.assertEqual(rec['publishedAt'], '2026-10-09')

    def test_latest_row_not_last_row_and_same_month_correction(self):
        rows = [raw(), raw(ym='11508', amount='35243'), raw(amount='42000', published='115/10/10')]
        for order in (rows, list(reversed(rows))):
            self.assertEqual(markets.norm_revenue(order)['8102']['month'], 42000)

    def test_partial_month_preserves_other_companies_and_does_not_regress(self):
        old = markets.norm_revenue([raw('1111', '11508'), raw('2222', '11509')])
        new = markets.norm_revenue([raw('1111'), raw('2222', '11508'), raw('3333', amount='0')])
        merged = revenue.merge_latest(old, new, today=TODAY)
        self.assertEqual(merged['1111']['ym'], '11509')
        self.assertEqual(merged['2222']['ym'], '11509')
        self.assertEqual(merged['3333']['month'], 0)
        self.assertEqual(revenue.merge_latest(new, old, today=TODAY), merged)

    def test_newer_publication_and_same_date_correction(self):
        old = markets.norm_revenue([raw(amount='42000', published='115/10/10')])
        stale = markets.norm_revenue([raw()])
        fixed = markets.norm_revenue([raw(amount='42100', published='115/10/10')])
        self.assertEqual(revenue.merge_latest(old, stale, today=TODAY)['8102']['month'], 42000)
        self.assertEqual(revenue.merge_latest(old, fixed, today=TODAY)['8102']['month'], 42100)

    def test_future_and_missing_amount_rejected(self):
        rows = markets.norm_revenue([raw('1111', '11510'), raw('2222', amount='--'), raw('3333', amount='-1')])
        self.assertEqual(set(revenue.merge_latest(rows, today=TODAY)), {'3333'})

    def test_csv_bom_schema_wrong_month_and_html(self):
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(raw()))
        writer.writeheader(); writer.writerow(raw())
        content = stream.getvalue().encode('utf-8-sig')
        self.assertEqual(revenue.parse_csv(content, (2026, 9))[0]['公司代號'], '8102')
        for body, period in [(content, (2026, 8)), (b'<html>denied</html>', (2026, 9)), (b'', (2026, 9))]:
            with self.assertRaises(FetchError):
                revenue.parse_csv(body, period)

    def test_all_markets_merge_partial_csv_with_api(self):
        for market, path in revenue.MARKET_PATH.items():
            with self.subTest(market=market), patch('revenue.S.fetch', return_value=[raw('1111', '11508'), raw('2222', '11508')]), patch('revenue.fetch_month', side_effect=[[raw('1111', '11508')], [raw('2222')]]) as fetch:
                result, status = revenue.fetch_revenue(market, {}, today=TODAY)
                self.assertEqual(result['1111']['ym'], '11508')
                self.assertEqual(result['2222']['ym'], '11509')
                self.assertEqual(status['currentMonthCount'], 1)
                self.assertEqual(status['olderMonthCount'], 1)
                self.assertIn(f'/t21/{path}/', result['2222']['source'])
                self.assertEqual(fetch.call_args_list[-1].args, (market, 2026, 9))

    def test_source_failure_preserves_last_success(self):
        previous = markets.norm_revenue([raw()])
        with patch('revenue.S.fetch', return_value=[]), patch('revenue.fetch_month', side_effect=FetchError('offline')):
            result, status = revenue.fetch_revenue('otc', previous, today=TODAY)
        self.assertEqual(result, previous)
        self.assertTrue(all(s['status'] == 'unavailable' for s in status['sources']))

    def test_persist_and_finalise_revenue_and_ps(self):
        records = markets.norm_revenue([raw()])
        stocks = {"8102": {"c": "8102", "m": "otc", "cap": 1413180175, "_rev": records["8102"]}}
        with tempfile.TemporaryDirectory() as tmp, patch("build_snapshot.DATA_DIR", Path(tmp)):
            build_snapshot.update_fundamentals(stocks)
            saved = json.loads((Path(tmp) / "fundamentals.json").read_text())
            self.assertEqual(saved["8102"]["revenue"]["month"], 41991)
            self.assertEqual(saved["8102"]["rev_cum"]["2026-09"], 346091)
            result = build_snapshot.finalise(stocks)[0]
            self.assertEqual(result["rev"]["ym"], "2026-09")
            self.assertEqual(result["rev"]["yoy"], 34.82)
            self.assertEqual(result["rev"]["mom"], 19.15)
            self.assertEqual(result["ps"], 3.11)

    def test_january_fetches_previous_year(self):
        with patch('revenue.S.fetch', return_value=[]), patch('revenue.fetch_month', return_value=[]) as fetch:
            revenue.fetch_revenue('listed', {}, today=date(2027, 1, 3))
        self.assertEqual([c.args for c in fetch.call_args_list], [('listed', 2026, 11), ('listed', 2026, 12)])


if __name__ == '__main__':
    unittest.main()
