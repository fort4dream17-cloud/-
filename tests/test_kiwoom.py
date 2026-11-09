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
