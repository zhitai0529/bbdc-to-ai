"""启动器统一读取 YAML 中的监听地址与端口。"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import sysconfig
import socket
import time

from rich.console import Console
from src.config import load_config


def main() -> int:
    console = Console()
    parser = argparse.ArgumentParser(description='启动 bbdc-to-ai 代理')
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1] / 'config.yaml')
    parser.add_argument('--mumu', action='store_true', help='自动连接已 root 的 MuMu Android 15，并在退出时恢复代理')
    args = parser.parse_args()
    process = None
    session = None
    try:
        config = load_config(args.config)
        mitmdump = Path(sysconfig.get_path('scripts')) / ('mitmdump.exe' if sys.platform == 'win32' else 'mitmdump')
        if not mitmdump.is_file():
            raise FileNotFoundError('当前虚拟环境未安装 mitmdump，请先运行 setup.bat')
        console.print(f'监听 {config.listen_host}:{config.listen_port}，模式 {config.mode}', style='cyan')
        console.print('仅将你自己的 MuMu 设备连接到此代理；按 Ctrl+C 停止。')
        with socket.socket() as probe:
            if probe.connect_ex((('127.0.0.1' if config.listen_host == '0.0.0.0' else config.listen_host), config.listen_port)) == 0:
                raise RuntimeError('监听端口已被占用，请先停止旧代理或更改 config.yaml')
        process = subprocess.Popen([str(mitmdump), '-s', str(Path(__file__).resolve().parent / 'interceptor.py'),
                                '--listen-host', config.listen_host, '-p', str(config.listen_port),
                                '--set', f'bbdc_config={args.config.resolve()}',
                                '--set', f'confdir={config.root / ".local_setup/mitmproxy"}',
                                '--set', 'flow_detail=0', '--set', 'termlog_verbosity=warn'], cwd=config.root)
        if args.mumu:
            from src.emulator_proxy import EmulatorProxy
            from src.mumu_adb import Adb
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError('mitmdump 提前退出，未设置设备代理')
                try:
                    with socket.create_connection(('127.0.0.1', config.listen_port), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError('代理未能就绪')
            session = EmulatorProxy(Adb(), config)
            session.start()
            console.print('MuMu 代理及临时 CA 已就绪。退出请按 Ctrl+C，自动恢复网络。', style='green')
        return process.wait()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        console.print(f'启动失败：{exc}', style='red', markup=False)
        return 1
    finally:
        if session:
            try:
                session.restore()
                console.print('已恢复 MuMu 原网络代理。', style='green')
            except Exception as exc:
                console.print(f'网络恢复未完成（{type(exc).__name__}），请运行 restore_mumu_network.bat。', style='red')
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == '__main__':
    raise SystemExit(main())
