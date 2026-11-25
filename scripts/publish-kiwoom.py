"""Publish validated flow files from a fresh worktree, independent of runner rebase state."""
import json,pathlib,shutil,subprocess,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
FILES=['index-market.json','market.json','index-status.json','status.json','kiwoom-status.json','runner-autostart.json']
def asof(raw):
    try:
        d=json.loads(raw);return d.get('meta',{}).get('as_of') or d.get('as_of') or ''
    except (ValueError,TypeError):return ''
def git(*args,cwd=None,check=True):
    return subprocess.run(['git',*args],cwd=cwd or ROOT,check=check)
def main():
    saved={f:(ROOT/'dist/data'/f).read_bytes() for f in FILES if (ROOT/'dist/data'/f).is_file()}
    if not all(f in saved for f in ['index-market.json','market.json','kiwoom-status.json']):
        raise ValueError('Validated flow publication inputs missing')
    for attempt in range(3):
        git('fetch','origin','main')
        with tempfile.TemporaryDirectory(prefix='flow-publish-') as tmp:
            work=pathlib.Path(tmp)/'checkout'
            git('worktree','add','--detach',str(work),'origin/main')
            try:
                # Never replace a newer validated flow snapshot.
                for f in ['index-market.json','market.json']:
                    if asof((work/'dist/data'/f).read_bytes())>asof(saved[f]):
                        raise ValueError('Remote flow is newer; refusing stale publication')
                for f,raw in saved.items():(work/'dist/data'/f).write_bytes(raw)
                git('add',*['dist/data/'+f for f in saved],cwd=work)
                delta=git('diff','--cached','--quiet',cwd=work,check=False).returncode
                if delta==0:print('Validated flows already published');return
                if delta!=1:raise ValueError('Unable to verify publication diff')
                git('-c','user.name=flow-data-bot','-c','user.email=flow-data-bot@users.noreply.github.com','commit','-m','Refresh validated Kiwoom investor flows',cwd=work)
                if git('push','origin','HEAD:main',cwd=work,check=False).returncode==0:
                    print('Validated flows published from isolated worktree');return
            finally:git('worktree','remove','--force',str(work),check=False)
        time.sleep(2)
    raise RuntimeError('Publication failed after three fresh-head attempts')
if __name__=='__main__':main()
