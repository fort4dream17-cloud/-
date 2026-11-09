"""Read KODEX publicly disclosed PDFs without login. Partial universe, no stock trade inference."""
import json,pathlib,urllib.request,urllib.error,re,time,math,sys
from datetime import datetime,timedelta,timezone
ROOT=pathlib.Path(__file__).resolve().parents[1]
BASE='https://www.samsungfund.com'
def stamp():return datetime.now(timezone(timedelta(hours=9))).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,d):
    q=p.with_suffix('.tmp');q.write_text(json.dumps(d,ensure_ascii=False,allow_nan=False),encoding='utf-8');q.replace(p)
def num(v):
    if v is None or str(v).strip()=='':return None
    n=float(str(v).replace(',',''));return n if math.isfinite(n) else None
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**k):return None
def get(path):
    if not path.startswith('/api/v1/kodex/'):raise ValueError('unapproved endpoint')
    req=urllib.request.Request(BASE+path,headers={'Accept':'application/json','User-Agent':'CoverageFlowMonitor/1.0 public-disclosure-reader'})
    for attempt in range(3):
        time.sleep(4)
        try:
            with urllib.request.build_opener(NoRedirect).open(req,timeout=15) as r:return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (500,502,503,504) or attempt==2:raise
            time.sleep(5*(attempt+1))

def parse_pdf(payload,date,stock_codes):
    p=payload['pdf'];d=datetime.strptime(str(p['gijunYMD']),'%Y%m%d').date().isoformat()
    if d!=date:raise ValueError('PDF date mismatch')
    rows=p['list']
    if len(rows)!=int(p['totalCnt']):raise ValueError('truncated PDF')
    out=[];seen=set()
    for r in rows:
        code=str(r['itmNo']).strip()
        if code not in stock_codes:continue
        if code in seen:raise ValueError('duplicate component')
        seen.add(code);w=num(r.get('ratio'));q=num(r.get('applyQ'))
        if w is not None and w<0:raise ValueError('negative equity weight')
        if q is not None and q<0:raise ValueError('negative PDF quantity')
        out.append({'code':code,'name':str(r['secNm']),'weight_pct':w,'pdf_quantity':q})
    return {'as_of':d,'reported_component_count':len(rows),'domestic_stock_count':len(out),'holdings':out,'quantity_basis':'운용사 공개 PDF 수량 · CU 설정단위 미검증'}
def main(root=ROOT):
    data=root/'dist/data';quotes=read(data/'etf-openapi.json');target=quotes['meta']['as_of'];known={f['code']:f for f in quotes['funds']};stocks=set(read(data/'openapi-quotes.json')['stocks'])
    state={'checked_at':stamp(),'as_of':target,'source':'삼성자산운용 KODEX 공개 PDF','web_login':False,'universe_count':len(known),'scope':'KODEX 국내주식 ETF · 다른 운용사/해외/파생/채권은 미연결'}
    old=read(data/'etf-holdings.json') if (data/'etf-holdings.json').exists() else {'funds':{}}
    funds=dict(old.get('funds',{}));products={};failed=[];reasons={}
    try:
        prior=old.get('meta',{})
        retry=prior.get('retry_after')
        if not retry and '429' in prior.get('message',''):
            retry=(datetime.fromisoformat(prior['checked_at'])+timedelta(minutes=30)).isoformat()
        if retry and datetime.fromisoformat(retry)>datetime.now(timezone.utc):
            state.update(source_rate_limited=True,retry_after=retry)
            raise ValueError('HTTP 429 cooldown: no provider requests sent')
        total=None
        for page in range(1,31):
            rows=get('/api/v1/kodex/product.do?ordrColm=NAV&ordrSort=DESC&pageNo='+str(page)+'&srchTerm=w')
            if not isinstance(rows,list) or not rows:break
            total=int(rows[0]['totalCnt'])
            before=len(products)
            for r in rows:products[r['stkTicker']]=r
            if len(products)>=total:break
            if len(products)==before:raise ValueError('master pagination repeated')
        state['master_count']=len(products);state['master_expected']=total
        if total is None or len(products)!=total:raise ValueError('master incomplete')
        selected=[r for c,r in products.items() if c in known and r.get('typeLnm')=='국내주식']
        if not selected:raise ValueError('no eligible domestic-equity ETFs')
        if len(selected)>200:raise ValueError('collector request budget exceeded')
        state['eligible_count']=len(selected);success=0;consecutive=0
        for item in selected:
            c=item['stkTicker'];fid=item['fId']
            if not re.fullmatch(r'[A-Za-z0-9]+',fid):raise ValueError('invalid product id')
            try:
                if funds.get(c,{}).get('as_of')==target:
                    success+=1;consecutive=0;continue
                p=parse_pdf(get('/api/v1/kodex/product-pdf/'+fid+'.do?gijunYMD='+target.replace('-','.')),target,stocks)
                funds[c]={**p,'code':c,'name':known[c]['name'],'source_url':BASE+'/etf/product/view.do?id='+fid,'fetched_at':stamp(),'manager':'삼성자산운용','index':known[c].get('index'),'aum':known[c].get('aum'),'pressure_available':False}
                success+=1;consecutive=0
            except (ValueError,KeyError,TypeError,urllib.error.URLError,TimeoutError) as e:
                if isinstance(e,urllib.error.HTTPError) and e.code==429:raise
                reasons[c]=(str(e)[:120] if isinstance(e,ValueError) else type(e).__name__+(' '+str(e.code) if isinstance(e,urllib.error.HTTPError) else ''))
                failed.append(c);consecutive+=1
                if consecutive>=8:break
            if (success+len(failed))%20==0:print('PDF collected',success,'failed',len(failed),flush=True)
        state.update(status='success' if success==len(selected) else 'partial',success_count=success,failed_codes=failed,failed_reasons=reasons,attempted_count=success+len(failed),unattempted_count=len(selected)-success-len(failed))
    except Exception as e:
        if isinstance(e,urllib.error.HTTPError) and e.code==429:
            delay=e.headers.get('Retry-After','1800') if e.headers else '1800'
            seconds=max(1800,int(delay)) if str(delay).isdigit() else 1800
            state.update(source_rate_limited=True,retry_after=(datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat())
        state.update(status='failed',message='Public disclosure collection: '+(str(e)[:160] if isinstance(e,ValueError) else type(e).__name__+(' '+str(e.code) if isinstance(e,urllib.error.HTTPError) else '')),success_count=0)
    current={c:f for c,f in funds.items() if c in known}
    reverse={}
    for c,f in current.items():
        for r in f['holdings']:reverse.setdefault(r['code'],{'name':r['name'],'etfs':[]})['etfs'].append({'etf_code':c,'weight_pct':r['weight_pct'],'as_of':f['as_of']})
    matching=sum(f['as_of']==target for f in current.values())
    state['matching_date_count']=matching;state['coverage_pct']=matching/len(known)*100 if known else None
    save(data/'etf-holdings.json',{'meta':state,'funds':current,'stocks':reverse});save(data/'etf-holdings-status.json',state);print(json.dumps(state,ensure_ascii=False));return state
if __name__=='__main__':sys.exit(1 if main()['status']=='failed' else 0)
