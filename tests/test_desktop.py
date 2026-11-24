from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import yaml

from src.config import PROJECT_ROOT, load_config
from src.desktop import ReviewWindow, legacy_main as main
from src.desktop_files import latest_review, load_output_dir, save_output_dir
from src.desktop_mumu import MumuDialogs
from src.desktop_worker import ExportJob, ExportJobResult, parse_result
from src.pipeline import process_payload


class DesktopTests(unittest.TestCase):
    def test_open_folder_opens_current_export_directory(self) -> None:
        with TemporaryDirectory() as folder:
            window = ReviewWindow.__new__(ReviewWindow)
            window.output_dir = Path(folder) / '复习文件'
            with patch('src.desktop.os.startfile', create=True) as explorer:
                window.open_folder()
            self.assertTrue(window.output_dir.is_dir())
            explorer.assert_called_once_with(window.output_dir)

    def test_startup_and_legacy_view_flag_only_schedule_local_preview(self) -> None:
        for args in ([], ['--open-latest']):
            with self.subTest(args=args), patch('src.desktop.tk.Tk') as tk, patch('src.desktop.ReviewWindow') as window:
                main(args)
                tk.return_value.after_idle.assert_called_once_with(window.return_value.open_latest)
                tk.return_value.after.assert_not_called()

    def test_only_view_button_requests_sync(self) -> None:
        window = ReviewWindow.__new__(ReviewWindow)
        window.job = None
        window.mumu = Mock()
        manager = Path('MuMuManager.exe')
        window.mumu.select_manager.return_value = manager
        with patch.object(window, 'start_export') as start:
            window.sync_and_view()
            start.assert_called_once_with(sync=True, manager=manager)
            start.reset_mock()
            window.export()
            start.assert_called_once_with(sync=False)

    def test_mumu_setup_button_starts_only_after_confirmation(self) -> None:
        window = ReviewWindow.__new__(ReviewWindow)
        window.root = Mock()
        window.job = None
        window.mumu = Mock()
        manager = Path('MuMuManager.exe')
        window.mumu.select_manager.return_value = manager
        window.mumu.confirm_setup.side_effect = [False, True]
        with patch.object(window, 'start_export') as start:
            window.configure_mumu()
            start.assert_not_called()
            window.configure_mumu()
            start.assert_called_once_with(sync=False, setup=True, manager=manager)

    def test_missing_mumu_offers_official_download_without_starting_setup(self) -> None:
        window = ReviewWindow.__new__(ReviewWindow)
        window.root = Mock()
        window.status = Mock()
        window.job = None
        window.mumu = MumuDialogs(window.root, window.status.set)
        with patch('src.desktop_mumu.discover_mumu_manager', return_value=None), \
                patch('src.desktop_mumu.messagebox.askyesnocancel', side_effect=[None, False]) as prompt, \
                patch.object(window, 'start_export') as start, \
                patch('src.desktop_mumu.webbrowser.open', return_value=True) as browser:
            window.configure_mumu()
            browser.assert_not_called()
            window.configure_mumu()
            browser.assert_called_once_with('https://mumu.163.com/')
            start.assert_not_called()
            self.assertEqual(prompt.call_args.args[0], '查找 MuMu 安装位置')

    def test_manually_located_mumu_is_saved_and_original_action_continues(self) -> None:
        window = ReviewWindow.__new__(ReviewWindow)
        window.root = Mock()
        window.status = Mock()
        window.job = None
        window.mumu = MumuDialogs(window.root, window.status.set)
        folder = Path.cwd() / 'MuMu'
        manager = folder / 'nx_main' / 'MuMuManager.exe'
        with patch('src.desktop_mumu.discover_mumu_manager', return_value=None), \
                patch('src.desktop_mumu.messagebox.askyesnocancel', return_value=True), \
                patch('src.desktop_mumu.filedialog.askdirectory', return_value=str(folder)), \
                patch('src.desktop_mumu.manager_in_location', return_value=manager) as find, \
                patch('src.desktop_mumu.remember_mumu_manager') as remember, \
                patch('src.desktop_mumu.messagebox.askokcancel', return_value=True), \
                patch.object(window, 'start_export') as start:
            window.configure_mumu()
            find.assert_called_once_with(folder)
            remember.assert_called_once_with(manager)
            start.assert_called_once_with(sync=False, setup=True, manager=manager)

    def test_invalid_mumu_folder_is_not_saved(self) -> None:
        window = ReviewWindow.__new__(ReviewWindow)
        window.root = Mock()
        window.status = Mock()
        window.job = None
        window.mumu = MumuDialogs(window.root, window.status.set)
        with patch('src.desktop_mumu.discover_mumu_manager', return_value=None), \
                patch('src.desktop_mumu.messagebox.askyesnocancel', return_value=True), \
                patch('src.desktop_mumu.filedialog.askdirectory', return_value=str(Path.cwd())), \
                patch('src.desktop_mumu.manager_in_location', return_value=None), \
                patch('src.desktop_mumu.remember_mumu_manager') as remember, \
                patch('src.desktop_mumu.messagebox.showwarning') as showwarning, \
                patch.object(window, 'start_export') as start:
            window.sync_and_view()
            remember.assert_not_called()
            start.assert_not_called()
            showwarning.assert_called_once()

    def test_setup_job_keeps_review_preview_and_shows_result(self) -> None:
        window = ReviewWindow.__new__(ReviewWindow)
        window.root = Mock()
        window.job = None
        window.status = Mock()
        window.mumu = MumuDialogs(window.root, window.status.set)
        with patch('src.desktop.ExportJob') as job, patch.object(window, 'set_busy'), \
                patch.object(window, 'clear_preview') as clear_preview:
            window.start_export(sync=False, setup=True)
            job.assert_called_once_with(sync=False, setup=True, manager=None)
            clear_preview.assert_not_called()
        with patch('src.desktop_mumu.messagebox.showinfo') as popup:
            guidance = '连接已就绪。请在 App 登录后点击「同步 MuMu」。'
            window.show_result(ExportJobResult('configured', False, message=guidance, setup=True))
            self.assertEqual(popup.call_args.args[0], '配置完成')
            self.assertEqual(popup.call_args.args[1], guidance)
        window.status.set.assert_called_with(guidance)

    def test_setup_error_explains_the_failure(self) -> None:
        window = ReviewWindow.__new__(ReviewWindow)
        window.root = Mock()
        window.status = Mock()
        window.mumu = MumuDialogs(window.root, window.status.set)
        with patch('src.desktop_mumu.messagebox.showwarning') as popup:
            window.show_result(ExportJobResult('error', False, message='请先安装不背单词。', setup=True))
        popup.assert_called_once_with('MuMu 配置未完成', '请先安装不背单词。', parent=window.root)

    def test_android_version_error_offers_official_update(self) -> None:
        root = Mock()
        dialogs = MumuDialogs(root, Mock())
        guidance = '当前实例是 Android 12。请在多开器新建 Android 15 实例。'
        with patch('src.desktop_mumu.messagebox.askyesno', return_value=True) as prompt, \
                patch('src.desktop_mumu.webbrowser.open', return_value=True) as browser:
            dialogs.show_result(ExportJobResult('error', False, message=guidance, setup=True,
                                                reason='android_unsupported'))
        self.assertIn(guidance, prompt.call_args.args[1])
        browser.assert_called_once_with('https://mumu.163.com/')

    def test_incompatible_manager_can_be_reselected_without_restart(self) -> None:
        root = Mock()
        dialogs = MumuDialogs(root, Mock())
        replacement = Path.cwd() / '另一个安装目录' / 'MuMuManager.exe'
        guidance = '无法读取 MuMu 实例列表，请检查 Windows 版 MuMu 安装。'
        with patch.object(dialogs, '_choose_folder', return_value=replacement) as locate, \
                patch('src.desktop_mumu.remember_mumu_manager') as remember:
            dialogs.show_result(ExportJobResult('error', True, message=guidance,
                                                reason='manager_incompatible'))
        locate.assert_called_once_with(guidance)
        remember.assert_called_once_with(replacement)
        self.assertEqual(dialogs.manager, replacement)

    def test_failed_sync_keeps_current_review_preview(self) -> None:
        window = ReviewWindow.__new__(ReviewWindow)
        window.root = Mock()
        window.job = None
        window.closing = False
        window.status = Mock()
        window.content = '已有复习'
        window.mumu = Mock()
        result = ExportJobResult('error', True, message='请打开 MuMu 后重试。', reason='manager_unavailable')
        with patch('src.desktop.ExportJob') as job, patch.object(window, 'set_busy'), \
                patch.object(window, 'clear_preview') as clear_preview:
            job.return_value.poll.return_value = result
            window.start_export(sync=True)
            window.poll()
            clear_preview.assert_not_called()
        window.mumu.show_result.assert_called_once_with(result)
        self.assertEqual(window.content, '已有复习')

    def test_app_missing_retry_reuses_automatically_found_manager_after_restart(self) -> None:
        with TemporaryDirectory() as folder:
            profile = Path(folder).resolve()
            manager = profile / 'MuMuManager.exe'
            manager.touch()
            first = MumuDialogs(Mock(), Mock())
            with patch('src.mumu_installation.data_directory', return_value=profile), \
                    patch('src.mumu_installation._default_locations', side_effect=[[manager], []]) as defaults, \
                    patch('src.desktop_mumu.messagebox.showwarning') as warning, \
                    patch('src.desktop_mumu.messagebox.askyesnocancel') as prompt:
                self.assertEqual(first.select_manager(), manager)
                result = parse_result(3, '{"status":"app_missing","message":"同一实例内安装"}',
                                      sync=False, setup=True)
                first.show_result(result)
                self.assertIn('请安装不背单词', warning.call_args.args[0])
                self.assertEqual(warning.call_args.args[1], '同一实例内安装')
                self.assertEqual(first.select_manager(), manager)
                restarted = MumuDialogs(Mock(), Mock())
                self.assertEqual(restarted.select_manager(), manager)
                defaults.assert_called_once()
                prompt.assert_not_called()

    def test_worker_passes_selected_manager_path_to_setup_and_sync(self) -> None:
        manager = Path.cwd() / '自定义 安装' / 'MuMuManager.exe'
        for sync, setup in ((True, False), (False, True)):
            with self.subTest(sync=sync, setup=setup), patch('src.desktop_worker.subprocess.Popen') as run:
                job = ExportJob(sync=sync, setup=setup, manager=manager)
                self.addCleanup(job.cleanup)
                self.assertEqual(run.call_args.args[0][-2:], ['--mumu-manager', str(manager)])

    def test_folder_picker_updates_directory_and_refreshes_preview(self) -> None:
        window = ReviewWindow.__new__(ReviewWindow)
        window.root = Mock()
        window.job = None
        window.output_dir = Path.cwd()
        window.location_text = Mock()
        selected = Path.cwd() / 'new reviews'
        with patch('src.desktop.filedialog.askdirectory', return_value=str(selected)), \
                patch('src.desktop.save_output_dir', return_value=selected) as save, \
                patch.object(window, 'open_latest') as refresh:
            window.change_folder()
        save.assert_called_once_with(selected)
        self.assertEqual(window.output_dir, selected)
        window.location_text.set.assert_called_once_with(str(selected))
        refresh.assert_called_once()

    def test_worker_dispatches_offline_and_sync_to_different_modules(self) -> None:
        for sync in (False, True):
            with self.subTest(sync=sync), patch('src.desktop_worker.subprocess.Popen') as run:
                run.return_value.poll.return_value = 2
                job = ExportJob(sync=sync)
                job.output.write(b'{"status": "no_records", "day": "2026-11-23"}')
                result = job.poll()
                self.assertEqual(result, ExportJobResult('no_records', sync, day='2026-11-23'))
                command = run.call_args.args[0]
                self.assertEqual(command[2:4], ['src.mumu' if sync else 'src.offline_export', '--json'])
                self.assertEqual(command[4:6], ['--sync-mumu', '--latest'] if sync else [])

    def test_closing_busy_window_cancels_active_job(self) -> None:
        window = ReviewWindow.__new__(ReviewWindow)
        window.root = Mock()
        window.job = Mock()
        window.job.poll.return_value = ExportJobResult('cancelled', True)
        window.close()
        window.job.request_cancel.assert_called_once_with()
        window.root.withdraw.assert_called_once_with()
        window.root.destroy.assert_not_called()
        window.poll()
        window.root.destroy.assert_called_once_with()

    def test_cancel_kills_owned_job_and_removes_scratch(self) -> None:
        with patch('src.desktop_worker.subprocess.Popen') as run:
            process = run.return_value
            process.poll.return_value = None
            job = ExportJob(sync=True)
            scratch = Path(job.scratch.name)
            (scratch / 'snapshot.sqlite').touch()
            self.assertIsNone(job.poll())
            job.request_cancel()
            self.assertIsNotNone(job.cancellation)
            self.assertEqual(job.cancellation.result(timeout=5), ExportJobResult('cancelled', True))
            process.kill.assert_called_once_with()
            process.wait.assert_called_once_with(timeout=1)
            self.assertTrue(job.output.closed)
            self.assertFalse(scratch.exists())

    def test_selected_folder_persists_and_is_used_for_both_reports(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / 'config.yaml'
            settings = yaml.safe_load((PROJECT_ROOT / 'config.yaml').read_text(encoding='utf-8-sig'))
            settings.update(output_dir='./output', state_dir='./state', raw_dump_dir='./raw',
                            write_unknown_codes_report=True)
            config_text = yaml.safe_dump(settings, allow_unicode=True, sort_keys=False)
            source.write_text(config_text.replace('output_dir: ./output', 'output_dir: ./output # 保留此注释'),
                              encoding='utf-8')
            original = load_config(source)
            original.output_dir.mkdir()
            old_review = original.output_dir / '2026-11-22_bbdc_review.md'
            old_review.write_text('原来的复习', encoding='utf-8')
            selected = root / "英语笔记 #1's"
            selected.mkdir()

            self.assertEqual(save_output_dir(selected, source), selected)
            self.assertEqual(load_output_dir(source), selected)
            changed = load_config(source)
            self.assertEqual(changed.history_path, original.history_path)
            self.assertEqual(changed.state_dir, original.state_dir)
            self.assertEqual(changed.raw_dump_dir, original.raw_dump_dir)
            self.assertIn(' # 保留此注释', source.read_text(encoding='utf-8'))
            self.assertIsNone(latest_review(selected))

            day = date(2026, 11, 23)
            rows = [{'wd': 'obstinate', 'ut': '2026-11-23 12:00:00', 'st': 4,
                     'ah': '210', 'rh': 'D', 'meaning': '顽固的'},
                    {'wd': 'opaque', 'ut': '2026-11-23 12:00:00', 'st': 4,
                     'ah': '999', 'rh': 'C', 'meaning': '不透明的'}]
            result = process_payload(rows, changed, day, announce=False)
            self.assertEqual(result.output, selected / '2026-11-23_bbdc_review.md')
            self.assertEqual(result.unknown_report, selected / '2026-11-23_unknown_codes.md')
            self.assertEqual(latest_review(selected), result.output)
            self.assertEqual(latest_review(original.output_dir), old_review)
            self.assertEqual(old_review.read_text(encoding='utf-8'), '原来的复习')


if __name__ == '__main__':
    unittest.main()
