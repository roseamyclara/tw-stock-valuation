import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import markets
import build_snapshot
from util import read_json


class NegativePeTests(unittest.TestCase):
    def test_source_reason_only_for_explicit_negative(self):
        for value in (None, '', '-', 'N/A', '0', '12.5'):
            self.assertNotIn('peReason', markets.pe_fields(value))
        for normalize, code_key, pe_key in (
            (markets.norm_daily_listed, '證券代號', '本益比'),
            (markets.norm_daily_otc_pe, '股票代號', '本益比'),
            (markets.norm_valuation_otc, 'SecuritiesCompanyCode', 'PriceEarningRatio'),
        ):
            row = normalize([{code_key: '1234', pe_key: '-2.5'}])['1234']
            self.assertIsNone(row['pe'])
            self.assertEqual(row['peReason'], 'negative_eps')

    def test_month_snapshot_preserves_reason_and_legacy_shape(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(build_snapshot, 'DATA_DIR', Path(tmp)):
            build_snapshot.update_month_history([
                {'c': '1234', 'pe': None, 'peReason': 'negative_eps'},
                {'c': '5678', 'pe': 12, 'pb': 1},
                {'c': '9012', 'pe': None, 'pb': 1},
            ], date(2026, 10, 8))
            stocks = read_json(Path(tmp) / 'history/2026.json')['2026-10']['s']
            self.assertEqual(stocks['1234'], [None, None, None, None, 'negative_eps'])
            self.assertEqual(stocks['5678'], [12, 1, None, None])
            self.assertEqual(stocks['9012'], [None, 1, None, None])


if __name__ == '__main__':
    unittest.main()
