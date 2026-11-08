"""KRX AUTH_KEY client. No pykrx, cookies, ID/password, redirects or login fallback."""
import json,math,os,re,time,urllib.request,urllib.error
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

SERVICES={'kospi':'idx/kospi_dd_trd','stocks':'sto/stk_bydd_trd','kosdaq':'sto/ksq_bydd_trd','etf':'etp/etf_bydd_trd'}
class APIError(ValueError):pass
def number(v):
    if isinstance(v,bool) or v is None or str(v).strip() in ('','-'):return None
    try:n=float(str(v).replace(',',''));return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None
def code(v):
    v=str(v)
    if re.fullmatch(r'KR[0-9A-Z]{10}',v):v=v[3:9]
    if not re.fullmatch(r'[0-9A-Z]{6}',v):raise APIError('종목코드 형식 불일치')
    return v
def now():return datetime.now(ZoneInfo('Asia/Seoul'))
def query_end():
    d=now().date()
    if now().hour<18:d-=timedelta(days=1)
    while d.weekday()>4:d-=timedelta(days=1)
    return d
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class Client:
    def __init__(self,key=None,transport=None,limit=600,pause=.15):
        self.key=(key if key is not None else next((os.environ[k] for k in ('KRX_API_KEY','KRX_OPEN_API_KEY','KRX_AUTH_KEY') if os.environ.get(k)), '')).strip()
        self.transport=transport;self.limit=limit;self.pause=pause;self.calls=0;self.errors={};self.memo={};self.counts={}
    def get(self,service,date):
        if service not in SERVICES:raise APIError('허용되지 않은 API 서비스')
        if not re.fullmatch(r'\d{8}',date):raise APIError('기준일 형식 오류')
        if service in self.errors:raise APIError(self.errors[service])
        if (service,date) in self.memo:return self.memo[service,date]
        if not self.key:raise APIError('KRX_API_KEY 미설정: OpenAPI AUTH_KEY만 사용하며 웹 로그인하지 않습니다.')
        if self.calls>=self.limit:raise APIError('OpenAPI 실행당 호출 한도 도달; 직전 데이터 보존')
        self.calls+=1;self.counts[service]=self.counts.get(service,0)+1
        try:
            if self.transport:payload=self.transport(service,date)
            else:
                url='https://data-dbg.krx.co.kr/svc/apis/'+SERVICES[service]+'?basDd='+date
                req=urllib.request.Request(url,headers={'AUTH_KEY':self.key,'Accept':'application/json'})
                with urllib.request.build_opener(NoRedirect).open(req,timeout=25) as response:
                    body=response.read(16*1024*1024+1)
                if len(body)>16*1024*1024:raise APIError('API 응답 크기 초과')
                payload=json.loads(body)
        except urllib.error.HTTPError as exc:
            safe=f'{SERVICES[service]} HTTP {exc.code}'
            if exc.code in (401,403):safe+=' · API 키 유효기간·서비스별 이용승인 확인 필요'
            self.errors[service]=safe;raise APIError(safe) from None
        except APIError:raise
        except Exception:
            safe=SERVICES[service]+' 응답 미확인';self.errors[service]=safe;raise APIError(safe) from None
        finally:
            if not self.transport:time.sleep(self.pause)
        rows=payload.get('OutBlock_1') if isinstance(payload,dict) else None
        if not isinstance(rows,list):raise APIError(SERVICES[service]+' 응답 스키마 불일치')
        seen=set()
        for row in rows:
            if not isinstance(row,dict) or str(row.get('BAS_DD','')).replace('-','')!=date:raise APIError('API 기준일 불일치')
            identity=str(row.get('IDX_NM','')) if service=='kospi' else code(row.get('ISU_CD',''))
            if not identity or identity in seen:raise APIError('API 식별자 중복/누락')
            seen.add(identity)
        self.memo[service,date]=rows
        return rows

def kospi_close(rows):
    found=[r for r in rows if str(r.get('IDX_NM','')).replace(' ','').upper() in ('코스피','KOSPI')]
    if len(found)!=1:raise APIError('KOSPI 지수 식별 실패; 다른 지수로 대체하지 않습니다.')
    value=number(found[0].get('CLSPRC_IDX'))
    if value is None or value<=0:raise APIError('KOSPI 지수 값 미확보')
    return value
