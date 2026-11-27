"""运行桌面助手的后台导出进程，并校验返回给窗口的结果。"""
from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass
from datetime import date, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory, TemporaryFile
from threading import Thread
import time
from typing import Literal

from src.config import PROJECT_ROOT
from src.review_protection import ExportChoice
from src.runtime import data_directory, is_packaged
from src.sync_session import claim_sync_stop


@dataclass(frozen=True)
class ExportJobResult:
    status: Literal['exported', 'no_records', 'configured', 'app_missing', 'mumu_missing', 'error', 'cancelled']
    sync: bool
    output: Path | None = None
    message: str | None = None
    day: str | None = None
    last_day: str | None = None
    new_word_count: int | None = None
    target_word_count: int | None = None
    latest_saved_at: datetime | None = None
    setup: bool = False
    reason: str | None = None
    copied: bool = False
    warning: str | None = None


def parse_result(returncode: int, output_text: str, *, sync: bool, setup: bool = False) -> ExportJobResult:
    reply = json.loads(output_text)
    statuses = {0: 'configured', 1: 'error'} if setup else {0: 'exported', 1: 'error', 2: 'no_records'}
    if sync or setup:
        statuses.update({3: 'app_missing', 4: 'mumu_missing'})
    expected_status = statuses.get(returncode)
    if expected_status is None or not isinstance(reply, dict) or reply.get('status') != expected_status:
        raise ValueError('导出程序返回了无效的结果')

    if expected_status == 'exported':
        output = reply.get('output')
        new_count = reply.get('new_word_count')
        target_count = reply.get('target_word_count')
        saved_at = reply.get('latest_saved_at')
        copied = reply.get('copied', False)
        warning = reply.get('warning')
        if (not isinstance(output, str) or not output or type(new_count) is not int
                or type(target_count) is not int or type(copied) is not bool
                or (saved_at is not None and not isinstance(saved_at, str))
                or (warning is not None and not isinstance(warning, str))):
            raise ValueError('导出结果缺少有效的文件路径、词数或记录时间')
        return ExportJobResult(
            'exported', sync, output=Path(output), new_word_count=new_count, target_word_count=target_count,
            latest_saved_at=datetime.fromisoformat(saved_at) if saved_at is not None else None,
            copied=copied, warning=warning,
        )

    if expected_status == 'no_records':
        day, last_day = reply.get('day'), reply.get('last_day')
        if not isinstance(day, str) or (last_day is not None and not isinstance(last_day, str)):
            raise ValueError('导出结果缺少有效的学习日期')
        return ExportJobResult('no_records', sync, day=day, last_day=last_day)

    message = reply.get('message')
    reason = reply.get('reason')
    return ExportJobResult(expected_status, sync,
                           message=message if isinstance(message, str) else None, setup=setup,
                           reason=reason if isinstance(reason, str) else None)


def python_command() -> tuple[str, dict[str, str]]:
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'NO_COLOR': '1'}
    if os.name != 'nt':
        return sys.executable, env
    if sys.prefix != sys.base_prefix:
        # Launch the interpreter directly so the process handle belongs to the job,
        # while CPython still locates the current virtual environment's packages.
        env['__PYVENV_LAUNCHER__'] = sys.executable
        return str(Path(sys._base_executable).with_name('python.exe')), env
    return str(Path(sys.executable).with_name('python.exe')), env


class ExportJob:
    def __init__(self, *, sync: bool, setup: bool = False, manager: Path | None = None,
                 day: date | None = None, choice: ExportChoice | None = None,
                 revision: str | None = None) -> None:
        self.sync = sync
        self.setup = setup
        self.cancellation: Future[ExportJobResult] | None = None
        module = 'src.mumu_setup' if setup else 'src.mumu' if sync else 'src.offline_export'
        packaged = is_packaged()
        # Keep the subprocess's temporary database copies available for parent cleanup.
        self.scratch = TemporaryDirectory(prefix='bbdc-desktop-', ignore_cleanup_errors=True)
        self.result_path = Path(self.scratch.name) / 'result.json'
        self.output = None
        try:
            if packaged:
                command = [sys.executable, '--run-worker', module, str(self.result_path)]
                env = os.environ.copy()
            else:
                executable, env = python_command()
                command = [executable, '-m', module, '--json']
                self.output = TemporaryFile(dir=self.scratch.name)
            if sync:
                command.extend(('--sync-mumu', '--latest'))
            elif not setup and day is not None:
                command.extend(('--date', day.isoformat()))
                if choice is not None and revision is not None:
                    command.extend(('--export-choice', choice, '--expected-revision', revision))
            if sync or setup:
                command.extend(('--scratch-dir', self.scratch.name))
                if manager is not None:
                    command.extend(('--mumu-manager', str(manager)))
            self.process = subprocess.Popen(
                command, cwd=data_directory() if packaged else PROJECT_ROOT,
                stdout=self.output if self.output is not None else subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, env=env,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        except OSError:
            self.cleanup()
            raise
        self.deadline = time.monotonic() + 240

    def poll(self) -> ExportJobResult | None:
        if self.cancellation is not None:
            return self.cancellation.result() if self.cancellation.done() else None
        returncode = self.process.poll()
        if returncode is None:
            if time.monotonic() >= self.deadline:
                self._cancel_timed_out()
            return None
        return self._collect_result(returncode)

    def wait_for_result(self) -> ExportJobResult:
        """Collect a closing window's job within its original worker deadline."""
        if self.cancellation is None:
            try:
                returncode = self.process.wait(timeout=max(0, self.deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                self._cancel_timed_out()
            else:
                return self._collect_result(returncode)
        return self.cancellation.result()

    def _cancel_timed_out(self) -> None:
        message = '操作超时。请等 MuMu 进入安卓桌面后重试。' if self.sync or self.setup else (
            '离线导出超时。请检查导出文件夹是否可用后重试。'
        )
        self.request_cancel(message)

    def _collect_result(self, returncode: int) -> ExportJobResult:
        try:
            if self.output is None:
                result = self.result_path.read_text(encoding='utf-8')
            else:
                self.output.seek(0)
                result = self.output.read().decode('utf-8')
            return parse_result(returncode, result, sync=self.sync, setup=self.setup)
        except (OSError, ValueError) as exc:
            return ExportJobResult('error', self.sync,
                                   message='后台任务没有返回结果。请重新打开助手后重试。'
                                           f'若再次失败，反馈时请附上：{type(exc).__name__}。',
                                   setup=self.setup)
        finally:
            self.cleanup()

    def request_sync_cancel(self) -> bool:
        if not self.sync or self.setup:
            return False
        if self.cancellation is not None:
            return True
        if self.process.poll() is not None or not claim_sync_stop(Path(self.scratch.name)):
            # Keep polling the original result when the worker has started saving.
            return False
        self.request_cancel()
        return True

    def request_cancel(self, timeout_message: str | None = None) -> None:
        if self.cancellation is not None:
            return
        pending: Future[ExportJobResult] = Future()
        self.cancellation = pending

        def cancel_in_background() -> None:
            try:
                self.cancel()
            except Exception as exc:
                result = ExportJobResult('error', self.sync, message=f'停止后台任务时出错：{exc}', setup=self.setup)
            else:
                result = ExportJobResult('error' if timeout_message else 'cancelled', self.sync,
                                         message=timeout_message, setup=self.setup)
            pending.set_result(result)

        try:
            Thread(target=cancel_in_background, daemon=False).start()
        except RuntimeError:
            cancel_in_background()

    def cancel(self) -> None:
        try:
            if self.sync or self.setup:
                from src.mumu_connection import cancel_mumu_sync
                cancel_mumu_sync(Path(self.scratch.name), self.stop_process)
            else:
                self.stop_process()
        except Exception:
            self.stop_process()
            raise
        finally:
            self.cleanup()

    def stop_process(self) -> None:
        if self.process.poll() is None:
            try:
                self.process.kill()
            except ProcessLookupError:
                return
            self.process.wait(timeout=1)

    def cleanup(self) -> None:
        if self.output is not None:
            self.output.close()
        self.scratch.cleanup()
