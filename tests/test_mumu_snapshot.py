from hashlib import sha256
from pathlib import Path
from subprocess import TimeoutExpired
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from src.localdb import COMMON_SHA256
from src.mumu_diagnostics import SyncError
from src.mumu_snapshot import enrich_meanings, read_protocol


class SnapshotCacheTests(unittest.TestCase):
    def test_verified_apk_cache_and_version_change(self) -> None:
        adb = Mock()
        data = b'synthetic.apk'
        digest = sha256(data).hexdigest()
        adb.shell.return_value = 'package:/data/app/test location/base.apk'
        adb.run.side_effect = [data, f'{digest}  test.apk\n'.encode(), b'2' * 64, b'different.apk']
        verified = {'app_profile': 'android-5.11.8', 'common_sha256': COMMON_SHA256,
                    'aes_iv_hex': '0' * 32, 'db_key': 's' * 14, 'dict_key': 'd' * 36}
        with TemporaryDirectory() as folder, patch('src.mumu_snapshot.protocol_from_apk',
                                                 side_effect=[verified, ValueError('App 版本未验证')]) as verify:
            cache = Path(folder) / 'protocol.json'
            self.assertEqual(read_protocol(adb, cache)['apk_sha256'], digest)
            self.assertEqual(read_protocol(adb, cache)['apk_sha256'], digest)
            self.assertEqual(verify.call_count, 1)
            self.assertEqual(adb.run.call_args.args, ('shell', "sha256sum '/data/app/test location/base.apk'"))
            with self.assertRaisesRegex(SyncError, '5.11.8 x86') as error:
                read_protocol(adb, cache)
            self.assertEqual(error.exception.reason, 'app_incompatible')
            self.assertEqual(verify.call_count, 2)

    def test_missing_apk_digest_tool_revalidates_apk(self) -> None:
        adb = Mock()
        data = b'synthetic.apk'
        adb.shell.return_value = 'package:/data/app/base.apk'
        adb.run.side_effect = [data, TimeoutExpired('sha256sum', 8), data]
        verified = {'app_profile': 'android-5.11.8', 'common_sha256': COMMON_SHA256,
                    'aes_iv_hex': '0' * 32, 'db_key': 's' * 14, 'dict_key': 'd' * 36}
        with TemporaryDirectory() as folder, patch('src.mumu_snapshot.protocol_from_apk',
                                                 return_value=verified) as verify:
            cache = Path(folder) / 'protocol.json'
            read_protocol(adb, cache)
            read_protocol(adb, cache)
            self.assertEqual(verify.call_count, 2)

    def test_dictionary_cache_needs_same_digest_and_same_exact_lookup(self) -> None:
        adb = Mock()
        adb.stable_database.side_effect = [b'encrypted-dictionary', b'updated-dictionary', b'updated-dictionary']
        adb.dictionary_sha256.side_effect = [sha256(b'encrypted-dictionary').hexdigest(),
                                              sha256(b'updated-dictionary').hexdigest()]
        with TemporaryDirectory() as folder, patch('src.mumu_snapshot.unpack_database'), \
                patch('src.mumu_snapshot.lookup_meanings',
                      side_effect=[['词典释义', None], ['新词典释义', None], ['另一条释义']]) as lookup:
            path = Path(folder)
            cache = path / 'lookups.json'
            first = [{'wi': 10, 'wd': 'Word', 'meaning': '旧学习库释义'},
                     {'wi': 11, 'wd': 'missing', 'meaning': '旧回退释义'}]
            enrich_meanings(adb, first, 'test', path, cache)
            self.assertEqual([row['meaning'] for row in first], ['词典释义', '旧回退释义'])
            second = [{'wi': 10, 'wd': 'Word', 'meaning': '新的学习库释义'},
                      {'wi': 11, 'wd': 'missing', 'meaning': '新的回退释义'}]
            enrich_meanings(adb, second, 'test', path, cache)
            self.assertEqual([row['meaning'] for row in second], ['词典释义', '新的回退释义'])
            lookup.assert_called_once()
            adb.stable_database.assert_called_once_with('simple.db')

            enrich_meanings(adb, second, 'test', path, cache)
            self.assertEqual(second[0]['meaning'], '新词典释义')
            different_spelling = [{'wi': 10, 'wd': 'word', 'meaning': '回退释义'}]
            enrich_meanings(adb, different_spelling, 'test', path, cache)
            self.assertEqual(different_spelling[0]['meaning'], '另一条释义')
            self.assertEqual(lookup.call_count, 3)
            self.assertEqual(adb.stable_database.call_count, 3)


if __name__ == '__main__':
    unittest.main()
