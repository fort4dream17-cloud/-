import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('freshness', Path(__file__).resolve().parents[1] / 'scripts/check-freshness.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FreshnessTests(unittest.TestCase):
    def test_status_success_does_not_hide_stale_payload(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); data = root / 'dist/data'; data.mkdir(parents=True)
            (data / 'status.json').write_text(json.dumps({'status': 'success', 'as_of': '2026-10-26'}))
            (data / 'market.json').write_text(json.dumps({'meta': {'as_of': '2026-10-23'}}))
            self.assertFalse(module.inspect(root, 'legacy', '2026-10-26', '2026-10-26')['ok'])

    def test_unknown_provider_session_never_skips(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(module.inspect(Path(d), 'legacy', None, '2026-10-26')['ok'])

    def test_index_needs_prices_flows_and_today_disclosures(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); data = root / 'dist/data'; data.mkdir(parents=True)
            for status, payload in [('index-status.json', 'index-market.json'), ('price-status.json', 'index-price-history.json')]:
                (data / status).write_text(json.dumps({'status': 'success', 'as_of': '2026-10-26'}))
                (data / payload).write_text(json.dumps({'meta': {'as_of': '2026-10-26'}}))
            path = data / 'disclosure-status.json'
            path.write_text(json.dumps({'status': 'success', 'checked_at': '2026-10-25T20:00:00+09:00'}))
            self.assertFalse(module.inspect(root, 'index', '2026-10-26', '2026-10-26')['ok'])
            path.write_text(json.dumps({'status': 'success', 'checked_at': '2026-10-26T20:00:00+09:00'}))
            self.assertTrue(module.inspect(root, 'index', '2026-10-26', '2026-10-26')['ok'])
            (data / 'index-status.json').write_text(json.dumps({'status': 'success', 'as_of': '2026-10-26', 'daily_flow_failed_codes': ['005930']}))
            self.assertFalse(module.inspect(root, 'index', '2026-10-26', '2026-10-26')['ok'])

    def test_verified_previous_session_can_be_valid_on_holiday(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); data = root / 'dist/data'; data.mkdir(parents=True)
            (data / 'status.json').write_text(json.dumps({'status': 'delayed_or_closed', 'as_of': '2026-10-23'}))
            (data / 'market.json').write_text(json.dumps({'meta': {'as_of': '2026-10-23'}}))
            self.assertTrue(module.inspect(root, 'legacy', '2026-10-23', '2026-10-26')['ok'])
