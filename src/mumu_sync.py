"""通过不背单词的正常界面同步学习数据。"""
from __future__ import annotations

import re
import subprocess
import time
from uuid import uuid4
from xml.etree import ElementTree as ET

from src.mumu_adb import Adb, PACKAGE
from src.mumu_connection import SyncError


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
