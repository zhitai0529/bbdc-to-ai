"""Run the native Flutter window with private, inherited UTF-8 pipes."""
from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import subprocess
from typing import TextIO

from src.desktop_api import DesktopAPI
from src.runtime import PROJECT_ROOT, data_directory, is_packaged
from src.storage import atomic_write


THEME_MODES = ('system', 'light', 'dark')


def theme_path() -> Path:
    return data_directory() / 'appearance-theme.txt'


def read_theme() -> str:
    try:
        value = theme_path().read_text(encoding='utf-8').strip()
    except (OSError, UnicodeError):
        return 'system'
    return value if value in THEME_MODES else 'system'


class FlutterAPI(DesktopAPI):
    def save_theme(self, mode: str) -> None:
        if mode not in THEME_MODES:
            raise ValueError('无效的主题选项。')
        atomic_write(theme_path(), mode + '\n')

    def _choose(self, initial: str = '') -> Path | None:
        # Folder dialogs execute on the Python host's main thread.
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        try:
            folder = filedialog.askdirectory(parent=root, initialdir=initial or None, mustexist=True)
            return Path(folder) if folder else None
        finally:
            root.destroy()


def serve(api: FlutterAPI, requests: TextIO, replies: TextIO) -> None:
    methods = {name: getattr(api, name) for name in (
        'initialize', 'select_day', 'save_prompt', 'save_theme', 'save_review_level', 'open_folder', 'change_folder',
        'locate_manager', 'download_mumu', 'start', 'poll',
    )}
    try:
        for line in requests:
            try:
                request = json.loads(line)
            except ValueError:
                continue  # The engine may also emit diagnostic lines.
            if not isinstance(request, dict) or type(request.get('id')) is not int:
                continue
            reply = {'id': request['id']}
            try:
                method = methods[request['method']]
                reply['result'] = method(*request.get('args', []))
            except Exception as exc:
                reply['error'] = str(exc) or type(exc).__name__
            try:
                replies.write(json.dumps(reply, ensure_ascii=False) + '\n')
                replies.flush()
            except (BrokenPipeError, OSError):
                break
    finally:
        api._close()


def binary() -> Path:
    folder = PROJECT_ROOT / 'flutter_ui'
    if not is_packaged():
        folder = folder / 'build/windows/x64/runner/Release'
    return folder / 'review_ui.exe'


def run_window(argv: Sequence[str] | None = None, *, startup_warning: str | None = None,
               smoke: bool = False) -> None:
    parser = argparse.ArgumentParser(description='不背单词复习助手')
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--open-latest', action='store_true')
    args = parser.parse_args(argv)
    executable = binary()
    with subprocess.Popen([str(executable), f'--theme={read_theme()}', *(['--smoke'] if smoke else [])],
                          cwd=executable.parent, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, text=True, encoding='utf-8', errors='replace',
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) as process:
        assert process.stdin is not None and process.stdout is not None
        serve(FlutterAPI(startup_warning, args.export, args.open_latest), process.stdout, process.stdin)
        if process.wait() != 0:
            raise RuntimeError('Flutter 窗口异常退出。')
