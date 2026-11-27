"""Window-independent commands for the desktop review assistant."""
from __future__ import annotations

from collections.abc import Callable
from datetime import date
import os
from pathlib import Path
import webbrowser

from src.config import Config, load_config
from src.dashboard_data import dashboard
from src.desktop_files import latest_review, save_output_dir, save_review_level, save_review_prompt
from src.desktop_jobs import DesktopJobs
from src.exercise import ExerciseExport, exercise_types, export_exercise as generate_exercise
from src.mumu_diagnostics import MUMU_DOWNLOAD_URL
from src.range_review import RangeExport, export_range_review as generate_range_review
from src.review_cache import ReviewCache
from src.review_protection import review_confirmation, valid_revision


def _parse_study_day(day: str) -> date:
    try:
        selected = date.fromisoformat(day)
        if day == selected.isoformat():
            return selected
    except (TypeError, ValueError) as exc:
        raise ValueError('请选择有效的学习日期。') from exc
    raise ValueError('请选择有效的学习日期。')


class DesktopAPI:
    def __init__(self, warning: str | None = None, auto_export: bool = False, latest: bool = False):
        self._jobs = DesktopJobs()
        self._warning = warning
        self._auto_export = auto_export
        self._latest = latest

    def initialize(self) -> dict:
        config = load_config()
        path = latest_review(config.output_dir) if self._latest else None
        return {'data': self._view_data(config, path.name[:10] if path else None),
                'warning': self._warning, 'export': self._auto_export}

    def select_day(self, day: str | None) -> dict:
        return self._view_data(load_config(), day)

    @staticmethod
    def _view_data(config: Config, day: str | None) -> dict:
        return {**dashboard(config, day), 'exercise_types': exercise_types()}

    def save_prompt(self, day: str, original: str, content: str) -> None:
        with self._jobs.idle():
            save_review_prompt(load_config(), date.fromisoformat(day), original, content)

    def save_review_level(self, level: str) -> None:
        with self._jobs.idle():
            save_review_level(level)

    def export_exercise(self, day: str, level: str, kind: str) -> ExerciseExport:
        selected = _parse_study_day(day)
        with self._jobs.idle():
            return generate_exercise(load_config(), selected, level, kind)

    def export_range_review(self, day: str, days: int) -> RangeExport:
        with self._jobs.idle():
            return generate_range_review(load_config(), _parse_study_day(day), days)

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

    def start(self, action: str, day: str | None = None, mode: str | None = None,
              revision: str | None = None) -> dict:
        selected = _parse_study_day(day) if day is not None else None
        if mode is not None and (action != 'export' or selected is None):
            raise ValueError('请选择要导出的学习日期。')
        if mode in ('copy', 'overwrite'):
            if not valid_revision(revision):
                raise ValueError('请重新点击「导出复习」确认文件版本。')
            return self._jobs.start(action, day=selected, choice=mode, revision=revision)
        if mode not in (None, 'check') or revision is not None:
            raise ValueError('无法识别的导出选项。')
        with self._jobs.idle():
            if action == 'export' and selected is not None:
                config = load_config()
                if ReviewCache(config, selected).path.is_file():
                    try:
                        revision = review_confirmation(config, selected, has_draft=mode == 'check')
                    except OSError as exc:
                        raise ValueError('无法核对原复习文件。请检查导出目录是否可访问，或关闭占用该文件的程序。') from exc
                    if revision is not None:
                        return {'status': 'confirm_export', 'day': selected.isoformat(), 'revision': revision,
                                'message': f'{selected} 已有草稿、手动修改，或来自旧版本的复习文件。'
                                           '可另存新生成的内容，或确认覆盖原文件。'}
            return self._jobs.start(action, day=selected)

    def poll(self) -> dict:
        return self._jobs.poll()

    def cancel_sync(self) -> dict[str, str]:
        return self._jobs.cancel_sync()

    def _close(self, hide: Callable[[], None] | None = None) -> None:
        if message := self._jobs.close(hide):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, '关闭助手', 0x30)
