"""Keep the executable launched by the desktop shortcuts up to date."""
from __future__ import annotations

from collections.abc import Iterable
from hashlib import sha256
import os
from pathlib import Path
import re
import shutil
from tempfile import NamedTemporaryFile

from filelock import FileLock

from src.runtime import data_directory
from src.storage import atomic_write
from src.version import VERSION
from src.windows_shortcuts import desktop_directory, downloads_directory, update_desktop_shortcuts

EXE_NAME = 'bbdc-to-ai.exe'
RECEIPT = 'sha256.txt'
VERSION_NAME = re.compile(r'[0-9]+\.[0-9]+\.[0-9]+')
DOWNLOAD_NAME = re.compile(r'bbdc-to-ai(?:-windows-x64)?(?:[-_ ]v?[0-9]+\.[0-9]+\.[0-9]+)?'
                           r'(?: \([0-9]+\))?\.exe', re.I)

# Published builds from before the app maintained its own version directory.
# Exact size and SHA-256 are required before removing an old downloaded copy.
LEGACY_RELEASES = {
    21203056: 'da7bb0ca6abc2767ec5d2260e1358391dcaf2855561529181cc51775f024df6a',
    21079731: 'ec600612db6eb5d49ac06a6eb96ac96cfa75cf6f0105b2d793b5fc1b73619549',
    21160545: '1b0dde3e5f68b49e8bad0c49e862e0d1d977bb00e21f43a2e7b03b0d6db1de0d',
    21167247: '7ee84ec0a2cda65641efdd1a6307100d047519ef2e0a5b09cc18a0ad0e4e5dfe',
    21167232: '9e2cebedc81b9c2f3b576eed6ea629853f621be0a6045d8b03e27beee48e015a',
    21173840: '2cefa97af8c730c3539eaa4acfad19a13076c9e085eb596d0c53d102a6ad649f',
    21178004: '7d68695f99d2454dfbc02b576f6194fb7615bc971578018ac4d21d57710920ae',
}


def version_number(name: str) -> tuple[int, int, int]:
    major, minor, patch = name.split('.')
    return int(major), int(minor), int(patch)


def executable_digest(path: Path) -> tuple[int, str]:
    with path.open('rb') as stream:
        digest = sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
        return stream.tell(), digest.hexdigest()


def plain_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink() and path.resolve() == path


def copy_executable(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.resolve() != destination.parent:
        raise OSError('助手安装目录指向了其他位置。')
    with NamedTemporaryFile(dir=destination.parent, suffix='.tmp', delete=False) as temporary:
        staging = Path(temporary.name)
    try:
        if os.name == 'nt':
            import ctypes

            # Copy alternate data streams, including the browser's Zone.Identifier.
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            copy_file = kernel32.CopyFileW
            copy_file.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_int)
            copy_file.restype = ctypes.c_int
            if not copy_file(str(source), str(staging), False):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            shutil.copyfile(source, staging)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)


def download_directories() -> tuple[Path, ...]:
    return downloads_directory(), desktop_directory()


def read_installed_versions(versions: Path) -> dict[str, tuple[Path, tuple[int, str]]]:
    installed = {}
    for folder in versions.iterdir():
        target = folder / EXE_NAME
        receipt = folder / RECEIPT
        if not VERSION_NAME.fullmatch(folder.name):
            continue
        try:
            if not plain_file(target) or not plain_file(receipt):
                continue
            digest = executable_digest(target)
            if receipt.read_text(encoding='ascii').strip() == digest[1]:
                installed[folder.name] = target, digest
        except (OSError, UnicodeError, RuntimeError):
            continue
    return installed


def remove_old_downloads(directories: Iterable[Path], outdated: set[tuple[int, str]], keep: Path) -> set[int]:
    sizes = {size for size, _ in outdated}
    locked_sizes: set[int] = set()
    candidates: set[Path] = set()
    for directory in directories:
        try:
            candidates.update(directory.iterdir())
        except OSError:
            continue
    for candidate in candidates:
        if not DOWNLOAD_NAME.fullmatch(candidate.name):
            continue
        size = 0
        try:
            candidate = candidate.absolute()
            if not plain_file(candidate):
                continue
            size = candidate.stat().st_size
            if size in sizes and executable_digest(candidate) in outdated:
                if candidate == keep:
                    locked_sizes.add(size)
                else:
                    candidate.unlink()
        except (OSError, RuntimeError):
            # Windows can lock an executable that is still running. Retry next startup.
            if size in sizes:
                locked_sizes.add(size)
    return locked_sizes


def maintain_installation(source: Path) -> Path:
    """Install this release if newer, publish shortcut targets, then retire older releases."""
    source = source.resolve(strict=True)
    profile = data_directory().resolve()
    profile.mkdir(parents=True, exist_ok=True)
    with FileLock(str(profile / '.exe-update.lock'), timeout=5):
        versions = profile / 'versions'
        versions.mkdir(exist_ok=True)
        if versions.resolve() != versions:
            raise OSError('助手版本目录指向了其他位置。')
        installed = read_installed_versions(versions)
        latest = max(installed.keys() | {VERSION}, key=version_number)
        target = versions / latest / EXE_NAME
        if latest not in installed:
            current = executable_digest(source)
            if target.exists():
                if not plain_file(target) or executable_digest(target) != current:
                    raise OSError('助手安装目录中存在无法识别的文件。')
            else:
                copy_executable(source, target)
            atomic_write(target.with_name(RECEIPT), current[1] + '\n')
        else:
            _, current = installed[latest]
        update_desktop_shortcuts(target)

        old: dict[Path, int] = {}
        outdated = set(LEGACY_RELEASES.items()) - {current}
        for number, (path, digest) in installed.items():
            if version_number(number) >= version_number(latest):
                continue
            outdated.add(digest)
            old[path] = digest[0]
        outdated.discard(current)
        locked_sizes = remove_old_downloads(download_directories(), outdated, source)
        for path, size in old.items():
            if path == source or size in locked_sizes:
                continue
            try:
                path.unlink()
                path.with_name(RECEIPT).unlink(missing_ok=True)
                path.parent.rmdir()
            except OSError:
                continue
        return target
