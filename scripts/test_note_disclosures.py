from __future__ import annotations

import unittest

from build_note_disclosures import parse_ixbrl_html, parse_pdf_note_text


class NoteDisclosureParserTests(unittest.TestCase):
    def test_tsmc_style_contract_and_customer_receipts(self):
        html = """<!doctype html>
        <html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"
              xmlns:xbrli="http://www.xbrl.org/2003/instance">
        <body>
          <xbrli:context id="I_2026Q2">
            <xbrli:entity><xbrli:identifier scheme="x">2330</xbrli:identifier></xbrli:entity>
            <xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period>
          </xbrli:context>
          <xbrli:context id="I_2025FY">
            <xbrli:entity><xbrli:identifier scheme="x">2330</xbrli:identifier></xbrli:entity>
            <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
          </xbrli:context>

          <p>（二）合約餘額</p>
          <table>
            <tr><th></th><th>115年6月30日</th><th>114年12月31日</th></tr>
            <tr>
              <td>合約負債（帳列應付費用及其他流動負債）</td>
              <td><ix:nonFraction name="tsmc:ContractLiabilities" contextRef="I_2026Q2" scale="3">55,852,048</ix:nonFraction></td>
              <td><ix:nonFraction name="tsmc:ContractLiabilities" contextRef="I_2025FY" scale="3">49,954,384</ix:nonFraction></td>
            </tr>
          </table>

          <p>（三）暫收客戶款</p>
          <table>
            <tr><th></th><th>115年6月30日</th><th>114年12月31日</th></tr>
            <tr>
              <td>流動（帳列應付費用及其他流動負債）</td>
              <td><ix:nonFraction name="tsmc:TemporaryReceiptsCurrent" contextRef="I_2026Q2" scale="3">141,853,142</ix:nonFraction></td>
              <td><ix:nonFraction name="tsmc:TemporaryReceiptsCurrent" contextRef="I_2025FY" scale="3">146,559,275</ix:nonFraction></td>
            </tr>
            <tr>
              <td>非流動（帳列其他非流動負債）</td>
              <td><ix:nonFraction name="tsmc:TemporaryReceiptsNoncurrent" contextRef="I_2026Q2" scale="3">92,372,004</ix:nonFraction></td>
              <td><ix:nonFraction name="tsmc:TemporaryReceiptsNoncurrent" contextRef="I_2025FY" scale="3">43,298,936</ix:nonFraction></td>
            </tr>
            <tr>
              <td>合計</td>
              <td><ix:nonFraction name="tsmc:TemporaryReceiptsTotal" contextRef="I_2026Q2" scale="3">234,225,146</ix:nonFraction></td>
              <td><ix:nonFraction name="tsmc:TemporaryReceiptsTotal" contextRef="I_2025FY" scale="3">189,858,211</ix:nonFraction></td>
            </tr>
          </table>
        </body></html>
        """
        result = parse_ixbrl_html(html, "2026Q2")
        self.assertEqual(result["contractCurrent"], 55_852_048_000)
        self.assertEqual(result["customerReceiptsCurrent"], 141_853_142_000)
        self.assertEqual(result["customerReceiptsNoncurrent"], 92_372_004_000)
        self.assertEqual(result["customerReceiptsTotal"], 234_225_146_000)


    def test_regex_fact_extraction_without_html_table_dependency(self):
        # Real MOPS inline-XBRL can be malformed as HTML. Facts must still be
        # extracted directly from ix:nonFraction + xbrli:context.
        html = """<html><body>
        <xbrli:context id="AsOf20260630">
          <xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period>
        </xbrli:context>
        <div>合約負債（帳列應付費用及其他流動負債）
          <ix:nonFraction name="tifrs-notes:ContractLiabilities"
            contextRef="AsOf20260630" scale="3">55,852,048</ix:nonFraction>
        </div>
        <ix:nonFraction name="tifrs-notes:TemporaryReceiptsFromCustomersCurrent"
          contextRef="AsOf20260630" scale="3">141,853,142</ix:nonFraction>
        <ix:nonFraction name="tifrs-notes:TemporaryReceiptsFromCustomersNoncurrent"
          contextRef="AsOf20260630" scale="3">92,372,004</ix:nonFraction>
        <ix:nonFraction name="tifrs-notes:TemporaryReceiptsFromCustomers"
          contextRef="AsOf20260630" scale="3">234,225,146</ix:nonFraction>
        </body></html>"""
        result = parse_ixbrl_html(html, "2026Q2")
        self.assertEqual(result["contractCurrent"], 55_852_048_000)
        self.assertEqual(result["customerReceiptsCurrent"], 141_853_142_000)
        self.assertEqual(result["customerReceiptsNoncurrent"], 92_372_004_000)
        self.assertEqual(result["customerReceiptsTotal"], 234_225_146_000)


    def test_tsmc_style_pdf_note_text(self):
        text = """
        單位：新台幣仟元
        （二）合約餘額
        115年6月30日 114年12月31日 114年6月30日
        合約負債（帳列應付費用及其他流動負債） $ 55,852,048 $ 49,954,384 $ 56,799,375

        （三）暫收客戶款
        115年6月30日 114年12月31日 114年6月30日
        流動（帳列應付費用及其他流動負債） $ 141,853,142 $ 146,559,275 $ 155,973,239
        非流動（帳列其他非流動負債） 92,372,004 43,298,936 65,942,034
        $ 234,225,146 $ 189,858,211 $ 221,915,273
        """
        result = parse_pdf_note_text(text, "2026Q2")
        self.assertEqual(result["contractCurrent"], 55_852_048_000)
        self.assertEqual(result["contractTotal"], 55_852_048_000)
        self.assertEqual(result["customerReceiptsCurrent"], 141_853_142_000)
        self.assertEqual(result["customerReceiptsNoncurrent"], 92_372_004_000)
        self.assertEqual(result["customerReceiptsTotal"], 234_225_146_000)


    def test_wrong_period_is_not_used(self):
        html = """<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"
                         xmlns:xbrli="http://www.xbrl.org/2003/instance"><body>
        <xbrli:context id="old"><xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period></xbrli:context>
        <table><tr><td>合約負債（流動）</td><td>
        <ix:nonFraction name="x:ContractLiabilities" contextRef="old" scale="3">123</ix:nonFraction>
        </td></tr></table>
        </body></html>"""
        result = parse_ixbrl_html(html, "2026Q2")
        self.assertIsNone(result["contractCurrent"])


if __name__ == "__main__":
    unittest.main()
