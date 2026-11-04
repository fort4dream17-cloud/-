import importlib.util,json,pathlib,tempfile,unittest,os,sys,types
from unittest.mock import patch,Mock
ROOT=pathlib.Path(__file__).resolve().parents[1]

class AuthGateTest(unittest.TestCase):
    def module(self):
        spec=importlib.util.spec_from_file_location('auth_gate_collector',ROOT/'scripts/collect.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

    def test_failed_auth_blocks_other_processes_without_import_or_request(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as d,patch.object(m,'ROOT',pathlib.Path(d)),patch.dict(os.environ,{'KRX_AUTH_RECOVERY':'','KRX_ID':'TEST_ONLY','KRX_PW':'TEST_ONLY'}):
            p=pathlib.Path(d)/'dist/data/krx-auth.json';p.parent.mkdir(parents=True)
            p.write_text(json.dumps({'status':'blocked','provider_code':'CD007'}))
            with self.assertRaisesRegex(ValueError,'KRX 자동 인증 중지'):
                m.authenticated_stock()

    def test_one_successful_recovery_clears_gate_and_contains_no_credentials(self):
        m=self.module();session=type('Session',(),{'request':lambda *a,**k:None});stock=Mock()
        modules={'requests':types.SimpleNamespace(sessions=types.SimpleNamespace(Session=session)),
                 'pykrx':types.SimpleNamespace(stock=stock),'pykrx.website':types.ModuleType('pykrx.website'),
                 'pykrx.website.comm':types.SimpleNamespace(webio=types.SimpleNamespace(_session=types.SimpleNamespace(is_authenticated=True)))}
        with tempfile.TemporaryDirectory() as d,patch.object(m,'ROOT',pathlib.Path(d)),patch.dict(os.environ,{'KRX_AUTH_RECOVERY':'true','KRX_ID':'TEST_ID_NEVER_PUBLISH','KRX_PW':'TEST_PW_NEVER_PUBLISH','FLOW_DATA_USE_CONFIRMED':'true'}),patch.dict(sys.modules,modules):
            p=pathlib.Path(d)/'dist/data/krx-auth.json';p.parent.mkdir(parents=True);p.write_text('{"status":"blocked"}')
            self.assertIs(m.authenticated_stock(),stock)
            self.assertEqual(json.loads(p.read_text())['status'],'verified')
            self.assertNotIn('NEVER_PUBLISH',p.read_text())
