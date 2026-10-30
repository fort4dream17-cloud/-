#!/usr/bin/env python3
"""Observed ETF signals only; require independently supplied adjusted prices.
Input quotes: {price_basis:'adjusted',delisted_included:true,sessions:[ISO...],
 quotes:{stock_code:{ISO_date:[adjusted_close,benchmark_close]}}}.
"""
import argparse
import json
import pathlib
import statistics
from passive_engine import backtest
from collect import atomic, now
ROOT=pathlib.Path(__file__).resolve().parents[1]

def run():
    parser=argparse.ArgumentParser();parser.add_argument('--prices');args=parser.parse_args()
    out={'status':'unavailable','checked_at':now().isoformat(),'groups':[],
      'message':'N/A: 당시 관측한 ETF 신호와 상장폐지 포함 수정주가·벤치마크 이력 필요. 소급 가상 신호 생성 안 함.'}
    if args.prices:
        data=json.loads(pathlib.Path(args.prices).read_text())
        if data.get('price_basis')!='adjusted' or data.get('delisted_included') is not True:
            raise ValueError('Adjusted prices and delisted securities required')
        days=json.loads((ROOT/'dist/data/etf-history.json').read_text())['days']
        for horizon in [5,20,60]:
            rows=backtest(days,data['quotes'],data['sessions'],horizon)
            for direction in [1,-1]:
                subset=[r for r in rows if r['direction']==direction];values=[r['excess_pct'] for r in subset]
                out['groups'].append({'horizon':horizon,'direction':direction,'n':len(subset),
                  'mean':statistics.mean(values) if values else None,'median':statistics.median(values) if values else None,
                  'win_pct':sum(v*direction>0 for v in values)/len(values)*100 if values else None,
                  'max_drawdown':min(r['max_drawdown_pct'] for r in subset) if subset else None})
        out['status']='calculated';out['message']='다음 거래일 종가 기준, 중복 신호 제거. 비용 미반영. 최대낙폭은 상대자산의 낙폭이며 공매도 전략 수익률 아님.'
    atomic(ROOT/'dist/data/etf-backtest.json',out)

if __name__=='__main__':run()
