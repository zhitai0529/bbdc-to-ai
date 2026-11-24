"""从 MuMu 读取经过校验的学习库和词典副本。"""
from __future__ import annotations

from collections.abc import Iterable
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import re
import shlex
import sqlite3
from subprocess import TimeoutExpired
from typing import Any, Literal

from src.localdb import COMMON_SHA256, decrypt_database, protocol_from_apk
from src.mumu_adb import Adb, PACKAGE
from src.storage import write_json


def read_optional_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def read_protocol(adb: Adb, cache_path: Path | None = None) -> dict[str, Any]:
    package_path = adb.shell(f'pm path {PACKAGE}')
    paths = [line[8:] for line in package_path.splitlines() if line.startswith('package:')]
    if len(paths) != 1:
        raise ValueError('未找到唯一 base.apk，当前仅支持已验证的单 APK 安装')
    cached = read_optional_json(cache_path) if cache_path is not None else {}
    if (cached.get('app_profile') == 'android-5.11.8'
            and cached.get('common_sha256') == COMMON_SHA256
            and isinstance(apk_digest := cached.get('apk_sha256'), str) and re.fullmatch('[0-9a-f]{64}', apk_digest)
            and isinstance(iv := cached.get('aes_iv_hex'), str) and re.fullmatch('[0-9a-f]{32}', iv)
            and isinstance(cached.get('db_key'), str) and len(cached['db_key']) == 14
            and isinstance(cached.get('dict_key'), str) and len(cached['dict_key']) == 36):
        try:
            digest = adb.run('shell', f'sha256sum {shlex.quote(paths[0])}', timeout=8).split(maxsplit=1)
        except (RuntimeError, TimeoutExpired):
            digest = []
        if digest and digest[0] == apk_digest.encode('ascii'):
            return cached

    data = adb.run('exec-out', 'cat', paths[0], timeout=90)
    protocol = protocol_from_apk(data)
    if cache_path is not None:
        protocol['apk_sha256'] = sha256(data).hexdigest()
        write_json(cache_path, protocol)
    return protocol


def copy_database(adb: Adb, name: str, password: str, version: int, folder: Path) -> Path:
    return unpack_database(adb.stable_database(name), name, password, version, folder)


def unpack_database(data: bytes, name: str, password: str, version: int, folder: Path) -> Path:
    path = folder / (name + '.sqlite')
    path.write_bytes(decrypt_database(data, password, version))
    return path


def open_verified(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True)
    try:
        if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite 副本完整性检查失败')
    except Exception:
        conn.close()
        raise
    return conn


def read_learning_rows(database: Path) -> list[dict[str, Any]]:
    with closing(open_verified(database)) as conn:
        conn.row_factory = sqlite3.Row
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                  if re.fullmatch(r'LangEasyLexisV3_User_\d+', row[0])]
        if len(tables) != 1:
            raise ValueError('学习数据库含多个账号或没有已知词表，不能自动选择')
        query = f'''SELECT word, word_id, state, updatetime, learned_time, process,
                           duration, result_history, answer_history, duration_history, interpret
                    FROM "{tables[0]}" WHERE state IN (3,4,9)'''
        return [{'wd': row['word'], 'wi': row['word_id'], 'st': row['state'],
                 'ut': row['updatetime'], 'lt': row['learned_time'], 'pr': row['process'],
                 'duration': row['duration'], 'rh': row['result_history'],
                 'ah': row['answer_history'], 'dh': row['duration_history'],
                 'meaning': row['interpret'] or ''} for row in conn.execute(query)]


def dictionary_entries(conn: sqlite3.Connection, column: Literal['id', 'word'],
                       keys: Iterable[int | str]) -> dict[int | str, str]:
    unique = list(dict.fromkeys(keys))
    entries: dict[int | str, str] = {}
    for start in range(0, len(unique), 500):
        batch = unique[start:start + 500]
        placeholders = ','.join('?' for _ in batch)
        for key, meaning in conn.execute(
            f'SELECT {column}, interpret FROM t_dict_simple WHERE {column} IN ({placeholders})', batch
        ):
            if meaning:
                entries.setdefault(key, meaning)
    return entries


def lookup_meanings(rows: list[dict[str, Any]], dictionary: Path) -> list[str | None]:
    with closing(open_verified(dictionary)) as conn:
        by_id = dictionary_entries(conn, 'id', (row['wi'] for row in rows))
        by_word = dictionary_entries(conn, 'word', (row['wd'] for row in rows if row['wi'] not in by_id))
    return [by_id.get(row['wi']) or by_word.get(row['wd']) for row in rows]


def add_meanings(rows: list[dict[str, Any]], dictionary: Path) -> None:
    for row, meaning in zip(rows, lookup_meanings(rows, dictionary)):
        row['meaning'] = meaning or row['meaning']


def enrich_meanings(adb: Adb, rows: list[dict[str, Any]], password: str, folder: Path,
                    cache_path: Path) -> None:
    # Keep lookup keys separate by both ID and exact spelling. A missing dictionary entry
    # falls back to the learning row's current gloss, even when its lookup is cached.
    keys = [json.dumps((row['wi'], row['wd']), ensure_ascii=False) for row in rows]
    cache = read_optional_json(cache_path)
    entries = cache.get('entries')
    if (cache.get('version') == 1 and isinstance(entries, dict)
            and all(key in entries and (entries[key] is None or isinstance(entries[key], str)) for key in keys)
            and isinstance(digest := cache.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', digest)
            and digest == adb.dictionary_sha256()):
        meanings = [entries[key] for key in keys]
    else:
        data = adb.stable_database('simple.db')
        dictionary = unpack_database(data, 'simple.db', password, 4, folder)
        meanings = lookup_meanings(rows, dictionary)
        write_json(cache_path, {'version': 1, 'sha256': sha256(data).hexdigest(),
                                'entries': dict(zip(keys, meanings))})
    for row, meaning in zip(rows, meanings):
        row['meaning'] = meaning or row['meaning']


def snapshot_rows(database: Path, dictionary: Path) -> list[dict[str, Any]]:
    rows = read_learning_rows(database)
    add_meanings(rows, dictionary)
    return rows
