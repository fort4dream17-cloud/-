import importlib.util,pathlib,unittest
from datetime import datetime,timezone
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('refresh_health',ROOT/'scripts/refresh-health.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class TestHealth(unittest.TestCase):
 def test_new_pending_run_does_not_hide_runner_blocker(self):
  r=m.diagnose('2026-11-06','2026-11-09',[{'status':'pending'},{'status':'queued','created_at':'2026-11-10T00:00:00Z'}],datetime(2026,11,10,1,tzinfo=timezone.utc))
  self.assertEqual(r['status'],'waiting_runner');self.assertEqual(r['queued_or_run_age_minutes'],60)
 def test_queued_has_no_false_auth_failure(self):
  result=m.diagnose('2026-11-06','2026-11-09',[{'status':'queued','created_at':'2026-11-10T00:00:00Z'}],datetime(2026,11,10,1,tzinfo=timezone.utc))
  self.assertEqual(result['status'],'waiting_runner');self.assertEqual(result['queued_or_run_age_minutes'],60);self.assertFalse(result['web_login'])
 def test_failure_and_current_are_separate(self):
  self.assertEqual(m.diagnose('2026-11-06','2026-11-09',[{'status':'completed','conclusion':'failure'}],datetime.now(timezone.utc))['status'],'failed')
  self.assertEqual(m.diagnose('2026-11-09','2026-11-09',[{'status':'completed','conclusion':'success'}],datetime.now(timezone.utc))['status'],'current')
 def test_etf_workflow_has_no_pc_or_kiwoom_dependency(self):
  s=(ROOT/'.github/workflows/update-etf-monitor.yml').read_text()
  self.assertIn('runs-on: ubuntu-latest',s);self.assertNotIn('self-hosted',s);self.assertNotIn('Update Kiwoom investor flows',s)
 def test_recovery_and_no_unbounded_old_quote_queue(self):
  s=(ROOT/'.github/workflows/update-kiwoom.yml').read_text();self.assertIn('45 9-14',s);self.assertIn('25 23',s)
  self.assertNotIn('queue: max',(ROOT/'.github/workflows/update-index-universe.yml').read_text())
