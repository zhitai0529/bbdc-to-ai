"""Shared error types and recovery instructions for MuMu tasks."""
from __future__ import annotations

MUMU_DOWNLOAD_URL = 'https://mumu.163.com/'

_INSTALLATION_REASONS = {'mumu_missing', 'manager_incompatible', 'manager_unavailable'}
_UPDATE_REASONS = {'android_unsupported', 'android_unknown', 'instance_empty', 'root_unavailable', 'adb_unavailable'}


def recovery_actions(status: str, reason: str | None) -> tuple[str, ...]:
    if status == 'mumu_missing' or reason in _INSTALLATION_REASONS:
        return 'download', 'locate'
    if reason in _UPDATE_REASONS:
        return ('download',)
    return ()


class SyncError(RuntimeError):
    status = 'error'
    exit_code = 1
    reason: str | None = None

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        super().__init__(message)
        if reason is not None:
            self.reason = reason


class AppNotInstalled(SyncError):
    status = 'app_missing'
    exit_code = 3
    reason = 'app_missing'


class MumuNotFound(SyncError):
    status = 'mumu_missing'
    exit_code = 4
    reason = 'mumu_missing'


class ManagerResponseError(SyncError):
    """MuMu did not accept a command or returned an unknown format."""


ANDROID_15_STEPS = (
    '打开 MuMu 多开器，查看实例的 Android 版本。已有 Android 15 时，启动该实例并重试。'
    '没有时，点「新建」选择 Android 15；如果列表里没有这个选项，请先去 MuMu 官网更新 Windows 版模拟器。'
    '旧实例可以保留。新实例需要安装并登录不背单词。'
)
UPDATE_MANAGER_STEPS = (
    '从 MuMu 官网下载并更新 Windows 版模拟器。若电脑装了多个 MuMu 版本，'
    '请在助手中重新选择新版 MuMu 的安装目录。更新后打开多开器，启动要用的 Android 15 实例，再重试。'
)
APP_VERSION_STEPS = (
    '目前适配的是不背单词 5.11.8 x86 单 APK。'
    '在 MuMu 中打开不背单词，核对 App 版本和安装包架构。'
    '如需换版本，先在 App 内同步账号数据，再在兼容的 Android 15 实例中安装受支持的版本。'
)


def incompatible_manager() -> SyncError:
    return SyncError('助手无法读取 MuMu 的实例列表。当前模拟器可能过旧，或安装不完整。' + UPDATE_MANAGER_STEPS,
                     reason='manager_incompatible')
