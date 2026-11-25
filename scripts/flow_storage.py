"""Lossless compact storage for validated flow rows; expands before analysis."""
import json,pathlib
def unpack(data):
    if data.get('row_format')!='columns-v1':return data
    cols=data['columns']
    if len(set(cols))!=len(cols) or any(len(r)!=len(cols) for r in data['rows']):raise ValueError('Invalid columnar flow rows')
    return {k:v for k,v in data.items() if k not in ('columns','row_format','rows')}|{'rows':[dict(zip(cols,r)) for r in data['rows']]}
def pack(data):
    data=unpack(data)
    cols=sorted({k for r in data['rows'] for k in r})
    return {**data,'row_format':'columns-v1','columns':cols,'rows':[[r.get(k) for k in cols] for r in data['rows']]}
def read_flow(path):return unpack(json.loads(path.read_text(encoding='utf-8')))
def write_flow(path,data):
    raw=json.dumps(pack(data),ensure_ascii=False,separators=(',',':')).encode('utf-8')
    if len(raw)>25*1024*1024:raise ValueError('Flow asset exceeds deployment file size; partitioning required')
    tmp=path.with_suffix('.tmp');tmp.write_bytes(raw);tmp.replace(path)
if __name__=='__main__':
    root=pathlib.Path(__file__).resolve().parents[1]
    for name in ['index-market.json','market.json']:
        path=root/'dist/data'/name;data=read_flow(path);write_flow(path,data)
        print(name,len(data['rows']),'rows,',path.stat().st_size,'bytes')
