#!/usr/bin/env python3
"""Normalize approved files and HTTPS feeds. KRX data is collected separately through OpenAPI."""
import argparse, csv, json, math, os, pathlib, subprocess, sys, tempfile, urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
ROOT=pathlib.Path(__file__).resolve().parents[1]
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
def run(args):
    out=pathlib.Path(args.output);status_path=out.parent/'status.json';logs=pathlib.Path(args.log_dir) if args.log_dir else ROOT/'logs';logs.mkdir(parents=True,exist_ok=True)
    prev=json.loads(status_path.read_text()) if status_path.exists() else {}
    stamp=now().isoformat()
    try:
        if args.provider=='file':d=file_dataset(args.input,args.meta,args.calendar)
        elif args.provider=='https':d=remote_dataset()
        else:raise ValueError('파일 또는 승인된 HTTPS 입력만 지원합니다.')
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
        atomic(out,d);state={'status':result,'last_attempt_at':stamp,'last_success_at':stamp,'as_of':latest,'message':message}
        atomic(status_path,state)
    except Exception as e:
        # Sanitize: never include provider tokens, URLs, credentials or response bodies in published logs.
        safe=str(e) if isinstance(e,ValueError) else '수집 연결/인증/공급자 오류 ('+type(e).__name__+')'
        for secret_key in ['FLOW_DATASET_TOKEN','FLOW_DATASET_URL']:
            secret=os.environ.get(secret_key)
            if secret:safe=safe.replace(secret,'[redacted]')
        state={'status':'failed','last_attempt_at':stamp,'last_success_at':prev.get('last_success_at'),'as_of':prev.get('as_of'),'message':safe[:500]}
        atomic(status_path,state)
        with (logs/'collection.jsonl').open('a') as f:f.write(json.dumps(state,ensure_ascii=False)+'\n')
        print(state['message'],file=sys.stderr);return 1
    with (logs/'collection.jsonl').open('a') as f:f.write(json.dumps(state,ensure_ascii=False)+'\n')
    print(json.dumps(state,ensure_ascii=False));return 0
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--provider',choices=['file','https'],default='file');p.add_argument('--input');p.add_argument('--meta');p.add_argument('--calendar');p.add_argument('--log-dir');p.add_argument('--start');p.add_argument('--end');p.add_argument('--output',default=str(ROOT/'dist/data/market.json'));a=p.parse_args()
    if a.provider=='file' and not a.input:p.error('--input required for file provider')
    sys.exit(run(a))



