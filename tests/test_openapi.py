import sys,pathlib,importlib.util,json,tempfile,unittest,urllib.error
from datetime import date
from unittest.mock import patch,Mock
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from krx_openapi import Client,APIError,kospi_close,number
spec=importlib.util.spec_from_file_location('openapi_collect',ROOT/'scripts/collect-openapi.py')
collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)

def fixture(service,day):
    if service=='kospi':rows=[{'BAS_DD':day,'IDX_NM':'코스피','CLSPRC_IDX':'3,000.50'}]
    else:
        code={'stocks':'005930','kosdaq':'000250','etf':'069500'}[service]
        rows=[{'BAS_DD':day,'ISU_CD':code,'ISU_NM':'SYNTHETIC UNIT TEST ONLY','TDD_CLSPRC':'10,000','ACC_TRDVOL':'100','ACC_TRDVAL':'1,000,000','MKTCAP':'1,000,000,000','FLUC_RT':'1.25','NAV':'10,001','INVSTASST_NETASST_TOTAMT':'100,000,000','LIST_SHRS':'10,000','IDX_IND_NM':'TEST'}]
    return {'OutBlock_1':rows}

class OpenAPITest(unittest.TestCase):
    def test_auth_denial_is_not_retried_and_does_not_leak_key(self):
        count=[]
        def transport(service,day):count.append(service);raise urllib.error.HTTPError('https://data-dbg.krx.co.kr',401,'SENSITIVE_KEY_NEVER_PUBLISH',{},None)
        client=Client('SENSITIVE_KEY_NEVER_PUBLISH',transport=transport)
        for _ in range(3):
            with self.assertRaisesRegex(APIError,'HTTP 401') as error:client.get('stocks','20261106')
            self.assertNotIn('SENSITIVE',str(error.exception))
        self.assertEqual(count,['stocks'])

    def test_dates_duplicates_and_wrong_benchmark_are_rejected(self):
        for rows in [[{'BAS_DD':'20260101','ISU_CD':'005930'}],[{'BAS_DD':'20261106','ISU_CD':'005930'}]*2]:
            client=Client('TEST',transport=lambda *a:{'OutBlock_1':rows})
            with self.assertRaises(APIError):client.get('stocks','20261106')
        with self.assertRaises(APIError):kospi_close([{'IDX_NM':'코스피200','CLSPRC_IDX':'100'}])
        self.assertIsNone(number('-'));self.assertEqual(number('0'),0)

    def test_request_is_get_with_header_key_and_no_redirect_or_web_fallback(self):
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.read.return_value=json.dumps(fixture('stocks','20261106')).encode()
        opener=Mock();opener.open.return_value=response
        with patch('urllib.request.build_opener',return_value=opener):Client('TEST_API_KEY',pause=0).get('stocks','20261106')
        req=opener.open.call_args.args[0]
        self.assertEqual(req.get_method(),'GET');self.assertEqual(req.get_header('Auth_key'),'TEST_API_KEY')
        self.assertNotIn('TEST_API_KEY',req.full_url);self.assertIn('data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd',req.full_url)

    def test_refresh_keeps_investor_data_unchanged_and_marks_missing_pdf(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);data=root/'dist/data';data.mkdir(parents=True)
            previous={'meta':{'as_of':'2026-11-05'},'rows':[{'pension':12,'foreign':-2}]}
            (data/'index-market.json').write_text(json.dumps(previous));before=(data/'index-market.json').read_bytes()
            (data/'index-universe.json').write_text(json.dumps({'records':[{'code':'005930'},{'code':'000250'}]}))
            client=Client('TEST',transport=fixture)
            with patch('builtins.print'):result=collector.run(root,client,date(2026,11,6))
            self.assertEqual(result,0);self.assertEqual((data/'index-market.json').read_bytes(),before)
            history=json.loads((data/'index-price-history.json').read_text())
            self.assertEqual(history['meta']['as_of'],'2026-11-06');self.assertEqual(history['meta']['price_basis'],'raw')
            self.assertEqual(history['stocks']['005930'][-1][1],10000)
            self.assertNotIn('pension',json.dumps(history))
            etfs=json.loads((data/'etf-openapi.json').read_text())
            self.assertEqual(etfs['funds'][0]['aum'],100000000);self.assertFalse(etfs['meta']['stock_pressure_available'])
            state=json.loads((data/'krx-auth.json').read_text());self.assertEqual(state['status'],'disabled')

    def test_failed_service_preserves_last_good_price_history(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);data=root/'dist/data';data.mkdir(parents=True)
            old='{"meta":{"as_of":"2026-10-29"},"stocks":{"SENTINEL":[]}}';(data/'index-price-history.json').write_text(old)
            def source(service,day):
                if service=='stocks':raise urllib.error.HTTPError('https://data-dbg.krx.co.kr',403,'denied',{},None)
                return fixture(service,day)
            with patch('builtins.print'):result=collector.run(root,Client('TEST',transport=source),date(2026,11,6))
            self.assertEqual(result,1);self.assertEqual((data/'index-price-history.json').read_text(),old)

    def test_old_entrypoint_cannot_authenticate_even_with_recovery_enabled(self):
        from collect import authenticated_stock
        with patch.dict('os.environ',{'KRX_AUTH_RECOVERY':'true','KRX_ID':'TEST','KRX_PW':'TEST'}):
            with self.assertRaisesRegex(ValueError,'영구 비활성화'):authenticated_stock()

    def test_workflows_do_not_inject_passwords_or_install_pykrx(self):
        for path in (ROOT/'.github/workflows').glob('*.yml'):
            content=path.read_text();self.assertNotIn('secrets.KRX_PW',content,path);self.assertNotIn('secrets.KRX_ID',content,path)
            self.assertNotIn('pip install -r scripts/requirements.txt',content,path)
