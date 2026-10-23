# GS 커버리지 수급 모니터

기존 정적 대시보드를 확장한 실제 데이터 연결용 애플리케이션입니다. 기본 화면에는 가상 숫자를 표시하지 않습니다. **현재 실제 데이터 공급 권한이 없어 운영 `market.json`은 비어 있습니다.** KRX 인증을 우회하지 않으며 접근 불가능한 수급을 기관합계나 0으로 대체하지 않습니다.

## 구조

```
dist/                 GitHub Pages / Cloudflare Pages에 그대로 배포
  index.html          기존 네이비·화이트 데스크톱 화면
  app.js              검색·정렬·필터·차트·CSV/JSON 입력·브리핑
  engine.js           순수 계산/검증 모듈 (브라우저와 Node 공용)
  vendor/             Apache ECharts 5.6.0, 로컬 번들
  data/market.json    실제 데이터만 (현재 empty)
  data/status.json    최근 수집 성공/실패·마지막 기준일
  data/example.json   사용자가 선택할 때만 여는 가상 데이터
config/coverage.json 기존 프로젝트의 10개 종목
scripts/collect.py    승인 파일/HTTPS JSON/인증된 pykrx 어댑터
scripts/validate.mjs  운영 데이터 검증
.github/workflows/    수집·GitHub Pages 배포 준비 파일
```

기존 프로젝트에는 21종목이 아닌 10종목만 들어 있었습니다. 이를 보존했습니다. 회사명·종목코드의 최신 변경은 운영 연결 때 공급자 마스터와 대조해야 합니다. 커버리지는 `config/coverage.json` 수정 후 `dist/data/coverage.json`에도 반영합니다. 현재 GitHub 사용자 저장소/사용자 Cloudflare 계정과는 연결되어 있지 않습니다. Sites 배포와 해당 계정으로의 배포는 별개입니다.

## 구현 상태

| 기능 | 상태 |
|---|---|
| 8개 투자주체·금액·수량 입력 구조 | 구현 |
| 당일, 5·10·20·60일, 정규화 비율·지속성·가속도 | 구현·계산 테스트 |
| A·B 및 외인 신규·C·D·E | 구현·임계값 변경 가능 |
| F | 확인된 이벤트 입력 + 거래량 배수 계산만 구현. 자동 이벤트 수집·패시브 금액 차감 없음 |
| 주가·20/60MA·상대수익률·거래량·수급 차트 | ECharts 구현, 입력 파일로 동작 |
| KOSPI/업종 비교 | 입력 지수로 계산. 업종지수 미입력 시 계산 보류 |
| 점수·브리핑·복사·현재 표 내보내기 | 구현 (검증 전 탐색 점수) |
| 자동 수집 | 파일/HTTPS 어댑터 검증. pykrx 라이브 호출은 인증 없음/빈 응답으로 실패 |
| GitHub Actions | 실행 파일 준비. 실제 저장소/Secrets 연결 전 실행 안 됨 |
| 휴장일 | 공급자 거래일 목록으로 내부 누락 검사. 새 기준일이 없으면 이전 기준일 유지. 공식 휴장 캘린더 미연결로 휴장과 지연을 단정하지 않음 |
| 백테스트 | 미구현. 시점보존·종목 편입이력·이벤트 중복 정책 확보 후 Phase 3 |

## 실제 데이터 연결 (추천 순서)

### 1. 사용 권한이 있는 CSV/JSON

대시보드의 **실제 데이터 불러오기**에서 파일을 선택합니다. 로컬 메모리에서 계산하며 서버로 업로드하지 않습니다. 새로고침하면 운영 JSON으로 돌아갑니다.

CSV는 출처·가격기준·잠정/확정 여부를 선택해야 합니다. CSV의 거래일 목록은 파일에서 추론하므로 **모든 종목에서 동시에 누락된 날짜를 검출할 수 없습니다.** 운영 연결에는 명시적 공급자 거래일 목록이 있는 JSON 또는 CLI를 사용하세요.

원본 KRX 다운로드 엑셀을 자동 인식하는 기능은 없습니다. 정규화 스키마에 맞추는 단계가 필요합니다. 정규화된 공급자 파일이 있으면 인증정보 없이도 차트·지표를 사용할 수 있습니다.

```bash
python scripts/collect.py --provider file --input /path/to/approved-dataset.json
node scripts/validate.mjs dist/data/market.json
```

CSV를 운영 JSON으로 바꾸려면 출처를 담은 `meta.json`, 날짜 문자열 배열인 `trading_dates.json`을 함께 제공합니다.

```bash
python scripts/collect.py --provider file --input /path/to/approved.csv --meta /path/to/meta.json --calendar /path/to/trading_dates.json
```

### 2. 승인된 공급자의 HTTPS 정규화 JSON

GitHub Secrets에 `FLOW_DATASET_URL`과 필요시 `FLOW_DATASET_TOKEN`을 설정합니다. 키나 비밀번호를 프런트엔드, 저장소, 채팅에 넣지 않습니다. 리다이렉트에 자격 증명을 전달하지 않으며 30초 시간제한, 30MB 크기제한을 적용합니다.

```bash
python scripts/collect.py --provider https
```

### 3. pykrx 1.2.9 (조건부 어댑터)

KRX 공식 Open API 키와 KRX Data Marketplace 로그인은 **다른 인증 방식**입니다. 이 어댑터는 `KRX_ID`/`KRX_PW`를 사용합니다. 비공식 수집 라이브러리의 정상 응답은 보장되지 않습니다. 공급자의 사용 목적·공개·재배포 허용 범위를 확인한 뒤 `FLOW_DATA_USE_CONFIRMED=true`로 설정합니다. 개인 리서치와 업무/공개 서비스의 이용조건은 같다고 가정하지 않습니다.

```bash
python -m venv .venv
.venv/bin/pip install -r scripts/requirements.txt
.venv/bin/python scripts/collect.py --provider pykrx
```

- `KRX_ID`, `KRX_PW`: 본인 환경변수/GitHub Secrets에서만 설정.
- KST 18시 이후 실행. 과거 구간 검증은 `--start YYYYMMDD --end YYYYMMDD` 사용.
- 최소 1초 간격, 요청당 25초 제한. 이는 내부 보수 설정이며 공급자의 승인된 호출한도를 뜻하지 않습니다.
- 일별 세부수급 금액/수량, 원종가, 시총/거래대금, KOSPI, Naver 수정주가 수집 코드.
- `외국인` 분류만 사용하며 `기타외국인`을 임의 합산하지 않습니다.
- `기타 기관` = 원천 `기타금융`. `기타법인`을 포함하지 않습니다.
- 외국인 보유율 = `보유수량 / 상장주식수`. `한도소진률`과 혼용하지 않습니다. 공급자 날짜의 장개시 기준·전일 확정치 성격이므로 당일 종가 시점과 다릅니다.
- 보유율/수량만 못 받으면 null·메타 노트로 표시. 핵심 가격/수급/시총/거래일 누락 시 전체 갱신 중단.
- 인증 실패/빈 응답/중복/누락/역행 데이터 시 마지막 `market.json` 유지, 상태와 로그만 갱신.
- **실제 인증 계정으로 성공한 통합 테스트는 아직 없습니다.** 라이브 테스트에서는 인증 없음과 빈 수급 응답을 확인했습니다.

## 데이터 스키마 v2

```json
{
  "schema_version": 2,
  "meta": {
    "data_kind": "real",
    "source": "원자료 공급자 / 조회 경로",
    "unit": "KRW_100M",
    "benchmark_name": "KOSPI",
    "price_basis": "adjusted",
    "adjustment_as_of": "공급자 수정기준 YYYY-MM-DD",
    "dividend_adjusted": null,
    "status": "final",
    "fetched_at": "ISO 8601 시간대 포함",
    "as_of": "최종 거래일 YYYY-MM-DD",
    "trading_dates": ["공급자 거래일을 오름차순으로 모두 입력"]
  },
  "rows": []
}
```

상기 구조는 **입력 안내용**이며 그대로 검증 통과하는 실제 데이터 예시가 아닙니다.

행 필수: `date,code(6자리 문자열),name,sector(조선/방산/건설기계),close,turnover,marketcap,benchmark`.
`price_basis=adjusted`이면 모든 행에 양수 `adjusted_close` 필수. `raw`이면 `adjusted_close`는 비웁니다. 가격은 원, 시총·거래대금·수급 금액은 **억원**, 거래량·순매수 수량은 주, 보유비율은 %입니다. 빈 값과 0을 구분하세요.

행 선택: `volume,sector_benchmark,pension,foreign,trust,private,financial,insurance,bank,other_institution,foreign_ownership,foreign_ownership_date,available_at`.
각 투자주체의 `*_qty`는 순매수 주식수입니다. 수량은 보존하되 현재 화면은 금액 분석에 집중합니다.

검증된 이벤트만 `events: [{type:"index_change"|"etf_rebalance"|"block_trade", verified:true, source_url:"https://..."}]`로 입력합니다. 이벤트 없이 거래량만 급증해도 패시브로 추정하지 않습니다.

`price_basis`: adjusted/raw/unknown. `dividend_adjusted`: true/false/null. `status`: final/provisional/unknown. 데이터가 실제여도 배당·확정 상태를 확인 못 했으면 null/unknown을 유지합니다. 서로 다른 배당 기준의 종목과 지수를 비교하면 총수익 초과성과가 아니므로 그 한계를 확인하세요.

## 산식

- 상대수익률: `(현재 수정주가/기준 수정주가)/(현재 지수/기준 지수)-1`. **기하 상대수익률 %**이며 기존 산술 차이 %p와 다릅니다. 20거래일 수익률에는 종가 21개가 필요합니다.
- 5·10·20·60일 수급: 해당 수의 마지막 관측치를 합산. 한 값이라도 없으면 null.
- 시총 비율: 기간 순매수 / **최종일 시총** ×100.
- 거래대금 비율: 기간 순매수 / **동일 기간 거래대금 합계** ×100.
- 가속도: 최근5일 합/5 − 직전15일 합/15. 표에는 연기금·외국인 가속도 합계.
- 차트 누적: 선택 시작일을0으로 고정, 다음 날부터 합산. 기간 합계 표와는 첫날 순매수만큼 차이가 납니다.
- MA20·MA60: 전체 이력에서 계산한 뒤 선택기간을 표시합니다. 이력 부족 시 빈 값.
- A/FN: 직전20일(최근5일 제외) 음수, 최근5일 양수, 기본 매수일수3일. B: 양측5·20일 양수. C:20일 상대수익률 음수+한쪽20일 순매수. D: 외국인 최근5일 양수+가속. E:직전20일 매수→최근5일 매도 또는 양측5일 매도. 모든 탐지의 최소금액·강도 등은 UI에서 조정합니다.
- 랭킹: 전체 유효 커버리지(필터 적용 전)에서 시총 대비 연기금20일, 외인20일, 합산 가속도/시총, 평균 매수 지속성, 괴리 정도를 각각 z-score 표준화, ±3 제한. `50+(50/3)*가중평균`. 초기30/25/20/15/10. 3종목 미만·필수값 없음은 점수 보류. 동률 지표는0, 중립점수50. **검증 전 탐색 지표**, 매수 추천 확률 아님.

## 배포

### Cloudflare Pages + 사용자 GitHub

1. 사용자 GitHub 저장소에 이 소스 트리를 업로드합니다. `.openai/hosting.json`은 Sites 전용이며 Cloudflare 배포에는 필요하지 않습니다.
2. Cloudflare Pages에서 저장소 연결, 브랜치 `main`, Framework preset `None`, Build command 비움, Output directory `dist`.
3. GitHub 데이터 갱신 커밋마다 Cloudflare가 재배포합니다. 무료 데이터의 공개·재배포를 허용한다고 가정하지 마세요. 비공개 저장소도 Pages 웹사이트의 비공개 접근을 보장하지 않습니다. 개인 전용이면 Cloudflare Access 등 별도 접근제어가 필요합니다.

### GitHub Pages

Settings → Pages → Source: GitHub Actions. 저장소 변수 `FLOW_PAGES_DEPLOY=true`일 때만 `deploy-pages.yml`이 실행됩니다. 상대경로 자산을 사용하므로 저장소 하위 경로를 지원합니다. 수집 workflow_run 완료 후에도 최신 main을 배포하므로 실패 상태표시를 반영할 수 있습니다.

### 자동 수집 (아직 미활성)

`.github/workflows/update-data.yml`: 월~금 **18:20 KST**, GitHub 예약 실행은 지연될 수 있습니다. 실제 실행은 사용자 저장소 연결 후 아래 변수를 설정해야 합니다.

- `FLOW_AUTO_UPDATE=true`
- `FLOW_PROVIDER=https` 또는 `pykrx`
- pykrx 사용 시 `FLOW_DATA_USE_CONFIRMED=true` 및 KRX_ID/PW Secrets
- HTTPS 공급자 사용 시 FLOW_DATASET_URL/TOKEN Secrets

공급자의 제공 시점이 익일인 서비스는 장 마감 수집에서 당일 데이터가 나오지 않을 수 있습니다. 수집 시각을 서비스 명세에 맞춰 수정하세요. 공식 휴장 캘린더·실제 제공 지연을 검증하기 전에는 18:20을 운영 보장 시각으로 표현하지 않습니다. 기존 날짜를 오늘 날짜로 바꾸지 않습니다.

Secrets는 `dist`에 절대 포함하지 않습니다. `logs/collection.jsonl`에는 비밀을 제거한 결과만 기록합니다. 로그 보존/용량 정책은 운영 규모에 따라 추가할 수 있습니다. 데이터 크기가 큰 경우 Git 커밋 대신 승인된 저장소/오브젝트 스토리지를 사용하도록 확장하세요.

## 검증

```bash
npm test
python -m unittest discover -s tests -p 'test_*.py'
node scripts/validate.mjs dist/data/market.json
```

실제 데이터 접근을 검증하는 테스트와 합성 단위 테스트를 구분합니다. 합성 테스트 데이터는 운영 파일에 게시하지 않습니다. UI 검증은 명시적 예시 모드에서 수행하며 실제 가격 연결 완료의 근거로 삼지 않습니다.

## 백테스트 확장 전 요구사항

시점별 `available_at`, 당시 커버리지 편입/퇴출 이력, 상장폐지 데이터, 당시 공시 가능한 수정주가/수급 확정치, 거래비용·시그널 다음 거래일 체결 규칙, 종목/시그널별 쿨다운과 중복 이벤트 처리 필요. 현재 10종목 고정·현재 재수정 이력을 과거에 소급해 성과를 제시하지 않습니다. 5/20/60일 이벤트 초과수익·승률·MDD는 이러한 자료 확보 전까지 화면에 제시하지 않습니다.

## 데이터 확인 기록 (2026-10-23)

- KRX Open API: 인증키·API별 승인 필요. 공개 서비스 목록에서 투자자 세부수급·외국인 보유율을 확인하지 못함.
- 공식 이용약관: 키당 일10,000회 이하, 비상업적 목적, 제3자 제공 제한, 출처 표시 등 조건. 업무·공개 서비스에 적용 가능한 권한은 별도 확인 필요.
- 라이브 pykrx1.2.9: KRX_ID/PW 미설정 로그인 실패, 2026-10-19~22 한화오션 수급 조회 빈 응답. 운영 JSON은 빈 상태 유지.
- 인증된 공식 API/pykrx 호출한도·정확한 제공지연·수정주가 배당처리·업종지수 매핑은 미검증.

출처:
- https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp
- https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd
- https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO002.jsp
- https://github.com/sharebook-kr/pykrx
- https://developers.cloudflare.com/pages/get-started/git-integration/

Apache ECharts는 차트 렌더러이며 데이터 공급원이 아닙니다. 번들 라이선스는 `dist/vendor/ECHARTS-LICENSE.txt` 참조.
