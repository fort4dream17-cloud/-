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

    def test_hidden_refresh_failure_sends_no_more_requests_even_if_caller_retries(self):
        m=self.module();records=[];wire=[]
        replies=iter(['CD001','CD007'])
        def request(session,*args,**kwargs):
            wire.append(args)
            return types.SimpleNamespace(json=lambda:{'_error_code':next(replies),'_error_message':'SECRET NEVER PUBLISH'})
        guarded=m.krx_request_guard(request,records.append)
        login='https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd'
        guarded(None,'POST',login,data={'pw':'SYNTHETIC_SECRET_ONLY'})
        with self.assertRaisesRegex(ValueError,'CD007'):guarded(None,'POST',login)
        for i in range(10):
            with self.assertRaises(ValueError):guarded(None,'POST',login)
            with self.assertRaises(ValueError):guarded(None,'GET','https://data.krx.co.kr/market')
        self.assertEqual(len(wire),2)
        self.assertEqual(records[0]['phase'],'session_refresh')
        self.assertEqual(records[0]['login_requests_in_process'],2)
        self.assertNotIn('SECRET',json.dumps(records))

    def test_duplicate_session_handshake_is_bounded(self):
        m=self.module();records=[];wire=[];replies=iter(['CD011','CD011'])
        def request(session,*args,**kwargs):
            wire.append(args);return types.SimpleNamespace(json=lambda:{'_error_code':next(replies)})
        guarded=m.krx_request_guard(request,records.append)
        login='https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd'
        guarded(None,method='POST',url=login)
        with self.assertRaisesRegex(ValueError,'CD011'):guarded(None,method='POST',url=login)
        with self.assertRaises(ValueError):guarded(None,method='POST',url=login)
        self.assertEqual(len(wire),2)

    def test_initial_rejection_stops_after_one_and_other_origins_are_unaffected(self):
        m=self.module();wire=[];records=[]
        def request(session,*args,**kwargs):
            wire.append(args);return types.SimpleNamespace(json=lambda:{'_error_code':'CD007'})
        guarded=m.krx_request_guard(request,records.append)
        login='https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd'
        with self.assertRaises(ValueError):guarded(None,'POST',login)
        with self.assertRaises(ValueError):guarded(None,'POST',login)
        guarded(None,'GET','https://example.org/public')
        self.assertEqual(len(wire),2)
        self.assertEqual(records[0]['phase'],'initial_login')

    def test_uncertain_login_response_is_not_retried(self):
        m=self.module();wire=[];records=[]
        def request(session,*args,**kwargs):wire.append(args);raise TimeoutError('SENSITIVE TRANSPORT DETAIL')
        guarded=m.krx_request_guard(request,records.append)
        login='https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd'
        for i in range(5):
            with self.assertRaises(ValueError):guarded(None,'POST',login)
        self.assertEqual(len(wire),1)
        self.assertNotIn('SENSITIVE',json.dumps(records))

    def test_successful_duplicate_login_handshake_is_preserved(self):
        m=self.module();records=[];replies=iter(['CD011','CD001'])
        def request(session,*args,**kwargs):return types.SimpleNamespace(json=lambda:{'_error_code':next(replies)})
        guarded=m.krx_request_guard(request,records.append)
        login='https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd'
        guarded(None,'POST',login);guarded(None,'POST',login)
        self.assertEqual(records,[])
