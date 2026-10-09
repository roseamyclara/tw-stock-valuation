import unittest
from ps_history import record_snapshot, stock_series


def row(code='8102', ps=3.11, basis='估算'):
    return {'c': code, 'ps': ps, 'ps_basis': basis, 'rev': {'ym': '2026-09'}}


class PsHistoryTests(unittest.TestCase):
    def test_month_end_and_same_day_latest_snapshot(self):
        store = {}
        record_snapshot(store, [row(ps=3.43)], '2026-08-31', '2026-08-31T23:00:00')
        record_snapshot(store, [row(ps=99)], '2026-08-28', '2026-08-29T23:00:00')
        self.assertEqual(store['2026-08']['stocks']['8102']['v'], 3.43)
        record_snapshot(store, [row(ps=3.2)], '2026-08-31', '2026-09-01T01:00:00')
        self.assertEqual(store['2026-08']['stocks']['8102']['v'], 3.2)
        self.assertEqual(len(store), 1)

    def test_separate_months_and_all_markets_without_pe(self):
        store = {}
        for code, market in [('1111', 'listed'), ('2222', 'otc'), ('3333', 'esb')]:
            r = row(code); r['m'] = market
            record_snapshot(store, [r], '2026-08-31', '')
            self.assertIsNotNone(store['2026-08']['stocks'][code]['v'])
        record_snapshot(store, [row()], '2026-10-08', '')
        self.assertEqual(set(store), {'2026-08', '2026-10'})

    def test_missing_values_are_gaps_and_metadata_survives(self):
        store = {}
        record_snapshot(store, [row(), row('1111', ps=4, basis='實際')], '2026-08-31', '')
        record_snapshot(store, [row(ps=None), row('1111', ps=5)], '2026-09-30', '')
        series = stock_series(store, '8102')
        self.assertEqual([r['v'] for r in series], [3.11, None])
        self.assertEqual(series[0]['basis'], '估算')
        self.assertEqual(series[0]['revenueMonth'], '2026-09')
        self.assertEqual(stock_series(store, '9999')[0]['v'], None)
        self.assertEqual(stock_series(store, '1111')[0]['basis'], '實際')

    def test_invalid_date_and_nonfinite_or_nonpositive_values(self):
        for date in [None, '', '2026-13-01', 'not-a-date']:
            self.assertFalse(record_snapshot({}, [row()], date, ''))
        for value in [None, 0, -1, float('nan'), float('inf'), '3.2']:
            self.assertFalse(record_snapshot({}, [row(ps=value)], '2026-10-08', ''))

    def test_completely_failed_snapshot_preserves_prior_month_value(self):
        store = {}
        record_snapshot(store, [row()], '2026-10-08', '2026-10-09T09:00:00')
        self.assertFalse(record_snapshot(store, [row(ps=None)], '2026-10-08', '2026-10-09T10:00:00'))
        self.assertEqual(store['2026-10']['stocks']['8102']['v'], 3.11)


if __name__ == '__main__':
    unittest.main()
