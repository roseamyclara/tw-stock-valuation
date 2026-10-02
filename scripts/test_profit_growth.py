import unittest
from build_profit_growth import compare,parse
class ProfitTests(unittest.TestCase):
 def test_positive(self): self.assertEqual(compare({'parent':120},{'parent':100})['yoy'],20)
 def test_no_mixed_basis(self): self.assertEqual(compare({'parent':120},{'total':100})['status'],'missing')
 def test_matching_total_fallback(self): self.assertEqual(compare({'parent':120,'total':140},{'total':100})['yoy'],40)
 def test_zero_and_loss(self):
  self.assertEqual(compare({'parent':10},{'parent':0})['status'],'去年同期為零')
  self.assertEqual(compare({'parent':10},{'parent':-2})['status'],'轉盈')
  self.assertEqual(compare({'parent':-10},{'parent':2})['status'],'轉虧')
  self.assertIsNone(compare({'parent':-10},{'parent':-20})['yoy'])
 def test_multi_industry_headers(self):
  html='單位：新台幣仟元<table><tr><th>公司<br>代號</th><th>本期淨利（淨損）</th></tr><tr><td>1234</td><td>1,000</td></tr><tr><th>公司代號</th><th>淨利（損）歸屬於母公司業主</th></tr><tr><td>5678</td><td>0</td></tr></table>'
  self.assertEqual(parse(html),{'1234':{'total':1000},'5678':{'parent':0}})
if __name__=='__main__':unittest.main()
