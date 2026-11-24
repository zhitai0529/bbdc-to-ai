from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.mumu_installation import bundled_adb, discover_mumu_manager, manager_in_location, remember_mumu_manager


class MumuInstallationTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.install = self.root / '自定义 安装目录'
        self.manager = self.install / 'nx_main' / 'MuMuManager.exe'
        self.manager.parent.mkdir(parents=True)
        self.manager.touch()

    def test_install_folder_manager_and_launcher_resolve_to_same_manager(self) -> None:
        launcher = self.manager.with_name('MuMuNxMain.exe')
        launcher.touch()
        for choice in (self.install, launcher, self.manager):
            with self.subTest(choice=choice):
                self.assertEqual(manager_in_location(choice), self.manager)
        self.assertIsNone(manager_in_location(self.root / 'other.exe'))

    def test_discovery_finds_custom_install_through_registry_or_running_player(self) -> None:
        for registry, running in (([self.install], []), ([], [self.manager.with_name('MuMuNxMain.exe')])):
            with self.subTest(registry=registry, running=running), \
                    patch('src.mumu_installation.data_directory', return_value=self.root), \
                    patch('src.mumu_installation._default_locations', return_value=[]), \
                    patch('src.mumu_installation._registry_locations', return_value=registry), \
                    patch('src.mumu_installation._running_locations', return_value=running):
                self.assertEqual(discover_mumu_manager(), self.manager)

    def test_remembered_path_is_preferred_and_stale_path_is_ignored(self) -> None:
        other = self.root / '其他安装' / 'MuMuManager.exe'
        other.parent.mkdir()
        other.touch()
        with patch('src.mumu_installation.data_directory', return_value=self.root / 'profile'), \
                patch('src.mumu_installation._default_locations', return_value=[other.parent]):
            remember_mumu_manager(self.manager)
            self.assertEqual(discover_mumu_manager(), self.manager)
            self.manager.unlink()
            self.assertEqual(discover_mumu_manager(), other)

    def test_bundled_adb_uses_selected_instance_android_version(self) -> None:
        for version in ('12.0', '15.0'):
            exe = self.install / 'nx_device' / version / 'shell' / 'adb.exe'
            exe.parent.mkdir(parents=True)
            exe.touch()
        self.assertEqual(bundled_adb(self.manager, '12.0'),
                         self.install / 'nx_device' / '12.0' / 'shell' / 'adb.exe')
