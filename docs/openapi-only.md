# OpenAPI 전용 운영

2026-11-08: KRX 웹 ID/PW 로그인을 영구 중지했다. 웹 인증 함수, 재로그인 가드, 웹 인증에 의존하던 과거 수집 스크립트를 소스에서 삭제했다. 워크플로에 `KRX_ID`, `KRX_PW`를 전달하지 않으며 pykrx를 설치하지 않는다. API 오류 시 웹 로그인으로 돌아가지 않는다.

## 운영

- GitHub Repository Secret `KRX_API_KEY` 사용. 기존 `KRX_OPEN_API_KEY`, `KRX_AUTH_KEY` 이름도 대체 입력으로 지원.
- 예약 실행: Update index universe and flow, 평일 KST 18:35/19:35/20:35 (GitHub 예약 지연 가능).
- 기존 Collect approved market data / Update ETF basket pressure의 수동 실행도 동일한 OpenAPI 작업으로 연결한다.
- 웹 인증 복구 워크플로도 삭제했다. API 확인은 Verify KRX OpenAPI 사용.
- API별 이용 승인·키 유효기간·조회 가능 기간은 별도다. HTTP 401/403은 API 연결 문제로 표시하며 해당 실행에서 같은 서비스 인증을 반복하지 않는다.
- 키는 `AUTH_KEY` 헤더에만 전달한다. 로그·JSON·URL에 기록하지 않고 리다이렉트도 금지한다.

## 연결 범위

| 서비스 | 엔드포인트 | 갱신 |
| --- | --- | --- |
| 유가증권 일별매매정보 | sto/stk_bydd_trd | 비수정 종가, 거래량/대금, 시총 |
| 코스닥 일별매매정보 | sto/ksq_bydd_trd | 비수정 종가, 거래량/대금, 시총 |
| KOSPI 시리즈 | idx/kospi_dd_trd | KOSPI 종가, 가격 상대수익률 |
| ETF 일별매매정보 | etp/etf_bydd_trd | 종가, NAV, 순자산, 발행좌수, 거래량/대금 |

공식 목록: https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd

공개 목록에 없는 투자자 세부 순매수·외국인 지분율·ETF PDF/CU/목표비중·지수 구성종목 변경은 갱신 완료로 처리하지 않는다. 기존 수급 JSON은 수정하지 않고 마지막 관측일을 표시한다. ETF 종목별 패시브 압력은 N/A다. 구성종목 자동 리밸런싱도 기존 관측 목록을 보존한다. 국민연금 공시는 독립적인 OpenDART 키 경로를 유지한다.

가격과 수급 기준일은 별개다. 신규 가격 차트의 날짜에 투자자 매매를 복사하거나 0으로 채우지 않는다. 비수정 주가이며 분할 등 기업행위 시 수익률 왜곡 가능성이 있다. MA20/MA60은 실제 확보한 연속 관측치에 한해 표시한다.

API 응답 기준일·종목 중복·지수 식별 검증 후 가격 이력 갱신. 실패 시 직전 검증 이력을 보존한다. API별 성공/실패는 dist/data/krx-openapi-status.json에 기록한다. OpenAPI 실제 접속 가능 여부와 데이터 게시 권한은 별개이며, 이 변경은 새로운 이용허락을 보장하지 않는다.


2026-11-09: 선택된 Secret 이름·설정된 별칭·키 충돌 여부만 공개 상태에 기록한다. 키 값이나 해시는 기록하지 않는다.
