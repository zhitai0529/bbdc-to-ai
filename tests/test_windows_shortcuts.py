from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from src.windows_shortcuts import update_desktop_shortcuts


@unittest.skipUnless(sys.platform == 'win32', 'Requires Windows Shell shortcuts')
class WindowsShortcutTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.desktop = self.root / '临时 桌面 [测试]'
        self.desktop.mkdir()
        self.previous = self.root / 'bbdc-to-ai-windows-x64 (2).exe'
        self.target = self.root / '新版本' / 'bbdc-to-ai.exe'
        self.unrelated = self.root / 'Another App.exe'
        for executable in (self.previous, self.target, self.unrelated):
            executable.parent.mkdir(exist_ok=True)
            executable.touch()

    def shell_shortcut(self, name: str, target: Path | None = None, arguments: str = '') -> tuple[Path, str]:
        script = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($env:BBDC_TEST_LINK)
if ($env:BBDC_TEST_TARGET) {
    $shortcut.TargetPath = $env:BBDC_TEST_TARGET
    $shortcut.Arguments = $env:BBDC_TEST_ARGUMENTS
    $shortcut.Save()
}
@($shortcut.TargetPath, $shortcut.Arguments) | ConvertTo-Json -Compress
'''
        powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        command = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        result = subprocess.run(
            [str(powershell), '-NoProfile', '-NonInteractive', '-EncodedCommand', command],
            env={**os.environ, 'BBDC_TEST_LINK': str(self.desktop / name),
                 'BBDC_TEST_TARGET': str(target) if target else '', 'BBDC_TEST_ARGUMENTS': arguments},
            capture_output=True, encoding='utf-8-sig', timeout=20, check=True,
        )
        executable, args = json.loads(result.stdout)
        return Path(executable), args

    def test_retargets_owned_link_and_keeps_unrelated_link(self) -> None:
        owned = '我的不背单词.lnk'
        unrelated = '不背单词复习助手.lnk'
        self.shell_shortcut(owned, self.previous)
        self.shell_shortcut(unrelated, self.unrelated)
        self.assertEqual(update_desktop_shortcuts(self.target, desktop_dir=self.desktop), (self.previous,))
        self.assertEqual(self.shell_shortcut(owned), (self.target, ''))
        self.assertEqual(self.shell_shortcut(unrelated), (self.unrelated, ''))
        self.assertEqual(update_desktop_shortcuts(self.target, desktop_dir=self.desktop), ())

    def test_converts_old_source_link_and_preserves_export_flag(self) -> None:
        name = '不背单词－导出复习.lnk'
        python = self.root / 'pythonw.exe'
        python.touch()
        self.shell_shortcut(name, python, '-m src.desktop --export')
        self.assertEqual(update_desktop_shortcuts(self.target, desktop_dir=self.desktop), ())
        self.assertEqual(self.shell_shortcut(name), (self.target, '--export'))

    def test_creates_shortcut_when_no_owned_link_exists(self) -> None:
        name = '不背单词复习助手.lnk'
        self.assertEqual(update_desktop_shortcuts(self.target, desktop_dir=self.desktop), ())
        self.assertEqual(self.shell_shortcut(name), (self.target, ''))

    def test_name_conflict_does_not_overwrite_existing_link(self) -> None:
        self.shell_shortcut('不背单词复习助手.lnk', self.unrelated)
        self.assertEqual(update_desktop_shortcuts(self.target, desktop_dir=self.desktop), ())
        self.assertEqual(self.shell_shortcut('不背单词复习助手.lnk'), (self.unrelated, ''))
        self.assertEqual(self.shell_shortcut('不背单词复习助手 (bbdc-to-ai 1).lnk'), (self.target, ''))
