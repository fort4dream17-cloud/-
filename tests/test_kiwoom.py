import sys,pathlib,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from kiwoom_flow import Client,APIError
class Headers(dict):pass
class TestKiwoom(unittest.TestCase):
    def client(self,rows):
        c=Client();c.token='test';c.post=lambda *a:({'stk_invsr_orgn':rows},Headers());return c
    def test_units_and_missing(self):
        f=self.client([{'dt':'20261106','frgnr_invsr':'-1234','penfnd_etc':'0'}]).flows('005930','20261106','20261106')['2026-11-06']
        self.assertEqual(f['foreign'],-12.34);self.assertEqual(f['pension'],0);self.assertIsNone(f['trust'])
    def test_future_rejected(self):
        with self.assertRaises(APIError):self.client([{'dt':'20261109'}]).flows('005930','20261106','20261106')
    def test_duplicates_rejected(self):
        with self.assertRaises(APIError):self.client([{'dt':'20261106'},{'dt':'20261106'}]).flows('005930','20261106','20261106')
if __name__=='__main__':unittest.main()

class TestPublication(unittest.TestCase):
    def test_partial_collection_never_replaces_market(self):
        import tempfile,json
        from unittest.mock import patch
        import kiwoom_flow as m
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);data=root/'dist/data';data.mkdir(parents=True)
            old={'schema_version':2,'meta':{'as_of':'2026-11-05'},'rows':[{'date':'2026-11-05','code':'005930','foreign':100,'pension':1}]}
            (data/'index-market.json').write_text(json.dumps(old));before=(data/'index-market.json').read_bytes()
            (data/'index-price-history.json').write_text(json.dumps({'meta':{'as_of':'2026-11-06'},'benchmarks':[],'stocks':{}}))
            client=self.client if hasattr(self,'client') else Client()
            client.authenticate=lambda:None
            client.flows=lambda *a:{'2026-11-06':{'foreign':1},'2026-11-05':{'foreign':1}}
            with patch.object(m,'Client',return_value=client):self.assertEqual(m.run(root),1)
            self.assertEqual((data/'index-market.json').read_bytes(),before)
            state=json.loads((data/'kiwoom-status.json').read_text());self.assertEqual(state['status'],'failed');self.assertIn('overlap mismatch',state['message'])

class TestDiagnostics(unittest.TestCase):
    def test_oauth_error_and_redaction(self):
        from kiwoom_flow import http_failure
        raw=b'{"error":"invalid_request","error_description":"bad secret123","token":"private"}'
        value=http_failure(400,raw,{'Content-Type':'application/json'},['secret123'])
        self.assertIn('invalid_request',value);self.assertNotIn('secret123',value);self.assertNotIn('private',value)
    def test_html_body_is_not_published(self):
        from kiwoom_flow import http_failure
        value=http_failure(400,b'<title>Request Rejected</title>hidden secret',{'Content-Type':'text/html'})
        self.assertIn('Request Rejected',value);self.assertNotIn('hidden secret',value)

class TestCurlTransport(unittest.TestCase):
    def test_token_only_in_stdin_and_no_redirect(self):
        from unittest.mock import patch
        import subprocess,json
        c=Client();c.key='test-app-key';c.secret='test-secret'
        def fake(args,**kw):
            self.assertNotIn(c.key,' '.join(args));self.assertNotIn(c.secret,' '.join(args));self.assertNotIn('--location',args)
            self.assertIn(c.key,kw['input'].decode());self.assertIn(c.secret,kw['input'].decode())
            pathlib.Path(args[args.index('--dump-header')+1]).write_text('HTTP/1.1 200 OK\nContent-Type: application/json\n')
            return subprocess.CompletedProcess(args,0,b'{"return_code":0,"token":"sample-token"}|KIWOOM_HTTP_STATUS|200',b'')
        with patch('kiwoom_flow.subprocess.run',side_effect=fake):c.authenticate()
        self.assertEqual(c.token,'sample-token');self.assertEqual(c.calls,1)
    def test_ip_rejection_does_not_retry(self):
        from unittest.mock import patch
        import subprocess
        c=Client();c.key='key';c.secret='secret'
        def fake(args,**kw):
            pathlib.Path(args[args.index('--dump-header')+1]).write_text('HTTP/1.1 200 OK\nContent-Type: application/json\n')
            return subprocess.CompletedProcess(args,0,b'{"return_code":3,"return_msg":"8050: IP not registered"}|KIWOOM_HTTP_STATUS|200',b'')
        with patch('kiwoom_flow.subprocess.run',side_effect=fake) as call:
            with self.assertRaisesRegex(APIError,'8050'):c.authenticate()
            self.assertEqual(call.call_count,1)
