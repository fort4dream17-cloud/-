import importlib.util,pathlib,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cancel_stale',ROOT/'scripts/cancel-stale-krx-runs.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class DrainTest(unittest.TestCase):
    def test_only_known_krx_runs_cancelled_and_wait_for_completion(self):
        calls=[];cancelled=set()
        def api(method,path):
            calls.append((method,path))
            if method=='POST':cancelled.add(4);return {}
            if 'status=queued' in path and not cancelled:
                return {'workflow_runs':[{'id':4,'name':'Update ETF basket pressure','status':'queued'},
                    {'id':7,'name':'Other unrelated workflow','status':'queued'}]}
            return {'workflow_runs':[]}
        module.drain(api,9,pause=lambda _:None)
        self.assertEqual([c for c in calls if c[0]=='POST'],[('POST','/actions/runs/4/cancel')])

    def test_timeout_fails_closed_when_cancellation_has_not_completed(self):
        times=iter([0,100])
        def api(method,path):
            if method=='POST':return {}
            return {'workflow_runs':[{'id':4,'name':'Update ETF basket pressure','status':'in_progress'}]} if 'status=in_progress' in path else {'workflow_runs':[]}
        with self.assertRaisesRegex(RuntimeError,'no login attempt'):
            module.drain(api,9,clock=lambda:next(times),pause=lambda _:None)
