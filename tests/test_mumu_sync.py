from pathlib import Path
import tempfile
from threading import Event, Thread
import unittest
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

from src.mumu_adb import PACKAGE
from src.mumu_connection import AppNotInstalled, MumuNotFound, SyncError, cancel_mumu_sync, launch_mumu, open_mumu
from src.mumu_sync import sync_learning_records


def node(name: str = '', text: str = '', *, scrollable: bool = False) -> ET.Element:
    return ET.Element('node', {
        'package': PACKAGE, 'resource-id': f'{PACKAGE}:id/{name}' if name else '',
        'text': text, 'enabled': 'true', 'clickable': 'true',
        'bounds': '[20,120][180,880]', 'scrollable': str(scrollable).lower(),
    })


class MumuSyncTests(unittest.TestCase):
    def test_opens_app_after_android_answers_not_just_when_port_appears(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manager = Path(folder) / 'NetEase/MuMu/nx_main/MuMuManager.exe'
            manager.parent.mkdir(parents=True)
            manager.touch()
            session = Path(folder)
            stopped = {'index': '3', 'is_process_started': False}
            started = {'index': '3', 'is_process_started': True, 'is_android_started': True, 'adb_port': 16416}
            device = Mock()
            device.shell.side_effect = [RuntimeError('ADB offline'), 'package:/data/app/base.apk']
            with patch('src.mumu_connection.discover_mumu_manager', return_value=manager), \
                    patch('src.mumu_connection.run_manager',
                          side_effect=[{'3': stopped}, stopped, {}, started, started, {}, {}]) as run, \
                    patch('src.mumu_connection.Adb', return_value=device), patch('src.mumu_connection.time.sleep'):
                self.assertIs(open_mumu(session), device)
                self.assertEqual((session / 'mumu-instance').read_text(encoding='ascii'), '3')
                cancel_mumu_sync(session, Mock())
            commands = [call.args[1:] for call in run.call_args_list]
            self.assertEqual([command for command in commands if command[0] == 'control'],
                             [('control', '-v', '3', 'launch'),
                              ('control', '-v', '3', 'app', 'launch', '-pkg', PACKAGE),
                              ('control', '-v', '3', 'shutdown')])
            self.assertEqual(device.shell.call_count, 2)

    def test_sync_uses_adb_from_detected_installation(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manager = Path(folder).resolve() / 'Custom Install/nx_main/MuMuManager.exe'
            manager.parent.mkdir(parents=True)
            manager.touch()
            state = {'index': '2', 'is_process_started': True, 'is_android_started': True,
                     'adb_port': 16416, 'android_version': '15.0'}
            with patch('src.mumu_connection.discover_mumu_manager', return_value=manager), \
                    patch('src.mumu_connection.run_manager', side_effect=[{'2': state}, {}]), \
                    patch('src.mumu_connection.Adb') as adb:
                adb.return_value.shell.return_value = 'package:/data/app/base.apk'
                self.assertIs(open_mumu(), adb.return_value)
            adb.assert_called_once_with(serial='127.0.0.1:16416', manager=manager, android_version='15.0')

    def test_retry_after_app_install_uses_explicit_manager_without_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manager = Path(folder).resolve() / 'MuMuManager.exe'
            manager.touch()
            state = {'index': '2', 'is_process_started': True, 'is_android_started': True, 'adb_port': 16416}
            with patch('src.mumu_connection.discover_mumu_manager', return_value=None) as discover, \
                    patch('src.mumu_connection.run_manager', side_effect=[{'2': state}, {'2': state}, {}]) as run, \
                    patch('src.mumu_connection.Adb') as adb:
                adb.return_value.shell.side_effect = ['', 'package:/data/app/base.apk']
                with self.assertRaisesRegex(AppNotInstalled, '实例 2'):
                    open_mumu(manager=manager)
                self.assertIs(open_mumu(manager=manager), adb.return_value)
            discover.assert_not_called()
            self.assertEqual([call.args[0] for call in run.call_args_list], [manager] * 3)

    def test_missing_explicit_manager_reports_missing_without_switching_installations(self) -> None:
        with tempfile.TemporaryDirectory() as folder, \
                patch('src.mumu_connection.discover_mumu_manager') as discover:
            with self.assertRaisesRegex(MumuNotFound, '找不到 MuMu'):
                open_mumu(manager=Path(folder) / 'missing.exe')
            discover.assert_not_called()

    def test_waits_if_android_package_manager_reports_a_transient_error(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            manager = Path(folder).resolve() / 'MuMuManager.exe'
            manager.touch()
            state = {'index': '2', 'is_process_started': True, 'is_android_started': True, 'adb_port': 16416}
            with patch('src.mumu_connection.run_manager', side_effect=[{'2': state}, state, {}]), \
                    patch('src.mumu_connection.Adb') as adb, patch('src.mumu_connection.time.sleep'):
                adb.return_value.shell.side_effect = ['cmd: Package manager is not available', 'package:/data/app/base.apk']
                self.assertIs(open_mumu(manager=manager), adb.return_value)
            self.assertEqual(adb.return_value.shell.call_count, 2)

    def test_cancel_does_not_shutdown_an_already_running_instance(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            session = Path(folder)
            manager = session / 'MuMuManager.exe'
            manager.touch()
            started = {'index': '3', 'is_process_started': True, 'is_android_started': True, 'adb_port': 16416}
            device = Mock()
            device.shell.return_value = 'package:/data/app/base.apk'
            stop = Mock()
            with patch('src.mumu_connection.discover_mumu_manager', return_value=manager), \
                    patch('src.mumu_connection.run_manager', side_effect=[{'3': started}, {}]) as run, \
                    patch('src.mumu_connection.Adb', return_value=device):
                self.assertIs(open_mumu(session), device)
                cancel_mumu_sync(session, stop)
            stop.assert_called_once_with()
            self.assertEqual(run.call_count, 2)
            self.assertFalse((session / 'mumu-instance').exists())

    def test_cancel_before_launch_prevents_startup(self) -> None:
        with tempfile.TemporaryDirectory() as folder, patch('src.mumu_connection.run_manager') as run:
            session = Path(folder)
            cancel_mumu_sync(session, Mock())
            with self.assertRaisesRegex(SyncError, '同步已取消'):
                launch_mumu(session / 'MuMuManager.exe', '3', session)
            run.assert_not_called()

    def test_cancel_waits_for_a_launch_in_progress(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            session = Path(folder)
            manager = session / 'MuMuManager.exe'
            launch_started = Event()
            launch_finished = Event()
            stop = Mock()

            def manager_command(path: Path, *args: str) -> dict:
                if args[-1] == 'launch':
                    launch_started.set()
                    launch_finished.wait(timeout=5)
                return {}

            with patch('src.mumu_connection.run_manager', side_effect=manager_command) as run:
                def start_instance() -> None:
                    try:
                        launch_mumu(manager, '3', session)
                    except SyncError:
                        pass

                launch = Thread(target=start_instance)
                cancel = Thread(target=cancel_mumu_sync, args=(session, stop))
                launch.start()
                try:
                    self.assertTrue(launch_started.wait(timeout=5))
                    cancel.start()
                    cancel.join(timeout=0.1)
                    self.assertTrue(cancel.is_alive())
                    stop.assert_not_called()
                finally:
                    launch_finished.set()
                    launch.join(timeout=5)
                    if cancel.ident is not None:
                        cancel.join(timeout=5)
                stop.assert_called_once_with()
                self.assertEqual([call.args[-1] for call in run.call_args_list], ['launch', 'shutdown'])

    def test_scrolls_to_sync_and_waits_for_fresh_success(self) -> None:
        adb = Mock()
        old_dialog = [node(text='数据同步成功'), node(text='确定')]
        screens = [
            old_dialog,
            [node('myHeadPhoto_container')],
            [node('cell_learn_settings')],
            [node(text='学习偏好'), node(text='学习节奏'), node(scrollable=True)],
            [node('more_learn_settings')],
            [node('sync_learn_data')],
            [node(text='正在同步中')],
            old_dialog,
        ]
        with patch('src.mumu_sync.read_screen', side_effect=screens) as read:
            sync_learning_records(adb)
        self.assertEqual(read.call_count, len(screens))
        actions = [call.args[2] for call in adb.run.call_args_list]
        self.assertEqual(actions, ['tap', 'tap', 'tap', 'swipe', 'tap', 'tap', 'tap'])

    def test_sync_failure_never_confirms_unrelated_prompt(self) -> None:
        adb = Mock()
        screens = [[node('sync_learn_data')], [node(text='数据同步失败'), node(text='确定')]]
        with patch('src.mumu_sync.read_screen', side_effect=screens):
            with self.assertRaisesRegex(SyncError, '同步失败'):
                sync_learning_records(adb)
        self.assertEqual(adb.run.call_count, 1)

    def test_retries_navigation_control_if_the_page_did_not_change(self) -> None:
        adb = Mock()
        profile = [node('myHeadPhoto_container')]
        screens = [profile, profile, [node('sync_learn_data')], [node(text='数据同步成功')]]
        with patch('src.mumu_sync.read_screen', side_effect=screens), \
                patch('src.mumu_sync.time.monotonic', side_effect=range(0, 100, 2)):
            sync_learning_records(adb)
        self.assertEqual(adb.run.call_count, 3)
