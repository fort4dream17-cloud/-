"""Kiwoom REST read-only flow collection. No web login or order endpoints."""
import json,os,pathlib,time,urllib.request,urllib.error,subprocess,sys,tempfile
from datetime import datetime
from collect import atomic,now,collection_end
from krx_openapi import Client as KRXClient, code as krx_code
ROOT=pathlib.Path(__file__).resolve().parents[1]
FIELDS=dict(personal='ind_invsr',foreign='frgnr_invsr',institution='orgn',financial='fnnc_invt',insurance='insrnc',trust='invtrt',other_institution='etc_fnnc',bank='bank',pension='penfnd_etc',private='samo_fund',government='natn',corporation='etc_corp',other_foreign='natfor')
def number(x):
    if x is None or str(x).strip()=='':return None
    return float(str(x).replace(',',''))
class APIError(Exception):pass
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
class Client:
    def __init__(self):
        self.key=os.environ.get('KIWOOM_APP_KEY','').strip();self.secret=os.environ.get('KIWOOM_SECRET_KEY','').strip();self.token=None;self.calls=0
    def post(self,path,body,headers=None):
        if self.calls>=2500:raise APIError('request budget exceeded')
        self.calls+=1;time.sleep(.3)
        req=urllib.request.Request('https://api.kiwoom.com'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json;charset=UTF-8',**(headers or {})},method='POST')
        try:
            with urllib.request.build_opener(NoRedirect).open(req,timeout=30) as r:payload=json.load(r);h=r.headers
        except urllib.error.HTTPError as e:
            try:
                error=json.loads(e.read(16384));msg=str(error.get('return_msg',''));code=str(error.get('return_code',''))
            except Exception:msg='';code=''
            for value in [self.key,self.secret,self.token]:
                if value:msg=msg.replace(value,'[redacted]')
            raise APIError('HTTP '+str(e.code)+' provider '+code+': '+msg[:250]) from None
        except Exception:raise APIError('network/response failure') from None
        if str(payload.get('return_code',0))!='0':
            msg=str(payload.get('return_msg',''))
            for value in [self.key,self.secret,self.token]:
                if value:msg=msg.replace(value,'[redacted]')
            raise APIError('provider '+str(payload.get('return_code'))+': '+msg[:250])
        return payload,h
    def authenticate(self):
        if not self.key or not self.secret:raise APIError('KIWOOM_APP_KEY / KIWOOM_SECRET_KEY missing')
        p,_=self.post('/oauth2/token',{'grant_type':'client_credentials','appkey':self.key,'secretkey':self.secret})
        self.token=p.get('token')
        if not self.token:raise APIError('access token missing')
    def flows(self,code,end,start):
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

def read(p):return json.loads(p.read_text())
def run(root=ROOT):
    data=root/'dist/data';state={'checked_at':now().isoformat(),'source':'Kiwoom REST ka10059','web_login':False,'market':'KRX','configured':bool(os.environ.get('KIWOOM_APP_KEY') and os.environ.get('KIWOOM_SECRET_KEY'))};client=Client()
    try:
        client.authenticate();state['authentication']='success'
        history=read(data/'index-price-history.json');target=history['meta']['as_of'];end=target.replace('-','')
        benchmark=dict(history['benchmarks']);krx=KRXClient();caps={}
        prepared=[];count=0;overlap=0
        for filename in ['index-market.json','market.json']:
            old=read(data/filename);bycode={}
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
            meta={**old['meta'],'as_of':target,'fetched_at':now().isoformat(),'source':'KRX OpenAPI prices + Kiwoom REST investor flows (KRX market)','status':'unknown','price_basis':'raw','dividend_adjusted':False,'trading_dates':sorted(set(old['meta']['trading_dates'])|{d for d in benchmark if old['meta']['trading_dates'][0]<=d<=target}),'notes':['수급: 키움 REST ka10059, KRX 시장 기준. 백만원을 억원으로 변환; 화면은 십억원.','최근 수급은 확정 여부 미확인. 연기금등은 국민연금 단독이 아님.','외국인 보유율 신규 자료 미확보. ETF 체결액으로 해석하지 않음.']}
            meta.pop('reported_windows',None)
            result={'schema_version':2,'meta':meta,'rows':merged}
            with tempfile.NamedTemporaryFile('w',suffix='.json') as f:
                json.dump(result,f);f.flush();subprocess.run(['node',str(root/'scripts/validate.mjs'),f.name],check=True,capture_output=True)
            prepared.append((filename,result))
        for filename,result in prepared:
            atomic(data/filename,result)
            atomic(data/('index-status.json' if filename.startswith('index-') else 'status.json'),{'status':'success','as_of':target,'last_success_at':now().isoformat(),'message':'키움 REST 세부 수급 + KRX OpenAPI 가격 갱신','web_login':False,'openapi_mode':False})
        state.update(status='success',as_of=target,processed_count=count,overlap_checks=overlap)
    except Exception as e:
        state.update(status='failed',message=str(e)[:400] if isinstance(e,APIError) else 'validation/processing failure: '+type(e).__name__)
    state['request_count']=client.calls;atomic(data/'kiwoom-status.json',state);print(json.dumps(state,ensure_ascii=False));return 0 if state['status']=='success' else 1
if __name__=='__main__':sys.exit(run())
