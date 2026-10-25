#!/usr/bin/env python3
"""Read NPS annual holdings XLSX and match the configured securities by exact names.
The source reports fractional ownership; publish percent units and explicit dates.
No daily pension holding estimate is produced.
"""
import argparse,json,pathlib,zipfile,xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
ALIASES={'267270':['HD현대건설기계']}
def extract(path,coverage,as_of,published_at,source_url):
    with zipfile.ZipFile(path) as z:
        strings=[''.join(t.itertext()) for t in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',NS)]
        sheet=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        by_name={};header=False
        for row in sheet.findall('.//m:row',NS):
            cells={}
            for c in row.findall('m:c',NS):
                v=c.find('m:v',NS);v=v.text if v is not None else ''
                cells[''.join(k for k in c.get('r') if k.isalpha())]=strings[int(v)] if c.get('t')=='s' and v else v
            if cells.get('B')=='종목명' and cells.get('E')=='지분율':header=True;continue
            if not header or not cells.get('B') or not cells.get('E'):continue
            try:percentage=float(cells['E'])*100
            except ValueError:continue
            if not 0<=percentage<=100:raise ValueError('Source ownership range error')
            if cells['B'] in by_name:raise ValueError('Duplicate source security name')
            by_name[cells['B']]=percentage
    records=[];missing=[]
    for security in coverage:
        names=[security['name']]+ALIASES.get(security['code'],[])
        matches=[n for n in names if n in by_name]
        if len(matches)>1:raise ValueError('Ambiguous exact-name match: '+security['code'])
        if not matches:missing.append(security['code']);continue
        name=matches[0]
        records.append({'code':security['code'],'source_name':name,'ownership_pct':round(by_name[name],6),'holder':'국민연금','as_of':as_of,'published_at':published_at,'source':'국민연금 기금운용본부 연간 공시','source_url':source_url})
    return {'holder':'국민연금','scope':'국민연금 공시 지분율; 전체 연기금 및 현재 지분율 아님','as_of':as_of,'published_at':published_at,'missing_codes':missing,'records':records}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--as-of',required=True);p.add_argument('--published-at',required=True);p.add_argument('--source-url',required=True);args=p.parse_args()
    coverage=json.loads((ROOT/'config/coverage.json').read_text())
    out=extract(args.input,coverage,args.as_of,args.published_at,args.source_url)
    (ROOT/'dist/data/pension-holdings.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print('Matched',len(out['records']),'of',len(coverage),'securities. Missing:',out['missing_codes'])
