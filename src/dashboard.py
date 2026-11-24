"""The local WebView window and its narrow JS-to-Python interface."""
from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import date
import os
from pathlib import Path
from threading import RLock
import webbrowser

from filelock import FileLock

from src.config import load_config
from src.dashboard_data import dashboard, review_path
from src.desktop_files import latest_review, save_output_dir
from src.desktop_worker import ExportJob
from src.mumu_installation import discover_mumu_manager, manager_in_location, remember_mumu_manager
from src.runtime import PROJECT_ROOT
from src.storage import atomic_write
from src.version import VERSION


class DashboardAPI:
    def __init__(self, warning: str | None = None, auto_export: bool = False, latest: bool = False):
        self._lock = RLock()
        self._job: ExportJob | None = None
        self._closed = False
        self._window = None
        self._warning = warning
        self._auto_export = auto_export
        self._latest = latest
        self._manager: Path | None = None

    def initialize(self) -> dict:
        config = load_config()
        path = latest_review(config.output_dir) if self._latest else None
        return {'data': dashboard(config, path.name[:10] if path else None),
                'warning': self._warning, 'export': self._auto_export}

    def select_day(self, day: str | None) -> dict:
        return dashboard(load_config(), day)

    def copy(self, content: str) -> None:
        import pyperclip
        if content:
            pyperclip.copy(content)

    def save_prompt(self, day: str, original: str, content: str) -> None:
        config = load_config()
        path = review_path(config.output_dir, date.fromisoformat(day))
        with self._lock:
            self._idle()
            config.state_dir.mkdir(parents=True, exist_ok=True)
            with FileLock(str(config.state_dir / '.pipeline.lock'), timeout=5):
                if path.read_text(encoding='utf-8-sig') != original:
                    raise ValueError('复习文件已在其他窗口更新，请先复制你的编辑，再重新打开该日期。')
                atomic_write(path, content)

    def open_folder(self) -> None:
        folder = load_config().output_dir
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def _choose(self, initial: str = '') -> Path | None:
        import webview
        selection = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=initial)
        return Path(selection[0]) if selection else None

    def change_folder(self) -> bool:
        with self._lock:
            self._idle()
            folder = self._choose(str(load_config().output_dir))
            if folder is not None:
                save_output_dir(folder)
            return folder is not None

    def locate_manager(self) -> bool:
        with self._lock:
            self._idle()
            folder = self._choose()
            if folder is None:
                return False
            manager = manager_in_location(folder)
            if not manager:
                raise ValueError('所选文件夹内未找到 MuMu 管理程序，请选择 MuMu 安装目录。')
            self._manager = manager
            return True

    def download_mumu(self) -> None:
        if not webbrowser.open('https://mumu.163.com/'):
            raise OSError('请在浏览器中打开 https://mumu.163.com/ 下载 MuMu。')

    def _idle(self) -> None:
        if self._closed or self._job is not None:
            raise ValueError('请等待当前任务结束。')

    def start(self, action: str) -> dict:
        with self._lock:
            self._idle()
            if action not in {'setup', 'sync', 'export'}:
                raise ValueError('无法识别的操作。')
            manager = None
            warning = ''
            if action != 'export':
                manager = self._manager
                if not manager or not manager.is_file():
                    manager = discover_mumu_manager()
                if manager is None:
                    return {'status': 'choose'}
                self._manager = manager
                try:
                    remember_mumu_manager(manager)
                except (OSError, ValueError):
                    warning = '本次已找到 MuMu，安装位置未能保存。'
            self._job = ExportJob(sync=action == 'sync', setup=action == 'setup', manager=manager)
            return {'status': 'started', 'message': warning}

    def poll(self) -> dict:
        with self._lock:
            job = self._job
            if job is None:
                return {'status': 'idle'}
            progress = Path(job.scratch.name) / 'setup-progress.txt'
            try:
                lines = progress.read_text(encoding='utf-8').splitlines()
            except (OSError, UnicodeError):
                lines = []
            result = job.poll()
            if result is None:
                return {'status': 'running', 'lines': lines}
            self._job = None
            message = result.message
            day = None
            if result.status == 'exported' and result.output:
                day = result.output.name[:10]
                message = (f'同步完成，新增 {result.new_word_count} 个词。' if result.sync else '今日复习已导出。')
                message += f'复习词表共 {result.target_word_count} 个。'
            elif result.status == 'no_records':
                message = f'{result.day} 暂无学习记录。'
                if result.last_day:
                    message += f'最近学习日为 {result.last_day}。'
            elif result.status == 'mumu_missing':
                self._manager = None
            if result.sync and not day:
                path = latest_review(load_config().output_dir)
                day = path.name[:10] if path else None
            return {'status': result.status, 'message': message, 'day': day, 'lines': lines}

    def _close(self) -> None:
        with self._lock:
            self._closed = True
            if self._job:
                self._job.request_cancel()
                if self._window is not None:
                    self._window.hide()
                # Keep the parent alive until its owned instance and worker are stopped.
                result = self._job.cancellation.result()
                self._job = None
                if result.status == 'error':
                    import ctypes
                    ctypes.windll.user32.MessageBoxW(None, result.message, '关闭助手', 0x30)


def page_html() -> str:
    folder = PROJECT_ROOT / 'frontend'
    template = (folder / 'index.html').read_text(encoding='utf-8')
    css = (folder / 'bundle.css').read_text(encoding='utf-8')
    js = (folder / 'bundle.js').read_text(encoding='utf-8').replace('</script', r'<\/script')
    return template.replace('/* bundled css */', css).replace('/* bundled js */', js)


def main(argv: Sequence[str] | None = None, *, startup_warning: str | None = None) -> None:
    parser = argparse.ArgumentParser(description='不背单词复习助手')
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--open-latest', action='store_true')
    args = parser.parse_args(argv)
    open_window(DashboardAPI(startup_warning, args.export, args.open_latest))


def open_window(api: DashboardAPI, ready: Callable | None = None) -> None:
    import webview

    webview.settings['ALLOW_FILE_URLS'] = False
    window = webview.create_window(f'不背单词复习助手 v{VERSION}', html=page_html(), js_api=api,
                                   width=1380, height=900, min_size=(860, 600), background_color='#0B0F19')
    api._window = window
    window.events.closing += api._close
    webview.start(ready, (window,), gui='edgechromium')
