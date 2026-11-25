"""Coordinate stopping a desktop sync with publication of its local files."""
from pathlib import Path

from filelock import FileLock, Timeout

from src.mumu_diagnostics import SyncError


def claim_sync_stop(session: Path) -> bool:
    try:
        with FileLock(str(session / 'save.lock'), timeout=0):
            if (session / 'saving').exists():
                return False
            (session / 'cancel').touch()
            return True
    except Timeout:
        return False


def begin_sync_save(session: Path) -> None:
    with FileLock(str(session / 'save.lock')):
        if (session / 'cancel').exists():
            raise SyncError('本次同步已停止。')
        # Keep the marker until the process and its result have been collected.
        (session / 'saving').touch()
