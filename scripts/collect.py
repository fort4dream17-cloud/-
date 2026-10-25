#!/usr/bin/env python3
"""Normalize approved files or explicitly authorized pykrx data. No synthetic fallback."""
import argparse, contextlib, csv, io, json, math, os, pathlib, subprocess, sys, tempfile, time, urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
ROOT=pathlib.Path(__file__).resolve().parents[1]
ACTORS={'foreign':'외국인','pension':'연기금','trust':'투신','private':'사모','financial':'금융투자','insurance':'보험','bank':'은행','other_institution':'기타금융'}
def now(): return datetime.now(ZoneInfo('Asia/Seoul'))
def collection_end(current, explicit=None):
    # This is a query boundary, not an exchange holiday calendar.
    # The returned provider observations determine the actual as_of date.
    if explicit:
        chosen=datetime.strptime(explicit, '%Y%m%d').date()
        if chosen>current.date() or (chosen==current.date() and current.hour<18):
            raise ValueError('미래일 또는 장 마감 전 당일 수집은 허용하지 않습니다.')
        return explicit
    chosen=current.date()
    if current.hour<18:chosen-=timedelta(days=1)
    while chosen.weekday()>=5:chosen-=timedelta(days=1)
    return chosen.strftime('%Y%m%d')
def atomic(path,value):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',dir=path.parent,delete=False,encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,allow_nan=False);name=f.name
    os.replace(name,path)
def num(v):
    try:
        f=float(v)
        return f if math.isfinite(f) else None
    except (ValueError,TypeError): return None
def read_file(path):
    p=pathlib.Path(path)
    if p.suffix.lower()=='.json':return json.loads(p.read_text(encoding='utf-8-sig'))
    raise ValueError('CSV는 --meta와 --calendar 옵션으로 명시적인 메타·거래일을 함께 제공하세요.')
def file_dataset(path,meta=None,calendar=None):
    p=pathlib.Path(path)
    if p.suffix.lower()=='.json':return read_file(p)
    if not meta or not calendar:raise ValueError('CSV 입력에는 --meta meta.json --calendar trading_dates.json이 필요합니다.')
    strings={'date','code','name','sector','foreign_ownership_date','available_at'}
    with p.open(encoding='utf-8-sig',newline='') as f:
        rd=csv.DictReader(f)
        if not rd.fieldnames or len(set(rd.fieldnames))!=len(rd.fieldnames):raise ValueError('CSV 헤더 중복/누락')
        rows=[]
        for row in rd:
            if None in row:raise ValueError('CSV 열 개수 오류')
            rows.append({k:(v.strip() if k in strings else None if v.strip()=='' else float(v)) for k,v in row.items()})
    m=read_file(meta);m['trading_dates']=read_file(calendar)
    return {'schema_version':2,'meta':m,'rows':rows}
def remote_dataset():
    url=os.environ.get('FLOW_DATASET_URL','')
    if not url.startswith('https://'):raise ValueError('FLOW_DATASET_URL에 이용권한이 있는 HTTPS 정규화 JSON 주소를 설정하세요.')
    headers={'Accept':'application/json'}
    if os.environ.get('FLOW_DATASET_TOKEN'):headers['Authorization']='Bearer '+os.environ['FLOW_DATASET_TOKEN']
    # No redirect: never forward a provider credential to another origin.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.build_opener(NoRedirect).open(req,timeout=30) as r:
        payload=r.read(30*1024*1024+1)
    if len(payload)>30*1024*1024:raise ValueError('JSON이 30MB를 초과했습니다.')
    return json.loads(payload)
def pykrx_dataset(start,end):
    if not os.environ.get('KRX_ID') or not os.environ.get('KRX_PW'):raise ValueError('KRX_ID/KRX_PW가 없어 세부 투자자 수급 수집을 실행하지 않았습니다.')
    if os.environ.get('FLOW_DATA_USE_CONFIRMED')!='true':raise ValueError('공급자 이용조건 확인 후 FLOW_DATA_USE_CONFIRMED=true로 설정하세요.')
    import requests
    old=requests.sessions.Session.request
    auth_codes=[]
    def bounded(self,*args,**kwargs):
        kwargs.setdefault('timeout',25)
        response=old(self,*args,**kwargs)
        # Inspect only a short provider error code, never publish response bodies.
        if '/MDCCOMS001D1.cmd' in str(response.url):
            try:
                code=response.json().get('_error_code','')
                if isinstance(code,str) and len(code)<=12 and code.isalnum():auth_codes.append(code)
            except (ValueError,AttributeError):pass
        return response
    requests.sessions.Session.request=bounded
    # pykrx prints the account ID at import; suppress its authentication output.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from pykrx import stock
        from pykrx.website.comm import webio
    if webio._session is None or not webio._session.is_authenticated:
        code=auth_codes[-1] if auth_codes else 'UNKNOWN'
        if code=='CD010':reason='KRX 사이트에서 비밀번호 변경 필요'
        else:reason='KRX 사이트 직접 로그인, 계정 상태 및 실행 환경 접근 허용 여부 확인 필요'
        raise ValueError('KRX 인증 실패 ['+code+']: '+reason+'. 데이터 조회를 중단했습니다.')
    def call(fn,*args,**kwargs):
        result=fn(*args,**kwargs);time.sleep(1)
        if result is None or result.empty:raise ValueError('공급자 응답이 비어 있습니다. 인증/호출제한/제공시각을 확인하세요.')
        return result
    def dated(df):
        out=df.copy();out.index=out.index.strftime('%Y-%m-%d');return out
    bench=dated(call(stock.get_index_ohlcv_by_date,start,end,'1001'))
    coverage=json.loads((ROOT/'config/coverage.json').read_text())
    rows=[];notes=[]
    for symbol in coverage:
        code=symbol['code'];adj=dated(call(stock.get_market_ohlcv_by_date,start,end,code,adjusted=True))
        raw=dated(call(stock.get_market_ohlcv_by_date,start,end,code,adjusted=False))
        flows=dated(call(stock.get_market_trading_value_by_date,start,end,code,detail=True))
        caps=dated(call(stock.get_market_cap_by_date,start,end,code))
        if any(k not in flows.columns for k in ACTORS.values()):raise ValueError(code+' 세부 투자자별 열 미제공. 기관합계로 대체하지 않습니다.')
        try:qty=dated(call(stock.get_market_trading_volume_by_date,start,end,code,detail=True))
        except Exception:qty=None;notes.append(code+' 투자자별 수량 수집 실패 — null')
        try:own=dated(call(stock.get_exhaustion_rates_of_foreign_investment_by_date,start,end,code))
        except Exception:own=None;notes.append(code+' 외국인 보유율 수집 실패 — null')
        dates=[d for d in bench.index if d>=adj.index[0]]
        for d in dates:
            for frame,label in [(adj,'수정주가'),(raw,'주가'),(flows,'투자자수급'),(caps,'시총')]:
                if d not in frame.index:raise ValueError(code+' '+d+' '+label+' 누락 — 부분 데이터 게시 중단')
            # A zero foreign holding is never inferred from missing provider observations.
            ownership=None
            if own is not None and d in own.index and num(own.loc[d].get('상장주식수')) and num(own.loc[d].get('보유수량')) is not None:
                ownership=float(own.loc[d,'보유수량'])/float(own.loc[d,'상장주식수'])*100
            r={**symbol,'date':d,'close':num(raw.loc[d,'종가']),'adjusted_close':num(adj.loc[d,'종가']),'volume':num(raw.loc[d,'거래량']),'turnover':num(caps.loc[d,'거래대금'])/1e8,'marketcap':num(caps.loc[d,'시가총액'])/1e8,'benchmark':num(bench.loc[d,'종가']),'sector_benchmark':None,'foreign_ownership':ownership,'foreign_ownership_date':d if ownership is not None else None,'available_at':now().isoformat()}
            for key,col in ACTORS.items():
                r[key]=num(flows.loc[d,col])/1e8
                r[key+'_qty']=num(qty.loc[d,col]) if qty is not None and d in qty.index and col in qty.columns else None
            rows.append(r)
    return {'schema_version':2,'meta':{'data_kind':'real','source':'pykrx 1.2.9 / KRX 수급·비수정 종가·시총 / Naver 수정주가','unit':'KRW_100M','benchmark_name':'KOSPI (1001)','price_basis':'adjusted','adjustment_as_of':str(bench.index[-1]),'dividend_adjusted':None,'fetched_at':now().isoformat(),'as_of':str(bench.index[-1]),'status':'unknown','trading_dates':list(bench.index),'foreign_ownership_basis':'공급자 조회일 장개시 기준; 전일 확정치 기반, 주가 기준시각과 다름','notes':notes+['수정주가의 배당 반영 여부는 확인되지 않았습니다.','잠정/확정 여부는 공급자 메타 미제공으로 미확인. 백테스트용 시점보존 데이터가 아닙니다.']},'rows':rows}
def run(args):
    out=pathlib.Path(args.output);status_path=out.parent/'status.json';logs=pathlib.Path(args.log_dir) if args.log_dir else ROOT/'logs';logs.mkdir(parents=True,exist_ok=True)
    prev=json.loads(status_path.read_text()) if status_path.exists() else {}
    stamp=now().isoformat()
    try:
        if args.provider=='file':d=file_dataset(args.input,args.meta,args.calendar)
        elif args.provider=='https':d=remote_dataset()
        else:
            current=now()
            end=collection_end(current,args.end);start=args.start or (current-timedelta(days=400)).strftime('%Y%m%d')
            d=pykrx_dataset(start,end)
        if d['meta'].get('data_kind')!='real':raise ValueError('운영 수집에 예시/빈 데이터는 허용하지 않습니다.')
        if not d.get('rows'):raise ValueError('관측 데이터가 없습니다.')
        with tempfile.NamedTemporaryFile('w',suffix='.json',delete=False,encoding='utf-8') as f:
            json.dump(d,f,ensure_ascii=False,allow_nan=False);tmp=f.name
        try:subprocess.run(['node',str(ROOT/'scripts/validate.mjs'),tmp],check=True,capture_output=True,text=True)
        except subprocess.CalledProcessError as e:raise ValueError('데이터 검증 실패: '+e.stderr.splitlines()[0:3].__str__()) from e
        finally:os.unlink(tmp)
        latest=d['meta']['as_of']
        existing=json.loads(out.read_text()) if out.exists() else None
        if existing and existing['meta'].get('data_kind')=='real' and latest<existing['meta']['as_of']:raise ValueError('기존보다 오래된 데이터로 덮어쓰기를 거부했습니다.')
        # Never declare a stale provider response to be today's observation.
        if latest>now().date().isoformat():raise ValueError('미래 기준일 데이터 거부')
        result='success';message='검증된 데이터 갱신'
        if existing and latest==existing['meta'].get('as_of'):
            result='no_new_session';message='새 기준일 없음. 휴장 또는 공급 지연 가능 — 기준일 유지. 값 정정은 재검증 후 반영.'
        if args.provider=='pykrx' and latest<now().date().isoformat():
            result='delayed_or_closed';message='최신 응답이 이전 거래일입니다. 휴장/제공 지연 여부를 확정하지 않았습니다.'
        atomic(out,d);state={'status':result,'last_attempt_at':stamp,'last_success_at':stamp,'as_of':latest,'message':message}
        atomic(status_path,state)
    except Exception as e:
        # Sanitize: never include provider tokens, URLs, credentials or response bodies in published logs.
        safe=str(e) if isinstance(e,ValueError) else '수집 연결/인증/공급자 오류 ('+type(e).__name__+')'
        for secret_key in ['KRX_ID','KRX_PW','FLOW_DATASET_TOKEN','FLOW_DATASET_URL']:
            secret=os.environ.get(secret_key)
            if secret:safe=safe.replace(secret,'[redacted]')
        state={'status':'failed','last_attempt_at':stamp,'last_success_at':prev.get('last_success_at'),'as_of':prev.get('as_of'),'message':safe[:500]}
        atomic(status_path,state)
        with (logs/'collection.jsonl').open('a') as f:f.write(json.dumps(state,ensure_ascii=False)+'\n')
        print(state['message'],file=sys.stderr);return 1
    with (logs/'collection.jsonl').open('a') as f:f.write(json.dumps(state,ensure_ascii=False)+'\n')
    print(json.dumps(state,ensure_ascii=False));return 0
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--provider',choices=['file','https','pykrx'],default='file');p.add_argument('--input');p.add_argument('--meta');p.add_argument('--calendar');p.add_argument('--log-dir');p.add_argument('--start');p.add_argument('--end');p.add_argument('--output',default=str(ROOT/'dist/data/market.json'));a=p.parse_args()
    if a.provider=='file' and not a.input:p.error('--input required for file provider')
    sys.exit(run(a))
