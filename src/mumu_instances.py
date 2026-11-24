"""Pure MuMu instance selection, independent of process launch and ADB."""
from __future__ import annotations

import re
from typing import Any

from src.mumu_diagnostics import ANDROID_15_STEPS, SyncError, incompatible_manager


def android_version(value: object) -> str | None:
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        match = re.fullmatch(r'(?:Android\s+)?([0-9]+(?:\.[0-9]+)*)', str(value).strip(), re.I)
        if match:
            return match[1]
    return None


def is_android_15(version: str) -> bool:
    return version.split('.', 1)[0] == '15'


def is_started(value: object) -> bool:
    return value is True or (type(value) is int and value == 1) or (
        isinstance(value, str) and value.casefold() in ('true', '1')
    )


def choose_instance(inventory: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    installed = {
        str(entry['index']): entry for entry in inventory.values()
        if isinstance(entry, dict) and re.fullmatch(r'[0-9]+', str(entry.get('index', '')))
    }
    if not installed:
        if inventory.keys() - {'errcode', 'errmsg'}:
            raise incompatible_manager()
        raise SyncError(
            '已找到 MuMu，但多开列表中没有模拟器实例。'
            '打开 MuMu 多开器，点「新建」创建 Android 15 实例；若没有这个选项，请先更新 MuMu。'
            '启动新实例后，再点「一键配置 MuMu」。',
            reason='instance_empty',
        )
    versions = {index: android_version(entry.get('android_version')) for index, entry in installed.items()}
    compatible = [index for index, version in versions.items() if version and is_android_15(version)]
    if not compatible:
        compatible = [index for index, version in versions.items() if version is None]
    if not compatible:
        found = '、'.join(f'Android {version}' for version in sorted({v for v in versions.values() if v}))
        raise SyncError(f'找到了 {found}，助手的 MuMu 配置与同步需要 Android 15。' + ANDROID_15_STEPS,
                        reason='android_unsupported')
    running = [index for index in compatible if is_started(installed[index].get('is_process_started'))
               or is_started(installed[index].get('is_android_started'))]
    if len(running) > 1:
        found = '、'.join(running)
        raise SyncError(
            f'有多个可用实例正在运行（编号 {found}）。在 MuMu 多开器停止其他实例，只保留装有不背单词的 '
            'Android 15 实例，再试一次。', reason='instance_ambiguous',
        )
    if not running and len(compatible) > 1:
        raise SyncError(
            '有多个可用实例，目前都未启动。打开 MuMu 多开器，只启动装有不背单词的 Android 15 实例，'
            '进入 Android 首页后再试。', reason='instance_ambiguous',
        )
    index = (running or compatible)[0]
    return index, installed[index]
