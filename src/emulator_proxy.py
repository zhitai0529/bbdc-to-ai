"""临时 ADB reverse + Android 15 CA 挂载，退出时恢复网络代理。"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shlex
import time

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from src.config import Config, load_config
from src.mumu_adb import Adb, PACKAGE
from src.storage import write_json


def is_loopback_proxy(adb: Adb, port: int) -> bool:
    return (adb.shell('settings get global global_http_proxy_host') == '127.0.0.1'
            and adb.shell('settings get global global_http_proxy_port') == str(port)
            and adb.shell('settings get global global_http_proxy_pac') in ('', 'null'))


def clear_global_proxy(adb: Adb) -> None:
    # Android 15 persists the active proxy in separate fields. Deleting http_proxy alone leaves it active.
    adb.shell("settings put global http_proxy ':0'")
    for _ in range(15):
        host = adb.shell('settings get global global_http_proxy_host')
        port = adb.shell('settings get global global_http_proxy_port')
        pac = adb.shell('settings get global global_http_proxy_pac')
        if host in ('', 'null') and port in ('', '0', 'null') and pac in ('', 'null'):
            return
        time.sleep(0.1)
    raise RuntimeError('Android 未清除全局代理')


def mount_marker(store: str) -> str:
    """Android 的 /data 挂载在 mountinfo 中通常显示为 /local/tmp。"""
    if not re.fullmatch(r'/data/local/tmp/bbdc-ai-cacerts-\d{14}', store):
        raise ValueError('证书挂载会话路径无效')
    return '/' + store.rsplit('/', 1)[-1] + ' /apex/com.android.conscrypt/cacerts '


class EmulatorProxy:
    def __init__(self, adb: Adb, config: Config) -> None:
        self.adb, self.config = adb, config
        self.state_path = config.root / '.local_setup/proxy_session.json'

    def start(self) -> None:
        if self.state_path.exists():
            raise RuntimeError('存在未恢复的代理会话，请先运行 restore_mumu_network.bat')
        self.adb.require_root()
        if self.adb.shell('getprop ro.build.version.release') != '15':
            raise ValueError('自动证书挂载只在本机 Android 15 验证；其他版本请手工配置')
        ca_path = self.config.root / '.local_setup/mitmproxy/mitmproxy-ca-cert.pem'
        cert = x509.load_pem_x509_certificate(ca_path.read_bytes())
        subject_hash = int.from_bytes(hashlib.md5(cert.subject.public_bytes()).digest()[:4], 'little')
        name = f'{subject_hash:08x}.0'
        public_path = self.config.root / '.local_setup' / name
        public_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        port = self.config.listen_port
        if f'tcp:{port} tcp:' in self.adb.run('reverse', '--list').decode():
            raise RuntimeError('该端口已有 ADB reverse，请改用空闲端口')
        previous = self.adb.shell('settings get global http_proxy')
        store = f'/data/local/tmp/bbdc-ai-cacerts-{datetime.now():%Y%m%d%H%M%S}'
        marker = mount_marker(store)
        state = {'serial': self.adb.serial, 'previous_proxy': previous, 'port': port,
                 'store': store, 'cert_name': name}
        write_json(self.state_path, state)
        try:
            self.adb.run('push', str(public_path), '/data/local/tmp/' + name)
            # 根命名空间先挂载；随后现有 zygote / App 命名空间各挂一次。
            script = f'''set -eu
store={shlex.quote(store)}
target=/apex/com.android.conscrypt/cacerts
mkdir -p "$store"
cp "$target"/* "$store/"
cp /data/local/tmp/{name} "$store/{name}"
chown -R 0:0 "$store"
chmod 755 "$store"
chmod 644 "$store"/*
chcon -R u:object_r:system_security_cacerts_file:s0 "$store"
mount --bind "$store" "$target"
for p in $(pidof zygote64 zygote) $(pidof {PACKAGE}); do
  nsenter -t "$p" -m -- sh -c 'grep -Fq "{marker}" /proc/self/mountinfo || mount --bind "{store}" /apex/com.android.conscrypt/cacerts'
done
'''
            self.adb.shell(script)
            self.adb.run('reverse', f'tcp:{port}', f'tcp:{port}')
            self.adb.shell(f'settings put global http_proxy 127.0.0.1:{port}')
        except Exception:
            self.restore()
            raise

    def restore(self) -> None:
        if not self.state_path.exists():
            return
        state = json.loads(self.state_path.read_text(encoding='utf-8'))
        if state['serial'] != self.adb.serial:
            raise ValueError('会话设备不匹配，未更改网络')
        current = self.adb.shell('settings get global http_proxy')
        if (current == f"127.0.0.1:{state['port']}"
                or (current in ('null', '', ':0') and is_loopback_proxy(self.adb, state['port']))):
            previous = state['previous_proxy']
            if previous in ('null', '', ':0'):
                clear_global_proxy(self.adb)
            else:
                self.adb.shell('settings put global http_proxy ' + shlex.quote(previous))
        reverses = self.adb.run('reverse', '--list').decode()
        if f"tcp:{state['port']} tcp:" in reverses:
            self.adb.run('reverse', '--remove', f"tcp:{state['port']}")
        self.adb.require_root()
        store = state['store']
        marker = mount_marker(store)
        # 只卸载本次会话自己的挂载；不会删除系统证书或修改系统镜像。
        command = f'while grep -Fq {shlex.quote(marker)} /proc/self/mountinfo; do umount /apex/com.android.conscrypt/cacerts || exit 1; done'
        self.adb.shell(f'''set -e
for p in $(pidof zygote64 zygote) $(pidof {PACKAGE}); do
nsenter -t "$p" -m -- sh -c {shlex.quote(command)}
done
{command}''')
        self.state_path.unlink()

    def recover_legacy_proxy(self) -> bool:
        """旧版可能已删掉会话标记，但 Android 仍指向工具的专用端口。"""
        port = self.config.listen_port
        if self.adb.shell('settings get global http_proxy') not in ('', 'null'):
            return False
        if not is_loopback_proxy(self.adb, port):
            return False
        reverses = self.adb.run('reverse', '--list').decode()
        if f'tcp:{port} tcp:' in reverses:
            return False
        clear_global_proxy(self.adb)
        return True


def main() -> int:
    from rich.console import Console
    console = Console()
    parser = argparse.ArgumentParser(description='恢复上次抓包前的 MuMu 网络代理')
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    config = load_config(args.config)
    path = config.root / '.local_setup/proxy_session.json'
    try:
        if path.exists():
            state = json.loads(path.read_text(encoding='utf-8'))
            EmulatorProxy(Adb(serial=state['serial']), config).restore()
            console.print('已恢复 MuMu 网络。', style='green')
        elif (config.root / '.local_setup/mitmproxy/mitmproxy-ca-cert.pem').is_file() and EmulatorProxy(
            Adb(), config
        ).recover_legacy_proxy():
            console.print('已清除旧版抓包遗留的 MuMu 代理。', style='green')
        else:
            console.print('没有待恢复的代理会话。')
        return 0
    except Exception as exc:
        console.print(f'恢复失败：{exc}。请保持 MuMu 开启后重试。', style='red', markup=False)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
