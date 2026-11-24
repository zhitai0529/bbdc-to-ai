"""Entry point for both the desktop window and its independent export worker."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

from src.runtime import is_packaged, prepare_external_programs
from src.version import VERSION


def run_worker(module: str, filename: Path, options: list[str]) -> int:
    if module not in {'src.mumu', 'src.mumu_setup', 'src.offline_export'}:
        return 2
    with filename.open('x', encoding='utf-8') as result, \
            filename.with_suffix('.log').open('x', encoding='utf-8') as log, \
            redirect_stdout(result), redirect_stderr(log):
        try:
            if module == 'src.mumu':
                from src.mumu import main as export

                prepare_external_programs()
            elif module == 'src.mumu_setup':
                from src.mumu_setup import main as export

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
    if args == ['--check-flutter']:
        from src.flutter_window import run_window
        prepare_external_programs()
        run_window([], smoke=True)
        return 0
    if args == ['--check-dashboard']:
        # Release smoke test uses a disposable LOCALAPPDATA. Do not install shortcuts.
        import time
        from src.dashboard import DashboardAPI, open_window
        ok = False

        def verify(window):
            nonlocal ok
            try:
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if window.evaluate_js("document.querySelectorAll('#kpis canvas').length === 4 && "
                                          "document.querySelector('#version').textContent.length > 1 && "
                                          "document.querySelector('#preview').hidden"):
                        window.evaluate_js("document.querySelector('[data-view=preview]').click()")
                        ok = window.evaluate_js("!document.querySelector('#preview').hidden && "
                                                "document.querySelector('#overview').hidden")
                        break
                    time.sleep(.1)
            finally:
                window.destroy()

        open_window(DashboardAPI(), verify)
        return 0 if ok else 1
    if args[:1] == ['--run-worker']:
        if len(args) < 3:
            return 2
        _, module, filename, *options = args
        return run_worker(module, Path(filename), options)

    from src.desktop import main as desktop

    prepare_external_programs()
    startup_warning = None
    if is_packaged() and sys.platform == 'win32':
        from filelock import Timeout

        from src.desktop_install import maintain_installation

        try:
            current = Path(sys.executable)
            installed = maintain_installation(current)
            if installed.parent.name != VERSION:
                # A previous download must not replace the newer installation.
                env = {**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'}
                subprocess.Popen([str(installed), *args], cwd=installed.parent, env=env,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
                return 0
        except (OSError, Timeout, subprocess.SubprocessError) as exc:
            startup_warning = f'助手可正常打开。桌面快捷方式暂未更新：{exc}'
    desktop(args, startup_warning=startup_warning)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
