"""ETF basket-implied demand, never executed trades. All amounts are KRW."""
import math

def number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)

def positive(x): return number(x) and x > 0
def divide(x, y): return x / y if number(x) and positive(y) else None
def total(values):
    values = [x for x in values if number(x)]
    return sum(values) if values else None

def keyed(rows, key='code'):
    result={}
    for row in rows:
        code=row[key]
        if code in result: raise ValueError('Duplicate identity: '+code)
        result[code]=row
    return result

def etf_stock_pressure(current, previous, code, price, previous_price=None, event=None):
    """Exact decomposition: dH = dS*q1 + S0*(q1-q0), after verified splits.
    PDF is a creation basket, not audited fund holdings. Unit changes are dated
    by listing observation; economic trade timing is unverified.
    """
    issues=[]; event=event or {}
    result={'creation':None,'rebalance':None,'net':None,'gross_buy':None,'gross_sell':None,
            'method':None,'issues':issues,'execution_verified':False,'timing':'변경상장 관측일; 실제 매매일 미확인'}
    if not previous: issues.append('전일 ETF 자료 없음');return result
    if not positive(price):issues.append('종목 가격 미확보');return result
    if current.get('pdf_date')!=current.get('quote_date') or previous.get('pdf_date')!=previous.get('quote_date'):
        issues.append('PDF·시세 기준일 불일치');return result
    if not current.get('pdf_ok') or not previous.get('pdf_ok'):
        issues.append('PDF 수집 미완료');return result
    if not current.get('physical_eligible'):
        issues.append('합성·파생·액티브 또는 현물 분류 미검증');return result
    c=keyed(current.get('holdings',[])).get(code)
    p=keyed(previous.get('holdings',[])).get(code)
    if not c and not p: return result
    if event.get('unresolved'):
        issues.append('기업행위·합병·설정단위 변경 검증 대기');return result
    s1,s0=current.get('units'),previous.get('units')
    if not positive(s1) or not positive(s0):issues.append('발행좌수 미확보');return result
    etf_split=event.get('etf_split',1);stock_split=event.get('stock_split',1)
    if not positive(etf_split) or not positive(stock_split):raise ValueError('Invalid split factor')
    if (etf_split!=1 or stock_split!=1) and not str(event.get('verified_source','')).startswith('https://'):
        issues.append('분할 보정 출처 미확인');return result
    raw_s0=s0;s0*=etf_split
    nav0=previous.get('nav');nav1=current.get('nav')
    # Do not silently turn a possible ETF split into creations/redemptions.
    unit_ratio=s1/raw_s0
    if etf_split==1 and positive(nav0) and positive(nav1) and (unit_ratio>=1.8 or unit_ratio<=.55) and abs(unit_ratio*nav1/nav0-1)<.08:
        issues.append('ETF 분할·병합 가능성 검증 대기');return result
    def q(row,fund):
        if row is None:return 0.0
        qty=row.get('qty_per_cu');cu=fund.get('cu_size')
        return qty/cu if number(qty) and qty>=0 and positive(cu) and fund.get('cu_verified') else None
    q1=q(c,current);q0=q(p,previous)
    if number(q0):q0=q0*stock_split/etf_split
    if stock_split==1 and p and c and number(q1) and number(q0) and q0>0 and positive(previous_price):
        quantity_ratio=q1/q0
        if (quantity_ratio>=1.8 or quantity_ratio<=.55) and abs(quantity_ratio*price/previous_price-1)<.08:
            issues.append('종목 분할·병합 가능성 검증 대기');return result
    delta=s1-s0
    if number(q1):
        result['creation']=delta*q1*price
        result['method']='좌수 변화 × 현재 CU 현물수량 × 종가'
    elif positive(nav0) and c and number(c.get('weight_pct')) and 0<=c['weight_pct']<=100 and current.get('weight_verified'):
        result['creation']=delta*(nav0/etf_split)*c['weight_pct']/100
        result['method']='좌수 변화 × 전일 NAV × 편입비중 (근사)'
        issues.append('현물 바스켓 수량 대신 비중 근사')
    else:issues.append('현물 수량·설정단위 또는 검증 비중 미확보')
    if number(q1) and number(q0) and current.get('passive_rebalance_eligible',True):
        result['rebalance']=s0*(q1-q0)*price
    else:issues.append('전·당일 좌당 구성수량 미확보; 리밸런싱 N/A')
    terms=[v for v in [result['creation'],result['rebalance']] if number(v)]
    if terms:
        result['net']=sum(terms)
        result['gross_buy']=sum(max(v,0) for v in terms)
        result['gross_sell']=sum(max(-v,0) for v in terms)
    result['partial']=not(number(result['creation']) and number(result['rebalance']))
    return result

def build_day(current, previous, facts, events=None):
    current_funds=keyed(current['etfs']);old=keyed(previous.get('etfs',[]))
    expected=current.get('universe_count',len(current_funds));pdf_count=sum(f.get('pdf_ok',False) for f in current_funds.values())
    missing_prior_funds=sorted(set(old)-set(current_funds))
    stock_codes=set()
    for f in list(current_funds.values())+list(old.values()):
        for h in f.get('holdings',[]):
            if h['code'] in facts:stock_codes.add(h['code'])
    result=[]
    for code in sorted(stock_codes):
        fact=facts[code];contributors=[]
        for fund_code,f in current_funds.items():
            before=old.get(fund_code);h=keyed(f.get('holdings',[])).get(code);prior=keyed((before or {}).get('holdings',[])).get(code)
            if not h and not prior:continue
            e=(events or {}).get(fund_code+':'+code,{})
            calc=etf_stock_pressure(f,before,code,fact.get('close'),fact.get('previous_close'),e)
            units=f.get('units');cu=f.get('cu_size');q=h.get('qty_per_cu') if h else None
            exposure=units*q/cu*fact['close'] if positive(units) and number(q) and positive(cu) and positive(fact.get('close')) and f.get('cu_verified') else None
            s0=(before or {}).get('units');nav0=(before or {}).get('nav')
            net_creation=(units-s0)*nav0 if number(units) and number(s0) and number(nav0) and not e.get('unresolved') else None
            if e.get('etf_split',1)!=1:net_creation=None
            contributors.append({'etf_code':fund_code,'name':f['name'],'manager':f.get('manager'),'index':f.get('index'),
              'type':f.get('type'),'as_of':f.get('quote_date'),'pdf_date':f.get('pdf_date'),
              'aum':f.get('aum'),'weight_pct':h.get('weight_pct') if h and f.get('weight_verified') else None,
              'turnover':f.get('turnover'),'turnover_rvol':divide(f.get('turnover'),f.get('adv20')),
              'volume_rvol':divide(f.get('volume'),f.get('volume_adv20')),
              'nav_gap_pct':(f['close']/f['nav']-1)*100 if positive(f.get('close')) and positive(f.get('nav')) else None,
              'net_creation':net_creation,'creation_aum_pct':divide(net_creation,f.get('aum'))*100 if divide(net_creation,f.get('aum')) is not None else None,
              'basket_exposure':exposure,**calc})
        if not contributors:continue
        values=[c for c in contributors if number(c['net'])]
        net=total([c['net'] for c in contributors]);adv=fact.get('adv20')
        partial=pdf_count<expected or bool(missing_prior_funds) or len(values)<len(contributors) or any(c.get('partial') for c in values)
        norm=lambda v:divide(v,adv)*100 if divide(v,adv) is not None else None
        result.append({'code':code,'name':fact['name'],'sector':fact.get('sector'),'date':current['as_of'],
          'net':net,'creation':total([c['creation'] for c in contributors]),'rebalance':total([c['rebalance'] for c in contributors]),
          'gross_buy':total([c['gross_buy'] for c in contributors]),'gross_sell':total([c['gross_sell'] for c in contributors]),
          'adv20':adv,'adv_pct':norm(net),'rvol':divide(fact.get('volume'),fact.get('volume_adv20')),
          'turnover_rvol':divide(fact.get('turnover'),adv),
          'financial_adv_pct':norm(fact.get('financial')),'foreign_adv_pct':norm(fact.get('foreign')),
          'institution_adv_pct':norm(fact.get('institution')),'return_pct':fact.get('return_pct'),
          'sector_relative_pct':fact.get('sector_relative_pct'),
          'basket_exposure_adv':divide(total([c['basket_exposure'] for c in contributors]),adv),
          'partial':partial,'confidence':'부분자료 · 매매시점 미확인' if partial else '바스켓·좌수 자료 충족 · 매매시점 미확인',
          'contributors':sorted(contributors,key=lambda c:abs(c['net']) if number(c['net']) else -1,reverse=True)})
    return {'schema_version':1,'meta':{'data_kind':'real','unit':'KRW','as_of':current['as_of'],
      'previous_session':previous.get('as_of'),'universe_count':expected,'quote_count':len(current_funds),
      'pdf_success_count':pdf_count,'pdf_success_pct':100*pdf_count/expected if expected else None,
      'status':'partial' if pdf_count<expected or missing_prior_funds else 'success','execution_verified':False,
      'prior_etfs_missing_today':missing_prior_funds,
      'scope':'국내 상장 전체 ETF의 국내 현물 종목 직접 바스켓; 재간접 ETF 룩스루 제외',
      'source':'KRX ETF master / daily quotes / PDF; pykrx',
      'timing':'변경상장 관측일 기준. 실제 설정·환매 요청일·기초주식 체결일은 미확인.'},'stocks':result,'etfs':list(current_funds.values())}

def rolling(history, code, sessions, n):
    dates=sessions[-n:]
    if len(dates)!=n:return None
    by_date={d['meta']['as_of']:d for d in history}
    values=[]
    for date in dates:
        row=next((r for r in by_date.get(date,{}).get('stocks',[]) if r['code']==code),None)
        if not row or row.get('partial') or not number(row.get('net')):return None
        values.append(row['net'])
    return sum(values)

def backtest(history, quotes, sessions, horizon):
    """Only observed signals, next close entry; no invented historic universe."""
    output=[]
    for day in history:
        at=day['meta']['as_of'];idx=sessions.index(at) if at in sessions else -1
        if idx<0 or idx+1+horizon>=len(sessions):continue
        # available_at must be known and before next-session close.
        if not day['meta'].get('available_at') or day['meta']['available_at'][:10]>sessions[idx+1]:continue
        for r in day['stocks']:
            if r.get('partial') or not number(r.get('adv_pct')) or abs(r['adv_pct'])<3:continue
            a=quotes.get(r['code'],{});entry=a.get(sessions[idx+1]);end=a.get(sessions[idx+1+horizon])
            if not entry or not end or not all(positive(x) for x in entry+end):continue
            excess=((end[0]/entry[0])/(end[1]/entry[1])-1)*100
            # MDD is a path statistic; never infer it from endpoints.
            path=[a.get(d) for d in sessions[idx+1:idx+2+horizon]]
            if any(not q or not all(positive(x) for x in q) for q in path):continue
            wealth=[(q[0]/entry[0])/(q[1]/entry[1]) for q in path];peak=wealth[0];mdd=0
            for w in wealth:peak=max(peak,w);mdd=min(mdd,w/peak-1)
            # De-cluster overlapping signals per stock and direction/horizon.
            direction=1 if r['adv_pct']>0 else -1
            if any(o['code']==r['code'] and o['direction']==direction and idx-o['session_index']<=horizon for o in output):continue
            output.append({'code':r['code'],'signal_date':at,'session_index':idx,'direction':direction,
              'excess_pct':excess,'max_drawdown_pct':mdd*100})
    return output
