# 키움 REST 수급 수집 연결

## 확인된 실제 오류 — 2026-11-09

동일한 공식 토큰 endpoint에 대해 urllib는 HTTP 400 HTML을 반환했고,
curl은 HTTP 200 JSON과 `8050: IP가 등록되지 않았습니다`를 반환했습니다.
따라서 키가 유효한지는 아직 확인되지 않았으며, 키가 틀렸다고 단정하지 않습니다.
REST 클라이언트를 curl로 바꾸고 등록되지 않은 일반 GitHub runner의 정기 인증 시도는 제거했습니다.

## 운영 구조

- KRX 가격·ETF 시세: 기존 GitHub-hosted 작업을 유지합니다.
- 세부 수급: 키움 허용 IP의 runner에서만 실행합니다.
- 현재 운영은 `[self-hosted, Windows, kiwoom]` 라벨의 Windows PC 실행기를 사용합니다. 별도 실행기 변수는 필요하지 않습니다.
- 명시적인 연결 검증은 토큰을 한 번만 요청하고 자동 재시도하지 않습니다.
- 연결 검증 실패 상태에서는 수집기가 토큰 발급을 반복하지 않습니다.
- 브라우저·HTS·KRX 비밀번호는 필요하지 않습니다.

## 등록된 IP의 PC 또는 서버 연결

1. 키움에 등록된 IP를 사용하는 PC/서버를 선택합니다. 장 마감 수집 시 켜져 있어야 하며, 공인 IP가 바뀌면 키움에서 등록을 갱신해야 합니다. 고정 공인 IP의 상시 서버가 가장 안정적입니다.
2. 저장소 Settings → Actions → Runners → New self-hosted runner를 열고 실제 OS를 선택합니다.
3. GitHub가 표시하는 최신 설치·등록 명령을 해당 PC/서버에서 실행합니다. 등록 시 추가 label을 `kiwoom`으로 지정합니다. 등록 토큰은 채팅·커밋에 저장하지 않습니다.
4. Windows runner를 서비스로 실행합니다. PC의 기존 Python과 curl을 사용하고, Git은 SHA-256 검증 후 작업 전용 임시 폴더에 준비합니다. 데이터 검증은 runner 내장 Node를 사용합니다. PC 전역의 PowerShell 실행 정책을 바꾸지 않습니다.
5. 기존 Secrets `KIWOOM_APP_KEY`, `KIWOOM_SECRET_KEY`, `KRX_API_KEY`는 유지합니다.
6. 실행기 라벨을 `kiwoom`으로 지정합니다. Windows 기본 라벨과 함께 수집 작업이 이 PC에만 배정됩니다.
7. Actions → Verify Kiwoom REST connection을 먼저 실행합니다. 성공한 뒤 Update Kiwoom investor flows를 실행합니다.
8. 이후 KRX 가격 갱신 workflow가 끝날 때 키움 수집 workflow가 이어집니다. PC와 실행기는 해당 시간에 켜져 있어야 합니다.

키움 홈페이지에 등록할 IP는 위 실행 환경의 외부 통신 공인 IP입니다. GitHub/Cloudflare 웹사이트 IP나 workers.dev 주소가 아닙니다.
일반 GitHub-hosted runner IP를 매번 추가하는 방법은 지속 운영에 적합하지 않습니다.

## 검증 및 한계

- 요청은 KRX 시장 코드, 금액, 순매수 기준입니다. NXT/SOR를 섞지 않습니다.
- 키움의 백만원 단위를 내부 억원으로 나눈 뒤 화면은 십억원으로 표시합니다.
- 기존 자료와 겹치는 날짜의 수급을 비교하며 큰 불일치 또는 누락 시 이전 데이터를 보존합니다.
- 누락은 0으로 채우지 않습니다. 외국인 지분율과 ETF 편입종목은 이 연결로 복구되지 않습니다.
- 단위 변환·누락·중복·미래일·덮어쓰기 방지·전송 시 인증정보 보호 테스트를 통과했습니다.
- 2026-11-09 14:54 KST, `kiwoom-pc`에서 실제 토큰 발급 성공을 확인했습니다. 전체 수급 갱신 결과는 `kiwoom-status.json`의 기준일과 상태를 별도로 확인합니다.
