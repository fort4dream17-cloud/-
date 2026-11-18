"""Publish only non-personal scheduled-task readiness, not user names or task XML."""
import datetime,json,pathlib,subprocess,xml.etree.ElementTree as ET

def decode_xml(raw):
    if isinstance(raw,str):return raw
    if raw.startswith((b"\xff\xfe",b"\xfe\xff")):return raw.decode("utf-16")
    if b"\x00" in raw[:100]:return raw.decode("utf-16-le")
    try:return raw.decode("utf-8-sig")
    except UnicodeDecodeError:return raw.decode("cp949")

ROOT=pathlib.Path(__file__).resolve().parents[1]
def inspect(xml):
    ns={'t':'http://schemas.microsoft.com/windows/2004/02/mit/task'};tree=ET.fromstring(decode_xml(xml))
    def value(path):
        e=tree.find(path,ns);return e.text if e is not None else None
    ready=value('.//t:Settings/t:Enabled')=='true' and value('.//t:Repetition/t:Interval')=='PT5M' and value('.//t:RunLevel')=='HighestAvailable' and tree.find('.//t:LogonTrigger',ns) is not None
    return {'status':'configured' if ready else 'needs_review','at_sign_in':tree.find('.//t:LogonTrigger',ns) is not None,'retry_interval':value('.//t:Repetition/t:Interval'),'before_sign_in':False}
def main():
    result={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        r=subprocess.run(['schtasks.exe','/Query','/TN','JH Coverage Flow Runner','/XML'],capture_output=True,timeout=15)
        result.update(inspect(r.stdout) if r.returncode==0 else {'status':'not_detected','message':'Run the one-time watchdog installer on the registered PC.'})
    except (OSError,ValueError,ET.ParseError,subprocess.TimeoutExpired) as e:result.update(status="unknown",error_type=type(e).__name__)
    target=ROOT/'dist/data/runner-autostart.json';target.write_text(json.dumps(result),encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
