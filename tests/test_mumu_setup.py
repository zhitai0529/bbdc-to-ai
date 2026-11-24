from pathlib import Path
from subprocess import TimeoutExpired
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, call, patch

from src.desktop_worker import ExportJob, parse_result
from src.mumu_connection import AppNotInstalled, MumuNotFound, SyncError
from src.mumu_setup import configure_mumu, main


class MumuSetupTests(unittest.TestCase):
    manager = Path('MuMuManager.exe')
    setting = (manager, 'setting', '--vmindex', '2', '--key', 'root_permission')

    def test_worker_routes_dependency_errors_by_status(self) -> None:
        for error, status, code in ((AppNotInstalled('安装不背单词'), 'app_missing', 3),
                                    (MumuNotFound('找不到 MuMu'), 'mumu_missing', 4)):
            with self.subTest(status=status), patch('src.mumu_setup.configure_mumu', side_effect=error) as setup, \
                    patch('builtins.print') as output:
                self.assertEqual(main(['--json', '--mumu-manager', str(self.manager)]), code)
                self.assertIn(f'"status": "{status}"', output.call_args.args[0])
                setup.assert_called_once_with(None, manager=self.manager)

    def test_root_disabled_on_running_instance_restarts_only_selected_instance(self) -> None:
        with TemporaryDirectory() as temp, patch('src.mumu_setup.select_mumu') as select, \
                patch('src.mumu_setup.run_manager') as run, patch('src.mumu_setup.connect_mumu') as connect, \
                patch('src.mumu_setup.load_config') as config, patch('src.mumu_setup.read_protocol') as verify, \
                patch('src.mumu_setup.time.sleep'):
            session = Path(temp)
            config.return_value.root = session
            running = {'android_version': '15.0', 'is_process_started': True}
            stopped = {'android_version': '15.0', 'is_process_started': False}
            select.return_value = self.manager, '2', running
            run.side_effect = [
                {'root_permission': 'false'},
                {'root_permission': {'writable': True, 'option_values': ['true', 'false']}},
                running, {}, stopped, {}, {'root_permission': 'true'},
            ]
            self.assertIn('ADB、Root', configure_mumu(session))
            self.assertEqual(run.call_args_list, [
                call(*self.setting), call(*self.setting, '--info'),
                call(self.manager, 'info', '-v', '2'), call(self.manager, 'control', '-v', '2', 'shutdown'),
                call(self.manager, 'info', '-v', '2'), call(*self.setting, '--value', 'true'), call(*self.setting),
            ])
            connect.assert_called_once_with(self.manager, '2', stopped, session, launch_app=False)
            connect.return_value.require_root.assert_called_once_with()
            verify.assert_called_once_with(connect.return_value, session / '.local_setup/protocol.json')

    def test_already_enabled_root_is_verified_without_changing_settings(self) -> None:
        instance = {'is_process_started': True, 'android_version': '15.0'}
        with patch('src.mumu_setup.select_mumu', return_value=(self.manager, '2', instance)), \
                patch('src.mumu_setup.run_manager', return_value={'root_permission': 'true'}) as run, \
                patch('src.mumu_setup.connect_mumu') as connect, patch('src.mumu_setup.load_config'), \
                patch('src.mumu_setup.read_protocol'):
            connect.return_value.require_root.side_effect = TimeoutExpired('adb', 1)
            with self.assertRaisesRegex(SyncError, 'ADB 没有取得 Root'):
                configure_mumu()
            run.assert_called_once_with(*self.setting)
            connect.assert_called_once_with(self.manager, '2', instance, None, launch_app=False)

    def test_readonly_root_switch_does_not_modify_mumu(self) -> None:
        with patch('src.mumu_setup.select_mumu', return_value=(self.manager, '2', {})), \
                patch('src.mumu_setup.run_manager', side_effect=[
                    {'root_permission': 'false'}, {'root_permission': {'writable': False}}]) as run, \
                patch('src.mumu_setup.connect_mumu') as connect:
            with self.assertRaisesRegex(SyncError, '未提供可写'):
                configure_mumu()
            self.assertEqual(run.call_args_list, [call(*self.setting), call(*self.setting, '--info')])
            connect.assert_not_called()

    def test_setup_worker_has_distinct_response(self) -> None:
        self.assertEqual(parse_result(0, '{"status":"configured","message":"ok"}',
                                      sync=False, setup=True).status, 'configured')
        with patch('src.desktop_worker.subprocess.Popen', return_value=Mock()) as start:
            job = ExportJob(sync=False, setup=True)
            self.addCleanup(job.cleanup)
            self.assertEqual(start.call_args.args[0][1:4], ['-m', 'src.mumu_setup', '--json'])
