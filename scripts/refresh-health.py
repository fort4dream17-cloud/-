"""Read-only Actions diagnostics; no provider credentials or login attempts."""
import json,os,pathlib,urllib.request
from datetime import datetime,timezone
ROOT=pathlib.Path(__file__).resolve().parents[1]
def read(p):
    try:return json.loads(p.read_text(encoding='utf-8'))
    except (ValueError,OSError):return {}
def diagnose(flow,price,runs,checked):
    relevant=[r for r in runs if r.get('event')!='pull_request']
    # A newer concurrency-pending run may hide an older runner-queued blocker.
    latest=next((r for r in relevant if r.get('status') in ('queued','in_progress')),relevant[0] if relevant else {})
    state='current' if flow and price and flow>=price else 'stale'
    message='가격 기준일까지 수급 관측 완료' if state=='current' else '수급 기준일이 가격 기준일보다 뒤처짐'
    if latest.get('status')=='queued':state='waiting_runner';message='등록된 PC 실행기 배정 대기 · PC 전원/실행기 연결 상태 확인 필요'
    elif latest.get('status')=='pending':state='waiting_previous';message='이전 수급 작업 종료 대기 · PC 실행기 대기 작업이 있는지 확인 필요'
    elif latest.get('status')=='in_progress':state='collecting';message='키움 수급 수집 실행 중 · 검증 완료 전 직전 자료 유지'
    elif latest.get('conclusion') in ('failure','timed_out','cancelled') and state!='current':state='failed';message='최근 수급 작업 실패/중단 · 직전 자료 유지'
    age=None
    try:age=max(0,round((checked-datetime.fromisoformat(latest['created_at'].replace('Z','+00:00'))).total_seconds()/60))
    except (KeyError,ValueError):pass
    return {'checked_at':checked.isoformat(),'status':state,'message':message,'flow_as_of':flow,'price_as_of':price,'run_status':latest.get('status'),'conclusion':latest.get('conclusion'),'queued_or_run_age_minutes':age,'run_url':latest.get('html_url'),'pc_required':True,'web_login':False}
def main(root=ROOT):
    repo=os.environ.get('GITHUB_REPOSITORY','fort4dream17-cloud/-')
    if repo!='fort4dream17-cloud/-':raise ValueError('unexpected repository')
    req=urllib.request.Request('https://api.github.com/repos/'+repo+'/actions/workflows/update-kiwoom.yml/runs?per_page=5',headers={'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'],'Accept':'application/vnd.github+json','User-Agent':'CoverageFlowMonitor-health'})
    with urllib.request.urlopen(req,timeout=20) as response:runs=json.load(response)['workflow_runs']
    data=root/'dist/data';flow=read(data/'index-market.json').get('meta',{}).get('as_of');price=read(data/'price-status.json').get('as_of')
    result=diagnose(flow,price,runs,datetime.now(timezone.utc))
    target=data/'refresh-health.json';tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');tmp.replace(target)
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
