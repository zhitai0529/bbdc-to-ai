"""通过 MuMu 自带的管理器配置单个本地实例。"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from contextlib import nullcontext
import json
from pathlib import Path
from subprocess import TimeoutExpired
import time

from filelock import FileLock

from src.config import load_config
from src.mumu_connection import AppNotInstalled, MumuNotFound, SyncError, connect_mumu, run_manager, select_mumu
from src.mumu_snapshot import read_protocol

ROOT_KEY = 'root_permission'


def configure_mumu(session: Path | None = None, *, manager: Path | None = None) -> str:
    manager, index, instance = select_mumu(manager=manager)
    android_version = str(instance.get('android_version', '')).split('.', 1)[0]
    if android_version and android_version != '15':
        raise SyncError('一键配置目前支持 MuMu Android 15。请打开 Android 15 实例后重试。')
    setting = ('setting', '--vmindex', index, '--key', ROOT_KEY)
    current = run_manager(manager, *setting).get(ROOT_KEY)
    if current not in ('true', 'false', True, False):
        raise SyncError('这个 MuMu 版本未提供可读取的 Root 开关。请在 MuMu 设置中开启 Root。')
    lock = FileLock(str(session / 'launch.lock')) if session is not None else nullcontext()

    def check_cancelled() -> None:
        if session is not None and (session / 'cancel').exists():
            raise SyncError('配置已取消。')

    if current in ('false', False):
        option = run_manager(manager, *setting, '--info').get(ROOT_KEY)
        if (not isinstance(option, dict) or option.get('writable') is not True
                or 'true' not in (option.get('option_values') or [])):
            raise SyncError('这个 MuMu 版本未提供可写的 Root 开关。请在 MuMu 设置中开启 Root。')
        instance = run_manager(manager, 'info', '-v', index)
        if instance.get('is_process_started'):
            with lock:
                check_cancelled()
                run_manager(manager, 'control', '-v', index, 'shutdown')
            deadline = time.monotonic() + 30
            while instance.get('is_process_started'):
                check_cancelled()
                if time.monotonic() >= deadline:
                    raise SyncError('等待 MuMu 关机超时。请退出该实例后再点「一键配置 MuMu」。')
                time.sleep(0.5)
                instance = run_manager(manager, 'info', '-v', index)
        with lock:
            check_cancelled()
            run_manager(manager, *setting, '--value', 'true')
        if run_manager(manager, *setting).get(ROOT_KEY) not in ('true', True):
            raise SyncError('MuMu 没有确认 Root 已开启。请检查模拟器设置后重试。')

    check_cancelled()
    adb = connect_mumu(manager, index, instance, session, launch_app=False)
    try:
        adb.require_root()
    except (RuntimeError, TimeoutExpired) as exc:
        raise SyncError('ADB 没有取得 Root 权限。请确认 MuMu 已应用 Root 设置，重启该实例后重试。') from exc
    config = load_config()
    read_protocol(adb, config.root / '.local_setup/protocol.json')
    return 'MuMu 的 ADB、Root 和不背单词版本检查通过。请在 App 里登录，再点「查看已有复习」。'


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='配置并检查 MuMu 同步环境')
    parser.add_argument('--json', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--scratch-dir', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--mumu-manager', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        message = configure_mumu(args.scratch_dir, manager=args.mumu_manager)
    except (AppNotInstalled, MumuNotFound) as exc:
        status, message, exit_code = exc.status, str(exc), exc.exit_code
    except (OSError, ValueError, RuntimeError, TimeoutExpired, KeyError) as exc:
        status, exit_code = 'error', 1
        message = str(exc) or '配置失败。请确认已安装 MuMu 和受支持的不背单词版本。'
    else:
        status, exit_code = 'configured', 0
    if args.json:
        print(json.dumps({'status': status, 'message': message}, ensure_ascii=False))
    else:
        print(message)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
