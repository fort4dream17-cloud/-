import unittest,pathlib,tempfile,json,sys,importlib.util
from datetime import date
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('collect_paused',ROOT/'scripts/collect-openapi.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class TestPause(unittest.TestCase):
 def test_pause_does_not_request_or_replace_etf_data(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);(root/'dist/data').mkdir(parents=True);(root/'config').mkdir()
   (root/'config/refresh-control.json').write_text('{"etf_paused":true}')
   etf=root/'dist/data/etf-openapi.json';etf.write_text('{"saved":"unchanged"}');before=etf.read_bytes()
   class Client:
    key='test';key_diagnostics={};calls=0
    def get(self,svc,day):
     if svc=='etf':raise AssertionError('ETF must not be requested')
     return []
   with patch.object(m,'refresh_prices',return_value={'status':'success','as_of':'2026-11-13'}) as prices,patch.object(m,'refresh_etfs') as funds:
    self.assertEqual(m.run(root,Client(),date(2026,11,13)),0);prices.assert_called_once();funds.assert_not_called()
   self.assertEqual(etf.read_bytes(),before)
   self.assertTrue(json.loads((root/'dist/data/etf-status.json').read_text())['paused'])
