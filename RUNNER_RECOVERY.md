# 수급 갱신 실행기 복구

## 권장: 한 번 설치하는 로그인 자동 시작·중단 복구

등록된 PC의 **같은 Windows 사용자 계정**에서 CMD를 **관리자 권한으로 실행**하고 다음 두 줄을 차례로 실행합니다.

```cmd
curl.exe -fL "https://raw.githubusercontent.com/fort4dream17-cloud/-/main/scripts/install-runner-watchdog.py" -o "%TEMP%\install-runner-watchdog.py"
python "%TEMP%\install-runner-watchdog.py"
```

등록 경로 `C:\Windows\System32\actions-runner`를 자동 확인합니다. 다른 경로는 Python 명령 뒤에 큰따옴표로 경로를 추가합니다. 기존 GitHub 등록·키움 키·실행 중 작업은 유지합니다. `INSTALLED`가 출력돼야 PC 설치가 완료된 것입니다. GitHub에 파일이 올라간 것만으로 PC에 설치되지는 않습니다.

- 작업 스케줄러 `JH Coverage Flow Runner`: 로그인 시 자동 실행, 5분 간격 재확인
- 동일 사용자 관리자 권한으로 `System32` 로그 쓰기 문제 해결
- 실행기나 수집 작업이 이미 실행 중이면 중복 시작하지 않음
- 비밀번호 저장·실행 정책 변경·절전 설정 변경 없음
- PC가 켜져 있고 Windows에 로그인한 상태에서만 동작. 잠금 화면은 가능하나 로그아웃·전원 꺼짐·절전 중 수집은 불가
- 설치 후 실행기 창을 매일 열 필요 없음. 현재 수동 실행 창은 진행 중 작업이 끝날 때까지 유지
- 상태는 다음 수급 작업에서 `dist/data/runner-autostart.json`으로 확인. 사용자명·SID·작업 XML은 공개하지 않음
- 로그: `%LOCALAPPDATA%\JHAnalytics\runner-watchdog\watchdog.log`
- 해제: 관리자 CMD에서 `schtasks /Delete /TN "JH Coverage Flow Runner" /F`. 진행 중 실행기는 중지하지 않음

로그인 없이 부팅 직후부터 실행해야 한다면 공식 GitHub Windows 서비스로 새로 등록하는 별도 설정이 필요합니다. 이 도구를 Windows 서비스 설치라고 표시하지 않습니다.

## 이전 방식: 로그인 시 창만 열기

키움 API의 등록 IP 조건 때문에 세부 수급 수집은 기존 Windows PC에서 실행합니다. 가격·ETF·수집 상태 진단은 GitHub 클라우드에서 독립 실행합니다.

## PC에서 한 번 설정

`scripts/enable-runner-autostart.cmd`를 다운로드합니다. 기존 등록된 `actions-runner` 폴더에서 CMD를 열고 다운로드한 파일의 전체 경로를 실행합니다. 또는 파일에 실행기 폴더 전체 경로를 첫 번째 인수로 전달합니다.

예: `enable-runner-autostart.cmd "C:\actions-runner"`

현재 사용자 시작프로그램에 `CoverageFlowRunner.cmd`를 추가합니다. 관리자 권한·계정 비밀번호·PowerShell 실행 정책 변경은 필요하지 않습니다. Windows 로그인 후 실행기가 시작됩니다. 이미 Windows 서비스로 등록했거나 실행기 창이 열려 있다면 중복 실행하지 마세요. 되돌리려면 시작프로그램의 해당 파일만 삭제합니다.

지금 갱신하려면 기존 실행기 폴더의 `run.cmd`를 실행하고 연결된 창을 유지하세요. GitHub에 대기 중인 최신 수급 작업이 배정됩니다. PC 전원·인터넷과 키움 등록 공인 IP가 필요하며, PC가 꺼져 있으면 이 방식으로 수집할 수 없습니다. 이 스크립트는 PC 전원이나 절전 정책을 바꾸지 않습니다.

## 자동 재실행

- KRX 가격 작업 완료 후 키움 수급 작업 요청
- 평일 18:45~23:45 KST 시간별 재실행, 다음 영업일 08:25 KST 복구 시도
- GitHub 예약 실행은 정확한 시각을 보장하지 않음
- ETF는 KRX 가격 작업 완료 후 클라우드에서 독립 처리
- 수집 상태 진단은 PC와 독립 실행하며 진단 확인시각과 실행 링크 표시

대기 상태는 인증 실패가 아닙니다. 비밀번호나 키를 바꾸기 전에 PC 실행기 연결부터 확인하세요. 단순히 큐에 있다는 이유로 계정 인증을 반복하지 않습니다.
