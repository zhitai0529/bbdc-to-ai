"""Entry point for both the desktop window and its independent export worker."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import json
from pathlib import Path
import sys
import traceback

from src.runtime import prepare_external_programs


def run_worker(module: str, filename: Path, options: list[str]) -> int:
    if module not in {'src.mumu', 'src.offline_export'}:
        return 2
    with filename.open('x', encoding='utf-8') as result, \
            filename.with_suffix('.log').open('x', encoding='utf-8') as log, \
            redirect_stdout(result), redirect_stderr(log):
        try:
            if module == 'src.mumu':
                from src.mumu import main as export

                prepare_external_programs()
            else:
                from src.offline_export import main as export

            return export(['--json', *options])
        except Exception as exc:
            traceback.print_exc(file=log)
            result.seek(0)
            result.truncate()
            json.dump({'status': 'error', 'message': f'导出模块运行失败：{exc}'}, result, ensure_ascii=False)
            return 1


def main() -> int:
    args = sys.argv[1:]
    if args[:1] == ['--run-worker']:
        if len(args) < 3:
            return 2
        _, module, filename, *options = args
        return run_worker(module, Path(filename), options)

    from src.desktop import main as desktop

    prepare_external_programs()
    desktop(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
