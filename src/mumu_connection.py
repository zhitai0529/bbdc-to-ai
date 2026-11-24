"""Locate the selected MuMu instance and manage its connection lifecycle."""
from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import re
import subprocess
import time
from typing import Any

from filelock import FileLock

from src.mumu_adb import Adb, PACKAGE
from src.mumu_installation import discover_mumu_manager


class SyncError(RuntimeError):
    pass


class AppNotInstalled(SyncError):
    status = 'app_missing'
    exit_code = 3


class MumuNotFound(SyncError):
    status = 'mumu_missing'
    exit_code = 4


def run_manager(manager: Path, *args: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [str(manager), *args], capture_output=True, timeout=35,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
    except FileNotFoundError as exc:
        raise MumuNotFound('找不到 MuMu 管理程序。请重新选择 MuMu 安装位置。') from exc
    try:
        response = json.loads(result.stdout.decode('utf-8-sig'))
    except ValueError as exc:
        raise SyncError('无法读取 MuMu 启动状态。请检查 MuMu 是否正常安装。') from exc
    if not isinstance(response, dict):
        raise SyncError('MuMu 返回了无效的操作结果。')
    if result.returncode or response.get('errcode', 0):
        raise SyncError(f"MuMu 操作失败：{response.get('errmsg') or result.returncode}")
    return response


def launch_mumu(manager: Path, index: str, session: Path) -> None:
    with FileLock(str(session / 'launch.lock')):
        if (session / 'cancel').exists():
            raise SyncError('同步已取消。')
        # Record ownership before starting the manager so cancellation can wait for launch to finish.
        (session / 'mumu-manager').write_text(str(manager), encoding='utf-8')
        (session / 'mumu-instance').write_text(index, encoding='ascii')
        run_manager(manager, 'control', '-v', index, 'launch')
        if (session / 'cancel').exists():
            raise SyncError('同步已取消。')


def cancel_mumu_sync(session: Path, stop_worker: Callable[[], None]) -> None:
    (session / 'cancel').touch()
    # The manager launch command already has a timeout of its own.
    with FileLock(str(session / 'launch.lock'), timeout=40):
        stop_worker()
        marker = session / 'mumu-instance'
        if marker.is_file():
            index = marker.read_text(encoding='ascii').strip()
            if not re.fullmatch(r'[0-9]+', index):
                raise SyncError('无法确认本次启动的 MuMu 实例。')
            manager = Path((session / 'mumu-manager').read_text(encoding='utf-8'))
            run_manager(manager, 'control', '-v', index, 'shutdown')


def select_mumu(*, manager: Path | None = None) -> tuple[Path, str, dict[str, Any]]:
    if manager is None:
        manager = discover_mumu_manager()
    if manager is None or not manager.is_file():
        raise MumuNotFound('找不到 MuMu 模拟器。请打开 MuMu，或选择其安装位置后重试。')
    manager = manager.resolve()
    instances = run_manager(manager, 'info', '-v', 'all')
    installed = [entry for entry in instances.values() if isinstance(entry, dict) and 'index' in entry]
    running = [entry for entry in installed if entry.get('is_process_started')]
    choices = running or installed
    if len(choices) != 1:
        raise SyncError('请在 MuMu 中只运行一个要使用的实例，然后重试。')
    instance = choices[0]
    index = str(instance['index'])
    if not re.fullmatch(r'[0-9]+', index):
        raise SyncError('无法识别 MuMu 实例的编号。')
    return manager, index, instance


def connect_mumu(manager: Path, index: str, instance: dict[str, Any], session: Path | None, *,
                 launch_app: bool = True) -> Adb:
    state = instance
    launch_requested = False
    deadline = time.monotonic() + 90
    if not state.get('is_android_started') or not state.get('adb_port'):
        # Recheck before claiming ownership of an instance that may be starting.
        state = run_manager(manager, 'info', '-v', index)
    while time.monotonic() < deadline:
        if not state.get('is_process_started') and not launch_requested:
            if session is not None:
                launch_mumu(manager, index, session)
            else:
                run_manager(manager, 'control', '-v', index, 'launch')
            launch_requested = True
        if state.get('is_android_started') and state.get('adb_port'):
            serial = f"{state.get('adb_host_ip', '127.0.0.1')}:{state['adb_port']}"
            try:
                adb = Adb(serial=serial, manager=manager, android_version=state.get('android_version'))
                packages = adb.shell(f'pm path {PACKAGE} 2>&1 || true')
            except (RuntimeError, subprocess.TimeoutExpired):
                pass  # The ADB port can appear before Android is ready to answer.
            else:
                if not packages:
                    raise AppNotInstalled(
                        f'已找到 MuMu 实例 {index}。请在这个实例内安装不背单词，安装完成后重试。'
                    )
                if packages.startswith('package:'):
                    if launch_app:
                        run_manager(manager, 'control', '-v', index, 'app', 'launch', '-pkg', PACKAGE)
                    return adb
        time.sleep(1)
        state = run_manager(manager, 'info', '-v', index)
    raise SyncError('连接 MuMu 的 ADB 超时。请确认模拟器已进入 Android 首页，然后重试。')


def open_mumu(session: Path | None = None, *, manager: Path | None = None) -> Adb:
    selected, index, instance = select_mumu(manager=manager)
    return connect_mumu(selected, index, instance, session)
