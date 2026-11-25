"""Own one desktop job per window and its selected MuMu installation."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from src.desktop_worker import ExportJob
from src.mumu_diagnostics import recovery_actions
from src.mumu_installation import discover_mumu_manager, manager_in_location, remember_mumu_manager


class DesktopJobs:
    def __init__(self) -> None:
        self._lock = RLock()
        self._job: ExportJob | None = None
        self._manager: Path | None = None
        self._closed = False

    @contextmanager
    def idle(self) -> Iterator[None]:
        with self._lock:
            if self._closed or self._job is not None:
                raise ValueError('请等待当前任务结束后再试。')
            yield

    def select_manager(self, folder: Path) -> None:
        manager = manager_in_location(folder)
        if manager is None:
            raise ValueError('这个文件夹里找不到 MuMu 管理程序。'
                             '请右键 MuMu 的桌面快捷方式，选择「打开文件所在的位置」，再选择显示的文件夹。')
        self._manager = manager

    def start(self, action: str) -> dict:
        with self.idle():
            if action not in {'setup', 'sync', 'export'}:
                raise ValueError('无法识别的操作。')
            manager = None
            warning = ''
            if action != 'export':
                manager = self._manager
                if manager is None or not manager.is_file():
                    manager = discover_mumu_manager()
                if manager is None:
                    return {'status': 'choose'}
                self._manager = manager
                try:
                    remember_mumu_manager(manager)
                except (OSError, ValueError):
                    warning = '已找到 MuMu，可以继续。若下次未自动找到，请重新选择安装位置。'
            try:
                self._job = ExportJob(sync=action == 'sync', setup=action == 'setup', manager=manager)
            except OSError as exc:
                raise ValueError('无法启动后台任务。请关闭并重新打开助手后再试。') from exc
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
            message, day = result.message, None
            if result.status == 'exported' and result.output:
                day = result.output.name[:10]
                message = (f'{day} 同步完成，新增 {result.new_word_count} 个词。' if result.sync
                           else f'{day} 的复习已导出。')
                message += f'待复习词共 {result.target_word_count} 个。可在「复习预览」查看。'
            elif result.status == 'no_records':
                message = (f'{result.day} 同步后暂无可导出的学习记录。请在 App 完成一组学习后再同步。' if result.sync
                           else f'本机还没有 {result.day} 的学习记录，请先点击「同步 MuMu」。')
                if result.last_day:
                    message += f'最近的学习日为 {result.last_day}。'
            elif result.status == 'mumu_missing':
                self._manager = None
            elif result.status == 'cancelled':
                message = '本次同步已停止。可再次点击「同步 MuMu」。'
            return {'status': result.status, 'message': message, 'day': day, 'lines': lines,
                    'reason': result.reason, 'recovery': list(recovery_actions(result.status, result.reason))}

    def cancel_sync(self) -> dict[str, str]:
        with self._lock:
            job = self._job
            if job is None or not job.sync or job.setup:
                return {'status': 'idle'}
            return {'status': 'cancelling' if job.request_sync_cancel() else 'finishing'}

    def close(self, hide: Callable[[], None] | None = None) -> str | None:
        with self._lock:
            self._closed = True
            job = self._job
            self._job = None
        if job is None:
            return None
        try:
            if hide is not None:
                hide()
        finally:
            try:
                if job.sync and not job.setup:
                    job.request_sync_cancel()
                else:
                    job.request_cancel()
            finally:
                result = job.wait_for_result()
        return result.message if result.status == 'error' else None
