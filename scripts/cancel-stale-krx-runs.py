#!/usr/bin/env python3
"""Drain old credential snapshots before an explicit recovery. GitHub only."""
import json,os,time,urllib.request,urllib.error
TARGETS={'Collect approved market data','Update index universe and flow','Update ETF basket pressure','Verify ETF source capabilities'}
STATES=('queued','in_progress','pending','waiting','requested')

def stale_runs(api,current_run):
    found={}
    for status in STATES:
        page=1
        while True:
            rows=api('GET','/actions/runs?status='+status+'&per_page=100&page='+str(page)).get('workflow_runs',[])
            for row in rows:
                if row['name'] in TARGETS and str(row['id'])!=str(current_run) and row['status']!='completed':found[row['id']]=row
            if len(rows)<100:break
            page+=1
    return found

def drain(api,current_run,clock=time.monotonic,pause=time.sleep):
    requested=set();deadline=clock()+90
    while True:
        pending=stale_runs(api,current_run)
        if not pending:
            print('Old KRX workflow runs drained:',len(requested));return
        for run_id in pending:
            if run_id not in requested:
                api('POST','/actions/runs/'+str(run_id)+'/cancel');requested.add(run_id)
        if clock()>=deadline:raise RuntimeError('Old KRX runs still active; no login attempt permitted')
        pause(3)

def main():
    token=os.environ['GH_TOKEN'];repo=os.environ['GITHUB_REPOSITORY']
    def api(method,path):
        req=urllib.request.Request('https://api.github.com/repos/'+repo+path,
            headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'},
            data=b'' if method=='POST' else None,method=method)
        try:
            with urllib.request.urlopen(req,timeout=20) as response:
                body=response.read();return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            if method=='POST' and exc.code==409:return {}
            raise RuntimeError('GitHub workflow cancellation failed, HTTP '+str(exc.code)) from None
    drain(api,os.environ['GITHUB_RUN_ID'])

if __name__=='__main__':main()
