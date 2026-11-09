"""One explicit token verification; no web login and no automatic retry."""
import json,sys
from kiwoom_flow import Client,APIError,ROOT
from collect import atomic,now
c=Client()
s={'checked_at':now().isoformat(),'web_login':False,'configured':bool(c.key and c.secret),'phase':'token','transport':'curl'}
try:
    c.authenticate()
    s.update(status='success',message='키움 REST 토큰 발급 성공. 수급 갱신은 별도 수집 작업에서 실행.')
except APIError as e:
    s.update(status='failed',message=str(e))
    if '8050' in str(e):s.update(reason='unregistered_ip',message='8050: 실행 서버의 공인 IP가 키움에 등록되지 않았습니다. 등록된 IP의 실행 환경이 필요합니다.')
atomic(ROOT/'dist/data/kiwoom-connection.json',s)
print(json.dumps(s,ensure_ascii=False))
sys.exit(0 if s['status']=='success' else 1)
