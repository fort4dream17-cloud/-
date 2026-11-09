"""Kiwoom REST read-only flow collection. No web login or order endpoints."""
import json,os,pathlib,time,subprocess,sys,tempfile,re,math
from datetime import datetime
from collect import atomic,now,collection_end
from krx_openapi import Client as KRXClient, code as krx_code
ROOT=pathlib.Path(__file__).resolve().parents[1]
FIELDS=dict(personal='ind_invsr',foreign='frgnr_invsr',institution='orgn',financial='fnnc_invt',insurance='insrnc',trust='invtrt',other_institution='etc_fnnc',bank='bank',pension='penfnd_etc',private='samo_fund',government='natn',corporation='etc_corp',other_foreign='natfor')
def number(x):
    if x is None or str(x).strip()=='':return None
    return float(str(x).replace(',',''))
class APIError(Exception):pass
def http_failure(status,raw,headers,secrets=()):
    # Publish diagnostics only; never persist a response body or credential echo.
    text=raw.decode('utf-8',errors='replace')
    def clean(value):
        value=str(value)
        for secret in secrets:
            if secret:value=value.replace(secret,'[redacted]')
        return value[:250]
    detail={'http_status':status,'content_type':str(headers.get('Content-Type','')).split(';')[0],'body_bytes':len(raw)}
    try:
        obj=json.loads(text)
        if isinstance(obj,dict):
            for k in ['return_code','return_msg','error','error_description','message','error_code','rsp_cd','rsp_msg']:
                if k in obj and isinstance(obj[k],(str,int,float)):detail[k]=clean(obj[k])
            detail['response_keys']=[clean(k) for k in obj if not any(x in k.lower() for x in ['token','key','secret','account'])][:15]
    except ValueError:
        title=re.search(r'<title[^>]*>([^<]{1,160})</title>',text,re.I)
        if title:detail['html_title']=clean(title.group(1))
        markers=['Request Rejected','Access Denied','Bad Request','Forbidden','not allowed','IP address']
        detail['markers']=[m for m in markers if m.lower() in text.lower()]
    return 'HTTP response '+json.dumps(detail,ensure_ascii=False)

class Client:
    def __init__(self):
        self.key=os.environ.get('KIWOOM_APP_KEY','').strip();self.secret=os.environ.get('KIWOOM_SECRET_KEY','').strip();self.token=None;self.calls=0;self.cache_hits=0
    def post(self,path,body,headers=None):
        if path not in ('/oauth2/token','/api/dostk/stkinfo'):raise APIError('endpoint not allowed')
        if self.calls>=2500:raise APIError('request budget exceeded')
        self.calls+=1;time.sleep(.3)
        # curl works with the provider gateway; urllib was rejected with HTML 400.
        # Credentials and bearer headers travel over stdin, never process arguments/logs.
        config='url = '+json.dumps('https://api.kiwoom.com'+path)+'\nrequest = "POST"\n'
        for k,v in {'Content-Type':'application/json;charset=UTF-8',**(headers or {})}.items():
            config+='header = '+json.dumps(k+': '+v)+'\n'
        config+='data = '+json.dumps(json.dumps(body,ensure_ascii=True))+'\n'
        marker=b'|KIWOOM_HTTP_STATUS|'
        with tempfile.TemporaryDirectory() as tmp:
            headerfile=pathlib.Path(tmp)/'headers'
            try:
                result=subprocess.run(['curl','--config','-','--silent','--show-error','--max-time','30','--max-filesize','10485760','--proto','=https','--dump-header',str(headerfile),'--write-out',marker.decode()+'%{http_code}'],input=config.encode(),capture_output=True,timeout=35)
            except (OSError,subprocess.TimeoutExpired):raise APIError('curl unavailable or request timed out') from None
            if result.returncode:raise APIError('curl network failure '+str(result.returncode))
            try:raw,status=result.stdout.rsplit(marker,1);status=int(status)
            except ValueError:raise APIError('invalid transport status') from None
            h={}
            for line in headerfile.read_text(errors='replace').splitlines():
                if line.startswith('HTTP/'):h={}
                elif ':' in line:
                    key,value=line.split(':',1);h[key.lower()]=value.strip()
        if status>=300:
            raise APIError(http_failure(status,raw,{'Content-Type':h.get('content-type','')},[self.key,self.secret,self.token]))
        try:payload=json.loads(raw)
        except ValueError:raise APIError('non-JSON provider response') from None
        if not isinstance(payload,dict):raise APIError('invalid provider response shape')
        if str(payload.get('return_code',0))!='0':
            raise APIError(http_failure(status,raw,{'Content-Type':h.get('content-type','')},[self.key,self.secret,self.token]))
        return payload,h
    def authenticate(self):
        if not self.key or not self.secret:raise APIError('KIWOOM_APP_KEY / KIWOOM_SECRET_KEY missing')
        p,_=self.post('/oauth2/token',{'grant_type':'client_credentials','appkey':self.key,'secretkey':self.secret})
        self.token=p.get('token')
        if not self.token:raise APIError('access token missing')
    def flows(self,code,end,start):
        folder=os.environ.get('KIWOOM_FLOW_CACHE')
        path=pathlib.Path(folder)/(code+'-'+end+'.json') if folder else None
        if path and path.exists():
            try:
                cached=read(path)
                age=(now()-datetime.fromisoformat(cached['fetched_at'])).total_seconds()
                if cached.get('version')==1 and 0<=age<1800 and cached.get('start','9999')<=start:
                    self.cache_hits+=1;return cached['flows']
            except (ValueError,KeyError,OSError):pass
        result=self._flows(code,end,start)
        if path:atomic(path,{'version':1,'fetched_at':now().isoformat(),'start':start,'flows':result})
        return result
    def _flows(self,code,end,start):
        headers={'api-id':'ka10059','authorization':'Bearer '+self.token};out={};seen=set()
        for page in range(20):
            p,h=self.post('/api/dostk/stkinfo',{'dt':end,'stk_cd':code,'amt_qty_tp':'1','trde_tp':'0','unit_tp':'1'},headers)
            rows=p.get('stk_invsr_orgn')
            if not isinstance(rows,list) or not rows:break
            dates=[]
            for r in rows:
                d=datetime.strptime(r['dt'],'%Y%m%d').date().isoformat();dates.append(d)
                if d>datetime.strptime(end,'%Y%m%d').date().isoformat():raise APIError('future observation')
                if d in out:raise APIError('duplicate observation')
                out[d]={k:(number(r.get(v))/100 if number(r.get(v)) is not None else None) for k,v in FIELDS.items()}
            if min(dates)<=start or h.get('cont-yn')!='Y':return out
            key=h.get('next-key')
            if not key or key in seen:raise APIError('invalid pagination')
            seen.add(key);headers.update({'cont-yn':'Y','next-key':key})
        if out and min(out)>start and h.get('cont-yn')=='Y':raise APIError('history pagination incomplete')
        return out

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def validate(root,result,filename):
    with tempfile.TemporaryDirectory() as tmp:
        candidate=pathlib.Path(tmp)/'dataset.json';candidate.write_text(json.dumps(result),encoding='utf-8')
        check=subprocess.run(['node',str(root/'scripts/validate.mjs'),str(candidate)],capture_output=True,text=True,encoding='utf-8',errors='replace')
    if check.returncode:
        lines=check.stderr.splitlines()
        detail=next((l for l in lines if l.startswith(('Error:','TypeError:','RangeError:'))),'Node validator exited '+str(check.returncode))
        raise APIError(filename+': '+detail[:300])

def run(root=ROOT):
    data=root/'dist/data';state={'checked_at':now().isoformat(),'source':'Kiwoom REST ka10059','web_login':False,'market':'KRX','configured':bool(os.environ.get('KIWOOM_APP_KEY') and os.environ.get('KIWOOM_SECRET_KEY'))};client=Client()
    try:
        gate=data/'kiwoom-connection.json'
        if gate.exists() and read(gate).get('status')=='failed':
            raise APIError('Connection verification failed; automatic token retries paused. Run Verify Kiwoom REST connection after correcting the configuration.')
        client.authenticate();state['authentication']='success'
        history=read(data/'index-price-history.json');target=history['meta']['as_of'];end=target.replace('-','')
        benchmark=dict(history['benchmarks']);krx=KRXClient();caps={}
        prepared=[];count=0;overlap=0
        for filename in ['index-market.json','market.json']:
            old=read(data/filename);bycode={}
            state['scope']=filename
            state['input_meta']={k:old['meta'].get(k) for k in ['unit','price_basis','data_kind','as_of']}
            validate(root,old,filename+' (existing)')

            for r in old['rows']:bycode.setdefault(r['code'],[]).append(r)
            merged=[]
            for code,rows in sorted(bycode.items()):
                rows.sort(key=lambda r:r['date']);last=rows[-1]['date'];start=rows[max(0,len(rows)-25)]['date']
                flows=client.flows(code,end,start)
                if target not in flows:raise APIError('latest flow missing for '+code)
                prices={q[0]:q[1:] for q in history['stocks'].get(code,[])}
                for r in rows:
                    if r['date'] in flows:
                        # Explicit unit consistency check against prior KRX values, allowing rounded million-KRW observations.
                        for k in ['foreign','pension']:
                            a=r.get(k);b=flows[r['date']].get(k)
                            if a is not None and b is not None:
                                overlap+=1
                                if abs(a-b)>max(.05,abs(a)*.05):raise APIError('overlap mismatch '+code+' '+r['date']+' '+k)
                        r={**r,**flows[r['date']],'flow_source':'Kiwoom REST ka10059'}
                    merged.append(r)
                for d in sorted(benchmark):
                    if not last<d<=target:continue
                    f=flows.get(d);q=prices.get(d)
                    if f is None or not q or q[0] is None:raise APIError('missing date/price '+code+' '+d)
                    if d not in caps:
                        allrows=krx.get('stocks',d.replace('-',''))+krx.get('kosdaq',d.replace('-',''));caps[d]={krx_code(x['ISU_CD']):number(x.get('MKTCAP')) for x in allrows}
                    cap=caps[d].get(code)
                    if cap is None or cap<=0:raise APIError('market cap missing '+code+' '+d)
                    # Daily turnover comes from the same provider session, not a carried-forward value.
                    allrows=krx.get('stocks',d.replace('-',''))+krx.get('kosdaq',d.replace('-',''))
                    qr=next((x for x in allrows if krx_code(x['ISU_CD'])==code),None)
                    if qr is None:raise APIError('quote missing '+code+' '+d)
                    merged.append({'date':d,'code':code,'name':rows[0]['name'],'sector':rows[0]['sector'],'close':q[0],'volume':q[1],'benchmark':benchmark[d],'turnover':number(qr.get('ACC_TRDVAL'))/1e8,'marketcap':cap/1e8,'foreign_ownership':None,'flow_source':'Kiwoom REST ka10059',**f})
                count+=1
                if count%25==0:print('Validated collection progress:',count,'stocks; cache hits:',client.cache_hits,flush=True)
            meta={**old['meta'],'as_of':target,'fetched_at':now().isoformat(),'source':'KRX OpenAPI prices + Kiwoom REST investor flows (KRX market)','status':'unknown','price_basis':'raw','dividend_adjusted':False,'trading_dates':sorted(set(old['meta']['trading_dates'])|{d for d in benchmark if old['meta']['trading_dates'][0]<=d<=target}),'notes':['수급: 키움 REST ka10059, KRX 시장 기준. 백만원을 억원으로 변환; 화면은 십억원.','최근 수급은 확정 여부 미확인. 연기금등은 국민연금 단독이 아님.','외국인 보유율 신규 자료 미확보. ETF 체결액으로 해석하지 않음.']}
            meta.pop('reported_windows',None)
            result={'schema_version':2,'meta':meta,'rows':merged}
            validate(root,result,filename)
            prepared.append((filename,result))
            state['validated_scopes']=[name for name,_ in prepared]
        for filename,result in prepared:
            atomic(data/filename,result)
            atomic(data/('index-status.json' if filename.startswith('index-') else 'status.json'),{'status':'success','as_of':target,'last_success_at':now().isoformat(),'message':'키움 REST 세부 수급 + KRX OpenAPI 가격 갱신','web_login':False,'openapi_mode':False})
        state.update(status='success',as_of=target,processed_count=count,overlap_checks=overlap)
    except Exception as e:
        state.update(status='failed',message=str(e)[:400] if isinstance(e,APIError) else 'validation/processing failure: '+type(e).__name__)
    state['request_count']=client.calls;state['cache_hits']=client.cache_hits;atomic(data/'kiwoom-status.json',state);print(json.dumps(state,ensure_ascii=False));return 0 if state['status']=='success' else 1
if __name__=='__main__':sys.exit(run())
