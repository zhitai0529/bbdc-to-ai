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
from src.mumu_diagnostics import (
    ANDROID_15_STEPS, AppNotInstalled as AppNotInstalled,
    ManagerResponseError, MumuNotFound as MumuNotFound, SyncError as SyncError,
    incompatible_manager,
)
from src.mumu_installation import discover_mumu_manager
from src.mumu_instances import android_version, choose_instance, is_android_15, is_started


def run_manager(manager: Path, *args: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [str(manager), *args], capture_output=True, timeout=35,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
    except FileNotFoundError as exc:
        raise MumuNotFound('找不到 MuMu 管理程序。请重新选择 MuMu 的安装目录；若使用旧版，请先更新 MuMu。') from exc
    except PermissionError as exc:
        raise SyncError('Windows 无法运行 MuMu 管理程序。请先从开始菜单打开 MuMu；'
                        '如果 MuMu 本身也打不开，请使用官网安装程序修复后再试。',
                        reason='manager_unavailable') from exc
    except subprocess.TimeoutExpired as exc:
        raise SyncError('等待 MuMu 管理程序响应超时。请查看 MuMu 是否有更新、启动失败或其他弹窗，'
                        '处理提示后在多开器重新打开目标实例，再试一次。',
                        reason='manager_unavailable') from exc
    try:
        response = json.loads(result.stdout.decode('utf-8-sig'))
    except ValueError as exc:
        raise ManagerResponseError('MuMu 管理程序没有返回可识别的结果。请在多开器启动目标实例后再试。',
                                   reason='manager_unavailable') from exc
    if not isinstance(response, dict):
        raise ManagerResponseError('MuMu 管理程序返回了不兼容的数据格式。请从 MuMu 官网更新 Windows 版后重试。',
                                   reason='manager_incompatible')
    if result.returncode or response.get('errcode') not in (None, 0, '0', ''):
        raise ManagerResponseError(
            f"MuMu 未完成请求（错误码 {response.get('errcode') or result.returncode}）。"
            '请查看模拟器窗口中的提示，进入 Android 首页后再试。',
            reason='manager_unavailable',
        )
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
        raise MumuNotFound(
            '找不到 MuMu 的管理程序。已安装时，打开 MuMu 后重试，或手动选择它的安装目录。'
            '若找不到管理程序或使用旧版，请从 MuMu 官网安装或更新 Windows 版，再在多开器里创建 Android 15 实例。'
        )
    manager = manager.resolve()
    try:
        instances = run_manager(manager, 'info', '-v', 'all')
    except ManagerResponseError as exc:
        raise incompatible_manager() from exc
    index, instance = choose_instance(instances)
    return manager, index, instance


def connect_mumu(manager: Path, index: str, instance: dict[str, Any], session: Path | None, *,
                 launch_app: bool = True) -> Adb:
    state = instance
    launch_requested = False
    deadline = time.monotonic() + 90
    if not is_started(state.get('is_android_started')) or not state.get('adb_port'):
        # Recheck before claiming ownership of an instance that may be starting.
        state = run_manager(manager, 'info', '-v', index)
    while time.monotonic() < deadline:
        version = android_version(state.get('android_version'))
        if version and not is_android_15(version):
            raise SyncError(f'实例 {index} 使用 Android {version}。' + ANDROID_15_STEPS,
                            reason='android_unsupported')
        running = is_started(state.get('is_process_started')) or is_started(state.get('is_android_started'))
        if not running and not launch_requested:
            if session is not None:
                launch_mumu(manager, index, session)
            else:
                run_manager(manager, 'control', '-v', index, 'launch')
            launch_requested = True
        if is_started(state.get('is_android_started')) and state.get('adb_port'):
            serial = f"{state.get('adb_host_ip', '127.0.0.1')}:{state['adb_port']}"
            try:
                adb = Adb(serial=serial, manager=manager, android_version=version)
                packages = adb.shell(f'pm path {PACKAGE} 2>&1 || true')
            except FileNotFoundError as exc:
                raise SyncError('没有找到 MuMu 附带的 ADB 连接工具。请从官网下载新版 MuMu 修复安装，'
                                '再打开 Android 15 实例重试。', reason='adb_unavailable') from exc
            except (RuntimeError, subprocess.TimeoutExpired):
                pass  # The ADB port can appear before Android is ready to answer.
            else:
                if not packages:
                    raise AppNotInstalled(
                        f'已找到 MuMu 实例 {index}，但其中没有安装不背单词。'
                        '请在这个实例安装不背单词 5.11.8 x86，打开 App 并登录后重试。'
                    )
                if packages.startswith('package:'):
                    if launch_app:
                        run_manager(manager, 'control', '-v', index, 'app', 'launch', '-pkg', PACKAGE)
                    return adb
        time.sleep(1)
        state = run_manager(manager, 'info', '-v', index)
    raise SyncError('连接 MuMu 的 ADB 超时。请在多开器打开目标 Android 15 实例，等到模拟器桌面出现再重试。'
                    '若已进入桌面，且设置中有「ADB 调试」选项，请确认已开启。可重启该实例后再试。',
                    reason='adb_timeout')


def open_mumu(session: Path | None = None, *, manager: Path | None = None) -> Adb:
    selected, index, instance = select_mumu(manager=manager)
    return connect_mumu(selected, index, instance, session)
