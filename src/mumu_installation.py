"""Locate MuMu's manager and the ADB shipped in the same installation."""
from __future__ import annotations

from collections.abc import Iterator
import os
from pathlib import Path
import re
import subprocess

from src.runtime import data_directory
from src.storage import atomic_write


MANAGER = 'MuMuManager.exe'
UNINSTALL_KEY = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'


def manager_in_location(location: Path) -> Path | None:
    try:
        if location.is_dir():
            folder = location
        elif location.name.lower().startswith(('mumu', 'uninstall', 'unins')):
            folder = location.parent
        else:
            return None
        for candidate in (folder / MANAGER, folder / 'nx_main' / MANAGER):
            if candidate.is_file():
                return candidate.resolve()
    except (OSError, RuntimeError):
        return None
    return None


def remember_mumu_manager(manager: Path) -> None:
    resolved = manager_in_location(manager)
    if resolved is None:
        raise ValueError('所选位置没有 MuMuManager.exe。请选择 MuMu 的安装目录。')
    atomic_write(data_directory() / 'mumu-location.txt', str(resolved) + '\n')


def _saved_manager() -> Path | None:
    try:
        saved = (data_directory() / 'mumu-location.txt').read_text(encoding='utf-8').strip()
    except (OSError, UnicodeError):
        return None
    return manager_in_location(Path(saved)) if saved and Path(saved).is_absolute() else None


def _default_locations() -> Iterator[Path]:
    for key in ('ProgramFiles', 'ProgramW6432', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
        base = os.environ.get(key)
        if base:
            yield Path(base) / 'NetEase' / 'MuMu'
            yield Path(base) / 'MuMuPlayer'


def _registry_locations() -> Iterator[Path]:
    try:
        import winreg
    except ImportError:
        return

    def value(key: winreg.HKEYType, name: str) -> str:
        try:
            text, _ = winreg.QueryValueEx(key, name)
        except OSError:
            return ''
        return os.path.expandvars(text.strip()) if isinstance(text, str) else ''

    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, UNINSTALL_KEY, 0, winreg.KEY_READ | view) as root:
                    for index in range(winreg.QueryInfoKey(root)[0]):
                        try:
                            with winreg.OpenKey(root, winreg.EnumKey(root, index)) as entry:
                                if 'mumu' not in value(entry, 'DisplayName').casefold():
                                    continue
                                location = value(entry, 'InstallLocation').strip('"')
                                if location:
                                    yield Path(location)
                                for name in ('DisplayIcon', 'UninstallString'):
                                    match = re.match(r'^"?([^"]+?\.(?:exe|ico))(?:"|[,\s]|$)', value(entry, name), re.I)
                                    if match:
                                        yield Path(match[1])
                        except OSError:
                            continue
            except OSError:
                continue


def _running_locations() -> Iterator[Path]:
    system = os.environ.get('SystemRoot')
    if os.name != 'nt' or not system:
        return
    powershell = Path(system) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    command = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8;"
               "Get-Process -Name MuMuNxMain,MuMuManager,MuMuPlayer -ErrorAction SilentlyContinue"
               " | ForEach-Object { $_.Path }")
    try:
        result = subprocess.run(
            [str(powershell), '-NoProfile', '-NonInteractive', '-Command', command],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3,
            encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return
    for line in result.stdout.splitlines():
        path = Path(line.strip())
        if path.is_absolute():
            yield path


def discover_mumu_manager() -> Path | None:
    if manager := _saved_manager():
        return manager
    for locations in (_default_locations, _registry_locations, _running_locations):
        for location in locations():
            if location.is_absolute() and (manager := manager_in_location(location)):
                return manager
    return None


def bundled_adb(manager: Path, android_version: str | None = None) -> Path | None:
    install = manager.parent.parent if manager.parent.name.lower() == 'nx_main' else manager.parent
    devices = install / 'nx_device'
    if android_version and re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', android_version):
        matching = devices / android_version / 'shell/adb.exe'
        if matching.is_file():
            return matching
    return next((path for path in sorted(devices.glob('*/shell/adb.exe'), reverse=True) if path.is_file()),
                install / 'adb.exe' if (install / 'adb.exe').is_file() else None)
