from pathlib import Path
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from src.desktop_install import copy_executable, executable_digest, maintain_installation


class DesktopInstallTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.profile = self.root / 'profile'
        self.downloads = self.root / 'Downloads'
        self.downloads.mkdir()
        self.shortcuts = Mock(return_value=())
        for name, value in (
            ('data_directory', Mock(return_value=self.profile)),
            ('download_directories', Mock(return_value=(self.downloads,))),
            ('update_desktop_shortcuts', self.shortcuts),
        ):
            patcher = patch('src.desktop_install.' + name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_release(self, source: Path, version: str) -> Path:
        with patch('src.desktop_install.VERSION', version):
            return maintain_installation(source)

    def test_new_release_retargets_shortcut_then_removes_previous_copy(self) -> None:
        older = self.downloads / 'bbdc-to-ai-windows-x64.exe'
        new = self.downloads / 'bbdc-to-ai-windows-x64 (1).exe'
        older.write_bytes(b'first test release')
        new.write_bytes(b'second test release')
        first = self.run_release(older, '1.2.0')
        self.assertTrue(first.is_file())
        self.assertTrue(older.is_file())
        state = self.profile / 'config.yaml'
        state.write_text('output_dir: literal', encoding='utf-8')

        def switch_to(path: Path) -> None:
            self.assertTrue(first.is_file())
            self.assertTrue(path.is_file())
            return ()

        self.shortcuts.side_effect = switch_to
        second = self.run_release(new, '1.2.1')
        self.assertEqual(self.shortcuts.call_args.args, (second,))
        self.assertFalse(first.exists())
        self.assertFalse(older.exists())
        self.assertTrue(new.is_file())
        self.assertEqual(state.read_text(encoding='utf-8'), 'output_dir: literal')

    def test_migrates_only_verified_legacy_executables(self) -> None:
        older = self.downloads / 'bbdc-to-ai-windows-x64.exe'
        older.write_bytes(b'known old bytes')
        new = self.downloads / 'bbdc-to-ai-windows-x64 (3).exe'
        new.write_bytes(b'new binary')
        unrelated = self.downloads / 'bbdc-to-ai-windows-x64 (2).exe'
        unrelated.write_bytes(b'not same bytes')
        other_name = self.downloads / 'school-project.exe'
        other_name.write_bytes(older.read_bytes())
        with patch('src.desktop_install.LEGACY_RELEASES', dict([executable_digest(older)])):
            self.run_release(new, '1.2.0')
        self.assertFalse(older.exists())
        self.assertTrue(new.is_file())
        self.assertTrue(unrelated.is_file())
        self.assertTrue(other_name.is_file())

    def test_older_download_cannot_replace_newer_installed_release(self) -> None:
        latest_download = self.downloads / 'latest.exe'
        older_download = self.downloads / 'older.exe'
        latest_download.write_bytes(b'new release')
        older_download.write_bytes(b'old release')
        latest = self.run_release(latest_download, '1.2.10')
        self.assertEqual(self.run_release(older_download, '1.2.9'), latest)
        self.assertEqual(latest.read_bytes(), b'new release')
        self.assertEqual(self.shortcuts.call_args.args, (latest,))

    def test_shortcut_failure_preserves_working_old_executable(self) -> None:
        older = self.downloads / 'bbdc-to-ai-windows-x64.exe'
        older.write_bytes(b'old old')
        first = self.run_release(older, '1.2.0')
        second = self.downloads / 'new.exe'
        second.write_bytes(b'new new')
        self.shortcuts.side_effect = OSError('shortcut busy')
        with self.assertRaisesRegex(OSError, 'shortcut busy'):
            self.run_release(second, '1.2.1')
        self.assertTrue(first.is_file())
        self.assertTrue(older.is_file())

    def test_locked_old_download_is_retired_on_next_launch(self) -> None:
        older = self.downloads / 'bbdc-to-ai-windows-x64.exe'
        new = self.downloads / 'bbdc-to-ai-windows-x64 (1).exe'
        older.write_bytes(b'old copy')
        new.write_bytes(b'new copy')
        first = self.run_release(older, '1.2.0')
        original_unlink = Path.unlink

        def locked_unlink(path: Path, *args, **kwargs) -> None:
            if path == older:
                raise PermissionError('running')
            original_unlink(path, *args, **kwargs)

        with patch.object(Path, 'unlink', locked_unlink):
            self.run_release(new, '1.2.1')
        self.assertTrue(older.is_file())
        self.assertTrue(first.is_file())
        self.run_release(new, '1.2.1')
        self.assertFalse(older.exists())
        self.assertFalse(first.exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows alternate data streams')
    def test_copy_preserves_windows_download_marker(self) -> None:
        source = self.downloads / 'download.exe'
        target = self.root / 'installed' / 'bbdc-to-ai.exe'
        zone_info = '[ZoneTransfer]\nZoneId=3'
        source.write_bytes(b'test executable')
        with open(str(source) + ':Zone.Identifier', 'w', encoding='ascii') as marker:
            marker.write(zone_info)
        copy_executable(source, target)
        with open(str(target) + ':Zone.Identifier', encoding='ascii') as marker:
            self.assertEqual(marker.read(), zone_info)
