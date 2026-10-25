#!/usr/bin/env python3
"""Only issuer-matched official OpenDART NPS reports are publishable."""
import io,json,os,pathlib,re,time,urllib.parse,urllib.request,zipfile,xml.etree.ElementTree as ET
from datetime import datetime
from collect import atomic,now
ROOT=pathlib.Path(__file__).resolve().parents[1]
ALLOWED_REPORTERS={'국민연금공단','국민연금관리공단'}
def report_record(code,row,corp_code=None,cutoff=None):
    reporter=re.sub(r'\s+','',str(row.get('repror','')))
    if reporter not in ALLOWED_REPORTERS:return None
    if not corp_code or row.get('corp_code')!=corp_code:return None
    date=str(row.get('rcept_dt','')).replace('-','');receipt=str(row.get('rcept_no',''))
    if not re.fullmatch(r'\d{8}',date) or not re.fullmatch(r'\d{14}',receipt) or receipt[:8]!=date:return None
    try:published=datetime.strptime(date,'%Y%m%d').date().isoformat();ratio=float(str(row.get('stkrt','')).replace(',',''))
    except (ValueError,TypeError):return None
    if published>(cutoff or now().date().isoformat()) or not 0<=ratio<=100:return None
    return {'code':code,'corp_code':corp_code,'holder':'국민연금','ownership_pct':ratio,'as_of':None,'published_at':published,'ratio_basis':'주식등 대량보유 보고비율 · 보고자·특별관계자 합산 · 보통주 본인 지분율과 다를 수 있음','source':'OpenDART 대량보유 상황보고 API','source_url':'https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+receipt,'rcept_no':receipt,'reporter':reporter,'verification':'opendart_api','verified_at':now().isoformat(),'ratio_type':'stock_etc_reported'}
def run():
    key=os.environ.get('DART_API_KEY');status=ROOT/'dist/data/disclosure-status.json';file=ROOT/'dist/data/pension-holdings.json'
    old=json.loads(file.read_text()) if file.exists() else {'records':[]}
    verified=[r for r in old.get('records',[]) if r.get('verification')=='opendart_api']
    removed=len(old.get('records',[]))-len(verified)
    # Remove incomparable annual snapshots and unverified connector records even on failure.
    base={'holder':'국민연금','scope':'OpenDART 주식등 대량보유 보고비율; 현재 보통주 지분율 아님','records':verified,'removed_unverified':old.get('removed_unverified',0)+removed}
    atomic(file,base)
    if not key:
        atomic(status,{'status':'key_not_configured','checked_at':now().isoformat(),'message':'공식 검증된 보고만 유지. DART_API_KEY 연결 필요.','removed_unverified':removed});print('OpenDART key not configured; unverified records removed.');return
    def request(path,params):
        url='https://opendart.fss.or.kr/api/'+path+'?'+urllib.parse.urlencode({'crtfc_key':key,**params})
        with urllib.request.urlopen(url,timeout=30) as response:return response.read()
    archive=zipfile.ZipFile(io.BytesIO(request('corpCode.xml',{})));root=ET.fromstring(archive.read('CORPCODE.xml'))
    corp={x.findtext('stock_code','').strip():x.findtext('corp_code') for x in root.findall('list') if x.findtext('stock_code','').strip()}
    universe=json.loads((ROOT/'dist/data/index-universe.json').read_text());codes={x['code'] for x in universe['records']};codes.update(x['code'] for x in json.loads((ROOT/'config/coverage.json').read_text()))
    cutoff=now().date().isoformat();failures=[];missing=[];new={}
    for index,code in enumerate(sorted(codes)):
        if code not in corp:missing.append(code);continue
        try:
            obj=json.loads(request('majorstock.json',{'corp_code':corp[code]}));time.sleep(.3)
            if obj.get('status')=='013':missing.append(code);continue
            if obj.get('status')!='000':raise ValueError('DART error')
            candidates=[r for row in obj.get('list',[]) if (r:=report_record(code,row,corp[code],cutoff))]
            if candidates:new[code]=max(candidates,key=lambda x:(x['published_at'],x['rcept_no']))
            else:missing.append(code)
        except Exception:failures.append(code)
        if index%50==0:print('Verified disclosure scan',index+1,'/',len(codes),flush=True)
    # Preserve prior official records only for failed requests, never for successful no-report results.
    records=[r for r in verified if r['code'] in failures and r['code'] not in new]+list(new.values())
    base.update({'records':records,'last_disclosure_scan':now().isoformat(),'no_report_codes':missing,'failed_codes':failures})
    atomic(file,base);atomic(status,{'status':'partial' if failures else 'success','checked_at':now().isoformat(),'matched_reports':len(new),'failed_codes':failures,'no_report_count':len(missing),'removed_unverified':removed,'source':'OpenDART majorstock'})
    print('Official NPS reports',len(new),'failed',len(failures),flush=True)
if __name__=='__main__':
    try:run()
    except Exception as e:
        atomic(ROOT/'dist/data/disclosure-status.json',{'status':'failed','checked_at':now().isoformat(),'message':'공시 공급자 연결 오류: '+type(e).__name__});print('Disclosure refresh failed:',type(e).__name__);raise SystemExit(1)
