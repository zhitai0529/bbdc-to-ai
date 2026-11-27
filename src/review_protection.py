"""Keep hand edits safe when the daily review is regenerated."""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import os
from pathlib import Path
import re
from typing import Literal
from uuid import uuid4

from src.config import Config
from src.exporter import review_path
from src.storage import atomic_write


ExportChoice = Literal['copy', 'overwrite']


class _ReviewChanged(ValueError):
    def __init__(self) -> None:
        super().__init__('原复习文件在确认后已更改或移动。请重新点击「导出复习」确认。')


def valid_revision(revision: object) -> bool:
    return isinstance(revision, str) and re.fullmatch(r'[0-9a-f]{64}', revision) is not None


def _file_digest(path: Path) -> str | None:
    try:
        with path.open('rb') as source:
            digest = sha256()
            for chunk in iter(lambda: source.read(65536), b''):
                digest.update(chunk)
            return digest.hexdigest()
    except FileNotFoundError:
        return None


def _path_id(path: Path) -> str:
    return sha256(os.fsencode(os.path.normcase(path.absolute()))).hexdigest()


def _stamp(config: Config, path: Path) -> Path:
    return config.state_dir / '.generated-reviews' / _path_id(path)


def _revision(path: Path, digest: str) -> str:
    return sha256(f'{_path_id(path)}:{digest}'.encode('ascii')).hexdigest()


def _is_generated(config: Config, path: Path, digest: str) -> bool:
    try:
        return _stamp(config, path).read_text(encoding='ascii') == digest
    except (OSError, UnicodeError):
        return False


def review_confirmation(config: Config, day: date, *, has_draft: bool) -> str | None:
    path = review_path(config.output_dir, day)
    digest = _file_digest(path)
    if digest is not None and (has_draft or not _is_generated(config, path, digest)):
        return _revision(path, digest)
    return None


def write_daily_review(config: Config, day: date, content: str, *, choice: ExportChoice | None = None,
                       revision: str | None = None) -> tuple[Path, bool]:
    """Write under the caller's pipeline lock, rechecking the approved file at save time."""
    path = review_path(config.output_dir, day)
    digest = _file_digest(path)
    if choice is not None and (digest is None or not valid_revision(revision) or _revision(path, digest) != revision):
        raise _ReviewChanged()

    generated_digest = sha256(content.replace('\n', os.linesep).encode('utf-8')).hexdigest()
    if choice == 'copy' or (choice is None and digest is not None and digest != generated_digest
                            and not _is_generated(config, path, digest)):
        return _write_copy(path, content, generated_digest, reuse=choice is None), True

    if digest != generated_digest:
        def verify_current() -> None:
            if _file_digest(path) != digest:
                raise _ReviewChanged()

        try:
            atomic_write(path, content, before_replace=verify_current)
        except _ReviewChanged:
            if choice is not None:
                raise
            return _write_copy(path, content, generated_digest, reuse=True), True
    if not _is_generated(config, path, generated_digest):
        try:
            atomic_write(_stamp(config, path), generated_digest)
        except OSError:
            # A missing stamp makes later exports ask for confirmation.
            pass
    return path, False


def _write_copy(original: Path, content: str, digest: str, *, reuse: bool) -> Path:
    suffix = digest[:12] if reuse else uuid4().hex[:12]
    copy = original.with_name(f'{original.stem}_copy_{suffix}.md')
    if reuse and _file_digest(copy) == digest:
        return copy
    while copy.exists() or copy.is_symlink():
        copy = original.with_name(f'{original.stem}_copy_{uuid4().hex[:12]}.md')
    atomic_write(copy, content)
    return copy
