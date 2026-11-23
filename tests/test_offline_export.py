from __future__ import annotations

from contextlib import redirect_stdout
from datetime import date, datetime
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import yaml

from src.config import PROJECT_ROOT, load_config
from src.offline_export import main
from src.pipeline import process_payload


DAY = date(2026, 11, 23)


class OfflineExportTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.source = root / 'config.yaml'
        settings = yaml.safe_load((PROJECT_ROOT / 'config.yaml').read_text(encoding='utf-8-sig'))
        settings.update(state_dir='./state', output_dir='./output', raw_dump_dir='./raw')
        self.source.write_text(yaml.safe_dump(settings, allow_unicode=True), encoding='utf-8')
        self.config = load_config(self.source)

    def run_export(self, *args: str) -> tuple[int, dict[str, object]]:
        output = StringIO()
        with redirect_stdout(output):
            code = main(['--config', str(self.source), '--json', *args])
        return code, json.loads(output.getvalue())

    def save_word(self, word: str, day: date, hour: int, *, fuzzy: bool = False) -> None:
        payload = [{'wd': word, 'st': 4, 'ut': f'{day} {hour:02d}:00:00',
                    'ah': '110' if fuzzy else '210', 'rh': 'B' if fuzzy else 'D', 'meaning': '测试用词'}]
        process_payload(payload, self.config, day, announce=False)

    def test_rebuild_from_merged_cache_into_current_output_location(self) -> None:
        self.save_word('first batch', DAY, 10)
        self.save_word('second batch', DAY, 15)
        settings = yaml.safe_load(self.source.read_text(encoding='utf-8'))
        settings['output_dir'] = './new_output'
        self.source.write_text(yaml.safe_dump(settings, allow_unicode=True), encoding='utf-8')
        cache = self.config.state_dir / f'{DAY}.json'
        original_cache = cache.stat().st_mtime_ns, cache.read_bytes()
        original_history = self.config.history_path.stat().st_mtime_ns, self.config.history_path.read_bytes()

        code, result = self.run_export('--date', str(DAY))
        self.assertEqual(code, 0)
        self.assertEqual(result['status'], 'exported')
        self.assertEqual(result['new_word_count'], 0)
        self.assertEqual(result['target_word_count'], 2)
        self.assertEqual(result['latest_saved_at'], '2026-11-23T15:00:00+08:00')
        destination = load_config(self.source).output_dir / f'{DAY}_bbdc_review.md'
        self.assertEqual(result['output'], str(destination))
        content = destination.read_text(encoding='utf-8')
        self.assertIn('| first batch |', content)
        self.assertIn('| second batch |', content)
        self.assertFalse(self.config.raw_dump_dir.exists())
        self.assertEqual((cache.stat().st_mtime_ns, cache.read_bytes()), original_cache)
        self.assertEqual((self.config.history_path.stat().st_mtime_ns, self.config.history_path.read_bytes()),
                         original_history)

    def test_no_records_reports_previous_day_without_exporting_it(self) -> None:
        previous = DAY.replace(day=22)
        self.save_word('previous', previous, 12)
        previous_file = self.config.output_dir / f'{previous}_bbdc_review.md'
        previous_file.unlink()
        code, result = self.run_export('--date', str(DAY))
        self.assertEqual(code, 2)
        self.assertEqual(result, {'status': 'no_records', 'day': str(DAY), 'last_day': str(previous)})
        self.assertFalse(previous_file.exists())
        self.assertFalse((self.config.output_dir / f'{DAY}_bbdc_review.md').exists())

    def test_default_date_before_four_am_uses_previous_study_day(self) -> None:
        previous = DAY.replace(day=22)
        self.save_word('previous', previous, 12)
        with patch('src.offline_export.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 23, 3, 59, tzinfo=self.config.timezone)
            code, result = self.run_export()
        self.assertEqual(code, 0)
        self.assertTrue(str(result['output']).endswith(f'{previous}_bbdc_review.md'))

    def test_offline_export_counts_today_only_once_for_escalation(self) -> None:
        self.save_word('repeat', DAY.replace(day=22), 12)
        self.save_word('repeat', DAY, 12, fuzzy=True)
        self.save_word('first time', DAY, 13, fuzzy=True)
        code, result = self.run_export('--date', str(DAY))
        self.assertEqual(code, 0)
        content = Path(result['output']).read_text(encoding='utf-8')
        self.assertIn('其中跨天惯犯自动提级：1 个', content)
        hard, fuzzy = content.split('### fuzzy_words', maxsplit=1)
        self.assertIn('| repeat |', hard)
        self.assertIn('| first time |', fuzzy)


if __name__ == '__main__':
    unittest.main()
