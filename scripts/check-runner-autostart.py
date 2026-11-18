"""Publish only non-personal scheduled-task readiness, not user names or task XML."""
import datetime,json,pathlib,subprocess,xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]
def inspect(xml):
    ns={'t':'http://schemas.microsoft.com/windows/2004/02/mit/task'};tree=ET.fromstring(xml)
    def value(path):
        e=tree.find(path,ns);return e.text if e is not None else None
    ready=value('.//t:Settings/t:Enabled')=='true' and value('.//t:Repetition/t:Interval')=='PT5M' and value('.//t:RunLevel')=='HighestAvailable' and tree.find('.//t:LogonTrigger',ns) is not None
    return {'status':'configured' if ready else 'needs_review','at_sign_in':tree.find('.//t:LogonTrigger',ns) is not None,'retry_interval':value('.//t:Repetition/t:Interval'),'before_sign_in':False}
def main():
    result={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        r=subprocess.run(['schtasks.exe','/Query','/TN','JH Coverage Flow Runner','/XML'],capture_output=True,timeout=15)
        result.update(inspect(r.stdout) if r.returncode==0 else {'status':'not_detected','message':'Run the one-time watchdog installer on the registered PC.'})
    except (OSError,ValueError,ET.ParseError,subprocess.TimeoutExpired):result.update(status='unknown')
    target=ROOT/'dist/data/runner-autostart.json';target.write_text(json.dumps(result),encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
