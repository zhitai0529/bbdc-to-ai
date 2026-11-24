from dataclasses import replace
from datetime import date
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from src.config import PROJECT_ROOT, load_config
from src.dashboard_data import review_path
from src.flutter_window import FlutterAPI, serve


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
            startup, status = self.call_host(('start', ['export']), ('poll', []))

        self.assertEqual(startup['result']['status'], 'started')
        self.assertEqual(status['result']['status'], 'running')
        discover.assert_not_called()
        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=1)
        self.assertTrue(captured['output'].closed)
        self.assertFalse(captured['scratch'].exists())
        self.assertEqual(self.api.poll()['status'], 'idle')
        with self.assertRaises(ValueError):
            self.api.start('export')
