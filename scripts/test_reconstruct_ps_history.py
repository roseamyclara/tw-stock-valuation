import unittest
from datetime import date
from reconstruct_ps_history import esb_rows, json_rows, months, parse_revenue, reconstruct, revenue_series

class ReconstructionTests(unittest.TestCase):
    def test_reject_silent_current_date_fallback(self):
        payload={'date':'20261008','fields':['代號','收盤','發行股數'],'data':[['8102','60','100']]}
        with self.assertRaisesRegex(ValueError, '日期不符'):
            json_rows(payload,date(2020,12,31),['代號','收盤','發行股數'])

    def test_field_mapping_and_non_stock_filter(self):
        p={'tables':[{'date':'109/12/31','fields':['名稱','發行股數 ','代號','收盤 '],
             'data':[['A','100','8102','10'],['ETF','500','00679B','40']]}]}
        self.assertEqual(json_rows(p,date(2020,12,31),['代號','收盤','發行股數']),{'8102':{'收盤':'10','發行股數':'100'}})

    def test_esb_date_average_and_historical_shares(self):
        text='TITLE,日行情表\nDATADATE,日期:109年12月31日\nHEADER,證券代號,日均價,最後,發行股數\nBODY,8102,20,25,1000\n'
        self.assertEqual(esb_rows(text,date(2020,12,31)),{'8102':[20,1000,'esb']})
        with self.assertRaises(ValueError): esb_rows(text,date(2019,12,31))

    def test_ttm_units_complete_months_and_no_future_revenue(self):
        valuation={'d':'2020-12-31','sources':{},'s':{'8102':[20,1000000,'esb']}}
        rev={('8102',m):1000 for m in months('2019-12','2020-11')}
        rev['8102','2020-12']=999999
        r=reconstruct('2020-12',valuation,rev)
        self.assertEqual(r['revenueMonth'],'2020-11')
        self.assertEqual(r['s']['8102'],[1.6667,20,1000000,12000000,'esb'])
        del rev['8102','2020-02']
        self.assertEqual(reconstruct('2020-12',valuation,rev)['s'],{})

    def test_cross_market_revenue_and_conflict(self):
        r=revenue_series([('esb','2020-01',{'8102':[100,80]}),('otc','2020-02',{'8102':[200,100]})])
        self.assertEqual(r['8102','2020-01'],100)
        self.assertEqual(r['8102','2020-02'],200)
        r=revenue_series([('esb','2020-01',{'8102':[100,80]}),('otc','2020-01',{'8102':[200,80]})])
        self.assertNotIn(('8102','2020-01'),r)

    def test_2012_comparatives_and_period_validation(self):
        r=revenue_series([('listed','2013-01',{'2330':[200,100]})])
        self.assertEqual(r['2330','2012-01'],100)
        with self.assertRaises(ValueError):
            parse_revenue('資料年月,公司代號,營業收入-當月營收\n115/9,8102,100\n','2013-01')

if __name__ == '__main__': unittest.main()
