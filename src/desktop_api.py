"""Window-independent commands for the desktop review assistant."""
from __future__ import annotations

from collections.abc import Callable
from datetime import date
import os
from pathlib import Path
import webbrowser

from src.config import load_config
from src.dashboard_data import dashboard
from src.desktop_files import latest_review, save_output_dir, save_review_prompt
from src.desktop_jobs import DesktopJobs
from src.mumu_diagnostics import MUMU_DOWNLOAD_URL


class DesktopAPI:
    def __init__(self, warning: str | None = None, auto_export: bool = False, latest: bool = False):
        self._jobs = DesktopJobs()
        self._warning = warning
        self._auto_export = auto_export
        self._latest = latest

    def initialize(self) -> dict:
        config = load_config()
        path = latest_review(config.output_dir) if self._latest else None
        return {'data': dashboard(config, path.name[:10] if path else None),
                'warning': self._warning, 'export': self._auto_export}

    def select_day(self, day: str | None) -> dict:
        return dashboard(load_config(), day)

    def save_prompt(self, day: str, original: str, content: str) -> None:
        with self._jobs.idle():
            save_review_prompt(load_config(), date.fromisoformat(day), original, content)

    def open_folder(self) -> None:
        folder = load_config().output_dir
        try:
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(folder)
        except OSError as exc:
            raise ValueError(f'无法打开导出文件夹。请到「MuMu 与设置」检查保存位置：\n{folder}') from exc

    def _choose(self, initial: str = '') -> Path | None:
        raise NotImplementedError

    def change_folder(self) -> bool:
        with self._jobs.idle():
            folder = self._choose(str(load_config().output_dir))
            if folder is not None:
                save_output_dir(folder)
            return folder is not None

    def locate_manager(self) -> bool:
        with self._jobs.idle():
            folder = self._choose()
            if folder is None:
                return False
            self._jobs.select_manager(folder)
            return True

    def download_mumu(self) -> None:
        if not webbrowser.open(MUMU_DOWNLOAD_URL):
            raise OSError(f'无法打开浏览器。请手动访问 {MUMU_DOWNLOAD_URL}。')

    def start(self, action: str) -> dict:
        return self._jobs.start(action)

    def poll(self) -> dict:
        return self._jobs.poll()

    def _close(self, hide: Callable[[], None] | None = None) -> None:
        if message := self._jobs.close(hide):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, '关闭助手', 0x30)
