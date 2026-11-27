"""本地原子写入与按接口路径备份。原始数据可能含个人信息，不应提交。"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import uuid4


def atomic_write(path: Path, content: str, *, before_replace: Callable[[], None] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=f'.{path.name}.', suffix='.tmp', delete=False) as handle:
            name = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if before_replace is not None:
            before_replace()
        os.replace(name, path)
    finally:
        if name is not None and Path(name).exists():
            Path(name).unlink(missing_ok=True)


def write_json(path: Path, payload: Any) -> None:
    atomic_write(path, json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def save_raw(directory: Path, request_path: str, payload: Any, captured_at: datetime) -> Path:
    # 不写 query、请求头或认证信息；同接口重复抓取也不会覆盖。
    path_only = unquote(urlsplit(request_path).path)
    slug = re.sub(r'[^A-Za-z0-9_.-]+', '_', path_only).strip('._')[:100] or 'root'
    stamp = captured_at.strftime('%Y%m%dT%H%M%S_%f')
    destination = directory / f'{stamp}__{slug}__{uuid4().hex[:12]}.json'
    write_json(destination, payload)
    return destination
