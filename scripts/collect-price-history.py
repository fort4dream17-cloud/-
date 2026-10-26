#!/usr/bin/env python3
"""Compact KRX price history, independent from shorter investor-flow observations.
330 sessions provide a year of closes plus MA60 warm-up. Never invent prices.
"""
import hashlib,json,os,pathlib,time
from datetime import timedelta
from collect import authenticated_stock,atomic,collection_end,now,num
ROOT=pathlib.Path(__file__).resolve().parents[1]
def valid_quote(close,volume):
    close=num(close);volume=num(volume)
    return [close if close is not None and close>0 else None,volume if volume is not None and volume>=0 else None]
def collect():
    import pandas as pd
    stock=authenticated_stock();cache=ROOT/'.cache/index-flow-v1';cache.mkdir(parents=True,exist_ok=True)
    def call(tag,fn,*args,**kwargs):
        path=cache/(hashlib.sha256(json.dumps([tag,args,kwargs],sort_keys=True).encode()).hexdigest()+'.json')
        if tag != 'price KOSPI' and path.exists():return pd.DataFrame(**json.loads(path.read_text()))
        data=fn(*args,**kwargs);time.sleep(1)
        if data is None or data.empty:raise ValueError('Empty KRX response: '+tag)
        payload=json.loads(data.to_json(orient='split',date_format='iso'));path.write_text(json.dumps(payload))
        return pd.DataFrame(**payload)
    end=collection_end(now());start=(now()-timedelta(days=560)).strftime('%Y%m%d')
    bench=call('price KOSPI',stock.get_index_ohlcv_by_date,start,end,'1001');bench.index=[str(d)[:10] for d in bench.index];dates=list(bench.index)[-330:]
    universe=json.loads((ROOT/'dist/data/index-universe.json').read_text());codes=[r['code'] for r in universe['records']];quotes={code:[] for code in codes}
    # Existing good snapshots make daily maintenance inexpensive after the initial backfill.
    previous=ROOT/'dist/data/index-price-history.json';old=json.loads(previous.read_text()) if previous.exists() else {}
    saved={code:{q[0]:q[1:] for q in a} for code,a in old.get('stocks',{}).items()}
    official_latest=None;api_state={'configured':bool(os.environ.get('KRX_API_KEY')),'status':'not_configured'}
    if api_state['configured']:
        import urllib.request
        try:
            output=[]
            for endpoint in ['stk_bydd_trd','ksq_bydd_trd']:
                url='https://data-dbg.krx.co.kr/svc/apis/sto/'+endpoint+'?basDd='+dates[-1].replace('-','')
                request=urllib.request.Request(url,headers={'AUTH_KEY':os.environ['KRX_API_KEY'],'Accept':'application/json'})
                with urllib.request.urlopen(request,timeout=25) as response:records=json.load(response).get('OutBlock_1',[])
                if len(records)<100:raise ValueError('KRX OpenAPI unavailable or service not approved')
                for record in records:
                    if record.get('BAS_DD','').replace('-','')!=dates[-1].replace('-',''):raise ValueError('KRX API date mismatch')
                    code=str(record.get('ISU_CD',''))
                    if len(code)!=6:continue
                    output.append({'code':code,'종가':num(str(record.get('TDD_CLSPRC','')).replace(',','')),'거래량':num(str(record.get('ACC_TRDVOL','')).replace(',',''))})
            official_latest=pd.DataFrame(output).set_index('code');api_state.update({'status':'verified','as_of':dates[-1]})
        except Exception:api_state['status']='unavailable_or_not_approved'
    for i,date in enumerate(dates):
        reuse=all(date in saved.get(code,{}) for code in codes) and not (date==dates[-1] and official_latest is not None)
        if reuse:
            for code in codes:quotes[code].append([date,*saved[code][date]])
            continue
        caps=official_latest if date==dates[-1] and official_latest is not None else call('marketcap '+date,stock.get_market_cap_by_ticker,date.replace('-',''),market='ALL')
        if '종가' not in caps.columns or '거래량' not in caps.columns:raise ValueError('KRX quote schema changed')
        for code in codes:
            q=valid_quote(caps.loc[code,'종가'],caps.loc[code,'거래량']) if code in caps.index else [None,None]
            quotes[code].append([date,*q])
        if i%20==0:print('Price history',i+1,'/',len(dates),flush=True)
    matched=sum(any(q[1] is not None for q in a) for a in quotes.values())
    if matched<len(codes)*.95:raise ValueError('Insufficient price history coverage')
    # Keep pre-IPO entries null so moving averages count actual exchange sessions.
    data={'meta':{'as_of':dates[-1],'fetched_at':now().isoformat(),'source':'KRX / pykrx daily market-wide closes','price_basis':'raw','dividend_adjusted':False,'sessions':len(dates),'quote_columns':['date','close_KRW','volume_shares'],'notes':['비수정 종가. 분할·합병 등 기업행위 시 상대수익률 왜곡 가능.','상장 전·가격 미제공 구간은 null. MA는 유효한 연속 20·60거래일이 필요합니다.']},'benchmarks':[[d,num(bench.loc[d,'종가'])] for d in dates],'stocks':quotes}
    data['meta']['krx_openapi']=api_state
    atomic(previous,data);atomic(ROOT/'dist/data/price-status.json',{'status':'success','as_of':dates[-1],'stock_count':matched,'sessions':len(dates),'updated_at':now().isoformat(),'krx_openapi':api_state});print('Price history complete',matched,len(dates),'OpenAPI',api_state['status'],flush=True)
if __name__=='__main__':
    try:collect()
    except Exception as e:
        # Provider exceptions can contain credentials; publish only the exception class.
        atomic(ROOT/'dist/data/price-status.json',{'status':'failed','checked_at':now().isoformat(),'message':'가격 수집 오류: '+type(e).__name__});print('Price collection failed:',type(e).__name__);raise SystemExit(1)
