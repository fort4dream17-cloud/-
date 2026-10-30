"""Whole adapter integration with synthetic provider frames in a temporary tree."""
import contextlib
import datetime
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

class EtfCollectorIntegration(unittest.TestCase):
    def test_whole_universe_mapping_units_adv_and_date_shards(self):
        try:import pandas as pd
        except ImportError:self.skipTest('pandas installed in CI through pykrx')
        root=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('etf_collector',root/'scripts/collect-etf.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        sessions=pd.bdate_range(end='2026-10-29',periods=21)
        master=pd.DataFrame([{'ISU_SRT_CD':'069500','ISU_CD':'TEST_ETF_ISIN','CU_QTY':'10','COM_ABBRV':'SYNTHETIC TEST','ETF_REPLICA_METHD_TP_CD':'실물'}])
        def quotes(date):return pd.DataFrame([{'ISU_SRT_CD':'069500','ISU_ABBRV':'SYNTHETIC TEST ETF','LIST_SHRS':'120' if date=='20261029' else '100','NAV':'100','TDD_CLSPRC':'100','ACC_TRDVOL':'120','ACC_TRDVAL':'1200','IDX_IND_NM':'TEST'}])
        pdf=pd.DataFrame([{'COMPST_ISU_CD':'005930','COMPST_ISU_NM':'SYNTHETIC TEST STOCK','COMPST_ISU_CU1_SHRS':'20','COMPST_RTO':'99'}])
        caps=pd.DataFrame({'종가':[50.0],'거래량':[100.0],'거래대금':[1000.0]},index=['005930'])
        stock=types.SimpleNamespace(get_index_ohlcv_by_date=lambda *a:pd.DataFrame({'종가':[100]*21},index=sessions),get_market_cap_by_ticker=lambda *a,**kw:caps,get_market_ticker_name=lambda c:'SYNTHETIC TEST STOCK')
        core=types.ModuleType('pykrx.website.krx.etx.core')
        core.ETF_전종목기본종목=lambda:types.SimpleNamespace(fetch=lambda:master)
        core.전종목시세_ETF=lambda:types.SimpleNamespace(fetch=quotes)
        core.PDF=lambda:types.SimpleNamespace(fetch=lambda *a:pdf)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);data=p/'dist/data';data.mkdir(parents=True);(p/'config').mkdir()
            (data/'index-market.json').write_text(json.dumps({'rows':[{'code':'005930','name':'SYNTHETIC TEST STOCK','date':'2026-10-29','financial':1,'foreign':2,'institution':3}]}))
            with patch.object(m,'ROOT',p),patch.object(m,'DATA',data),patch.object(m,'authenticated_stock',return_value=stock),patch.object(m,'now',return_value=datetime.datetime.fromisoformat('2026-10-29T20:00:00+09:00')),patch.object(m.time,'sleep'),patch.dict(sys.modules,{'pykrx.website.krx.etx.core':core}),patch.dict(os.environ,{'ETF_PUBLICATION_CONFIRMED':'true'}),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(m.collect(),0)
            result=json.loads((data/'etf-flow.json').read_text())
            self.assertEqual(result['meta']['universe_count'],1)
            self.assertEqual(result['meta']['pdf_success_pct'],100)
            row=result['stocks'][0]
            self.assertEqual(row['net'],2000)
            self.assertEqual(row['adv20'],1000)
            self.assertEqual(row['adv_pct'],200)
            self.assertTrue(row['partial'])
            self.assertIsNone(row['rebalance'])
            self.assertIsNone(row['cumulative']['5'])
            shard=result['meta']['fund_shards']['069500']
            self.assertEqual(shard,'funds-20261029-000.json')
            detail=json.loads((data/'etf-db'/shard).read_text())['funds']['069500']
            self.assertEqual(detail['stock_effects']['005930']['basket_exposure'],12000)

    def test_no_raw_publication_without_scope_permission(self):
        root=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('etf_collector_guard',root/'scripts/collect-etf.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory() as d:
            data=Path(d);mock=unittest.mock.Mock()
            with patch.object(m,'DATA',data),patch.object(m,'authenticated_stock',mock),patch.dict(os.environ,{'ETF_PUBLICATION_CONFIRMED':''}),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(m.collect(),0)
            mock.assert_not_called()
            self.assertFalse((data/'etf-flow.json').exists())
            self.assertEqual(json.loads((data/'etf-status.json').read_text())['status'],'publication_unconfirmed')
