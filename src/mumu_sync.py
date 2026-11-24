"""通过 MuMu 和不背单词的正常界面启动、同步学习数据。"""
from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import re
import subprocess
import time
from uuid import uuid4
from xml.etree import ElementTree as ET

from filelock import FileLock

from src.mumu_adb import Adb, PACKAGE
from src.mumu_installation import discover_mumu_manager as manager_path


class SyncError(RuntimeError):
    pass


def run_manager(manager: Path, *args: str) -> dict:
    result = subprocess.run(
        [str(manager), *args], capture_output=True, timeout=35,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    try:
        response = json.loads(result.stdout.decode('utf-8-sig'))
    except (ValueError, UnicodeError) as exc:
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


def select_mumu() -> tuple[Path, str, dict]:
    manager = manager_path()
    if manager is None:
        raise SyncError('找不到 MuMu 模拟器。请检查 MuMu 是否已安装。')
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


def connect_mumu(manager: Path, index: str, instance: dict, session: Path | None, *,
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
                packages = adb.shell(f'pm path {PACKAGE} || true')
            except (RuntimeError, subprocess.TimeoutExpired):
                pass  # The ADB port can appear before Android is ready to answer.
            else:
                if not packages.startswith('package:'):
                    raise SyncError('这个 MuMu 实例未安装不背单词。')
                if launch_app:
                    run_manager(manager, 'control', '-v', index, 'app', 'launch', '-pkg', PACKAGE)
                return adb
        time.sleep(1)
        state = run_manager(manager, 'info', '-v', index)
    raise SyncError('连接 MuMu 的 ADB 超时。请确认模拟器已进入 Android 首页，然后重试。')


def open_mumu(session: Path | None = None) -> Adb:
    manager, index, instance = select_mumu()
    return connect_mumu(manager, index, instance, session)


def read_screen(adb: Adb) -> list[ET.Element]:
    path = f'/data/local/tmp/bbdc-sync-{uuid4().hex}.xml'
    # MuMu 15 may exit with 139 after writing a valid dump. Read the file and check the XML.
    command = (f'uiautomator dump --compressed {path} >/dev/null 2>&1; '
               f'cat {path} 2>/dev/null; rm -f {path}')
    xml = adb.run('shell', command, timeout=12)
    try:
        screen = ET.fromstring(xml)
    except ET.ParseError:
        return []
    return [node for node in screen.iter('node') if node.get('package') == PACKAGE]


def bounds(node: ET.Element) -> tuple[int, int, int, int]:
    box = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds', ''))
    if box is None:
        raise SyncError('MuMu 没有返回可用的界面位置。')
    left, top, right, bottom = map(int, box.groups())
    if right <= left or bottom <= top:
        raise SyncError('同步控件当前不可见。')
    return left, top, right, bottom


def control(nodes: list[ET.Element], name: str) -> ET.Element | None:
    return next((node for node in nodes if node.get('resource-id') == f'{PACKAGE}:id/{name}'
                 and node.get('clickable') == 'true' and node.get('enabled') == 'true'), None)


def tap(adb: Adb, node: ET.Element) -> None:
    left, top, right, bottom = bounds(node)
    adb.run('shell', 'input', 'tap', str((left + right) // 2), str((top + bottom) // 2), timeout=8)


def scroll_preferences(adb: Adb, nodes: list[ET.Element], page: str) -> bool:
    scrollers = [node for node in nodes if node.get('scrollable') == 'true'
                 and (page != 'profile' or node.get('resource-id') == f'{PACKAGE}:id/bottom_scroll')]
    if not scrollers:
        return False
    left, top, right, bottom = bounds(scrollers[0])
    x = (left + right) // 2
    height = bottom - top
    adb.run('shell', 'input', 'swipe', str(x), str(top + height * 4 // 5),
            str(x), str(top + height // 5), '420', timeout=8)
    return True


def sync_learning_records(adb: Adb) -> None:
    deadline = time.monotonic() + 45
    last_tap: dict[str, float] = {}
    swipes = {'learning': 0, 'profile': 0}
    requested = False
    while time.monotonic() < deadline:
        try:
            nodes = read_screen(adb)
        except subprocess.TimeoutExpired:
            continue
        labels = {node.get('text', '') for node in nodes}
        if any('同步失败' in label for label in labels):
            raise SyncError('不背单词提示数据同步失败。请检查 MuMu 的网络。')
        if labels & {'登录', '请先登录', '手机号登录', '微信登录'}:
            raise SyncError('请先在 MuMu 的不背单词中登录原账号。')
        if '数据同步成功' in labels:
            # Only acknowledge this specific success dialog, never a generic confirmation.
            button = next((node for node in nodes if node.get('text') == '确定'
                           and node.get('clickable') == 'true' and node.get('enabled') == 'true'), None)
            if button is not None:
                tap(adb, button)
            if requested:
                return
            continue
        if requested or '正在同步中' in labels:
            continue

        for item in ('sync_learn_data', 'more_learn_settings', 'cell_learn_settings', 'myHeadPhoto_container'):
            node = control(nodes, item)
            if node is None:
                continue
            now = time.monotonic()
            if item in last_tap and now - last_tap[item] < 2:
                break
            tap(adb, node)
            last_tap[item] = now
            if item == 'sync_learn_data':
                requested = True
                deadline = time.monotonic() + 45
            break
        else:
            if '学习偏好' in labels and '学习节奏' in labels:
                page = 'learning'
            elif any(node.get('resource-id') == f'{PACKAGE}:id/bottom_scroll' for node in nodes):
                page = 'profile'
            else:
                page = None
            if page and swipes[page] < 4 and scroll_preferences(adb, nodes, page):
                swipes[page] += 1
    if requested:
        raise SyncError('已发起同步，但未看到 App 确认成功。请稍后重试。')
    raise SyncError('未找到同步入口。若正在答题或有弹窗，请先回到不背单词首页。')
