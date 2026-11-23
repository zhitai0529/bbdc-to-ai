"""从 MuMu 读取经过校验的学习库和词典副本。"""
from __future__ import annotations

from collections.abc import Iterable
from contextlib import closing
from pathlib import Path
import re
import sqlite3
from typing import Any, Literal

from src.localdb import decrypt_database, protocol_from_apk
from src.mumu_adb import Adb, PACKAGE


def read_protocol(adb: Adb) -> dict[str, Any]:
    package_path = adb.shell(f'pm path {PACKAGE}')
    paths = [line[8:] for line in package_path.splitlines() if line.startswith('package:')]
    if len(paths) != 1:
        raise ValueError('未找到唯一 base.apk，当前仅支持已验证的单 APK 安装')
    return protocol_from_apk(adb.run('exec-out', 'cat', paths[0], timeout=90))


def copy_database(adb: Adb, name: str, password: str, version: int, folder: Path) -> Path:
    path = folder / (name + '.sqlite')
    path.write_bytes(decrypt_database(adb.stable_database(name), password, version))
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


def add_meanings(rows: list[dict[str, Any]], dictionary: Path) -> None:
    with closing(open_verified(dictionary)) as conn:
        by_id = dictionary_entries(conn, 'id', (row['wi'] for row in rows))
        by_word = dictionary_entries(conn, 'word', (row['wd'] for row in rows if row['wi'] not in by_id))
    for row in rows:
        row['meaning'] = by_id.get(row['wi']) or by_word.get(row['wd']) or row['meaning']


def snapshot_rows(database: Path, dictionary: Path) -> list[dict[str, Any]]:
    rows = read_learning_rows(database)
    add_meanings(rows, dictionary)
    return rows
