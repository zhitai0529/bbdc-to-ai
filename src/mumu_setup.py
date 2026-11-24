"""通过 MuMu 自带的管理器配置单个本地实例。"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from contextlib import nullcontext
import json
from pathlib import Path
from subprocess import TimeoutExpired
import time
from typing import Any

from filelock import FileLock

from src.config import load_config
from src.mumu_connection import connect_mumu, run_manager, select_mumu
from src.mumu_diagnostics import ANDROID_15_STEPS, UPDATE_MANAGER_STEPS, AppNotInstalled, ManagerResponseError, SyncError
from src.mumu_instances import android_version, is_android_15, is_started
from src.mumu_snapshot import read_protocol

ROOT_KEY = 'root_permission'


def progress(session: Path | None, message: str) -> None:
    if session is not None:
        try:
            with (session / 'setup-progress.txt').open('a', encoding='utf-8') as stream:
                print(message, file=stream)
        except OSError:
            pass  # The optional desktop log must not interrupt configuration.


def check_cancelled(session: Path | None) -> None:
    if session is not None and (session / 'cancel').exists():
        raise SyncError('配置已取消。')


def enable_instance_root(
    manager: Path, index: str, instance: dict[str, Any], session: Path | None,
) -> dict[str, Any]:
    """Enable the selected instance's supported setting, leaving other instances alone."""
    setting = ('setting', '--vmindex', index, '--key', ROOT_KEY)
    progress(session, '正在读取实例的 Root 开关。')
    try:
        current = run_manager(manager, *setting).get(ROOT_KEY)
    except ManagerResponseError as exc:
        raise SyncError('当前 MuMu 管理程序未能读取 Root 开关。' + UPDATE_MANAGER_STEPS,
                        reason='manager_incompatible') from exc
    if current not in ('true', 'false', True, False):
        raise SyncError('当前 MuMu 管理程序未提供可读取的 Root 开关。' + UPDATE_MANAGER_STEPS,
                        reason='manager_incompatible')
    if current in ('true', True):
        return instance

    try:
        option = run_manager(manager, *setting, '--info').get(ROOT_KEY)
    except ManagerResponseError as exc:
        raise SyncError('当前 MuMu 管理程序无法读取 Root 的配置选项。' + UPDATE_MANAGER_STEPS,
                        reason='manager_incompatible') from exc
    if (not isinstance(option, dict) or option.get('writable') is not True
            or 'true' not in (option.get('option_values') or [])):
        raise SyncError(
            '当前 MuMu 未提供可写的 Root 开关。请打开该 Android 15 实例的设置，找到「Root 权限」并开启，'
            '重启该实例后重试。如果设置中没有此选项，请从 MuMu 官网更新 Windows 版。',
            reason='root_unavailable',
        )

    lock = FileLock(str(session / 'launch.lock')) if session is not None else nullcontext()
    instance = run_manager(manager, 'info', '-v', index)
    if is_started(instance.get('is_process_started')):
        with lock:
            check_cancelled(session)
            run_manager(manager, 'control', '-v', index, 'shutdown')
        deadline = time.monotonic() + 30
        while is_started(instance.get('is_process_started')):
            check_cancelled(session)
            if time.monotonic() >= deadline:
                raise SyncError('等待 MuMu 关机超时。请在多开器点目标实例旁的「停止」，'
                                '等它关闭后回到助手，再点「一键配置 MuMu」。', reason='root_not_ready')
            time.sleep(0.5)
            instance = run_manager(manager, 'info', '-v', index)
    with lock:
        check_cancelled(session)
        run_manager(manager, *setting, '--value', 'true')
    if run_manager(manager, *setting).get(ROOT_KEY) not in ('true', True):
        raise SyncError('MuMu 没有确认 Root 已开启。请在目标实例的设置手动开启「Root 权限」，再重启该实例重试。',
                        reason='root_not_ready')
    return instance

def configure_mumu(session: Path | None = None, *, manager: Path | None = None) -> str:
    progress(session, '正在查找 MuMu Android 实例。')
    manager, index, instance = select_mumu(manager=manager)
    version = android_version(instance.get('android_version'))
    if version is None:
        raise SyncError('MuMu 没有报告该实例的 Android 版本。'
                        '请先在 MuMu 多开器启动明确标为 Android 15 的实例，再重试。'
                        '如果已经启动 Android 15 而仍看到此提示，请从 MuMu 官网更新 Windows 版。',
                        reason='android_unknown')
    if not is_android_15(version):
        raise SyncError(f'实例 {index} 使用 Android {version}，一键配置需要 Android 15。' + ANDROID_15_STEPS,
                        reason='android_unsupported')
    progress(session, f'已选中 MuMu 实例 {index}（Android {version}）。')
    check_cancelled(session)
    instance = enable_instance_root(manager, index, instance, session)
    check_cancelled(session)
    progress(session, '正在连接 ADB。')
    try:
        adb = connect_mumu(manager, index, instance, session, launch_app=False)
    except AppNotInstalled:
        progress(session, 'ADB 连接通过。')
        raise
    progress(session, 'ADB 连接通过。')
    try:
        adb.require_root()
    except (RuntimeError, TimeoutExpired) as exc:
        raise SyncError('ADB 没有取得 Root 权限。请在目标实例的设置确认已开启「Root 权限」，'
                        '从多开器停止并重新启动该实例，等 Android 桌面出现后重试。',
                        reason='root_not_ready') from exc
    progress(session, 'Root 检查通过。')
    progress(session, '正在核对不背单词版本。')
    config = load_config()
    read_protocol(adb, config.root / '.local_setup/protocol.json')
    return 'MuMu 的 ADB、Root 和不背单词版本检查通过。请在 App 里登录，再回到助手点「同步 MuMu」。'


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='配置并检查 MuMu 同步环境')
    parser.add_argument('--json', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--scratch-dir', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--mumu-manager', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    reason = None
    try:
        message = configure_mumu(args.scratch_dir, manager=args.mumu_manager)
    except SyncError as exc:
        status, message, exit_code, reason = exc.status, str(exc), exc.exit_code, exc.reason
    except (OSError, ValueError, RuntimeError, TimeoutExpired, KeyError) as exc:
        status, exit_code = 'error', 1
        message = str(exc) or '配置失败。请确认已安装 MuMu 和受支持的不背单词版本。'
    else:
        status, exit_code = 'configured', 0
    if args.json:
        reply = {'status': status, 'message': message}
        if reason is not None:
            reply['reason'] = reason
        print(json.dumps(reply, ensure_ascii=False))
    else:
        print(message)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
