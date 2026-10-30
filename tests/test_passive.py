"""Synthetic math fixtures only. No fixture is published as market data."""
import copy
import importlib.util
import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from passive_engine import etf_stock_pressure, build_day, rolling, backtest, keyed

def fund(units=100,qty=20,date='2026-10-29'):
    return {'code':'UNIT','name':'SYNTHETIC UNIT TEST','units':units,'nav':10,'close':10,'aum':units*10,
      'cu_size':10,'cu_verified':True,'pdf_ok':True,'quote_date':date,'pdf_date':date,
      'physical_eligible':True,'holdings':[{'code':'TEST','qty_per_cu':qty,'weight_pct':10}]}

class PassiveTests(unittest.TestCase):
    def test_creation_and_rebalance_exactly_reconcile_without_double_count(self):
        a=fund(120,30);b=fund(100,20,'2026-10-28')
        r=etf_stock_pressure(a,b,'TEST',5)
        self.assertEqual(r['creation'],300)
        self.assertEqual(r['rebalance'],500)
        self.assertEqual(r['net'],(120*3-100*2)*5)
        self.assertFalse(r['execution_verified'])

    def test_price_only_weight_drift_is_not_rebalancing(self):
        a=fund();b=fund(date='2026-10-28');a['holdings'][0]['weight_pct']=20
        r=etf_stock_pressure(a,b,'TEST',10,5)
        self.assertEqual(r['creation'],0)
        self.assertEqual(r['rebalance'],0)

    def test_missing_data_not_zero(self):
        a=fund();b=fund();a['cu_size']=None
        r=etf_stock_pressure(a,b,'TEST',5)
        self.assertIsNone(r['net'])
        b['pdf_date']='2026-10-20'
        self.assertIsNone(etf_stock_pressure(fund(),b,'TEST',5)['creation'])

    def test_verified_weight_proxy_is_explicit_approximation(self):
        a=fund(120);b=fund();a['cu_verified']=False;a['weight_verified']=True
        r=etf_stock_pressure(a,b,'TEST',5)
        self.assertEqual(r['creation'],20)
        self.assertIsNone(r['rebalance'])
        self.assertIn('근사',r['method'])

    def test_gross_sides_do_not_disappear_in_net(self):
        a=fund(150,10);b=fund(100,20)
        r=etf_stock_pressure(a,b,'TEST',5)
        self.assertEqual(r['gross_buy'],250)
        self.assertEqual(r['gross_sell'],500)
        self.assertEqual(r['net'],-250)

    def test_confirmed_etf_and_stock_splits_do_not_create_false_flow(self):
        a=fund(200,10);b=fund(100,20)
        r=etf_stock_pressure(a,b,'TEST',5,event={'etf_split':2,'verified_source':'https://example.test/official'})
        self.assertEqual(r['net'],0)
        a=fund(100,40);b=fund(100,20)
        self.assertEqual(etf_stock_pressure(a,b,'TEST',5,10,{'stock_split':2,'verified_source':'https://example.test/official'})['net'],0)

    def test_possible_split_is_held_for_review(self):
        a=fund(200,20);b=fund(100,20);a['nav']=5
        self.assertIsNone(etf_stock_pressure(a,b,'TEST',5)['net'])

    def test_active_fund_has_creation_effect_but_no_mechanical_rebalance(self):
        a=fund(120);b=fund();a['passive_rebalance_eligible']=False
        r=etf_stock_pressure(a,b,'TEST',5)
        self.assertEqual(r['creation'],200);self.assertIsNone(r['rebalance'])

    def test_duplicate_etf_and_constituent_rejected(self):
        with self.assertRaises(ValueError):keyed([fund(),fund()])
        a=fund();a['holdings']*=2
        with self.assertRaises(ValueError):etf_stock_pressure(a,fund(),'TEST',5)

    def test_missing_collection_cannot_be_presented_as_complete_total(self):
        current={'as_of':'2026-10-29','universe_count':2,'etfs':[fund(120)]}
        previous={'as_of':'2026-10-28','etfs':[fund()]}
        d=build_day(current,previous,{'TEST':{'name':'UNIT TEST','close':5,'adv20':1000}})
        self.assertEqual(d['meta']['pdf_success_pct'],50)
        self.assertEqual(d['stocks'][0]['adv_pct'],20)
        self.assertTrue(d['stocks'][0]['partial'])
        self.assertIsNone(d['stocks'][0]['financial_adv_pct'])

    def test_rolling_requires_each_real_session_and_complete_scope(self):
        days=[{'meta':{'as_of':str(i)},'stocks':[{'code':'TEST','net':10,'partial':False}]} for i in range(5)]
        self.assertEqual(rolling(days,'TEST',[str(i) for i in range(5)],5),50)
        self.assertIsNone(rolling(days[:-1],'TEST',[str(i) for i in range(5)],5))
        days[2]['stocks'][0]['partial']=True
        self.assertIsNone(rolling(days,'TEST',[str(i) for i in range(5)],5))

    def test_backtest_has_next_close_entry_maturity_and_overlap_control(self):
        sessions=['2026-10-'+str(i).zfill(2) for i in range(1,11)]
        days=[{'meta':{'as_of':sessions[i],'available_at':sessions[i]+'T18:00:00+09:00'},'stocks':[{'code':'TEST','net':1,'adv_pct':4,'partial':False}]} for i in range(4)]
        quotes={'TEST':{d:[100+i,100] for i,d in enumerate(sessions)}}
        result=backtest(days,quotes,sessions,5)
        self.assertEqual(len(result),1)
        self.assertAlmostEqual(result[0]['excess_pct'],(106/101-1)*100)
        self.assertEqual(result[0]['max_drawdown_pct'],0)
        self.assertEqual(backtest(days,quotes,sessions,60),[])

    def test_backtest_rejects_data_published_after_entry_close(self):
        sessions=['2026-10-'+str(i).zfill(2) for i in range(1,11)]
        day={'meta':{'as_of':sessions[0],'available_at':sessions[1]+'T15:31:00+09:00'},'stocks':[{'code':'TEST','adv_pct':4,'partial':False}]}
        quotes={'TEST':{d:[100+i,100] for i,d in enumerate(sessions)}}
        self.assertEqual(backtest([day],quotes,sessions,5),[])
        day['meta']['available_at']=sessions[1]+'T15:29:00+09:00'
        self.assertEqual(len(backtest([day],quotes,sessions,5)),1)
