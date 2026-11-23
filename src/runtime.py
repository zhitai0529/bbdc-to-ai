"""Runtime paths for a source checkout and the standalone Windows application."""
from __future__ import annotations

import os
from pathlib import Path
import sys

from filelock import FileLock

from src.storage import atomic_write


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def is_packaged() -> bool:
    return bool(getattr(sys, 'frozen', False))


def data_directory() -> Path:
    if not is_packaged():
        return PROJECT_ROOT
    local_app_data = os.environ.get('LOCALAPPDATA')
    base = Path(local_app_data) if local_app_data else Path.home() / 'AppData' / 'Local'
    return (base / 'bbdc-to-ai').resolve()


def default_config_path() -> Path:
    folder = data_directory()
    path = folder / 'config.yaml'
    if not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        with FileLock(str(folder / '.config.lock'), timeout=5):
            if not path.is_file():
                template = (PROJECT_ROOT / 'config.example.yaml').read_text(encoding='utf-8')
                atomic_write(path, template)
    return path


def prepare_external_programs() -> None:
    if sys.platform == 'win32' and is_packaged():
        import ctypes

        # PyInstaller's search path is only appropriate for DLLs bundled with our process.
        # MuMu and ADB must load their own libraries when started by the app.
        ctypes.windll.kernel32.SetDllDirectoryW(None)
