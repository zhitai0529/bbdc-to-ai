"""Retarget the current Windows user's desktop shortcuts."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID


SHORTCUT_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$desktop = $env:BBDC_SHORTCUT_DESKTOP
if (-not $desktop -or -not [IO.Directory]::Exists($desktop)) {
    throw 'The Windows desktop directory is unavailable.'
}

$shell = New-Object -ComObject WScript.Shell
$target = $env:BBDC_SHORTCUT_TARGET
$workDir = [IO.Path]::GetDirectoryName($target)
$appName = '不背单词复习助手'
$legacyNames = @("$appName.lnk", '不背单词－查看复习.lnk', '不背单词－导出复习.lnk')
$appExe = '^bbdc-to-ai(?:-windows-x64)?(?:[-_ ]v?\d+\.\d+\.\d+)?(?: \(\d+\))?\.exe$'
$sourceArgs = '^\s*-m\s+src\.desktop(?:\s|$)'
$retired = @()
$found = $false

foreach ($entry in Get-ChildItem -LiteralPath $desktop -Filter '*.lnk' -File) {
    if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        continue
    }
    try {
        $shortcut = $shell.CreateShortcut($entry.FullName)
        $previous = $shortcut.TargetPath
        $previousName = [IO.Path]::GetFileName($previous)
    } catch {
        continue
    }
    $oldExe = $previousName -match $appExe
    $oldSource = ($entry.Name -in $legacyNames -and $previousName -match '^pythonw?\.exe$' -and
                  $shortcut.Arguments -match $sourceArgs)
    if ($previous -ne $target -and -not $oldExe -and -not $oldSource) {
        continue
    }
    $arguments = ''
    if ($shortcut.Arguments -match '(?:^|\s)(--export|--open-latest)(?:\s|$)') {
        $arguments = $Matches[1]
    }
    if ($previous -ne $target -or $shortcut.Arguments -ne $arguments -or $shortcut.WorkingDirectory -ne $workDir) {
        $shortcut.TargetPath = $target
        $shortcut.Arguments = $arguments
        $shortcut.WorkingDirectory = $workDir
        $shortcut.IconLocation = "$target,0"
        $shortcut.Save()
        if ($oldExe -and $previous -ne $target) {
            $retired += $previous
        }
    }
    $found = $true
}

if (-not $found) {
    $filename = Join-Path $desktop "$appName.lnk"
    $sequence = 1
    while (Test-Path -LiteralPath $filename) {
        $filename = Join-Path $desktop "$appName (bbdc-to-ai $sequence).lnk"
        $sequence++
    }
    $shortcut = $shell.CreateShortcut($filename)
    $shortcut.TargetPath = $target
    $shortcut.WorkingDirectory = $workDir
    $shortcut.IconLocation = "$target,0"
    $shortcut.Save()
}
ConvertTo-Json -InputObject @($retired) -Compress
'''


def _known_folder(identifier: str, fallback: str) -> Path:
    if sys.platform == 'win32':
        import ctypes

        shell = ctypes.WinDLL('shell32')
        memory = ctypes.WinDLL('ole32')
        guid = (ctypes.c_ubyte * 16).from_buffer_copy(UUID(identifier).bytes_le)
        buffer = ctypes.c_void_p()
        lookup = shell.SHGetKnownFolderPath
        lookup.argtypes = (ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
        lookup.restype = ctypes.c_int32
        memory.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
        memory.CoTaskMemFree.restype = None
        try:
            if lookup(ctypes.byref(guid), 0, None, ctypes.byref(buffer)) == 0 and buffer.value:
                return Path(ctypes.wstring_at(buffer))
        finally:
            if buffer.value:
                memory.CoTaskMemFree(buffer)
    return Path.home() / fallback


def desktop_directory() -> Path:
    return _known_folder('b4bfcc3a-db2c-424c-b029-7fe99a87c641', 'Desktop')


def downloads_directory() -> Path:
    return _known_folder('374de290-123f-4565-9164-39c4925e467b', 'Downloads')


def update_desktop_shortcuts(target: Path, *, desktop_dir: Path | None = None) -> tuple[Path, ...]:
    """Retarget existing app links or create a desktop link, returning previous EXE targets."""
    if sys.platform != 'win32':
        return ()
    target = target.resolve(strict=True)
    if not target.is_file():
        raise FileNotFoundError('新版 EXE 不存在，无法更新桌面快捷方式。')
    desktop = desktop_dir if desktop_dir is not None else desktop_directory()
    windows = Path(os.environ.get('SystemRoot', 'C:/Windows'))
    powershell = windows / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    command = base64.b64encode(SHORTCUT_SCRIPT.encode('utf-16-le')).decode('ascii')
    result = subprocess.run(
        [str(powershell), '-NoProfile', '-NonInteractive', '-EncodedCommand', command],
        env={
            **os.environ,
            'BBDC_SHORTCUT_TARGET': str(target),
            'BBDC_SHORTCUT_DESKTOP': str(desktop.resolve()),
        },
        capture_output=True, encoding='utf-8-sig', errors='replace', timeout=20,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    if result.returncode:
        raise OSError('无法更新 Windows 桌面快捷方式。')
    try:
        previous = json.loads(result.stdout)
    except ValueError as exc:
        raise OSError('无法读取 Windows 桌面快捷方式的更新结果。') from exc
    if not isinstance(previous, list) or not all(isinstance(path, str) for path in previous):
        raise OSError('无法读取 Windows 桌面快捷方式的更新结果。')
    return tuple(dict.fromkeys(Path(path) for path in previous if Path(path).is_absolute()))
