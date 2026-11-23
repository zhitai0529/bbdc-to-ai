from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
import json
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from unittest.mock import Mock
import yaml

from src.config import load_config
from src.interceptor import BBDCInterceptor, is_target_host
from src.parser import parse_payload
from src.pipeline import process_payload
from src.storage import save_raw

ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026, 11, 12)


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        directory = Path(self.temp.name)
        self.config = replace(load_config(), root=directory, raw_dump_dir=directory / 'raw', state_dir=directory / 'state',
                              output_dir=directory / 'output')
        self.payload = json.loads((ROOT / 'tests/fixtures/synthetic_response.json').read_text(encoding='utf-8'))

    def test_conservative_classification_and_dates(self) -> None:
        result = parse_payload(self.payload, self.config, DAY)
        self.assertEqual({word.spelling: word.level for word in result.words},
                         {'obstinate': 'hard', 'ambiguous': 'fuzzy', 'apple': 'mastered', 'opaque': 'unclassified'})
        self.assertEqual(result.skipped_other_date, 1)
        self.assertEqual(result.skipped_undated, 1)

    def test_numeric_direction_and_error_precedence(self) -> None:
        rules = deepcopy(self.config.parser)
        rules.update(numeric_proficiency_enabled=True, higher_is_better=False,
                     hard_threshold=4, mastered_threshold=1, error_counts_enabled=True)
        config = replace(self.config, parser=rules)
        payload = [{'word': 'high', 'stage': 5, 'learned_at': '2026-11-12'},
                   {'word': 'low', 'stage': 0, 'learned_at': '2026-11-12'},
                   {'word': 'middle', 'stage': 2, 'learned_at': '2026-11-12'},
                   {'word': 'mistaken', 'recognition': '认识', 'wrong_count': 4, 'learned_at': '2026-11-12'},
                   {'word': 'unknown', 'recognition': '不认识', 'wrong_count': 1, 'learned_at': '2026-11-12'}]
        result = parse_payload(payload, config, DAY)
        self.assertEqual([word.level for word in result.words], ['hard', 'mastered', 'fuzzy', 'hard', 'hard'])

    def test_nested_mapping_and_utc_milliseconds(self) -> None:
        rules = deepcopy(self.config.parser)
        rules['record_paths'] = ['data.items']
        rules['fields']['recognition'] = ['progress.status']
        rules['fields']['learned_at'] = ['progress.time']
        milliseconds = datetime.fromisoformat('2026-11-11T16:10:00+00:00').timestamp() * 1000
        payload = {'data': {'items': [{'word': {'spelling': 'nested', 'meaning': '嵌套'},
                                      'progress': {'status': '不认识', 'time': milliseconds}}]}}
        result = parse_payload(payload, replace(self.config, parser=rules), DAY)
        self.assertEqual(len(result.words), 1)
        self.assertEqual(result.words[0].level, 'hard')
        self.assertEqual(result.words[0].meaning, '嵌套')

    def test_duplicate_sync_and_newer_state(self) -> None:
        first = process_payload(self.payload, self.config, DAY, announce=False)
        again = process_payload(self.payload, self.config, DAY, announce=False)
        self.assertEqual(len(first.words), len(again.words))
        self.assertEqual(again.words[0].spelling, 'ambiguous')
        update = [{'spelling': 'obstinate', 'recognition': '认识', 'error_count': 0,
                   'learned_at': '2026-11-12T10:00:00+08:00'}]
        process_payload(update, self.config, DAY, announce=False)
        old = process_payload(self.payload, self.config, DAY, announce=False)
        obstinate = next(word for word in old.words if word.spelling == 'obstinate')
        self.assertEqual(obstinate.level, 'mastered')
        self.assertEqual(obstinate.meaning, '顽固的')
        self.assertEqual(obstinate.errors, 0)

    def test_export_excludes_mastered_and_persists_restart(self) -> None:
        result = process_payload(self.payload, self.config, DAY, announce=False)
        self.assertIsNotNone(result.output)
        text = result.output.read_text(encoding='utf-8')
        self.assertIn('obstinate', text)
        self.assertIn('ambiguous', text)
        self.assertNotIn('apple', text)
        self.assertNotIn('opaque', text)
        self.assertIn('├──', text)
        self.assertIn('熟练掌握：1', text)
        restored = process_payload([{'word': 'extra', 'recognition': '模糊', 'learned_at': '2026-11-12'}],
                                   self.config, DAY, announce=False)
        self.assertEqual(len(restored.words), 5)

    def test_bad_dates_and_nonword_json_do_not_become_today(self) -> None:
        for payload in (None, 'text', {'token': 'secret'}, [1, 2]):
            self.assertEqual(parse_payload(payload, self.config, DAY).words, [])
        result = parse_payload([{'word': 'broken', 'learned_at': 'not a date', 'recognition': '认识'}],
                               self.config, DAY)
        self.assertEqual(result.skipped_invalid_date, 1)
        self.assertEqual(result.words, [])

    def test_configuration_change_does_not_mix_old_classifications(self) -> None:
        process_payload(self.payload, self.config, DAY, announce=False)
        rules = deepcopy(self.config.parser)
        rules['error_counts_enabled'] = True
        with self.assertRaisesRegex(ValueError, '配置已变化'):
            process_payload(self.payload, replace(self.config, parser=rules), DAY, announce=False)

    def test_raw_dump_names_no_query_or_overwrite(self) -> None:
        now = datetime.now(self.config.timezone)
        one = save_raw(self.config.raw_dump_dir, '/api/sync?token=secret', {'ok': 1}, now)
        two = save_raw(self.config.raw_dump_dir, '/api/sync?token=secret', {'ok': 2}, now)
        self.assertNotEqual(one, two)
        self.assertNotIn('secret', one.name)
        self.assertIn('api_sync', one.name)
        self.assertEqual(json.loads(one.read_text(encoding='utf-8')), {'ok': 1})

    def test_domain_boundary_and_malformed_response(self) -> None:
        for host in ('bbdc.cn', 'api.bbdc.cn', 'API.BBDC.CN.'):
            self.assertTrue(is_target_host(host))
        for host in ('evilbbdc.cn', 'bbdc.cn.evil.example', 'example.org'):
            self.assertFalse(is_target_host(host))
        addon = BBDCInterceptor()
        addon.config = self.config
        flow = Mock()
        flow.request.pretty_host = 'api.bbdc.cn'
        flow.request.path = '/test'
        flow.response.headers = {'content-type': 'Application/JSON; charset=utf-8'}
        flow.response.get_content.return_value = b'{invalid'
        addon.response(flow)  # 不抛出异常
        flow.response.get_content.return_value = b'{"ok":true}'
        addon.response(flow)
        self.assertEqual(len(list(self.config.raw_dump_dir.glob('*.json'))), 1)
        flow.request.pretty_host = 'evilbbdc.cn'
        addon.response(flow)
        self.assertEqual(len(list(self.config.raw_dump_dir.glob('*.json'))), 1)

    def test_real_mitmdump_offline_addon_loading_and_export(self) -> None:
        from mitmproxy import connection, http, io
        directory = Path(self.temp.name)
        current = datetime.now(self.config.timezone)
        payload = {'data': {'words': [{'word': 'integration', 'meaning': '集成',
                                      'recognition': '不认识', 'learned_at': current.isoformat()}]}}
        flow = http.HTTPFlow(connection.Client(peername=('127.0.0.1', 12345), sockname=('127.0.0.1', 8888)),
                             connection.Server(address=('api.bbdc.cn', 443)))
        flow.request = http.Request.make('GET', 'https://api.bbdc.cn/api/test?token=not_saved')
        flow.response = http.Response.make(200, json.dumps(payload).encode(), {'Content-Type': 'application/json'})
        flow_file = directory / 'test.mitm'
        with flow_file.open('wb') as handle:
            io.FlowWriter(handle).add(flow)
        settings = yaml.safe_load((ROOT / 'config.yaml').read_text(encoding='utf-8'))
        settings.update(mode='auto', raw_dump_dir=str(self.config.raw_dump_dir),
                        output_dir=str(self.config.output_dir), state_dir=str(self.config.state_dir))
        config_file = directory / 'config.yaml'
        config_file.write_text(yaml.safe_dump(settings, allow_unicode=True), encoding='utf-8')
        mitmdump = Path(sysconfig.get_path('scripts')) / ('mitmdump.exe' if sys.platform == 'win32' else 'mitmdump')
        completed = subprocess.run([str(mitmdump), '-n', '-r', str(flow_file),
                                    '-s', str(ROOT / 'src/interceptor.py'), '--set', f'bbdc_config={config_file}',
                                    '--set', f'confdir={directory / "certs"}'],
                                   capture_output=True, timeout=30)
        self.assertEqual(completed.returncode, 0, (completed.stdout + completed.stderr).decode(errors='replace'))
        self.assertEqual(len(list(self.config.raw_dump_dir.glob('*.json'))), 1)
        output = self.config.output_dir / f'{current.date().isoformat()}_bbdc_review.md'
        self.assertTrue(output.is_file(), (completed.stdout + completed.stderr).decode(errors='replace'))
        self.assertIn('integration', output.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
