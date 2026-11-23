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


def main() -> None:
    executable = Path(sys.argv[1]).resolve(strict=True)
    day = date(2026, 11, 23)
    with TemporaryDirectory(prefix='bbdc-release-test-') as temporary:
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
    print('Standalone EXE smoke test passed.')


if __name__ == '__main__':
    main()
