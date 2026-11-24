"""MuMu inventory diagnostics must not confuse setup states."""
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.mumu_connection import select_mumu
from src.mumu_diagnostics import SyncError
from src.mumu_instances import choose_instance


class InstanceSelectionTests(unittest.TestCase):
    def test_prefers_android_15_over_already_running_android_12(self) -> None:
        target = {'index': 1, 'android_version': '15.0', 'is_process_started': False}
        inventory = {'0': {'index': 0, 'android_version': 12, 'is_process_started': True}, '1': target}
        self.assertEqual(choose_instance(inventory), ('1', target))

    def test_selects_one_running_android_15_even_when_old_version_is_also_running(self) -> None:
        target = {'index': 2, 'android_version': '15.0', 'is_process_started': 'true'}
        inventory = {'0': {'index': 0, 'android_version': 12, 'is_process_started': True},
                     '1': {'index': 1, 'android_version': 'Android 15', 'is_process_started': 'false'},
                     '2': target}
        self.assertEqual(choose_instance(inventory), ('2', target))

    def test_older_android_has_version_specific_recovery(self) -> None:
        old = {'index': 0, 'android_version': 'Android 12', 'is_process_started': True}
        with self.assertRaisesRegex(SyncError, 'Android 12.*多开器.*新建.*更新') as cm:
            choose_instance({'0': old})
        self.assertEqual(cm.exception.reason, 'android_unsupported')

    def test_empty_inventory_distinguished_from_old_manager_protocol(self) -> None:
        for inventory in ({}, {'errcode': 0, 'errmsg': ''}):
            with self.subTest(inventory=inventory), self.assertRaisesRegex(SyncError, '没有模拟器实例.*新建') as cm:
                choose_instance(inventory)
            self.assertEqual(cm.exception.reason, 'instance_empty')
        with self.assertRaisesRegex(SyncError, '无法读取.*实例列表.*官网') as cm:
            choose_instance({'0': {'vmindex': 0}})
        self.assertEqual(cm.exception.reason, 'manager_incompatible')

    def test_multiple_running_and_multiple_stopped_need_different_steps(self) -> None:
        for running, message in ((True, '正在运行.*停止其他'), (False, '都未启动.*只启动')):
            with self.subTest(running=running), self.assertRaisesRegex(SyncError, message) as cm:
                choose_instance({str(i): {'index': i, 'android_version': 15, 'is_process_started': running}
                                 for i in range(2)})
            self.assertEqual(cm.exception.reason, 'instance_ambiguous')

    def test_rejected_inventory_calls_an_update_out(self) -> None:
        with TemporaryDirectory() as folder, patch('src.mumu_connection.subprocess.run') as run:
            manager = Path(folder) / 'MuMuManager.exe'
            manager.touch()
            for output in (b'Unsupported command', b'{"errcode": 2, "errmsg": "Unsupported command"}'):
                run.return_value = CompletedProcess([], 1, output)
                with self.subTest(output=output), self.assertRaisesRegex(SyncError, '更新 Windows 版') as cm:
                    select_mumu(manager=manager)
                self.assertEqual(cm.exception.reason, 'manager_incompatible')
