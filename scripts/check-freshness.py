#!/usr/bin/env python3
"""Check provider-observed sessions; never infer a holiday from stale data."""
import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def inspect(root, scope, expected, today, require_disclosure=True):
    data = root / 'dist/data'
    reasons = []
    observed = {}
    pairs = [('status.json', 'market.json')] if scope == 'legacy' else [
        ('index-status.json', 'index-market.json'),
        ('price-status.json', 'index-price-history.json')]
    if not expected:
        reasons.append('KRX 최신 거래일 확인 실패')
    for status_name, data_name in pairs:
        status, payload = read(data / status_name), read(data / data_name)
        date = payload.get('meta', {}).get('as_of')
        observed[data_name] = date
        allowed = ('success', 'delayed_or_closed') if scope == 'legacy' else ('success',)
        if status.get('status') not in allowed:
            reasons.append(status_name + ': 수집 상태 불량')
        if not expected or date != expected or status.get('as_of') != expected:
            reasons.append(data_name + ': 공급자 최신 거래일과 불일치')
        if status.get('missing_codes') or status.get('daily_flow_failed_codes'):
            reasons.append(status_name + ': 수집 누락 존재')
        if not payload:
            reasons.append(data_name + ': 데이터 없음')
    if scope == 'index' and require_disclosure:
        status = read(data / 'disclosure-status.json')
        observed['disclosure_checked_at'] = status.get('checked_at')
        try:
            checked = datetime.fromisoformat(status['checked_at']).astimezone(ZoneInfo('Asia/Seoul')).date().isoformat()
        except (KeyError, ValueError, TypeError):
            checked = None
        if status.get('status') != 'success' or status.get('failed_codes') or checked != today:
            reasons.append('OpenDART 당일 조회 미완료 또는 일부 실패')
    return {'ok': not reasons, 'reasons': reasons, 'observed': observed}


def provider_session():
    from collect import authenticated_stock, collection_end, now
    stock = authenticated_stock()
    frame = stock.get_index_ohlcv_by_date(
        (now() - timedelta(days=45)).strftime('%Y%m%d'), collection_end(now()), '1001')
    if frame is None or frame.empty:
        raise ValueError('Empty benchmark')
    date = max(str(d)[:10] for d in frame.index)
    if date > now().date().isoformat():
        raise ValueError('Future benchmark')
    return date


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--scope', choices=['index', 'legacy'], required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan', action='store_true')
    mode.add_argument('--verify', action='store_true')
    args = p.parse_args()
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    today = now.date().isoformat()
    plan_file = ROOT / '.cache' / ('freshness-' + args.scope + '.json')
    if args.plan:
        try:
            expected = provider_session()
            error = None
        except Exception as exc:
            expected, error = None, type(exc).__name__
        plan = {'expected_session': expected, 'checked_at': now.isoformat(), 'provider_error': error}
        plan_file.parent.mkdir(parents=True, exist_ok=True)
        plan_file.write_text(json.dumps(plan))
        result = inspect(ROOT, args.scope, expected, today, os.environ.get('GITHUB_EVENT_NAME') != 'push')
        # A previous session on a weekday might be a holiday OR delayed upstream.
        # Retry at later slots rather than declaring the day closed or current.
        unresolved = now.weekday() < 5 and expected != today
        needed = not result['ok'] or unresolved or os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch'
        output = os.environ.get('GITHUB_OUTPUT')
        if output:
            with open(output, 'a') as f:
                f.write('needed=' + str(needed).lower() + '\n')
        print(json.dumps({'needed': needed, **plan, **result}, ensure_ascii=False))
        return 0
    plan = read(plan_file)
    expected = plan.get('expected_session')
    result = inspect(ROOT, args.scope, expected, today, os.environ.get('GITHUB_EVENT_NAME') != 'push')
    unresolved = now.weekday() < 5 and expected and expected < today
    state = 'failed' if not result['ok'] else ('closed_or_provider_delayed' if unresolved else 'current')
    report = {'status': state, 'scope': args.scope, 'checked_at': now.isoformat(),
              'expected_session': expected, 'calendar_basis': 'KRX KOSPI actual observed session; no holiday inference',
              'run_url': 'https://github.com/' + os.environ.get('GITHUB_REPOSITORY', '') + '/actions/runs/' + os.environ.get('GITHUB_RUN_ID', ''),
              **result}
    path = ROOT / 'dist/data' / (args.scope + '-update-monitor.json')
    path.write_text(json.dumps(report, ensure_ascii=False))
    summary = '## 데이터 갱신 검증\n\n' + json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
            f.write(summary)
    print(json.dumps(report, ensure_ascii=False))
    if not result['ok']:
        print('::error::갱신 검증 실패: ' + '; '.join(result['reasons']))
        return 1
    if unresolved:
        print('::warning::KRX 최신 응답은 이전 거래일입니다. 휴장 또는 공급 지연 미확인. 후속 예약에서 다시 확인합니다.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
