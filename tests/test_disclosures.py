import importlib.util,pathlib,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('disclosures',ROOT/'scripts/update-pension-disclosures.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class DisclosureTest(unittest.TestCase):
    def test_receipt_date_is_not_holding_date(self):
        row={'corp_code':'01390344','repror':'국민연금공단','rcept_dt':'20260908','rcept_no':'20260908000302','stkrt':'8.02'}
        record=module.report_record('329180',row,'01390344')
        self.assertIsNone(record['as_of']);self.assertEqual(record['published_at'],'2026-09-08')
        self.assertIn('특별관계자 합산',record['ratio_basis'])
        self.assertIsNone(module.report_record('329180',{**row,'repror':'다른 주요주주'},'01390344'))
        self.assertIsNone(module.report_record('329180',{**row,'stkrt':'101'},'01390344'))

    def test_mismatched_issuer_and_future_receipt_are_rejected(self):
        row={'corp_code':'01390344','repror':'국민연금공단','rcept_dt':'20260908','rcept_no':'20260908000302','stkrt':'8.02'}
        self.assertIsNone(module.report_record('329180',row,'00000000'))
        self.assertIsNone(module.report_record('329180',row,'01390344','2026-09-01'))

    def test_stale_report_is_not_published_as_a_current_ratio(self):
        row={'corp_code':'01390344','repror':'국민연금공단','rcept_dt':'20240908','rcept_no':'20240908000302','stkrt':'8.02'}
        self.assertIsNone(module.report_record('329180',row,'01390344','2026-10-25'))
