"""Entry point for both the desktop window and its independent export worker."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import sys

from src.runtime import prepare_external_programs


def main() -> int:
    args = sys.argv[1:]
    if args[:1] == ['--run-worker']:
        if len(args) < 3:
            return 2
        _, module, filename, *options = args
        if module == 'src.mumu':
            from src.mumu import main as export

            prepare_external_programs()
        elif module == 'src.offline_export':
            from src.offline_export import main as export
        else:
            return 2
        with Path(filename).open('x', encoding='utf-8') as result, redirect_stdout(result):
            with Path(filename).with_suffix('.log').open('x', encoding='utf-8') as log, redirect_stderr(log):
                return export(['--json', *options])

    from src.desktop import main as desktop

    prepare_external_programs()
    desktop(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
