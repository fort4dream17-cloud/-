"""Build ETF market diagnostics from observed KRX quotes; never treat turnover as flows."""
import json,pathlib,math
from datetime import datetime,timedelta,timezone
ROOT=pathlib.Path(__file__).resolve().parents[1]
def stamp():return datetime.now(timezone(timedelta(hours=9))).isoformat()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,d):
    p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix('.tmp');q.write_text(json.dumps(d,ensure_ascii=False,allow_nan=False),encoding='utf-8');q.replace(p)
def finite(v):return isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v)
def ratio(a,b):return a/b if finite(a) and finite(b) and b>0 else None
def build(current,days,calendar=None):
    asof=current['meta']['as_of'];ordered=sorted({d['as_of']:d for d in days if d['as_of']<=asof}.values(),key=lambda d:d['as_of'])[-121:]
    if calendar is not None:ordered=[d for d in ordered if d['as_of'] in calendar]
    byday={d['as_of']:{f['code']:f for f in d['funds']} for d in ordered}
    byday[asof]={f['code']:f for f in current['funds']}
    dates=sorted(byday);out=[];hist={}
    seen=set()
    for f in current['funds']:
        c=f['code']
        if c in seen:raise ValueError('duplicate ETF')
        seen.add(c)
        if f.get('quote_date')!=asof:raise ValueError('ETF date mismatch')
        history=[byday[d].get(c) for d in dates];prior=history[:-1][-20:]
        def mean(k):return sum(x[k] for x in prior)/20 if len(prior)==20 and all(x and finite(x.get(k)) and x[k]>=0 for x in prior) else None
        adv=mean('turnover');avol=mean('volume');prev=history[-2] if len(history)>1 else None
        delta=f['units']-prev['units'] if prev and all(finite(x.get('units')) and x['units']>0 for x in [prev,f]) else None
        # Units changes can include corporate actions: this is a diagnostic, not confirmed creation/redemption.
        proxy=delta*f['nav'] if finite(delta) and finite(f.get('nav')) and f['nav']>0 else None
        ret={}
        for n in [5,20,60]:
            p=history[-n-1] if len(history)>n else None
            r=ratio(f.get('close'),p.get('close') if p else None);ret[str(n)]=(r-1)*100 if r is not None else None
        navratio=ratio(f.get('close'),f.get('nav'))
        out.append({**f,'adv20':adv,'turnover_rvol':ratio(f.get('turnover'),adv),'volume_rvol':ratio(f.get('volume'),avol),'nav_gap_pct':(navratio-1)*100 if navratio is not None else None,'units_delta':delta,'units_change_value':proxy,'returns':ret,'creation_confirmed':False})
        hist[c]=[[d,*[byday[d].get(c,{}).get(k) for k in ['close','nav','aum','units','turnover','volume']]] for d in dates]
    return {'meta':{'as_of':asof,'fetched_at':stamp(),'source':'KRX OpenAPI','unit':'KRW','count':len(out),'sessions':len(dates),'history_columns':['date','close','nav','aum','units','turnover','volume'],'notes':['ADV20/RVOL은 기준일을 제외한 직전 20개 시장 관측일. 누락/신규 ETF는 N/A.','좌수변화 환산액 = 좌수 증감 × 당일 NAV. 분할·합병 미검증으로 설정·환매 확정액이나 주식 매매액이 아님.']},'funds':out,'history':hist}
def main(root=ROOT):
    data=root/'dist/data';current=read(data/'etf-openapi.json');manifest=read(data/'etf-openapi-history.json');days=[]
    for item in manifest.get('days',[]):
        p=data/item['file']
        if not p.resolve().is_relative_to((data/'etf-openapi-db').resolve()):raise ValueError('invalid history path')
        try:
            d=read(p)
            if d['as_of']!=item['as_of']:raise ValueError('history date mismatch')
            days.append(d)
        except FileNotFoundError:continue
    calendar={r[0] for r in read(data/'index-price-history.json')['benchmarks']}
    result=build(current,days,calendar);save(data/'etf-monitor.json',result);print(json.dumps(result['meta'],ensure_ascii=False))
if __name__=='__main__':main()
