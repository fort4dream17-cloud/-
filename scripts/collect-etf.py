#!/usr/bin/env python3
"""Whole domestic ETF universe adapter. Public raw-data export is explicit opt-in.
Uses no ETF-name proxy for flows, no AUM differences as subscriptions, no lookthrough.
"""
import json
import os
import pathlib
import re
import time
from datetime import timedelta
from collect import authenticated_stock, atomic, now, collection_end
from passive_engine import build_day, number, positive, rolling, keyed

ROOT=pathlib.Path(__file__).resolve().parents[1]
DATA=ROOT/'dist/data'
SOURCE='https://data.krx.co.kr/'

def num(value):
    try:
        if value is None or str(value).strip() in ('','-'):return None
        value=float(str(value).replace(',',''))
        return value if number(value) else None
    except (ValueError,TypeError):return None

def code(value):
    value=str(value)
    if re.fullmatch(r'KR[0-9A-Z]{10}',value):return value[3:9]
    return value

def read(path, default):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default

def checked_write(path, value):
    payload=json.dumps(value,ensure_ascii=False,allow_nan=False)
    if len(payload.encode())>24*1024*1024:raise ValueError('Cloudflare file limit; shard output before publishing')
    atomic(path,value)

def request(fn,*args,**kwargs):
    try:return fn(*args,**kwargs)
    finally:time.sleep(1)

def collect():
    report={'checked_at':now().isoformat(),'status':'publication_unconfirmed','source':SOURCE,
            'data_kind':'unavailable','publication_rights':'unverified','universe_count':None,
            'pdf_success_count':None,'pdf_success_pct':None,
            'message':'KRX·운용사 원자료의 본 공개 대시보드 이용·재배포 권한 확인 필요. 이용 범위가 확인된 데이터 공급원 연결 후 전체 수집 가능합니다.'}
    if os.environ.get('ETF_PUBLICATION_CONFIRMED')!='true':
        atomic(DATA/'etf-status.json',report);print(json.dumps(report,ensure_ascii=False));return 0
    report['publication_rights']='operator_confirmed'
    stock=authenticated_stock()
    from pykrx.website.krx.etx.core import ETF_전종목기본종목, 전종목시세_ETF, PDF
    from datetime import datetime
    end=collection_end(now());start=(now()-timedelta(days=100)).strftime('%Y%m%d')
    benchmark=request(stock.get_index_ohlcv_by_date,start,end,'1001')
    if benchmark is None or benchmark.empty:raise ValueError('Missing KRX trading calendar')
    sessions=[d.strftime('%Y-%m-%d') for d in benchmark.index]
    day,previous_day=sessions[-2:][1],sessions[-2:][0]
    master=request(ETF_전종목기본종목().fetch)
    if master.empty or 'ISU_SRT_CD' not in master or master['ISU_SRT_CD'].duplicated().any():raise ValueError('Invalid whole ETF universe')
    masters={str(r['ISU_SRT_CD']):r for _,r in master.iterrows()}
    snapshots=DATA/'etf-snapshots';snapshots.mkdir(exist_ok=True)
    saved=read(snapshots/'current.json',{})
    # Reuse only previously observed snapshots, never reconstruct historical CUs.
    saved_funds=keyed(saved.get('etfs',[])) if saved.get('as_of')==previous_day else {}
    output=[];failed=[]
    for date in [previous_day,day]:
        quote=request(전종목시세_ETF().fetch,date.replace('-',''))
        if quote.empty or quote['ISU_SRT_CD'].duplicated().any():raise ValueError('Invalid ETF quotes')
        etfs=[]
        for i,(_,r) in enumerate(quote.iterrows()):
            ticker=str(r['ISU_SRT_CD']);m=masters.get(ticker);old=saved_funds.get(ticker)
            cu=num(m.get('CU_QTY')) if m is not None else None
            # A CU observed after the quote date is not assumed to be historical.
            verified_cu=date==now().date().isoformat()
            if date==previous_day and old:
                etfs.append(old);continue
            units=num(r.get('LIST_SHRS'));nav=num(r.get('NAV'));aum=num(r.get('INVSTASST_NETASST_TOTAMT'))
            if not positive(aum):aum=units*nav if positive(units) and positive(nav) else None
            replication=str(m.get('ETF_REPLICA_METHD_TP_CD','')) if m is not None else ''
            name=str(r['ISU_ABBRV'])
            f={'code':ticker,'isin':str(m['ISU_CD']) if m is not None else None,'name':name,
               'manager':str(m.get('COM_ABBRV')) if m is not None else None,
               'index':str(r.get('IDX_IND_NM','')),'type':replication,
               'physical_eligible':'실물' in replication,'passive_rebalance_eligible':'액티브' not in name,
               'quote_date':date,'pdf_date':date,'pdf_date_basis':'request_parameter',
               'close':num(r.get('TDD_CLSPRC')),'nav':nav,'aum':aum,'aum_basis':'NAV × 상장좌수 또는 공급자 순자산',
               'units':units,'units_basis':'상장좌수; 설정환매 요청일과 시차 가능',
               'cu_size':cu,'cu_verified':verified_cu,'cu_observed_at':now().isoformat(),
               'volume':num(r.get('ACC_TRDVOL')),'turnover':num(r.get('ACC_TRDVAL')),
               'adv20':None,'volume_adv20':None,'weight_verified':False,'holdings':[],'pdf_ok':False,
               'gross_creations':None,'gross_redemptions':None,'target_weights':None}
            try:
                if not f['isin']:raise ValueError('Missing ISIN')
                frame=request(PDF().fetch,date.replace('-',''),f['isin'])
                if frame is None or not set(['COMPST_ISU_CD','COMPST_ISU_CU1_SHRS']).issubset(frame.columns):raise ValueError('Invalid PDF schema')
                seen=set()
                for _,h in frame.iterrows():
                    c=code(h['COMPST_ISU_CD'])
                    if c in seen:raise ValueError('Duplicate PDF constituent')
                    seen.add(c)
                    f['holdings'].append({'code':c,'name':str(h.get('COMPST_ISU_NM','')),
                       'qty_per_cu':num(h.get('COMPST_ISU_CU1_SHRS')),'weight_pct':None,
                       'provider_weight_pct':num(h.get('COMPST_RTO'))})
                f['pdf_ok']=True
            except Exception as exc:failed.append({'etf_code':ticker,'date':date,'error_type':type(exc).__name__})
            etfs.append(f)
            if i%50==0:print('ETF PDF',date,i+1,'/',len(quote),flush=True)
        output.append({'as_of':date,'universe_count':len(quote),'etfs':etfs,'source':SOURCE})
    previous,current=output
    # Market-wide denominators use prior 20 sessions, exclude signal day.
    market={}
    for date in sessions[-21:]:
        market[date]=request(stock.get_market_cap_by_ticker,date.replace('-',''),market='ALL')
    facts={};latest=market[day];before=market[previous_day]
    existing=read(DATA/'index-market.json',{'rows':[]})
    actual={r['code']:r for r in existing['rows'] if r['date']==day}
    sectors=read(ROOT/'config/sector-lookup.json',{}).get('sectors',{})
    for c,r in latest.iterrows():
        c=str(c);p=num(r.get('종가'));prev=num(before.loc[c,'종가']) if c in before.index else None
        turns=[num(market[d].loc[c,'거래대금']) if c in market[d].index else None for d in sessions[-21:-1]]
        volumes=[num(market[d].loc[c,'거래량']) if c in market[d].index else None for d in sessions[-21:-1]]
        a=actual.get(c,{})
        facts[c]={'name':str(a.get('name') or stock.get_market_ticker_name(c) or c),'sector':sectors.get(c),
          'close':p,'previous_close':prev,'turnover':num(r.get('거래대금')),'volume':num(r.get('거래량')),
          'adv20':sum(turns)/20 if len(turns)==20 and all(number(v) for v in turns) else None,
          'volume_adv20':sum(volumes)/20 if len(volumes)==20 and all(number(v) for v in volumes) else None,
          'financial':a.get('financial')*1e8 if number(a.get('financial')) else None,
          'foreign':a.get('foreign')*1e8 if number(a.get('foreign')) else None,
          'institution':a.get('institution')*1e8 if number(a.get('institution')) else None,
          'return_pct':(p/prev-1)*100 if positive(p) and positive(prev) else None,'sector_relative_pct':None}
    # Prior 20 ETF quote snapshots supply turnover/volume baselines.
    eft_series={d:request(전종목시세_ETF().fetch,d.replace('-','')) for d in sessions[-21:-1]}
    for f in current['etfs']:
        values=[];volumes=[]
        for frame in eft_series.values():
            rows=frame[frame['ISU_SRT_CD']==f['code']]
            values.append(num(rows.iloc[0].get('ACC_TRDVAL')) if len(rows)==1 else None)
            volumes.append(num(rows.iloc[0].get('ACC_TRDVOL')) if len(rows)==1 else None)
        f['adv20']=sum(values)/20 if len(values)==20 and all(number(v) for v in values) else None
        f['volume_adv20']=sum(volumes)/20 if len(volumes)==20 and all(number(v) for v in volumes) else None
    events=read(ROOT/'config/etf-events.json',{}).get(day,{})
    for f in current['etfs']:
        if f.get('cu_verified') and positive(f.get('cu_size')) and positive(f.get('nav')):
            f['weight_verified']=True
            f['weight_basis']='CU 현물수량 × 종가 / (CU × NAV); 실제 펀드 보유비중과 다를 수 있음'
            for h in f['holdings']:
                close=facts.get(h['code'],{}).get('close')
                if positive(close) and number(h.get('qty_per_cu')):
                    h['weight_pct']=h['qty_per_cu']*close/(f['cu_size']*f['nav'])*100
    result=build_day(current,previous,facts,events)
    result['meta'].update({'available_at':now().isoformat(),'publication_rights':'operator_confirmed',
       'observed_history_only':True,'pdf_failures':failed,'sector_benchmark':'unavailable',
       'licensed_supplier_feed':'not_configured','actual_execution':'unavailable'})
    # Shard the ETF database to respect Cloudflare's per-file limit.
    detail={f['code']:{**f,'stock_effects':{}} for f in current['etfs']}
    for row in result['stocks']:
        row['etf_codes']=[c['etf_code'] for c in row['contributors']]
        for c in row['contributors']:detail[c['etf_code']]['stock_effects'][row['code']]=c
        row['top_etfs']=[{'code':c['etf_code'],'name':c['name'],'net':c['net']} for c in row['contributors'][:3]]
        del row['contributors']
    directory=DATA/'etf-db';directory.mkdir(exist_ok=True)
    codes=sorted(detail);shard_map={}
    for offset in range(0,len(codes),50):
        name=f'funds-{day.replace("-","")}-{offset//50:03d}.json';part=codes[offset:offset+50]
        checked_write(directory/name,{'as_of':day,'funds':{c:detail[c] for c in part}})
        shard_map.update({c:name for c in part})
    result['meta']['fund_shards']=shard_map
    result['catalog']=[{k:f.get(k) for k in ['code','name','manager','index','type','quote_date','pdf_date','pdf_ok','aum','nav','units','cu_size','turnover','volume']} for f in current['etfs']]
    del result['etfs']
    history=read(DATA/'etf-history.json',{'days':[]})['days']
    history=[d for d in history if d['meta']['as_of']!=day]
    history.append({'meta':result['meta'],'stocks':[{k:r.get(k) for k in ['code','net','creation','rebalance','adv_pct','partial']} for r in result['stocks']]})
    history=sorted(history,key=lambda d:d['meta']['as_of'])[-125:]
    for row in result['stocks']:
        row['cumulative']={str(n):rolling(history,row['code'],sessions,n) for n in [5,20,60]}
    # Validate all output before replacing last-good main datasets.
    for value in [result,{'days':history},current,previous]:json.dumps(value,allow_nan=False)
    checked_write(snapshots/'previous.json',previous);checked_write(snapshots/'current.json',current)
    checked_write(DATA/'etf-history.json',{'days':history})
    checked_write(DATA/'etf-flow.json',result)
    report={**result['meta'],'checked_at':now().isoformat(),'message':'추정 압력 계산 완료. 실체결액 아님.'}
    atomic(DATA/'etf-status.json',report)
    print('ETF collection complete',len(current['etfs']),len(result['stocks']),flush=True)
    return 0

if __name__=='__main__':
    try:raise SystemExit(collect())
    except Exception as exc:
        atomic(DATA/'etf-status.json',{'status':'failed','checked_at':now().isoformat(),'message':'ETF 수집 실패: '+type(exc).__name__,'data_kind':'unavailable'})
        print('ETF collection failed:',type(exc).__name__);raise SystemExit(1)
