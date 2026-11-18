import importlib.util,pathlib,unittest,xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('watchdog_setup',ROOT/'scripts/install-runner-watchdog.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class TestWatchdog(unittest.TestCase):
 def test_task_preserves_current_user_and_retries_without_password_or_timeout(self):
  tree=ET.fromstring(m.task_xml('S-1-test',r'C:\Python\python.exe',r'C:\User Space\watchdog.py',r'C:\Windows\System32\actions-runner'));ns={'t':'http://schemas.microsoft.com/windows/2004/02/mit/task'}
  def text(path):return tree.find(path,ns).text
  self.assertEqual(text('.//t:LogonType'),'InteractiveToken');self.assertEqual(text('.//t:UserId'),'S-1-test')
  self.assertEqual(text('.//t:MultipleInstancesPolicy'),'IgnoreNew');self.assertEqual(text('.//t:ExecutionTimeLimit'),'PT0S');self.assertEqual(text('.//t:Repetition/t:Interval'),'PT5M')
  self.assertIn('"C:\\User Space\\watchdog.py"',text('.//t:Exec/t:Arguments'))
  self.assertIsNone(tree.find('.//t:Password',ns))
 def test_watchdog_has_valid_python_and_no_token_or_registration_calls(self):
  compile(m.WATCHDOG,'watchdog.py','exec')
  self.assertNotIn('config.cmd',m.WATCHDOG);self.assertNotIn('KIWOOM_APP_KEY',m.WATCHDOG);self.assertIn('Runner.Worker.exe',m.WATCHDOG);self.assertIn('LK_NBLCK',m.WATCHDOG)
 def test_published_diagnostics_omit_account_identifiers(self):
  spec=importlib.util.spec_from_file_location('readiness',ROOT/'scripts/check-runner-autostart.py');d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
  result=d.inspect(m.task_xml('S-1-private-user',r'C:\Python\python.exe',r'C:\Users\Private\watchdog.py',m.DEFAULT_RUNNER))
  self.assertEqual(result['status'],'configured');self.assertFalse(result['before_sign_in']);self.assertNotIn('S-1-',str(result));self.assertNotIn('Private',str(result))

 def test_windows_xml_encodings(self):
  spec=importlib.util.spec_from_file_location('readiness',ROOT/'scripts/check-runner-autostart.py');d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
  xml=m.task_xml('S-1-test','python.exe','watchdog.py',m.DEFAULT_RUNNER).decode('utf-16')
  for raw in [xml.encode('utf-16'),xml.encode('utf-16-le'),xml.encode('utf-8'),xml.replace('S-1-test','사용자').encode('cp949')]:
   self.assertEqual(d.inspect(raw)['status'],'configured')
