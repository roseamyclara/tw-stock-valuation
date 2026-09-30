import unittest
from build_contract_liabilities import parse_report

def report(rows, period='民國115年第2季', unit='新台幣仟元'):
    return f'<h2>合併資產負債表</h2>{period} {unit}<table>'+''.join(f'<tr><td>{name}</td><td>{value}</td><td>9</td><td>888</td></tr>' for name,value in rows)+'</table>'

class ContractTests(unittest.TestCase):
    def test_units_and_current_column(self):
        d=parse_report(report([('合約負債－流動','1,234'),('合約負債－非流動','56')]),2026,2)
        self.assertEqual(d['total'],1290000)
    def test_missing_not_zero_or_total(self):
        d=parse_report(report([('合約負債－流動','123')]),2026,2)
        self.assertIsNone(d['noncurrent']);self.assertIsNone(d['total'])
    def test_zero_is_disclosed(self):
        d=parse_report(report([('合約負債－流動','0')]),2026,2)
        self.assertEqual(d['current'],0);self.assertEqual(d['status'],'disclosed')
    def test_insurance_not_customer_contracts(self):
        d=parse_report(report([('保險合約負債','100')]),2026,2)
        self.assertEqual(d['status'],'not_separately_disclosed')
    def test_mismatched_period_or_currency_rejected(self):
        with self.assertRaises(ValueError):parse_report(report([],period='民國114年第2季'),2026,2)
        with self.assertRaises(ValueError):parse_report(report([],unit='美元'),2026,2)
    def test_throttle_and_no_report(self):
        self.assertIsNone(parse_report('查無資料',2026,2))
        with self.assertRaises(RuntimeError):parse_report('因為安全性考量',2026,2)

if __name__=='__main__':unittest.main()
