#!/usr/bin/env python3
"""Market-wide requests for the selected index universe; never fabricate history.
All investor categories use explicit daily KRX detail observations for 60 sessions.
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
    bench=call('KOSPI',stock.get_index_ohlcv_by_date,start,end,'1001');bench.index=[str(d)[:10] for d in bench.index];dates=list(bench.index);last=dates[-1];end=last.replace('-','');recent=dates[-60:]
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
    capframes={}
    for date in recent:
        capframes[date]=call('marketcap '+date,stock.get_market_cap_by_ticker,date.replace('-',''),market='ALL')
    latest_caps=capframes[last]
    latest_names=call('pension '+last,stock.get_market_net_purchases_of_equities_by_ticker,end,end,market='ALL',investor='연기금')
    old_data=json.loads((ROOT/'dist/data/index-market.json').read_text()) if (ROOT/'dist/data/index-market.json').exists() else {'rows':[]}
    old_rows={(r['code'],r['date']):r for r in old_data['rows']}
    daily={};daily_failures=[]
    # The detailed endpoint explicitly reports zero activity. Missing responses stay missing.
    for index,code in enumerate(sorted(new)):
        try:
            frame=call('daily detail '+code,stock.get_market_trading_value_by_date,recent[0].replace('-',''),end,code,detail=True)
            if not {v for k,v in ACTORS.items() if k!='institution'}.issubset(frame.columns):raise ValueError('Daily investor detail schema mismatch')
            frame.index=[str(d)[:10] for d in frame.index];daily[code]=frame
        except Exception as e:
            daily_failures.append(code);print('Daily investor detail unavailable',code,type(e).__name__,flush=True)
        if index%25==0:print('Daily investor history',index+1,'/',len(new),flush=True)
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
            previous=old_rows.get((code,date),{})
            for key in [*ACTORS,'government']:
                label=ACTORS.get(key);df=daily.get(code)
                amount=frame_get(df,date,label) if df is not None and label else None
                row[key]=amount/1e8 if amount is not None else previous.get(key)
                if previous.get(key+'_qty') is not None:row[key+'_qty']=previous[key+'_qty']
            parts=[row[k] for k in ['financial','insurance','trust','private','bank','pension','other_institution']]
            if all(value is not None for value in parts):row['institution']=sum(parts)
            row['flow_daily_source']='KRX investor detail' if code in daily and date in daily[code].index else 'previous observation / unavailable'
            rows.append(row)
        windows[code]={'as_of':last,'actors':{}}
        for key in ACTORS:
            windows[code]['actors'][key]={}
            for n in [5,10,20,60]:
                if n not in turnovers:continue
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
    data={'schema_version':2,'meta':{'data_kind':'real','source':'KRX / pykrx 시장 전체 단위 조회; 업종은 사용자 업종분류(261025).xlsx','unit':'KRW_100M','benchmark_name':'KOSPI (1001)','price_basis':'raw','dividend_adjusted':False,'fetched_at':now().isoformat(),'as_of':last,'status':'unknown','trading_dates':recent,'reported_windows':windows,'window_dates':{str(n):{'from':dates[-n],'to':last,'sessions':n} for n in [5,10,20,60] if len(dates)>=n},'notes':notes+['투자주체별 일별 수급은 최근 60거래일이며 가격 이력은 별도 파일로 제공합니다.','5·10·20·60일 누적은 실제 기간 집계 조회이며 일별 관측치로 임의 배분하지 않습니다.','세부 투자자별 일별 응답에 명시된 0만 사용합니다. 응답 누락은 직전 검증값을 유지하거나 null로 남깁니다.','확장 종목 가격은 비수정 종가로 기업행위에 따른 수익률 왜곡 가능성이 있습니다. 기존 커버리지의 수정주가 데이터는 별도 보존합니다.','국가 분리 수급은 공급자에서 미제공.','외국인 보유비율 변화는 과거 보유량 미확보 시 미확인.'],'missing_codes':missing,'daily_flow_failed_codes':daily_failures,'daily_flow_actors':list(ACTORS)},'rows':rows}
    # The validator enforces uniqueness, calendar continuity, units and missing values.
    with tempfile.NamedTemporaryFile('w',suffix='.json',delete=False) as f:json.dump(data,f,ensure_ascii=False,allow_nan=False);temp=f.name
    try:subprocess.run(['node',str(ROOT/'scripts/validate.mjs'),temp],check=True)
    finally:os.unlink(temp)
    atomic(ROOT/'dist/data/index-market.json',data);atomic(ROOT/'dist/data/index-universe.json',universe);atomic(ROOT/'config/index-membership-history.json',history)
    atomic(ROOT/'dist/data/index-status.json',{'status':'partial' if daily_failures else 'success','as_of':last,'last_success_at':now().isoformat(),'stock_count':len(windows),'missing_codes':missing,'unclassified':universe['unclassified'],'daily_flow_failed_codes':daily_failures,'daily_flow_sessions':len(recent)})
    print('Index collection complete',len(windows),'stocks',len(rows),'rows',flush=True)
if __name__=='__main__':
    try:collect()
    except Exception as e:
        msg=str(e) if isinstance(e,ValueError) else type(e).__name__
        for key in ['KRX_ID','KRX_PW','FLOW_SECTOR_MAP_URL','FLOW_SECTOR_MAP_TOKEN']:msg=msg.replace(os.environ.get(key) or '\0','[redacted]')
        atomic(ROOT/'dist/data/index-status.json',{'status':'failed','last_attempt_at':now().isoformat(),'message':msg[:400]})
        print('Index collection failed:',msg[:400],flush=True);raise SystemExit(1)
