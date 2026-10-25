"""Offline collector integration: synthetic unit fixtures never enter production files."""
import importlib.util,json,pathlib,tempfile,unittest,subprocess,sys,datetime
ROOT=pathlib.Path(__file__).resolve().parents[1]
class PipelineTest(unittest.TestCase):
    def test_failed_update_preserves_last_dataset_and_records_status(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d);out=p/'market.json';original={'sentinel':'last-good'};out.write_text(json.dumps(original))
            source=p/'bad.json';source.write_text('{"schema_version":2,"meta":{"data_kind":"example"},"rows":[]}')
            r=subprocess.run([sys.executable,str(ROOT/'scripts/collect.py'),'--provider','file','--input',str(source),'--output',str(out),'--log-dir',str(p/'logs')],capture_output=True)
            self.assertNotEqual(r.returncode,0);self.assertEqual(json.loads(out.read_text()),original)
            self.assertEqual(json.loads((p/'status.json').read_text())['status'],'failed')
    def test_validated_file_ingestion_then_duplicate_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d);out=p/'market.json';source=p/'input.json'
            a=[]
            for i in range(65):
                date=(datetime.date(2025,1,1)+datetime.timedelta(days=i)).isoformat()
                a.append(dict(date=date,code='042660',name='TEST FIXTURE',sector='조선',close=100,adjusted_close=100,benchmark=100,marketcap=1000,turnover=10,pension=1,foreign=1))
            obj=dict(schema_version=2,meta=dict(data_kind='real',status='final',source='SYNTHETIC UNIT TEST ONLY',unit='KRW_100M',benchmark_name='TEST',price_basis='adjusted',dividend_adjusted=False,fetched_at='2025-05-01T00:00:00Z',as_of=a[-1]['date'],trading_dates=[r['date'] for r in a]),rows=a)
            source.write_text(json.dumps(obj));cmd=[sys.executable,str(ROOT/'scripts/collect.py'),'--provider','file','--input',str(source),'--output',str(out),'--log-dir',str(p/'logs')]
            good=subprocess.run(cmd,capture_output=True);self.assertEqual(good.returncode,0,good.stderr)
            before=out.read_bytes();obj['rows'].append(a[0]);source.write_text(json.dumps(obj))
            bad=subprocess.run(cmd,capture_output=True);self.assertNotEqual(bad.returncode,0);self.assertEqual(out.read_bytes(),before)
    def test_missing_credentials_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as d:
            import os
            env={k:v for k,v in os.environ.items() if k not in ('KRX_ID','KRX_PW')}
            r=subprocess.run([sys.executable,str(ROOT/'scripts/collect.py'),'--provider','pykrx','--end','20251022','--output',d+'/market.json','--log-dir',d+'/logs'],capture_output=True,env=env)
            self.assertNotEqual(r.returncode,0);self.assertIn('KRX_ID',r.stderr.decode());self.assertFalse(pathlib.Path(d+'/market.json').exists())
class CollectionDateTest(unittest.TestCase):
    def test_safe_query_boundaries(self):
        spec=importlib.util.spec_from_file_location('collector',ROOT/'scripts/collect.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        for stamp,expected in [('2026-10-25T14:00:00+09:00','20261023'),('2026-10-26T14:00:00+09:00','20261023'),('2026-10-26T18:20:00+09:00','20261026'),('2026-10-27T09:00:00+09:00','20261026')]:
            self.assertEqual(m.collection_end(datetime.datetime.fromisoformat(stamp)),expected)
        current=datetime.datetime.fromisoformat('2026-10-26T14:00:00+09:00')
        self.assertEqual(m.collection_end(current,'20261023'),'20261023')
        for end in ['20261026','20261027']:
            with self.assertRaises(ValueError):m.collection_end(current,end)
if __name__=='__main__':unittest.main()
