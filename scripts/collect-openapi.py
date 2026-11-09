#!/usr/bin/env python3
"""Independent price and ETF quote refresh; investor flows/PDF are unavailable."""
import argparse,json,pathlib
from datetime import timedelta,date
from collect import atomic
from krx_openapi import Client,APIError,code,number,now,query_end,kospi_close,SERVICES
ROOT=pathlib.Path(__file__).resolve().parents[1]
def read(path,default=None):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default if default is not None else {}
def iso(d):return d.strftime('%Y-%m-%d')
def days(a,b):
    while a<=b:
        if a.weekday()<5:yield a
        a+=timedelta(days=1)
def quote(r,day):
    p=number(r.get('TDD_CLSPRC'));v=number(r.get('ACC_TRDVOL'))
    return {'code':code(r['ISU_CD']),'name':str(r.get('ISU_NM','')),'date':day,
      'close':p if p is not None and p>0 else None,'volume':v if v is not None and v>=0 else None,
      'turnover':number(r.get('ACC_TRDVAL')),'marketcap':number(r.get('MKTCAP')),'return_pct':number(r.get('FLUC_RT'))}
def quotes_day(client,d):
    records=client.get('stocks',d.strftime('%Y%m%d'))+client.get('kosdaq',d.strftime('%Y%m%d'))
    result={}
    for r in records:
        q=quote(r,iso(d))
        if q['code'] in result:raise APIError('시장 간 종목 중복')
        result[q['code']]=q
    return result
def refresh_prices(root,client,end):
    data=root/'dist/data';old=read(data/'index-price-history.json');latest=None
    for ago in range(15):
        d=end-timedelta(days=ago)
        if d.weekday()>4:continue
        rows=client.get('kospi',d.strftime('%Y%m%d'))
        if rows:
            kospi_close(rows);latest=d;break
    if latest is None:raise APIError('최근 KOSPI 관측일 미확보')
    current=quotes_day(client,latest)
    if not current:raise APIError('최근 주식 시세 미확보')
    stamp=now().isoformat()
    atomic(data/'openapi-quotes.json',{'meta':{'as_of':iso(latest),'fetched_at':stamp,'unit':'KRW','price_basis':'raw','source':'KRX OpenAPI','web_login':False},'stocks':current})
    try:last=date.fromisoformat(old['meta']['as_of'])
    except (KeyError,ValueError):last=latest-timedelta(days=120)
    begin=max(last-timedelta(days=3),latest-timedelta(days=560))
    bench={str(q[0]):q[1] for q in old.get('benchmarks',[])}
    saved={c:{q[0]:q[1:] for q in rows} for c,rows in old.get('stocks',{}).items()}
    universe=read(data/'index-universe.json',{'records':[]})['records']
    coverage=read(root/'config/coverage.json',[])
    selected={r['code'] for r in universe+coverage}|set(saved)
    if not selected:selected=set(current)
    for d in days(begin,latest):
        rows=client.get('kospi',d.strftime('%Y%m%d'))
        if not rows:continue
        b=kospi_close(rows);quotes=quotes_day(client,d)
        if not quotes:raise APIError('일별 주식 시세 누락: '+iso(d))
        bench[iso(d)]=b
        for c in selected:saved.setdefault(c,{})[iso(d)]=[quotes[c]['close'],quotes[c]['volume']] if c in quotes else [None,None]
    sessions=sorted(d for d in bench if d<=iso(latest))[-330:]
    result={'meta':{'as_of':iso(latest),'fetched_at':stamp,'source':'KRX OpenAPI AUTH_KEY · 웹 로그인 없음','price_basis':'raw','dividend_adjusted':False,
      'sessions':len(sessions),'quote_columns':['date','close_KRW','volume_shares'],'web_login':False,
      'notes':['비수정 종가·배당 미반영. 기업행위 시 수익률 왜곡 가능.','세부 수급과 가격 기준일은 별도로 표시합니다.','기존 검증된 종가 이력을 보존하고 신규 관측일만 API로 보완합니다.']},
      'benchmarks':[[d,bench[d]] for d in sessions],'stocks':{c:[[d,*saved[c].get(d,[None,None])] for d in sessions] for c in sorted(selected)}}
    atomic(data/'index-price-history.json',result)
    state={'status':'success','as_of':iso(latest),'updated_at':stamp,'stock_count':len(current),'sessions':len(sessions),'source':'KRX OpenAPI','web_login':False}
    atomic(data/'price-status.json',state);return state
def refresh_etfs(root,client,end):
    data=root/'dist/data';old=read(data/'etf-openapi-history.json',{'days':[]})
    observed={d['as_of']:d for d in old['days']};current=None
    for d in days(end-timedelta(days=40),end):
        rows=client.get('etf',d.strftime('%Y%m%d'))
        if not rows:continue
        funds=[]
        for r in rows:
            q=quote(r,iso(d));funds.append({**q,'quote_date':iso(d),'nav':number(r.get('NAV')),
              'aum':number(r.get('INVSTASST_NETASST_TOTAMT')),'units':number(r.get('LIST_SHRS')),
              'index':str(r.get('IDX_IND_NM','')),'manager':None,'type':None,'pdf_ok':False,'weight_pct':None})
        filename='etf-openapi-db/'+d.strftime('%Y%m%d')+'.json'
        current={'as_of':iso(d),'funds':funds}
        atomic(data/filename,current)
        observed[iso(d)]={'as_of':iso(d),'count':len(funds),'file':filename}
    if not current:raise APIError('ETF 일별 관측 미확보')
    history=sorted(observed.values(),key=lambda x:x['as_of'])[-61:]
    atomic(data/'etf-openapi-history.json',{'days':history})
    result={'meta':{'as_of':current['as_of'],'fetched_at':now().isoformat(),'source':'KRX ETF 일별매매정보 OpenAPI','unit':'KRW','count':len(current['funds']),
      'web_login':False,'holdings_available':False,'stock_pressure_available':False},'funds':current['funds']}
    atomic(data/'etf-openapi.json',result);return {'status':'success','as_of':current['as_of'],'count':len(current['funds'])}
def run(root,client,end,probe=False):
    data=root/'dist/data';data.mkdir(parents=True,exist_ok=True)
    report={'checked_at':now().isoformat(),'mode':'openapi_only','web_login':False,'configured':bool(client.key),'key_configuration':client.key_diagnostics,'services':[],'components':{}}
    for svc in SERVICES:
        entry={'service':SERVICES[svc],'query_date':iso(end)}
        try:entry.update({'status':'success','row_count':len(client.get(svc,end.strftime('%Y%m%d')))})
        except APIError as exc:entry.update({'status':'failed','message':str(exc)})
        report['services'].append(entry)
    if not probe:
        for label,fn in [('prices',refresh_prices),('etf_quotes',refresh_etfs)]:
            try:report['components'][label]=fn(root,client,end)
            except APIError as exc:report['components'][label]={'status':'failed','message':str(exc)}
        prices=report['components']['prices'];etfs=report['components']['etf_quotes']
        if prices['status']=='failed':atomic(data/'price-status.json',{'status':'failed','checked_at':now().isoformat(),'web_login':False,'message':prices['message']})
        message='OpenAPI 전용 · 웹 로그인 중지. 투자자별 세부 수급·외국인 지분율·지수 편입종목은 API 미제공으로 직전 관측일 유지.'
        for scope,file in [('index','index-status.json'),('legacy','status.json')]:
            past=read(data/('index-market.json' if scope=='index' else 'market.json'))
            atomic(data/file,{'status':'api_limited','openapi_mode':True,'as_of':past.get('meta',{}).get('as_of'),'price_as_of':prices.get('as_of'),'message':message,'checked_at':now().isoformat(),'web_login':False})
        atomic(data/'etf-status.json',{'status':'api_limited','openapi_mode':True,'as_of':etfs.get('as_of'),'universe_count':etfs.get('count'),
            'checked_at':now().isoformat(),'message':'OpenAPI 전용 · ETF 시세/NAV/순자산/발행좌수만 갱신. PDF·CU 구성수량 미제공으로 종목별 패시브 압력은 N/A.'+(' API 오류: '+etfs['message'] if etfs['status']=='failed' else ''),'web_login':False})
    report['request_count']=client.calls
    good=all(s['status']=='success' for s in report['services']) if probe else all(c['status']=='success' for c in report['components'].values())
    report['status']='success' if good else 'partial_or_failed'
    atomic(data/'krx-openapi-status.json',report)
    atomic(data/'krx-auth.json',{'status':'disabled','web_login':False,'checked_at':now().isoformat(),'message':'KRX 웹 로그인 영구 중지. OpenAPI AUTH_KEY만 사용합니다.','automatic_retry':False})
    print(json.dumps(report,ensure_ascii=False));return 0 if good else 1
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--probe',action='store_true');a=p.parse_args()
    try:raise SystemExit(run(ROOT,Client(),query_end(),a.probe))
    except Exception as exc:
        atomic(ROOT/'dist/data/krx-openapi-status.json',{'status':'failed','mode':'openapi_only','web_login':False,'checked_at':now().isoformat(),'message':'OpenAPI 처리 실패: '+type(exc).__name__})
        print('OpenAPI processing failed:',type(exc).__name__);raise SystemExit(1)

