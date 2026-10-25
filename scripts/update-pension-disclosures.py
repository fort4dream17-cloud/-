#!/usr/bin/env python3
"""Refresh NPS report ratios from official OpenDART, preserving annual fallbacks.
No executive/shareholder's unrelated holdings are treated as pension ownership.
The majorstock headline ratio includes the reporter and special related parties.
"""
import io,json,os,pathlib,re,time,urllib.parse,urllib.request,zipfile,xml.etree.ElementTree as ET
from collect import atomic,now
ROOT=pathlib.Path(__file__).resolve().parents[1]
ALLOWED_REPORTERS={'국민연금공단','국민연금관리공단'}
def report_record(code,row):
    reporter=re.sub(r'\s+','',row.get('repror',''))
    if reporter not in ALLOWED_REPORTERS:return None
    date=row.get('rcept_dt','').replace('-','');receipt=row.get('rcept_no','')
    if not re.fullmatch(r'\d{8}',date) or not re.fullmatch(r'\d{14}',receipt):return None
    try:ratio=float(str(row.get('stkrt','')).replace(',',''))
    except ValueError:return None
    if not 0<=ratio<=100:return None
    return {'code':code,'holder':'국민연금','ownership_pct':ratio,'as_of':None,'published_at':date[:4]+'-'+date[4:6]+'-'+date[6:],'date_basis':'공시 접수일; 실제 보유 기준일은 원문 확인 필요','ratio_basis':'주식등 보유비율; 보고자·특별관계자 합산','source':'DART 주식등의 대량보유상황보고','source_url':'https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+receipt,'rcept_no':receipt,'reporter':row.get('repror')}
def run():
    key=os.environ.get('DART_API_KEY');status=ROOT/'dist/data/disclosure-status.json'
    if not key:
        atomic(status,{'status':'key_not_configured','checked_at':now().isoformat(),'message':'현재 연결된 공시 스냅샷 유지. 정기 OpenDART 갱신에는 DART_API_KEY가 필요합니다.'});print('DART_API_KEY not configured; preserving published disclosures.');return
    def request(path,params):
        # Never print request URLs containing the API key or server response bodies.
        url='https://opendart.fss.or.kr/api/'+path+'?'+urllib.parse.urlencode({'crtfc_key':key,**params})
        with urllib.request.urlopen(url,timeout=30) as r:return r.read()
    archive=zipfile.ZipFile(io.BytesIO(request('corpCode.xml',{})));root=ET.fromstring(archive.read('CORPCODE.xml'))
    corp={x.findtext('stock_code','').strip():x.findtext('corp_code') for x in root.findall('list') if x.findtext('stock_code','').strip()}
    universe=json.loads((ROOT/'dist/data/index-universe.json').read_text());codes=set(x['code'] for x in universe['records']);codes.update(x['code'] for x in json.loads((ROOT/'config/coverage.json').read_text()))
    file=ROOT/'dist/data/pension-holdings.json';data=json.loads(file.read_text()) if file.exists() else {'records':[]};records=data['records'];failures=[];new=[]
    for code in sorted(codes):
        if code not in corp:failures.append(code);continue
        try:
            obj=json.loads(request('majorstock.json',{'corp_code':corp[code]}));time.sleep(.4)
            if obj.get('status')=='013':continue
            if obj.get('status')!='000':raise ValueError('DART status '+str(obj.get('status')))
            candidates=[r for row in obj.get('list',[]) if (r:=report_record(code,row))]
            if candidates:new.append(max(candidates,key=lambda x:(x['published_at'],x['rcept_no'])))
        except Exception:failures.append(code)
    # Preserve dated annual records; new reports take precedence in the UI by their position/report dates.
    ids={r.get('rcept_no') for r in records if r.get('rcept_no')};records.extend(r for r in new if r['rcept_no'] not in ids)
    data.update({'records':records,'last_disclosure_scan':now().isoformat(),'disclosure_scan_scope':'국민연금 명의 대량보유 보고; 다른 주주의 임원/주요주주 보고는 포함하지 않음'})
    atomic(file,data);atomic(status,{'status':'partial' if failures else 'success','checked_at':now().isoformat(),'matched_reports':len(new),'failed_codes':failures,'source':'OpenDART majorstock'})
if __name__=='__main__':
    try:run()
    except Exception as e:
        atomic(ROOT/'dist/data/disclosure-status.json',{'status':'failed','checked_at':now().isoformat(),'message':'공시 공급자 연결 오류: '+type(e).__name__});print('Disclosure refresh failed:',type(e).__name__);raise SystemExit(1)
