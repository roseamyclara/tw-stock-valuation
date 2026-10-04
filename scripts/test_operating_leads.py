from __future__ import annotations

import unittest

from build_operating_leads import (
    parse_balance_sheet,
    parse_revenue_payload,
)


class OperatingLeadParserTests(unittest.TestCase):
    def test_balance_sheet_maps_company_columns_and_calculates_total(self):
        html = """<!doctype html><html><body>
        <input name="yearseason" value="20262">
        <span>金額單位：新台幣仟元</span>
        <table>
          <thead>
            <tr><th rowspan="2">會計項目</th><th colspan="2">2026Q2</th></tr>
            <tr><th>4563 百德</th><th>2330 台積電</th></tr>
          </thead>
          <tbody>
            <tr><td>合約負債－流動</td><td>145,000</td><td>2,000</td></tr>
            <tr><td>合約負債－非流動</td><td>10,000</td><td>—</td></tr>
            <tr><td>存貨</td><td>1,382,000</td><td>300,000</td></tr>
          </tbody>
        </table></body></html>"""
        result = parse_balance_sheet(html, "2026Q2", {"4563", "2330"})
        self.assertEqual(result["4563"]["contractCurrent"], 145_000_000)
        self.assertEqual(result["4563"]["contractNoncurrent"], 10_000_000)
        self.assertEqual(result["4563"]["contractTotal"], 155_000_000)
        self.assertEqual(result["4563"]["inventory"], 1_382_000_000)
        self.assertIsNone(result["2330"]["contractNoncurrent"])
        self.assertIsNone(result["2330"]["contractTotal"])

    def test_balance_sheet_rejects_silent_period_fallback(self):
        html = """<html><body>
        <input name="yearseason" value="20261">
        <span>金額單位：新台幣仟元</span>
        <table><tr><th>會計項目</th><th>4563 百德</th></tr></table>
        </body></html>"""
        with self.assertRaisesRegex(ValueError, "期別不符"):
            parse_balance_sheet(html, "2026Q2", {"4563"})

    def test_missing_is_not_zero(self):
        html = """<html><body>
        <input name="yearseason" value="20262">
        <span>金額單位：新台幣仟元</span>
        <table>
          <tr><th>會計項目</th><th>4563 百德</th></tr>
          <tr><td>合約負債－流動</td><td>—</td></tr>
          <tr><td>存貨</td><td>-</td></tr>
        </table></body></html>"""
        result = parse_balance_sheet(html, "2026Q2", {"4563"})
        self.assertIsNone(result["4563"]["contractCurrent"])
        self.assertIsNone(result["4563"]["inventory"])

    def test_revenue_series_identity_mapping(self):
        payload = {
            "ylabel": "新台幣仟元",
            "xaxisList": ["2025Q4", "2026Q1", "2026Q2"],
            "checkedNameList": ["4563 百德", "2330 台積電"],
            "showNameList": ["Quaser", "TSMC"],
            "displayCompanyId": ["4563 百德", "2330 台積電"],
            "graphData": [
                {"label": "TSMC", "data": [[0, 100], [1, 110], [2, 120]]},
                {"label": "Quaser", "data": [[0, 781000], [1, 551000], [2, 740000]]},
            ],
        }
        result = parse_revenue_payload(payload, ["4563", "2330"])
        self.assertEqual(result["4563"]["2026Q2"], 740_000_000)
        self.assertEqual(result["2330"]["2026Q2"], 120_000)


if __name__ == "__main__":
    unittest.main()
