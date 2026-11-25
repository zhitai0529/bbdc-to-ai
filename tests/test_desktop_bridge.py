from dataclasses import replace
from datetime import date
from io import StringIO
import json
from pathlib import Path
from subprocess import TimeoutExpired
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import Mock, patch

from src.config import PROJECT_ROOT, load_config
from src.dashboard_data import review_path
from src.flutter_window import FlutterAPI, serve
from src.mumu_diagnostics import SyncError
from src.parser import WordRecord
from src.review_cache import ReviewCache
from src.sync_session import begin_sync_save, claim_sync_stop


class DesktopBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = replace(load_config(PROJECT_ROOT / 'config.example.yaml'), root=self.root,
                              output_dir=self.root / 'reviews', state_dir=self.root / 'data')
        self.api = FlutterAPI()
        config = patch('src.desktop_api.load_config', return_value=self.config)
        config.start()
        self.addCleanup(config.stop)

    def call_host(self, *commands: tuple[str, list[str]]) -> list[dict]:
        requests = StringIO(''.join(json.dumps({'id': index, 'method': method, 'args': args}) + '\n'
                                    for index, (method, args) in enumerate(commands)))
        replies = StringIO()
        serve(self.api, requests, replies)
        return [json.loads(line) for line in replies.getvalue().splitlines()]

    def test_review_level_round_trips_without_changing_existing_markdown(self) -> None:
        config = self.root / 'config.yaml'
        template = (PROJECT_ROOT / 'config.example.yaml').read_text(encoding='utf-8')
        original = template.replace('review_level: postgrad\n', '')
        config.write_text(original, encoding='utf-8')
        day = date(2026, 11, 25).isoformat()
        settings = load_config(config)
        settings.output_dir.mkdir()
        path = review_path(settings.output_dir, date.fromisoformat(day))
        path.write_text('# 已保存的复习', encoding='utf-8')
        with patch('src.desktop_files.default_config_path', return_value=config), \
                patch('src.desktop_api.load_config', side_effect=lambda: load_config(config)):
            before, saved, rejected, after = self.call_host(
                ('select_day', [day]), ('save_review_level', ['cet4']),
                ('save_review_level', ['invalid']), ('select_day', [day]),
            )
        self.assertEqual(before['result']['review_level'], 'postgrad')
        self.assertIsNone(saved['result'])
        self.assertIn('review_level', rejected['error'])
        self.assertEqual(after['result']['review_level'], 'cet4')
        self.assertEqual(load_config(config).output_dir, settings.output_dir)
        self.assertEqual(config.read_text(encoding='utf-8').replace('review_level: "cet4"\n', ''), original)
        self.assertEqual(after['result']['prompt'], '# 已保存的复习')
        self.assertEqual(path.read_text(encoding='utf-8'), '# 已保存的复习')

    def test_exercise_bridge_exports_for_selected_day_and_keeps_daily_settings(self) -> None:
        day = date(2026, 11, 23)
        cache = ReviewCache(self.config, day)
        cache.path.parent.mkdir()
        cache.save([WordRecord('verify', '核实', level='hard')])
        day_text = day.isoformat()
        snapshot, invalid, exported, after = self.call_host(
            ('select_day', [day_text]), ('export_exercise', ['20261123', 'cet4', 'cloze']),
            ('export_exercise', [day_text, 'cet4', 'cloze']), ('select_day', [day_text]),
        )
        self.assertEqual(len(snapshot['result']['exercise_types']), 6)
        self.assertIn('有效的学习日期', invalid['error'])
        result = exported['result']
        self.assertEqual(result['filename'], f'{day_text}_bbdc_exercise_cet4_cloze.md')
        self.assertEqual(result['markdown'], (self.config.output_dir / result['filename']).read_text(encoding='utf-8'))
        self.assertEqual(after['result']['review_level'], self.config.review_level)
        self.assertIsNone(after['result']['prompt'])

    def test_failed_sync_forwards_diagnostic_and_leaves_local_preview_available(self) -> None:
        day = date(2026, 11, 23)
        self.config.output_dir.mkdir()
        path = review_path(self.config.output_dir, day)
        prompt = '# 已保存的复习内容'
        path.write_text(prompt, encoding='utf-8')
        manager = self.root / 'MuMuManager.exe'
        diagnostic = {'status': 'error', 'reason': 'android_unsupported',
                      'message': '请启动 Android 15 实例。'}
        process = Mock()
        process.poll.return_value = 1

        def start_worker(_command, *, stdout, **_options):
            stdout.write(json.dumps(diagnostic).encode('utf-8'))
            return process

        with patch('src.desktop_jobs.discover_mumu_manager', return_value=manager), \
                patch('src.desktop_jobs.remember_mumu_manager'), \
                patch('src.desktop_worker.subprocess.Popen', side_effect=start_worker):
            first, start, failure, after = self.call_host(
                ('select_day', [day.isoformat()]), ('start', ['sync']), ('poll', []),
                ('select_day', [day.isoformat()]),
            )

        self.assertEqual(start['result']['status'], 'started')
        for key, value in diagnostic.items():
            self.assertEqual(failure['result'][key], value)
        self.assertEqual(failure['result']['recovery'], ['download'])
        self.assertIsNone(failure['result']['day'])
        self.assertEqual(first['result']['prompt'], prompt)
        self.assertEqual(after['result']['prompt'], prompt)
        self.assertEqual(path.read_text(encoding='utf-8'), prompt)

    def test_offline_worker_is_independent_and_cancelled_at_window_exit(self) -> None:
        process = Mock()
        process.poll.return_value = None
        captured = {}

        def start_worker(command, *, stdout, **_options):
            self.assertEqual(command[1:], ['-m', 'src.offline_export', '--json'])
            captured['output'] = stdout
            return process

        def create_scratch(**options):
            directory = TemporaryDirectory(**options)
            self.addCleanup(directory.cleanup)
            captured['scratch'] = Path(directory.name)
            return directory

        with patch('src.desktop_jobs.discover_mumu_manager') as discover, \
                patch('src.desktop_worker.subprocess.Popen', side_effect=start_worker), \
                patch('src.desktop_worker.TemporaryDirectory', side_effect=create_scratch):
            startup, cancellation, status = self.call_host(
                ('start', ['export']), ('cancel_sync', []), ('poll', []),
            )

        self.assertEqual(startup['result']['status'], 'started')
        self.assertEqual(cancellation['result']['status'], 'idle')
        self.assertEqual(status['result']['status'], 'running')
        discover.assert_not_called()
        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=1)
        self.assertTrue(captured['output'].closed)
        self.assertFalse(captured['scratch'].exists())
        self.assertEqual(self.api.poll()['status'], 'idle')
        with self.assertRaises(ValueError):
            self.api.start('export')

    def test_sync_can_be_cancelled_and_restarted_without_closing_window(self) -> None:
        manager = self.root / 'MuMuManager.exe'
        manager.touch()
        process = Mock()
        process.poll.return_value = None
        cleanup_started, can_finish = Event(), Event()

        def cleanup(session, stop_worker):
            if not cleanup_started.is_set():
                self.assertTrue((session / 'cancel').is_file())
                cleanup_started.set()
                can_finish.wait(5)
            stop_worker()

        with patch('src.desktop_jobs.discover_mumu_manager', return_value=manager), \
                patch('src.desktop_jobs.remember_mumu_manager'), \
                patch('src.desktop_worker.subprocess.Popen', return_value=process) as start, \
                patch('src.mumu_connection.cancel_mumu_sync', side_effect=cleanup) as stop:
            self.assertEqual(self.api.start('sync')['status'], 'started')
            try:
                self.assertEqual(self.api.cancel_sync()['status'], 'cancelling')
                self.assertTrue(cleanup_started.wait(5))
                self.assertEqual(self.api.cancel_sync()['status'], 'cancelling')
                self.assertEqual(self.api.poll()['status'], 'running')
                with self.assertRaises(ValueError):
                    self.api.start('sync')
            finally:
                can_finish.set()
                self.api._jobs._job.cancellation.result(timeout=5)
            result = self.api.poll()
            self.assertEqual(result['status'], 'cancelled')
            self.assertIn('本次同步已停止', result['message'])
            self.assertIsNone(result['day'])
            self.assertEqual(self.api.cancel_sync()['status'], 'idle')
            stop.assert_called_once()
            self.assertEqual(self.api.start('sync')['status'], 'started')
            self.assertEqual(start.call_count, 2)
            self.api._close()

    def test_stop_request_during_publication_preserves_successful_result(self) -> None:
        manager = self.root / 'MuMuManager.exe'
        process = Mock()
        process.poll.return_value = None
        output = review_path(self.config.output_dir, date(2026, 11, 25))

        def saving_worker(command, *, stdout, **_options):
            begin_sync_save(Path(command[command.index('--scratch-dir') + 1]))
            reply = {'status': 'exported', 'output': str(output), 'new_word_count': 2, 'target_word_count': 2}
            stdout.write(json.dumps(reply).encode('utf-8'))
            return process

        with patch('src.desktop_jobs.discover_mumu_manager', return_value=manager), \
                patch('src.desktop_jobs.remember_mumu_manager'), \
                patch('src.desktop_worker.subprocess.Popen', side_effect=saving_worker):
            self.assertEqual(self.api.start('sync')['status'], 'started')
            self.assertEqual(self.api.cancel_sync()['status'], 'finishing')
            process.poll.return_value = 0
            result = self.api.poll()
        process.kill.assert_not_called()
        self.assertEqual(result['status'], 'exported')
        self.assertEqual(result['day'], '2026-11-25')

    def test_closing_during_publication_hides_window_and_allows_save_to_finish(self) -> None:
        manager = self.root / 'MuMuManager.exe'
        process = Mock()
        process.poll.return_value = None
        hide = Mock()
        captured = {}

        def saving_worker(command, *, stdout, **_options):
            session = Path(command[command.index('--scratch-dir') + 1])
            begin_sync_save(session)
            captured.update(session=session, output=stdout)
            return process

        def finish(**kwargs):
            hide.assert_called_once_with()
            self.assertGreater(kwargs['timeout'], 0)
            self.assertLessEqual(kwargs['timeout'], 240)
            self.assertFalse((captured['session'] / 'cancel').exists())
            captured['output'].write(b'{"status":"no_records","day":"2026-11-25"}')
            return 2

        process.wait.side_effect = finish
        with patch('src.desktop_jobs.discover_mumu_manager', return_value=manager), \
                patch('src.desktop_jobs.remember_mumu_manager'), \
                patch('src.desktop_worker.subprocess.Popen', side_effect=saving_worker):
            self.assertEqual(self.api.start('sync')['status'], 'started')
            self.assertIsNone(self.api._jobs.close(hide))
        process.kill.assert_not_called()
        self.assertTrue(captured['output'].closed)
        self.assertFalse(captured['session'].exists())

    def test_closing_during_stalled_publication_uses_worker_timeout(self) -> None:
        manager = self.root / 'MuMuManager.exe'
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [TimeoutExpired('worker', 0), 1]

        def stalled_worker(command, **_options):
            begin_sync_save(Path(command[command.index('--scratch-dir') + 1]))
            return process

        with patch('src.desktop_jobs.discover_mumu_manager', return_value=manager), \
                patch('src.desktop_jobs.remember_mumu_manager'), \
                patch('src.desktop_worker.subprocess.Popen', side_effect=stalled_worker), \
                patch('src.desktop_worker.time.monotonic', side_effect=[100, 340]):
            self.assertEqual(self.api.start('sync')['status'], 'started')
            self.assertIn('操作超时', self.api._jobs.close())
        self.assertEqual(process.wait.call_args_list[0].kwargs, {'timeout': 0})
        process.kill.assert_called_once_with()

    def test_cancellation_claim_prevents_worker_from_starting_publication(self) -> None:
        self.assertTrue(claim_sync_stop(self.root))
        with self.assertRaisesRegex(SyncError, '已停止'):
            begin_sync_save(self.root)
        self.assertFalse((self.root / 'saving').exists())
