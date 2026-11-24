"""Check the standalone worker in a fresh Windows profile with synthetic data."""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from src.config import PROJECT_ROOT, load_config
from src.pipeline import process_payload
from src.version import VERSION


def inspect_archive(executable: Path) -> None:
    from PyInstaller.archive.readers import CArchiveReader

    from PyInstaller.utils.win32.versioninfo import read_version_info_from_executable

    archive = CArchiveReader(str(executable))
    version_info = read_version_info_from_executable(str(executable))
    expected_version = (*map(int, VERSION.split('.')), 0)
    if version_info is None or (version_info.ffi.fileVersionMS >> 16, version_info.ffi.fileVersionMS & 65535,
                                version_info.ffi.fileVersionLS >> 16, version_info.ffi.fileVersionLS & 65535
                                ) != expected_version:
        raise RuntimeError(f'Expected Windows executable version {VERSION}')
    required = {'config.example.yaml', 'rules.yaml', 'THIRD-PARTY-NOTICES.txt'}
    if missing := required.difference(archive.toc):
        raise RuntimeError(f'Missing packaged resources: {sorted(missing)}')
    if not any(Path(name).name.startswith('_cffi_backend') and name.endswith('.pyd') for name in archive.toc):
        raise RuntimeError('Missing _cffi_backend native extension')
    for name in archive.toc:
        entry = name.lower().replace('\\', '/')
        if (entry in {'config.yaml', 'protocol.json', 'mumu-location.txt'}
                or entry.endswith(('.apk', '.db', '.mitm', '.pem', '.p12'))
                or {'raw_dumps', '.bbdc_state', '.local_setup', 'output'}.intersection(entry.split('/'))):
            raise RuntimeError(f'Unexpected data file in packaged application: {name}')
    with (PROJECT_ROOT / 'config.example.yaml').open('rb') as template:
        if archive.extract('config.example.yaml') != template.read():
            raise RuntimeError('The bundled configuration must match the public template.')
    print('Standalone EXE contents verified.')


def main() -> None:
    executable = Path(sys.argv[1]).resolve(strict=True)
    if '--inspect' in sys.argv[2:]:
        inspect_archive(executable)
        return
    day = date(2026, 11, 23)
    with TemporaryDirectory(prefix='bbdc-release-test-', ignore_cleanup_errors=True) as temporary:
        area = Path(temporary).resolve()
        profile = area / '独立配置'
        profile.mkdir()
        env = {**os.environ, 'LOCALAPPDATA': str(profile), 'PATH': str(Path(os.environ['SystemRoot']) / 'System32')}
        app_data = profile / 'bbdc-to-ai'

        def run_worker(name: str, code: int) -> dict:
            reply_path = area / f'{name}.json'
            result = subprocess.run(
                [str(executable), '--run-worker', 'src.offline_export', str(reply_path), '--date', day.isoformat()],
                cwd=area, env=env, timeout=60,
            )
            if result.returncode != code:
                log = reply_path.with_suffix('.log')
                contents = log.read_text(encoding='utf-8') if log.is_file() else ''
                raise RuntimeError(f'Expected exit {code}, got {result.returncode}. {contents}')
            return json.loads(reply_path.read_text(encoding='utf-8'))

        assert run_worker('empty', 2)['status'] == 'no_records'
        setup_reply = area / 'setup.json'
        result = subprocess.run(
            [str(executable), '--run-worker', 'src.mumu_setup', str(setup_reply),
             '--mumu-manager', str(area / 'missing' / 'MuMuManager.exe')],
            cwd=area, env=env, timeout=60,
        )
        setup = json.loads(setup_reply.read_text(encoding='utf-8'))
        if result.returncode != 4 or setup['status'] != 'mumu_missing':
            raise RuntimeError(f'Unexpected result when the selected MuMu path is absent: {result.returncode}, {setup}')
        config = load_config(app_data / 'config.yaml')
        assert config.output_dir == app_data / 'output'
        assert config.output_dir.is_relative_to(profile)
        assert (app_data / 'config.yaml').read_text(encoding='utf-8') == (
            PROJECT_ROOT / 'config.example.yaml'
        ).read_text(encoding='utf-8')
        process_payload([{'wd': 'opaque', 'st': 4, 'ut': f'{day} 10:00:00', 'ah': '999', 'rh': 'C',
                          'meaning': '不透明的'}], config, day, announce=False)
        destination = config.output_dir / f'{day}_bbdc_review.md'
        destination.unlink()
        reply = run_worker('export', 0)
        assert reply['status'] == 'exported' and reply['target_word_count'] == 1
        assert Path(reply['output']) == destination
        assert '| opaque | 不透明的 | 复习不会 | 1 |' in destination.read_text(encoding='utf-8')
        assert not (config.output_dir / f'{day}_unknown_codes.md').exists()
        subprocess.run([str(executable), '--check-dashboard'], env=env, cwd=area, timeout=65, check=True)
    print('Standalone EXE smoke test passed.')


if __name__ == '__main__':
    main()
