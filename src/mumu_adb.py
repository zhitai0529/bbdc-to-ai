"""Android 设备连接与只读文件快照。"""
from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from src.mumu_diagnostics import SyncError
from src.mumu_installation import bundled_adb, discover_mumu_manager

PACKAGE = 'cn.com.langeasy.LangEasyLexis'
NO_CONSOLE = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


class Adb:
    def __init__(self, executable: str | None = None, serial: str | None = None, *,
                 manager: Path | None = None, android_version: str | None = None) -> None:
        # WSA and other explicitly selected devices may have no MuMu installation.
        if manager is None and not (serial and executable and Path(executable).is_file()):
            manager = discover_mumu_manager()
        bundled = bundled_adb(manager, android_version) if manager is not None else None
        candidates = [executable, bundled, shutil.which('adb')]
        self.executable = next((str(p) for p in candidates if p and Path(p).is_file()), '')
        if not self.executable:
            raise FileNotFoundError('找不到 MuMu adb.exe，请通过 --adb 指定')
        self.serial = serial or ''
        self._use_su = False
        if serial:
            self._connect(serial)
        else:
            managed_addresses: set[str] = set()
            if manager is not None:
                info = subprocess.run([str(manager), 'info', '-v', 'all'], capture_output=True,
                                      timeout=15, creationflags=NO_CONSOLE)
                try:
                    instances = json.loads(info.stdout.decode('utf-8-sig'))
                    for instance in instances.values():
                        if instance.get('is_android_started') and instance.get('adb_port'):
                            address = f"{instance.get('adb_host_ip', '127.0.0.1')}:{instance['adb_port']}"
                            managed_addresses.add(address)
                            self._connect(address)
                except (ValueError, AttributeError):
                    pass
            devices = subprocess.check_output([self.executable, 'devices'], timeout=15,
                                              creationflags=NO_CONSOLE).decode()
            ready = re.findall(r'^([^\s]+)\s+device\s*$', devices, re.M)
            # MuMu can expose the same instance via its manager address and an emulator-* alias.
            candidates = [address for address in ready if address in managed_addresses] if managed_addresses else ready
            if len(candidates) != 1:
                raise ValueError('请先打开 MuMu；设备不唯一时通过 --serial 指定 ADB 地址')
            self.serial = candidates[0]

    def _connect(self, serial: str) -> None:
        subprocess.run([self.executable, 'connect', serial], capture_output=True,
                       timeout=15, creationflags=NO_CONSOLE)

    def run(self, *args: str, timeout: int = 30) -> bytes:
        result = subprocess.run([self.executable, '-s', self.serial, *args], capture_output=True,
                                timeout=timeout, creationflags=NO_CONSOLE)
        if result.returncode:
            raise RuntimeError(f'ADB {args[0]} 失败，退出码 {result.returncode}')
        return result.stdout

    def shell(self, command: str) -> str:
        return self.run('shell', command).decode('utf-8', errors='replace').strip()

    def require_root(self) -> None:
        message = (
            'ADB 没有取得 Root 权限，暂时无法读取学习记录。'
            '在助手打开「MuMu 与设置」并运行「一键配置 MuMu」。'
            '配置后，等目标实例进入 Android 桌面再点「同步 MuMu」。'
        )
        try:
            if 'uid=0(' not in self.shell('id'):
                self.run('root')
                self._connect(self.serial)
                self.run('wait-for-device')
            if 'uid=0(' in self.shell('id'):
                return
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            raise SyncError(message, reason='root_not_ready') from exc
        raise SyncError(message, reason='root_not_ready')

    def prepare_database_access(self) -> None:
        if 'uid=0(' in self.shell('id'):
            self._use_su = False
            return
        if self.shell('getprop ro.product.device') not in ('windows_x86_64', 'windows_arm64'):
            self.require_root()
            return

        message = 'WSA 还未给 Shell 读取学习库所需的权限。请在 Magisk 中允许 Shell 后重试。'
        try:
            identity = self.run('shell', '-T', "su -c 'id'", timeout=30).decode()
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            raise PermissionError(message) from exc
        if 'uid=0(' not in identity:
            raise PermissionError(message)
        self._use_su = True

    def _database_shell(self, command: str, *, timeout: int = 30) -> bytes:
        if self._use_su:
            command = 'su -c ' + shlex.quote(command)
        return self.run('shell', '-T', command, timeout=timeout)

    def dictionary_sha256(self) -> str | None:
        path = f'/data/user/0/{PACKAGE}/databases/simple.db'
        clean = f'test ! -s {path}-wal && test ! -s {path}-journal'
        try:
            reply = self._database_shell(f'{clean} && sha256sum {path} && {clean}', timeout=8)
        except (RuntimeError, subprocess.TimeoutExpired):
            return None
        pieces = reply.split(maxsplit=1)
        if pieces and re.fullmatch(rb'[0-9a-f]{64}', pieces[0]):
            return pieces[0].decode('ascii')
        return None

    def _read_database(self, path: str) -> bytes:
        if not self._use_su:
            return self.run('exec-out', 'cat', path)

        # Magisk/WSA can translate LF to CRLF even with a raw ADB stream.
        raw = self._database_shell(f'wc -c < {path} && base64 {path}')
        size, _, payload = raw.partition(b'\n')
        try:
            data = base64.b64decode(b''.join(payload.split()), validate=True)
            expected_size = int(size)
        except (ValueError, binascii.Error) as exc:
            raise RuntimeError('WSA 未返回有效的数据库副本') from exc
        if not data or len(data) != expected_size:
            raise RuntimeError('WSA 返回的数据库副本大小不完整')
        return data

    def stable_database(self, name: str) -> bytes:
        if name not in {'LangEasyLexis.db', 'simple.db'}:
            raise ValueError('仅允许词表和学习数据库')
        path = f'/data/user/0/{PACKAGE}/databases/{name}'
        status = (f'if ! test -f {path}; then echo missing; '
                  f'elif test -s {path}-wal || test -s {path}-journal; then echo pending; fi')
        ready = self._database_shell(status).strip()
        if ready == b'missing':
            raise FileNotFoundError('不背单词尚未保存所需数据。请在模拟器里打开 App，登录原账号并完成一组学习，'
                                    '然后回到 App 首页，同步成功后重试。')
        if ready:
            raise RuntimeError('有学习记录尚未写入主文件，请结束本组学习后再试。')
        previous = self._read_database(path)
        for _ in range(3):
            current = self._read_database(path)
            if current == previous and not self._database_shell(status).strip():
                return current
            previous = current
        raise RuntimeError('数据库正在写入，请结束本组学习后再试。')
