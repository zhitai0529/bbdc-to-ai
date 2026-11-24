from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.bbdc_schema import study_date
from src.config import load_config
from src.dashboard import DashboardAPI
from src.dashboard_data import dashboard, review_path
from src.exporter import export_review
from src.parser import WordRecord
from src.pipeline import process_payload
from src.runtime import PROJECT_ROOT


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.config = replace(load_config(PROJECT_ROOT / 'config.example.yaml'), root=root,
                              state_dir=root / 'cache', output_dir=root / 'out')
        self.day = study_date(datetime.now(self.config.timezone))
        self.api = DashboardAPI()
        p = patch('src.desktop_api.load_config', return_value=self.config)
        p.start()
        self.addCleanup(p.stop)

    def populate(self, day: date, records: list[tuple[str, str, str]]):
        process_payload([{'wd': spelling, 'ah': ah, 'rh': rh, 'st': 4, 'ut': f'{day} 12:00:00'}
                         for spelling, ah, rh in records], self.config, day, announce=False)

    def test_dates_promotions_unknown_codes_and_missing_days(self):
        earlier = self.day - timedelta(days=4)
        self.populate(earlier, [('repeat', '110', 'B')])
        self.populate(self.day, [('repeat', '110', 'B'), ('known', '0', 'A'), ('unknown', '999', 'C')])
        snap = self.api.initialize()['data']
        self.assertEqual([r['day'] for r in snap['series']], [earlier.isoformat(), self.day.isoformat()])
        self.assertEqual([snap['stats'][k] for k in ('total','mastered','hard','fuzzy','promoted')], [3,1,2,0,1])
        self.assertIn('其中跨天惯犯自动提级：1 个', snap['prompt'])
        self.assertEqual(snap['unknown'][0]['examples'], 'unknown')
        self.assertEqual(snap['repeats'][0]['days'], 2)
        past = self.api.select_day(earlier.isoformat())
        self.assertEqual(past['stats']['promoted'], 0)
        self.assertEqual(past['sidebar']['total'], 3)
        self.assertEqual(past['repeats'], [])

    def test_imported_markdown_is_readable_without_database(self):
        self.config.output_dir.mkdir()
        path = review_path(self.config.output_dir, self.day)
        path.write_text('# 旧复习', encoding='utf-8-sig')
        state = dashboard(self.config)
        self.assertEqual(state['prompt'], '# 旧复习')
        self.assertIsNone(state['stats'])
        self.assertFalse(self.config.history_path.exists())
        self.api.save_prompt(self.day.isoformat(), '# 旧复习', '# 修订')
        with self.assertRaises(ValueError):
            self.api.save_prompt(self.day.isoformat(), '# 旧复习', '# 过时编辑')
        self.assertEqual(path.read_text(encoding='utf-8'), '# 修订')

    def test_older_exports_fill_dashboard_without_creating_word_history(self):
        yesterday = self.day - timedelta(days=1)
        earlier = self.day - timedelta(days=2)
        self.populate(self.day, [('repeat', '110', 'B')])
        # Simulate an older version writing to the same output folder, from another profile.
        old = export_review([
            WordRecord('repeat', level='hard'),
            WordRecord('known', level='mastered', source='bbdc-android-5.11.8', raw_rating='0'),
        ], self.config.output_dir, yesterday)
        legacy = (PROJECT_ROOT / 'examples/synthetic_review.md').read_text(encoding='utf-8')
        review_path(self.config.output_dir, earlier).write_text(
            legacy.replace('2026-11-12', earlier.isoformat()), encoding='utf-8-sig')
        original_history = self.config.history_path.read_bytes()
        original_export = old.read_bytes()
        current = dashboard(self.config)
        self.assertEqual([(row['day'], row['total']) for row in current['series']],
                         [(earlier.isoformat(), 4), (yesterday.isoformat(), 2), (self.day.isoformat(), 1)])
        self.assertIsNone(current['series'][0]['promoted'])
        self.assertEqual(current['stats']['promoted'], 0)
        self.assertEqual(current['repeats'], [])
        previous = dashboard(self.config, yesterday.isoformat())
        self.assertTrue(previous['stats']['export_summary'])
        self.assertEqual(previous['stats']['mastered'], 1)
        self.assertEqual(previous['sidebar']['total'], 1)
        self.assertIsNone(previous['stats']['latest'])
        self.assertIn('复习 Prompt', previous['prompt'])
        self.assertEqual(self.config.history_path.read_bytes(), original_history)
        self.assertEqual(old.read_bytes(), original_export)

    def test_dashboard_prefers_recorded_history_and_ignores_inconsistent_export(self):
        yesterday = self.day - timedelta(days=1)
        earlier = self.day - timedelta(days=2)
        self.populate(yesterday, [('valid', '110', 'B')])
        export_review([WordRecord('obsolete', level='hard')] * 2, self.config.output_dir, yesterday)
        path = export_review([WordRecord('unconfirmed')], self.config.output_dir, earlier)
        path.write_text(path.read_text(encoding='utf-8').replace('顽固词：0 个', '顽固词：2 个'),
                        encoding='utf-8')
        current = dashboard(self.config)
        self.assertEqual([(row['day'], row['total']) for row in current['series']], [(yesterday.isoformat(), 1)])
        self.assertIn(earlier.isoformat(), current['dates'])
        invalid = dashboard(self.config, earlier.isoformat())
        self.assertIsNone(invalid['stats'])
        self.assertIn('复习 Prompt', invalid['prompt'])

    def test_offline_startup_and_cancellation(self):
        with patch('src.desktop_jobs.discover_mumu_manager') as discover, patch('src.desktop_jobs.ExportJob') as worker:
            self.api.initialize()
            worker.assert_not_called()
            self.api.start('export')
            discover.assert_not_called()
            worker.assert_called_once_with(sync=False, setup=False, manager=None)
            with self.assertRaises(ValueError):
                self.api.start('sync')
            self.api._close()
            worker.return_value.request_cancel.assert_called_once()

    def test_sync_and_setup_use_discovery_and_remembered_manager(self):
        manager = Path(self.tmp.name) / 'MuMuManager.exe'
        manager.touch()
        with patch('src.desktop_jobs.discover_mumu_manager', side_effect=[None, manager]), \
                patch('src.desktop_jobs.remember_mumu_manager') as remember, patch('src.desktop_jobs.ExportJob') as worker:
            self.assertEqual(self.api.start('setup')['status'], 'choose')
            self.api.start('sync')
            worker.assert_called_once_with(sync=True, setup=False, manager=manager)
            remember.assert_called_once_with(manager)

    def test_only_confined_iso_date_can_be_saved(self):
        with self.assertRaises(ValueError):
            self.api.save_prompt('../private', '', 'oops')

    def test_bad_history_does_not_hide_existing_review(self):
        self.config.history_path.parent.mkdir()
        self.config.history_path.write_bytes(b'not a database')
        self.config.output_dir.mkdir()
        review_path(self.config.output_dir, self.day).write_text('saved prompt', encoding='utf8')
        snapshot = self.api.initialize()['data']
        self.assertIn('历史库暂时无法读取', snapshot['warning'])
        self.assertEqual(snapshot['prompt'], 'saved prompt')
