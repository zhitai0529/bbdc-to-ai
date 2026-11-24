"""全部使用合成记录/密钥，真实账号数据不进入测试源码。"""
from __future__ import annotations

import base64
from dataclasses import replace
from datetime import date, datetime
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from mitmproxy import connection, http

from src.bbdc_schema import study_date
from src.config import load_config
from src.emulator_proxy import EmulatorProxy, mount_marker
from src.envelope import EncryptedPayloadError, unwrap_payload
from src.interceptor import BBDCInterceptor, is_target_host
from src.localdb import decrypt_database
from src.mumu import NoStudyRecords, export_snapshot, export_study_day, snapshot_rows
from src.mumu_adb import Adb
from src.parser import parse_payload
from src.pipeline import process_payload

DAY = date(2026, 11, 11)


def record(word: str, rating: str, answer: str, **extra: object) -> dict:
    return dict(wd=word, st=4, ut='2026-11-12 01:30:00', lt='2023-01-01 12:00:00',
                rh=rating, ah=answer, meaning='测试释义', **extra)


class AndroidProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.config = replace(load_config(), root=self.folder, raw_dump_dir=self.folder / 'raw',
                              state_dir=self.folder / 'state', output_dir=self.folder / 'output')

    def test_confirmed_ratings_and_unknown_codes(self) -> None:
        rows = [record('direct', 'A', '0'), record('uncertain', 'B', '110'),
                record('wrong once', 'D', '210'), record('wrong twice', 'E', '410'),
                record('unknown rating', 'C', '110'), record('unknown answer', 'D', '999')]
        words = parse_payload(rows, self.config, DAY).words
        self.assertEqual([w.level for w in words],
                         ['mastered', 'fuzzy', 'hard', 'hard', 'hard', 'hard'])
        self.assertEqual([w.errors for w in words[:4]], [0, 0, 1, 2])
        self.assertEqual([w.raw_rating for w in words[:4]], ['A', 'B', 'D', 'E'])

    def test_four_am_boundary_uses_review_update_not_first_learned(self) -> None:
        self.assertEqual(study_date(datetime.fromisoformat('2026-11-12T03:59:59')), DAY)
        self.assertEqual(study_date(datetime.fromisoformat('2026-11-12T04:00:00')), date(2026, 11, 12))
        row = record('reviewed', 'D', '210')
        self.assertEqual(len(parse_payload([row], self.config, DAY).words), 1)
        row['ut'] = '2026-11-12 04:00:00'
        self.assertEqual(len(parse_payload([row], self.config, DAY).words), 0)

    def test_downloaded_unstudied_words_are_not_included(self) -> None:
        row = record('downloaded', 'A', '0')
        row['st'] = 1
        self.assertEqual(parse_payload([row], self.config, DAY).words, [])

    def test_last_round_history_and_ellipsis_phrase(self) -> None:
        rows = [record('take… for granted', 'DE#A', '210,410#0'),
                record('multiple attempts', 'A#D', '0#110,210')]
        words = parse_payload(rows, self.config, DAY).words
        self.assertEqual(len(words), 2)
        self.assertEqual(words[0].level, 'mastered')
        self.assertEqual(words[1].errors, 1)

    def test_real_output_labels_do_not_claim_permanent_mastery(self) -> None:
        result = process_payload([record('retained', 'D', '210'), record('excluded', 'A', '0')],
                                 self.config, DAY, announce=False)
        text = result.output.read_text(encoding='utf-8')
        self.assertIn('本轮直接认识或已标熟：1', text)
        self.assertIn('不保证永久掌握', text)
        self.assertIn('retained', text)
        self.assertNotIn('excluded', text)

    def test_aes_envelope_and_safe_failure_messages(self) -> None:
        iv, secret = bytes(range(16)), '0123456789abcdef' * 2
        self.assertEqual(len(secret), 32)
        protocol = self.folder / 'protocol.json'
        protocol.write_text(json.dumps({'aes_iv_hex': iv.hex()}), encoding='utf-8')
        payload = {'records': [record('decoded', 'D', '210')]}
        pad = PKCS7(128).padder()
        padded = pad.update(json.dumps(payload).encode()) + pad.finalize()
        encrypt = Cipher(algorithms.AES(secret.encode()), modes.CBC(iv)).encryptor()
        body = base64.b64encode(encrypt.update(padded) + encrypt.finalize()).decode()
        wrapped = {'data_encrypted': 1, 'data_body': body, 'v3_security': {'secret': secret}}
        self.assertEqual(unwrap_payload(wrapped, protocol), payload)
        with self.assertRaises(EncryptedPayloadError):
            unwrap_payload(wrapped)
        wrapped['data_body'] = 'malformed'
        with self.assertRaises(EncryptedPayloadError) as error:
            unwrap_payload(wrapped, protocol)
        self.assertNotIn(secret, str(error.exception))
        wrapped['v3_security'] = {}
        with self.assertRaises(EncryptedPayloadError):
            unwrap_payload(wrapped, protocol)
        self.assertEqual(unwrap_payload({'data_body': '{"ok":1}', 'data_encrypted': 0}), {'ok': 1})

    def test_uploaded_stat_is_independent_of_response_decryption(self) -> None:
        flow = http.HTTPFlow(connection.Client(peername=('127.0.0.1', 1), sockname=('127.0.0.1', 8888)),
                             connection.Server(address=('api.beingfine.cn', 443)))
        flow.request = http.Request.make('POST', 'https://api.beingfine.cn/v3/bb/user-stat/process/123')
        flow.request.urlencoded_form = {'stat': json.dumps([record('uploaded', 'D', '210')]),
                                        'token': 'never-back-up-this-authentication'}
        flow.response = http.Response.make(200, json.dumps({'result_code': 200, 'data_body': '',
                                                          'data_encrypted': 1}).encode(),
                                           {'Content-Type': 'application/json'})
        addon = BBDCInterceptor()
        addon.config = self.config
        with patch('src.interceptor.process_payload') as pipeline:
            addon.response(flow)
        pipeline.assert_called_once()
        saved = list(self.config.raw_dump_dir.glob('*sync_request*.json'))
        self.assertEqual(len(saved), 1)
        self.assertNotIn('never-back-up', saved[0].read_text(encoding='utf-8'))
        for url, status in [('https://api.beingfine.cn/unrelated', 200),
                            ('https://api.beingfine.cn/v3/bb/user-stat/process/123', 500)]:
            flow.request.url = url
            flow.response.status_code = status
            addon.response(flow)
        self.assertEqual(len(list(self.config.raw_dump_dir.glob('*sync_request*.json'))), 1)
        self.assertTrue(is_target_host('api.beingfine.cn'))
        self.assertFalse(is_target_host('beingfine.cn.example.org'))

    def test_snapshot_joins_meanings_and_closes_windows_handles(self) -> None:
        database, dictionary = self.folder / 'study.db', self.folder / 'dict.db'
        conn = sqlite3.connect(database)
        conn.execute('CREATE TABLE LangEasyLexisV3_User_123 (word TEXT, word_id INTEGER, state INTEGER, '
                     'updatetime TEXT, learned_time TEXT, process TEXT, duration INTEGER, '
                     'result_history TEXT, answer_history TEXT, duration_history TEXT, interpret TEXT)')
        conn.execute("INSERT INTO LangEasyLexisV3_User_123 VALUES ('joined',1,4,'2026-11-12 01:00:00',"
                     "'2023-01-01','',100,'D','210','','')")
        conn.commit()
        conn.close()
        conn = sqlite3.connect(dictionary)
        conn.execute('CREATE TABLE t_dict_simple (id INTEGER, word TEXT, interpret TEXT)')
        conn.execute('INSERT INTO t_dict_simple VALUES (1,?,?)', ('joined', '[{"p":"v.","i":"连接"}]'))
        conn.commit()
        conn.close()
        rows = snapshot_rows(database, dictionary)
        self.assertEqual(len(rows), 1)
        self.assertIn('连接', rows[0]['meaning'])
        database.unlink()  # Windows 上未关闭 sqlite 连接会在此报错。
        dictionary.unlink()

    def test_empty_day_does_not_open_dictionary_or_overwrite_history(self) -> None:
        existing = self.config.output_dir / '2026-11-11_bbdc_review.md'
        existing.parent.mkdir()
        existing.write_text('historical review', encoding='utf-8')
        target = date(2026, 11, 20)
        with patch('src.mumu.initialize_protocol', return_value={'db_key': 'test'}), \
                patch('src.mumu.copy_database') as copy_database, \
                patch('src.mumu.read_learning_rows', return_value=[record('historical', 'D', '210')]):
            with self.assertRaises(NoStudyRecords) as error:
                export_snapshot(Mock(), self.config, target, announce=False)
            self.assertEqual(error.exception.day, target)
            self.assertEqual(error.exception.last_day, DAY)
            copy_database.assert_called_once()
            self.assertEqual(copy_database.call_args.args[1], 'LangEasyLexis.db')
        self.assertEqual(list(self.config.output_dir.glob('*.md')), [existing])
        self.assertEqual(existing.read_text(encoding='utf-8'), 'historical review')

    def test_export_includes_target_day_rows_and_keeps_their_real_date(self) -> None:
        target = date(2026, 11, 20)
        current = record('current', 'D', '210')
        current['ut'] = '2026-11-20T00:00:00+00:00'
        undated = record('undated', 'A', '0')
        undated['ut'] = None
        rows = [record('historical', 'B', '110'), current, undated]
        with patch('src.mumu.initialize_protocol', return_value={'db_key': 'test', 'dict_key': 'test'}), \
                patch('src.mumu.copy_database'), patch('src.mumu.enrich_meanings'), \
                patch('src.mumu.read_learning_rows', return_value=rows):
            output = export_snapshot(Mock(), self.config, target, announce=False)
        self.assertEqual(output.name, '2026-11-20_bbdc_review.md')
        review = output.read_text(encoding='utf-8')
        self.assertIn('| current |', review)
        self.assertNotIn('| historical |', review)

    def test_second_group_adds_new_words_to_same_day_file(self) -> None:
        target = date(2026, 11, 20)
        first = record('first batch', 'B', '110')
        first['ut'] = '2026-11-20 10:00:00'
        second = record('new difficult', '2', '2')
        second.update(ut='2026-11-20 15:00:00', lt='20261120150000')
        easy = record('new easy', '0', '0')
        easy.update(ut='2026-11-20 15:01:00', lt='20261120150100')
        with patch('src.mumu.initialize_protocol', return_value={'db_key': 'test', 'dict_key': 'test'}), \
                patch('src.mumu.copy_database'), patch('src.mumu.enrich_meanings'), \
                patch('src.mumu.read_learning_rows', side_effect=[[first], [first, second, easy], [first, second, easy]]):
            initial = export_study_day(Mock(), self.config, target, announce=False)
            updated = export_study_day(Mock(), self.config, target, announce=False)
            repeated = export_study_day(Mock(), self.config, target, announce=False)
        self.assertEqual(initial.path, updated.path)
        self.assertEqual((initial.new_word_count, updated.new_word_count, repeated.new_word_count), (1, 2, 0))
        self.assertEqual(updated.latest_saved_at, '2026-11-20T15:01:00+08:00')
        self.assertEqual(updated.target_word_count, 2)
        review = updated.path.read_text(encoding='utf-8')
        self.assertIn('| first batch |', review)
        self.assertIn('| new difficult | 测试释义 | 初学时答错 | 2 |', review)
        self.assertNotIn('| new easy |', review)
        self.assertFalse(updated.path.with_name('2026-11-20_unknown_codes.md').exists())

    def test_initial_learning_codes_require_the_complete_matching_digit(self) -> None:
        result = parse_payload([record('learned', '9', '9'), record('mixed history', 'A1', '1'),
                                record('mismatched', '1', '2')], self.config, DAY)
        self.assertEqual([(word.level, word.errors) for word in result.words],
                         [('hard', 9), ('hard', 1), ('hard', 1)])
        self.assertEqual([word.unknown_bbdc_code for word in result.words], [False, True, True])

    def test_mumu_manager_address_takes_priority_over_adb_alias(self) -> None:
        vendor = self.folder / 'programs'
        shell = vendor / 'NetEase/MuMu/nx_device/15.0/shell'
        shell.mkdir(parents=True)
        (shell / 'adb.exe').touch()
        manager = vendor / 'NetEase/MuMu/nx_main/MuMuManager.exe'
        manager.parent.mkdir()
        manager.touch()
        instances = {'1': {'is_android_started': True, 'adb_port': 16416}}
        devices = b'List of devices attached\n127.0.0.1:16416\tdevice\nemulator-5556\tdevice\n'
        with patch.dict('os.environ', {'ProgramFiles': str(vendor)}), patch('src.mumu_adb.shutil.which', return_value=None), \
                patch('src.mumu_adb.subprocess.run', side_effect=lambda *args, **kwargs: Mock(stdout=json.dumps(instances).encode())), \
                patch('src.mumu_adb.subprocess.check_output', return_value=devices):
            self.assertEqual(Adb().serial, '127.0.0.1:16416')
            instances['2'] = {'is_android_started': True, 'adb_port': 16448}
            with patch('src.mumu_adb.subprocess.check_output', return_value=devices + b'127.0.0.1:16448\tdevice\n'):
                with self.assertRaisesRegex(ValueError, '设备不唯一'):
                    Adb()

    def test_wsa_reads_stable_database_with_magisk_and_binary_safe_encoding(self) -> None:
        adb = object.__new__(Adb)
        binary = b'\x00\x01\n\r\n\xff\x80'
        wire = b'7\r\n' + base64.b64encode(binary) + b'\r\n'
        with patch.object(adb, 'shell', side_effect=['uid=2000(shell)', 'windows_x86_64']), \
                patch.object(adb, 'run', side_effect=[b'uid=0(root)', b'', wire, wire, b'']) as run, \
                patch.object(adb, 'require_root') as adb_root:
            adb.prepare_database_access()
            self.assertEqual(adb.stable_database('LangEasyLexis.db'), binary)
            reads = [call.args for call in run.call_args_list if '&& base64' in call.args[-1]]
            self.assertEqual(len(reads), 2)
            self.assertTrue(all(args[0:2] == ('shell', '-T') for args in reads))
            self.assertTrue(all(args[2].startswith("su -c 'wc -c < /data/user/0/") for args in reads))
            adb_root.assert_not_called()

    def test_adb_connection_and_commands_hide_console_on_windows(self) -> None:
        executable = self.folder / 'adb.exe'
        executable.touch()
        with patch('src.mumu_adb.NO_CONSOLE', 0x08000000), \
                patch('src.mumu_adb.discover_mumu_manager') as discover, \
                patch('src.mumu_adb.subprocess.run', return_value=Mock(returncode=0, stdout=b'ok')) as run:
            adb = Adb(str(executable), '127.0.0.1:16416')
            self.assertEqual(adb.run('shell', 'true'), b'ok')
            self.assertEqual(run.call_count, 2)
            self.assertTrue(all(call.kwargs['creationflags'] == 0x08000000 for call in run.call_args_list))
            discover.assert_not_called()

    def test_dictionary_digest_checks_for_unmerged_writes(self) -> None:
        adb = object.__new__(Adb)
        digest = 'a' * 64
        with patch.object(adb, '_database_shell', side_effect=[f'{digest}  /file'.encode(),
                                                              RuntimeError('still writing')]) as shell:
            self.assertEqual(adb.dictionary_sha256(), digest)
            self.assertIsNone(adb.dictionary_sha256())
            command = shell.call_args.args[0]
            self.assertEqual(command.count('-wal'), 2)
            self.assertEqual(command.count('-journal'), 2)

    def test_missing_database_is_reported_before_the_binary_read(self) -> None:
        adb = object.__new__(Adb)
        adb._use_su = True
        with patch.object(adb, 'run', return_value=b'missing\r\n') as run:
            with self.assertRaisesRegex(FileNotFoundError, '登录原账号并完成一组学习'):
                adb.stable_database('LangEasyLexis.db')
            run.assert_called_once()

    def test_wsa_permission_denial_does_not_restart_adb_as_root(self) -> None:
        adb = object.__new__(Adb)
        with patch.object(adb, 'shell', side_effect=['uid=2000(shell)', 'windows_x86_64']), \
                patch.object(adb, 'run', side_effect=RuntimeError('Permission denied')), \
                patch.object(adb, 'require_root') as adb_root:
            with self.assertRaisesRegex(PermissionError, '在 Magisk 中允许 Shell'):
                adb.prepare_database_access()
            adb_root.assert_not_called()

    def test_mount_marker_matches_android_mount_roots(self) -> None:
        store = '/data/local/tmp/bbdc-ai-cacerts-20261112123640'
        marker = mount_marker(store)
        for root in ('/local/tmp/', '/data/local/tmp/'):
            line = f'42 30 8:1 {root}{store.rsplit("/", 1)[-1]} /apex/com.android.conscrypt/cacerts rw - ext4 /dev/x rw'
            self.assertIn(marker, line)
        with self.assertRaises(ValueError):
            mount_marker('/data/local/tmp/another-store')

    def test_restore_keeps_user_changed_proxy(self) -> None:
        state = self.folder / '.local_setup/proxy_session.json'
        state.parent.mkdir()
        state.write_text(json.dumps({'serial': 'test-device', 'port': 8888, 'previous_proxy': 'null',
                                    'store': '/data/local/tmp/bbdc-ai-cacerts-20261112123640'}))
        adb = Mock(serial='test-device')
        adb.shell.return_value = 'user-selected-proxy:9999'
        adb.run.return_value = b''
        EmulatorProxy(adb, self.config).restore()
        commands = [str(call.args[0]) for call in adb.shell.call_args_list]
        self.assertFalse(any('settings put' in c or 'settings delete' in c for c in commands))
        self.assertTrue(any('grep -Fq' in c and '/bbdc-ai-cacerts-' in c for c in commands))
        self.assertFalse(state.exists())

    def test_restore_clears_android_effective_proxy_before_removing_forward(self) -> None:
        session = EmulatorProxy(Mock(serial='test-device'), self.config)
        session.state_path.parent.mkdir()
        session.state_path.write_text(json.dumps({'serial': 'test-device', 'port': 8888, 'previous_proxy': 'null',
                                                 'store': '/data/local/tmp/bbdc-ai-cacerts-20261112123640'}))
        commands = {
            'settings get global http_proxy': '127.0.0.1:8888',
            'settings get global global_http_proxy_host': '127.0.0.1',
            'settings get global global_http_proxy_port': '8888',
            'settings get global global_http_proxy_pac': 'null',
        }

        def shell(command: str) -> str:
            if command == "settings put global http_proxy ':0'":
                commands['settings get global global_http_proxy_host'] = ''
                commands['settings get global global_http_proxy_port'] = '0'
            return commands.get(command, '')

        def run(*args: str) -> bytes:
            if args == ('reverse', '--list'):
                return b'tcp:8888 tcp:8888'
            self.assertEqual(args, ('reverse', '--remove', 'tcp:8888'))
            self.assertEqual(commands['settings get global global_http_proxy_port'], '0')
            self.assertTrue(session.state_path.exists())
            return b''

        session.adb.shell.side_effect = shell
        session.adb.run.side_effect = run
        session.restore()
        self.assertFalse(session.state_path.exists())

    def test_legacy_recovery_only_clears_an_orphaned_tool_proxy(self) -> None:
        adb = Mock()
        values = {'http_proxy': 'null', 'global_http_proxy_host': '127.0.0.1',
                  'global_http_proxy_port': '8888', 'global_http_proxy_pac': 'null'}

        def shell(command: str) -> str:
            if command == "settings put global http_proxy ':0'":
                values.update(http_proxy=':0', global_http_proxy_host='', global_http_proxy_port='0')
                return ''
            return values[command.split()[-1]]

        adb.shell.side_effect = shell
        session = EmulatorProxy(adb, self.config)
        adb.run.return_value = b'tcp:8888 tcp:8888'
        self.assertFalse(session.recover_legacy_proxy())
        self.assertEqual(values['global_http_proxy_host'], '127.0.0.1')
        adb.run.return_value = b''
        self.assertTrue(session.recover_legacy_proxy())
        self.assertFalse(session.recover_legacy_proxy())

    def test_launcher_keyboard_interrupt_restores_before_stopping_listener(self) -> None:
        from src.launcher import main
        calls = []
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [KeyboardInterrupt, 0]
        process.terminate.side_effect = lambda: calls.append('terminate')
        session = Mock()
        session.restore.side_effect = lambda: calls.append('restore')
        with patch('sys.argv', ['launcher', '--mumu']), \
                patch('src.launcher.load_config', return_value=self.config), \
                patch('src.launcher.subprocess.Popen', return_value=process), \
                patch('src.launcher.socket.socket') as sock, \
                patch('src.launcher.socket.create_connection'), \
                patch('src.emulator_proxy.EmulatorProxy', return_value=session), patch('src.mumu_adb.Adb'):
            sock.return_value.__enter__.return_value.connect_ex.return_value = 1
            self.assertEqual(main(), 0)
        self.assertEqual(calls, ['restore', 'terminate'])


class SQLCipherTests(unittest.TestCase):
    def test_all_pages_authenticated_in_both_supported_formats(self) -> None:
        # 独立构造两页已知明文；第二页损坏也必须整库拒绝。
        for version, size, reserve, digest, iterations in [(2, 1024, 48, 'sha1', 4000),
                                                          (4, 4096, 80, 'sha512', 256000)]:
            with self.subTest(version=version):
                salt, password = bytes(range(16)), 'synthetic-password'
                key = hashlib.pbkdf2_hmac(digest, password.encode(), salt, iterations, 32)
                mac_key = hashlib.pbkdf2_hmac(digest, key, bytes(x ^ 0x3a for x in salt), 2, 32)
                plain = bytearray(size * 2)
                plain[:16] = b'SQLite format 3\0'
                plain[16:18] = struct.pack('>H', size)
                encrypted = bytearray()
                for page_number in (1, 2):
                    start = 16 if page_number == 1 else 0
                    iv = bytes([page_number]) * 16
                    part = plain[(page_number - 1) * size + start:page_number * size - reserve]
                    cipher = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
                    body = cipher.update(part) + cipher.finalize()
                    tag = hmac.new(mac_key, body + iv + struct.pack('<I', page_number), digest).digest()
                    page = (salt if page_number == 1 else b'') + body + iv + tag
                    encrypted += page + bytes(size - len(page))
                self.assertEqual(decrypt_database(bytes(encrypted), password, version), bytes(plain))
                with self.assertRaisesRegex(ValueError, '第 1 页校验失败'):
                    decrypt_database(bytes(encrypted), 'wrong-password', version)
                encrypted[size + 30] ^= 1
                with self.assertRaisesRegex(ValueError, '第 2 页校验失败'):
                    decrypt_database(bytes(encrypted), password, version)


if __name__ == '__main__':
    unittest.main()
