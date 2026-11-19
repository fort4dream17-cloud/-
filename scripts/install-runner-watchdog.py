"""One-time Windows scheduled-task setup for the EXISTING runner, no re-registration.

Run in an elevated CMD with Python. Does not store passwords, change execution
policy, change sleep settings, stop jobs, or modify the runner credentials.
"""
import csv,ctypes,datetime,json,os,pathlib,subprocess,sys,tempfile
import xml.etree.ElementTree as ET

TASK='JH Coverage Flow Runner'
DEFAULT_RUNNER=r'C:\Windows\System32\actions-runner'
WATCHDOG=r'''import datetime,json,msvcrt,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]).resolve()
home=pathlib.Path(__file__).resolve().parent
lock=(home/'watchdog.lock').open('a+b')
lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
except OSError:raise SystemExit(0)
def log(text):
 p=home/'watchdog.log'
 if p.exists() and p.stat().st_size>500000:p.replace(home/'watchdog.previous.log')
 with p.open('a',encoding='utf-8') as f:f.write(datetime.datetime.now().isoformat()+' '+text+'\n')
try:
 if not (root/'run.cmd').is_file() or not (root/'.runner').is_file():
  log('Configured runner files missing; no registration attempted.');raise SystemExit(1)
 # Read process executable paths only, never credential-bearing command lines.
 ps="$ErrorActionPreference='Stop'; @(Get-CimInstance Win32_Process -Filter \"Name='Runner.Listener.exe' OR Name='Runner.Worker.exe'\" | Select-Object ExecutablePath) | ConvertTo-Json -Compress"
 r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',ps],capture_output=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
 processes=json.loads(r.stdout.decode('utf-8-sig') or '[]')
 if isinstance(processes,dict):processes=[processes]
 for process in processes:
  exe=process.get('ExecutablePath')
  if not exe:
   log('Cannot identify existing runner process; skipping to prevent duplicates.');raise SystemExit(1)
  if pathlib.Path(exe).resolve().parent==root/'bin':
   log('Existing listener/worker is running; no duplicate started.');raise SystemExit(0)
 log('Starting registered runner. No provider authentication is performed by watchdog.')
 result=subprocess.run(['cmd.exe','/d','/c','call run.cmd'],cwd=root,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
 log('Runner exited with code '+str(result.returncode)+'; scheduled task will retry.')
 raise SystemExit(result.returncode)
except Exception as e:
 log('Watchdog error: '+type(e).__name__);raise SystemExit(1)
'''

def task_xml(user_sid,python,script,runner):
    ns='http://schemas.microsoft.com/windows/2004/02/mit/task';ET.register_namespace('',ns)
    def child(parent,name,text=None,**attrs):
        el=ET.SubElement(parent,'{'+ns+'}'+name,attrs)
        if text is not None:el.text=str(text)
        return el
    task=ET.Element('{'+ns+'}Task',{'version':'1.4'})
    reg=child(task,'RegistrationInfo');child(reg,'Description','Start existing JH flow runner at sign-in and retry every five minutes; current user only.')
    triggers=child(task,'Triggers');login=child(triggers,'LogonTrigger');child(login,'Enabled','true');child(login,'UserId',user_sid)
    daily=child(triggers,'CalendarTrigger');rep=child(daily,'Repetition');child(rep,'Interval','PT5M');child(rep,'Duration','P1D');child(rep,'StopAtDurationEnd','false')
    child(daily,'StartBoundary',datetime.date.today().isoformat()+'T00:00:00');child(daily,'Enabled','true');schedule=child(daily,'ScheduleByDay');child(schedule,'DaysInterval','1')
    principals=child(task,'Principals');principal=child(principals,'Principal',id='Owner');child(principal,'UserId',user_sid);child(principal,'LogonType','InteractiveToken');child(principal,'RunLevel','HighestAvailable')
    settings=child(task,'Settings')
    for k,v in [('MultipleInstancesPolicy','IgnoreNew'),('DisallowStartIfOnBatteries','false'),('StopIfGoingOnBatteries','false'),('AllowHardTerminate','false'),('StartWhenAvailable','true'),('RunOnlyIfNetworkAvailable','true'),('AllowStartOnDemand','true'),('Enabled','true'),('Hidden','false'),('ExecutionTimeLimit','PT0S')]:child(settings,k,v)
    retry=child(settings,'RestartOnFailure');child(retry,'Interval','PT1M');child(retry,'Count','3')
    actions=child(task,'Actions',Context='Owner');exe=child(actions,'Exec');child(exe,'Command',python);child(exe,'Arguments',subprocess.list2cmdline([script,runner]));child(exe,'WorkingDirectory',str(pathlib.Path(script).parent))
    return ET.tostring(task,encoding='utf-16',xml_declaration=True)

def main():
    if os.name!='nt':raise SystemExit('This installer runs only on the registered Windows PC.')
    if not ctypes.windll.shell32.IsUserAnAdmin():raise SystemExit('Open CMD as Administrator, then run this script again. Use the SAME Windows user as the runner.')
    runner=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else DEFAULT_RUNNER).resolve()
    if not (runner/'run.cmd').is_file() or not (runner/'.runner').is_file():raise SystemExit('Configured runner not found: '+str(runner))
    config=json.loads((runner/'.runner').read_text(encoding='utf-8-sig'))
    url=config.get('gitHubUrl','').rstrip('/')
    if url and url!='https://github.com/fort4dream17-cloud/-':raise SystemExit('This runner belongs to another repository; no changes made.')
    raw=subprocess.check_output(['whoami.exe','/user','/fo','csv','/nh'])
    rows=list(csv.reader(raw.decode('mbcs').strip().splitlines()));sid=rows[0][-1].strip()
    if not sid.startswith('S-1-'):raise SystemExit('Unable to identify current Windows user.')
    home=pathlib.Path(os.environ['LOCALAPPDATA'])/'JHAnalytics'/'runner-watchdog';home.mkdir(parents=True,exist_ok=True)
    script=home/'watchdog.py';script.write_text(WATCHDOG,encoding='utf-8')
    pythonw=pathlib.Path(sys.executable).with_name('pythonw.exe')
    if not pythonw.is_file():raise SystemExit('pythonw.exe missing next to Python; no scheduled task changes made.')
    xml=task_xml(sid,str(pythonw),str(script),str(runner))
    with tempfile.TemporaryDirectory() as tmp:
        file=pathlib.Path(tmp)/'task.xml';file.write_bytes(xml)
        subprocess.run(['schtasks.exe','/Create','/TN',TASK,'/XML',str(file),'/F'],check=True)
    # Disable only the legacy startup shortcut created by this project AFTER task registration succeeds.
    startup=pathlib.Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/Startup/CoverageFlowRunner.cmd'
    if startup.exists() and 'call run.cmd' in startup.read_text(errors='replace') and str(runner).lower() in startup.read_text(errors='replace').lower():
        startup.replace(startup.with_suffix('.cmd.disabled'))
    subprocess.run(['schtasks.exe','/Run','/TN',TASK],check=True)
    subprocess.run(['schtasks.exe','/Query','/TN',TASK,'/FO','LIST'],check=True)
    print('\nINSTALLED: automatic start at Windows sign-in; retry every 5 minutes while signed in.')
    print('No password saved. Existing runner windows/jobs are left running.')
    print('PC must remain ON, signed in and awake. This does not start before sign-in or power on the PC.')
    print('Log: '+str(home/'watchdog.log'))
    print('Undo: schtasks /Delete /TN "'+TASK+'" /F (does not stop an active runner).')

if __name__=='__main__':
    try:main()
    except subprocess.CalledProcessError as e:raise SystemExit('Windows command failed, exit code '+str(e.returncode)+'. Setup is not confirmed.')
