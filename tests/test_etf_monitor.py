import importlib.util,pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
def module(name,file):
 s=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
b=module('etf_monitor','build-etf-monitor.py');h=module('etf_holdings','collect-etf-holdings.py')
class TestMonitor(unittest.TestCase):
 def test_adv_excludes_signal_day_and_missing_history_stays_na(self):
  from datetime import date,timedelta
  dates=[(date(2026,10,1)+timedelta(days=i)).isoformat() for i in range(21)]
  days=[{'as_of':d,'funds':[{'code':'069500','close':100,'nav':100,'turnover':100,'volume':10,'units':100,'aum':10000}]} for d in dates]
  f={**days[-1]['funds'][0],'quote_date':dates[-1],'turnover':200,'units':110}
  result=b.build({'meta':{'as_of':dates[-1]},'funds':[f]},days)['funds'][0]
  self.assertEqual(result['adv20'],100);self.assertEqual(result['turnover_rvol'],2);self.assertEqual(result['units_change_value'],1000);self.assertFalse(result['creation_confirmed']);self.assertIsNone(result['returns']['60'])
  days[2]['funds']=[]
  self.assertIsNone(b.build({'meta':{'as_of':dates[-1]},'funds':[f]},days)['funds'][0]['adv20'])
 def test_duplicate_current_etf_rejected(self):
  with self.assertRaises(ValueError):b.build({'meta':{'as_of':'2026-11-06'},'funds':[{'code':'069500','quote_date':'2026-11-06'}]*2},[])
class TestPdf(unittest.TestCase):
 def payload(self):return {'pdf':{'gijunYMD':'20261106','totalCnt':2,'list':[{'itmNo':'005930','secNm':'삼성전자','ratio':'33.18','applyQ':'6962'},{'itmNo':'KRD010010001','secNm':'현금','ratio':None,'applyQ':'1'}]}}
 def test_full_pdf_filters_nonstock_without_claiming_no_holdings(self):
  p=h.parse_pdf(self.payload(),'2026-11-06',{'005930'});self.assertEqual(p['reported_component_count'],2);self.assertEqual(len(p['holdings']),1);self.assertEqual(p['holdings'][0]['weight_pct'],33.18)
 def test_date_and_truncation_fail_closed(self):
  with self.assertRaises(ValueError):h.parse_pdf(self.payload(),'2026-11-09',{'005930'})
  p=self.payload();p['pdf']['totalCnt']=200
  with self.assertRaises(ValueError):h.parse_pdf(p,'2026-11-06',{'005930'})
