"""Android 设备连接与只读文件快照。"""
from __future__ import annotations

import base64
import binascii
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

PACKAGE = 'cn.com.langeasy.LangEasyLexis'


class Adb:
    def __init__(self, executable: str | None = None, serial: str | None = None) -> None:
        candidates = [executable, shutil.which('adb')]
        base = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'NetEase/MuMu/nx_device'
        if base.exists():
            candidates.extend(str(p) for p in sorted(base.glob('*/shell/adb.exe'), reverse=True))
        self.executable = next((str(p) for p in candidates if p and Path(p).is_file()), '')
        if not self.executable:
            raise FileNotFoundError('找不到 MuMu adb.exe，请通过 --adb 指定')
        self.serial = serial or ''
        self._use_su = False
        if serial:
            subprocess.run([self.executable, 'connect', serial], capture_output=True, timeout=15)
        else:
            manager = base.parent / 'nx_main/MuMuManager.exe'
            managed_addresses: set[str] = set()
            if manager.is_file():
                info = subprocess.run([str(manager), 'info', '-v', 'all'], capture_output=True, timeout=15)
                try:
                    instances = json.loads(info.stdout.decode('utf-8-sig'))
                    for instance in instances.values():
                        if instance.get('is_android_started') and instance.get('adb_port'):
                            address = f"{instance.get('adb_host_ip', '127.0.0.1')}:{instance['adb_port']}"
                            managed_addresses.add(address)
                            subprocess.run([self.executable, 'connect', address], capture_output=True, timeout=15)
                except (ValueError, AttributeError):
                    pass
            devices = subprocess.check_output([self.executable, 'devices'], timeout=15).decode()
            ready = re.findall(r'^([^\s]+)\s+device\s*$', devices, re.M)
            # MuMu can expose the same instance via its manager address and an emulator-* alias.
            candidates = [address for address in ready if address in managed_addresses] if managed_addresses else ready
            if len(candidates) != 1:
                raise ValueError('请先打开 MuMu；设备不唯一时通过 --serial 指定 ADB 地址')
            self.serial = candidates[0]

    def run(self, *args: str, timeout: int = 30) -> bytes:
        result = subprocess.run([self.executable, '-s', self.serial, *args], capture_output=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError(f'ADB {args[0]} 失败，退出码 {result.returncode}')
        return result.stdout

    def shell(self, command: str) -> str:
        return self.run('shell', command).decode('utf-8', errors='replace').strip()

    def require_root(self) -> None:
        if 'uid=0(' not in self.shell('id'):
            self.run('root')
            subprocess.run([self.executable, 'connect', self.serial], capture_output=True, timeout=15)
            self.run('wait-for-device')
        if 'uid=0(' not in self.shell('id'):
            raise RuntimeError('需要 MuMu 的 root 权限和 adb root；未修改 root 开关')

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

    def _database_shell(self, command: str) -> bytes:
        if self._use_su:
            command = 'su -c ' + shlex.quote(command)
        return self.run('shell', '-T', command)

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
            raise FileNotFoundError(f'不背单词还未创建 {name}，请先进入 App 首页并同步学习记录')
        if ready:
            raise RuntimeError('有学习记录尚未写入主文件，请结束本组学习后再试。')
        previous = self._read_database(path)
        for _ in range(3):
            current = self._read_database(path)
            if current == previous and not self._database_shell(status).strip():
                return current
            previous = current
        raise RuntimeError('数据库正在写入，请结束本组学习后再试。')
