#!/usr/bin/env python3
"""Market-wide requests for the selected index universe; never fabricate history.
Daily pension/foreign history starts with 26 observed sessions and is cached.
Other actor windows use provider period aggregates, not synthetic daily allocations.
"""
import hashlib,importlib.util,json,os,pathlib,re,time,subprocess,tempfile
from datetime import timedelta
from collect import authenticated_stock,atomic,collection_end,now,num
ROOT=pathlib.Path(__file__).resolve().parents[1]
ACTORS={'personal':'개인','foreign':'외국인','institution':'기관합계','financial':'금융투자','insurance':'보험','trust':'투신','other_institution':'기타금융','bank':'은행','pension':'연기금','private':'사모','corporation':'기타법인','other_foreign':'기타외국인'}
def frame_get(df,code,col):
    return num(df.loc[code,col]) if code in df.index and col in df.columns else None
def collect():
    import pandas as pd
    stock=authenticated_stock();cache=ROOT/'.cache/index-flow-v1';cache.mkdir(parents=True,exist_ok=True)
    def call(tag,fn,*args,**kwargs):
        ident=json.dumps([tag,args,kwargs],sort_keys=True);path=cache/(hashlib.sha256(ident.encode()).hexdigest()+'.json')
        if path.exists():return pd.DataFrame(**json.loads(path.read_text()))
        data=fn(*args,**kwargs);time.sleep(1)
        if data is None or data.empty:raise ValueError('Empty provider response at '+tag)
        payload=json.loads(data.to_json(orient='split',date_format='iso'))
        path.write_text(json.dumps(payload));print(tag,'rows',len(data),flush=True)
        return pd.DataFrame(**payload)
    end=collection_end(now());start=(now()-timedelta(days=400)).strftime('%Y%m%d')
    bench=call('KOSPI',stock.get_index_ohlcv_by_date,start,end,'1001');bench.index=[str(d)[:10] for d in bench.index];dates=list(bench.index);last=dates[-1];end=last.replace('-','');recent=dates[-26:]
    universe=json.loads((ROOT/'dist/data/index-universe.json').read_text());lookup=json.loads((ROOT/'config/sector-lookup.json').read_text())['sectors'];old={x['code']:x for x in universe['records']};notes=[];new={};verified=True;classification_source='사용자 업종분류(261025).xlsx';classification_as_of='2026-10-25'
    # Optional permitted supplier feed. Do not guess a sector from a company name.
    feed=os.environ.get('FLOW_SECTOR_MAP_URL','')
    if feed:
        import urllib.request
        if not feed.startswith('https://'):raise ValueError('Sector feed must use HTTPS')
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        headers={'Accept':'application/json'}
        if os.environ.get('FLOW_SECTOR_MAP_TOKEN'):headers['Authorization']='Bearer '+os.environ['FLOW_SECTOR_MAP_TOKEN']
        with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(feed,headers=headers),timeout=25) as response:payload=json.load(response)
        if not isinstance(payload.get('sectors'),dict) or not payload.get('source') or not payload.get('as_of'):raise ValueError('Sector feed needs source, as_of, sectors')
        if any(not re.fullmatch('[0-9A-Z]{6}',code) or not isinstance(sector,str) or not sector.strip() for code,sector in payload['sectors'].items()):raise ValueError('Sector feed contains invalid records')
        lookup.update(payload['sectors']);classification_source=payload['source'];classification_as_of=payload['as_of']
    for label,index_id,market,minimum,maximum in [('KOSPI200','1028','KOSPI',180,220),('KOSDAQ150','2203','KOSDAQ',130,170)]:
        try:
            index_name=stock.get_index_ticker_name(index_id).replace(' ','')
            if not any(k in index_name for k in (['코스피200','KOSPI200'] if label=='KOSPI200' else ['코스닥150','KOSDAQ150'])):raise ValueError('Index identity mismatch')
            codes=stock.get_index_portfolio_deposit_file(index_id,end);time.sleep(1)
            if not minimum<=len(set(codes))<=maximum or any(not re.fullmatch('[0-9A-Z]{6}',str(c)) for c in codes):raise ValueError('Invalid constituent response')
            for code in codes:new[code]={**old.get(code,{}),'code':code,'market':market,'indices':[label],'sector':lookup.get(code,'미분류'),'classification_source':classification_source if code in lookup else '신규 편입: 분류 원본 미매칭','classification_as_of':classification_as_of if code in lookup else None}
        except Exception:
            verified=False;notes.append(label+' 공식 구성종목 조회 실패: 기존 원본 목록 보존')
            for code,r in old.items():
                if label in r['indices']:new[code]=r
    # Preserve membership event history with the actual provider observation date.
    added=sorted(set(new)-set(old));removed=sorted(set(old)-set(new));changes=ROOT/'config/index-membership-history.json';history=json.loads(changes.read_text()) if changes.exists() else []
    if added or removed:history.append({'observed_at':now().isoformat(),'effective_snapshot':last,'added':added,'removed':removed,'source':'KRX index portfolio; confirmed snapshot, not an advance announcement'})
    capframes={};flows={k:{} for k in ['foreign','pension']}
    for date in recent:
        d=date.replace('-','');capframes[date]=call('marketcap '+date,stock.get_market_cap_by_ticker,d,market='ALL')
        for key in flows:flows[key][date]=call(key+' '+date,stock.get_market_net_purchases_of_equities_by_ticker,d,d,market='ALL',investor=ACTORS[key])
    latest_caps=capframes[last];latest_names=flows['pension'][last];latest_foreign=flows['foreign'][last]
    ownership={}
    for market in ['KOSPI','KOSDAQ']:
        try:ownership[market]=call('ownership '+market+' '+last,stock.get_exhaustion_rates_of_foreign_investment_by_ticker,end,market=market)
        except Exception:notes.append(market+' 외국인 지분율 미제공')
    aggregates={};turnovers={}
    for n in [1,5,10,20,60]:
        if len(dates)<n:continue
        begin=dates[-n].replace('-','')
        turnovers[n]=call('turnover '+str(n)+' '+last,stock.get_market_net_purchases_of_equities_by_ticker,begin,end,market='ALL',investor='전체')
        aggregates[n]={}
        for key,label in ACTORS.items():
            if key in flows and n in [1,5,10,20]:continue
            aggregates[n][key]=call(key+' period '+str(n)+' '+last,stock.get_market_net_purchases_of_equities_by_ticker,begin,end,market='ALL',investor=label)
    rows=[];windows={};missing=[]
    for code,symbol in sorted(new.items()):
        latest_close=frame_get(latest_caps,code,'종가');cap=frame_get(latest_caps,code,'시가총액')
        if latest_close is None or latest_close<=0 or cap is None or cap<=0:missing.append(code);continue
        if not symbol.get('name'):
            symbol['name']=str(latest_names.loc[code,'종목명']) if code in latest_names.index else code
        own=ownership.get(symbol['market']);held=frame_get(own,code,'보유수량') if own is not None else None;listed=frame_get(own,code,'상장주식수') if own is not None else None
        for date in recent:
            caps=capframes[date];close=frame_get(caps,code,'종가');marketcap=frame_get(caps,code,'시가총액');turn=frame_get(caps,code,'거래대금')
            if close is None or close<=0 or marketcap is None or marketcap<=0 or turn is None:continue
            row={'code':code,'name':symbol['name'],'sector':symbol['sector'],'market':symbol['market'],'date':date,'close':close,'adjusted_close':None,'marketcap':marketcap/1e8,'turnover':turn/1e8,'volume':frame_get(caps,code,'거래량'),'benchmark':num(bench.loc[date,'종가']),'foreign_ownership':held/listed*100 if date==last and held is not None and listed else None,'foreign_ownership_date':last if date==last and held is not None and listed else None}
            for key in [*ACTORS,'government']:
                df=flows[key][date] if key in flows else aggregates[1].get(key) if date==last else None
                amount=frame_get(df,code,'순매수거래대금') if df is not None else None;qty=frame_get(df,code,'순매수거래량') if df is not None else None
                row[key]=amount/1e8 if amount is not None else None;row[key+'_qty']=qty
            rows.append(row)
        windows[code]={'as_of':last,'actors':{}}
        for key in ACTORS:
            windows[code]['actors'][key]={}
            for n in [5,10,20,60]:
                if n not in turnovers:continue
                if key in flows and n<=20:
                    vals=[frame_get(flows[key][d],code,'순매수거래대금') for d in recent[-n:]];amount=sum(vals)/1e8 if all(v is not None for v in vals) else None
                else:
                    val=frame_get(aggregates[n][key],code,'순매수거래대금');amount=val/1e8 if val is not None else None
                turn=frame_get(turnovers[n],code,'매수거래대금');turn=turn/1e8 if turn is not None else None
                windows[code]['actors'][key][str(n)]={'amount':amount,'cap':amount/(cap/1e8)*100 if amount is not None else None,'turnover':amount/turn*100 if amount is not None and turn and turn>0 else None}
    # Exclude a security with an internal gap; keep an explicit missing-code list.
    grouped={}
    for row in rows:grouped.setdefault(row['code'],[]).append(row)
    bad={code for code,a in grouped.items() if [r['date'] for r in a] != [d for d in recent if a[0]['date']<=d<=last]}
    if bad:
        rows=[r for r in rows if r['code'] not in bad];missing.extend(sorted(bad))
        for code in bad:windows.pop(code,None)
    universe.update({'as_of':last,'source':'KRX 공식 지수 구성종목 조회 / 사용자 제공 업종분류 매핑' if verified else universe['source'],'records':list(new.values()),'counts':{k:sum(k in r['indices'] for r in new.values()) for k in ['KOSPI200','KOSDAQ150']},'unclassified':[r['code'] for r in new.values() if r['sector']=='미분류'],'notes':notes,'membership_verified':verified})
    data={'schema_version':2,'meta':{'data_kind':'real','source':'KRX / pykrx 시장 전체 단위 조회; 업종은 사용자 업종분류(261025).xlsx','unit':'KRW_100M','benchmark_name':'KOSPI (1001)','price_basis':'raw','dividend_adjusted':False,'fetched_at':now().isoformat(),'as_of':last,'status':'unknown','trading_dates':recent,'reported_windows':windows,'window_dates':{str(n):{'from':dates[-n],'to':last,'sessions':n} for n in [5,10,20,60] if len(dates)>=n},'notes':notes+['초기 확장 이력은 최근 26거래일입니다. 3M/6M/1Y/YTD 선택 시 확보 구간만 표시합니다.','5·10·20·60일 누적은 실제 기간 집계 조회이며 일별 관측치로 임의 배분하지 않습니다.','연기금·외국인 외 주체의 일별 이력이 없는 날은 null입니다. 매수 일수·연속 일수는 일별 이력이 있을 때만 계산합니다.','확장 종목 가격은 비수정 종가로 기업행위에 따른 수익률 왜곡 가능성이 있습니다. 기존 커버리지의 수정주가 데이터는 별도 보존합니다.','국가 분리 수급은 공급자에서 미제공.','외국인 보유비율 변화는 과거 보유량 미확보 시 미확인.'],'missing_codes':missing},'rows':rows}
    # The validator enforces uniqueness, calendar continuity, units and missing values.
    with tempfile.NamedTemporaryFile('w',suffix='.json',delete=False) as f:json.dump(data,f,ensure_ascii=False,allow_nan=False);temp=f.name
    try:subprocess.run(['node',str(ROOT/'scripts/validate.mjs'),temp],check=True)
    finally:os.unlink(temp)
    atomic(ROOT/'dist/data/index-market.json',data);atomic(ROOT/'dist/data/index-universe.json',universe);atomic(ROOT/'config/index-membership-history.json',history)
    atomic(ROOT/'dist/data/index-status.json',{'status':'success','as_of':last,'last_success_at':now().isoformat(),'stock_count':len(windows),'missing_codes':missing,'unclassified':universe['unclassified']})
    print('Index collection complete',len(windows),'stocks',len(rows),'rows',flush=True)
if __name__=='__main__':
    try:collect()
    except Exception as e:
        msg=str(e) if isinstance(e,ValueError) else type(e).__name__
        for key in ['KRX_ID','KRX_PW','FLOW_SECTOR_MAP_URL','FLOW_SECTOR_MAP_TOKEN']:msg=msg.replace(os.environ.get(key) or '\0','[redacted]')
        atomic(ROOT/'dist/data/index-status.json',{'status':'failed','last_attempt_at':now().isoformat(),'message':msg[:400]})
        print('Index collection failed:',msg[:400],flush=True);raise SystemExit(1)
