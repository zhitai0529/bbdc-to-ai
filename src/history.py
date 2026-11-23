"""SQLite 每日词汇历史，保存提级前的分类。"""
from __future__ import annotations

from contextlib import closing
from datetime import date
from pathlib import Path
import sqlite3

from src.parser import WordRecord


def _count_between(conn: sqlite3.Connection, first: date, last: date) -> dict[str, int]:
    return dict(conn.execute("""
        SELECT word, COUNT(*)
        FROM daily_word_log
        WHERE study_date BETWEEN ? AND ? AND category IN ('hard', 'fuzzy')
        GROUP BY word
    """, (first.isoformat(), last.isoformat())))


def count_prior_days(path: Path, day: date, window_days: int) -> dict[str, int]:
    """读取窗口内的历史日期，当天由当前的词表补计。"""
    if window_days <= 1 or day == date.min or not path.is_file():
        return {}
    first_day = date.fromordinal(max(1, day.toordinal() - window_days + 1))
    last_day = date.fromordinal(day.toordinal() - 1)
    with closing(sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True, timeout=10)) as conn:
        return _count_between(conn, first_day, last_day)


def log_and_count_recent(
    path: Path, day: date, words: list[WordRecord], window_days: int
) -> dict[str, int]:
    """每个学习日每词一行，在同一个事务内写入和查询（含当天）。"""
    first_day = date.fromordinal(max(1, day.toordinal() - window_days + 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=10)) as conn, conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_word_log (
                study_date TEXT NOT NULL,
                word TEXT NOT NULL,
                category TEXT NOT NULL CHECK (category IN ('hard', 'fuzzy', 'mastered', 'unconfirmed')),
                wrong_count REAL,
                rating TEXT,
                ah TEXT,
                rh TEXT,
                updated_at TEXT,
                PRIMARY KEY (study_date, word)
            )
        """)
        conn.executemany("""
            INSERT INTO daily_word_log (study_date, word, category, wrong_count, rating, ah, rh, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (study_date, word) DO UPDATE SET
                category = excluded.category,
                wrong_count = excluded.wrong_count,
                rating = excluded.rating,
                ah = excluded.ah,
                rh = excluded.rh,
                updated_at = excluded.updated_at
        """, (
            (day.isoformat(), word.spelling.casefold(),
             'unconfirmed' if word.level == 'unclassified' else word.level,
             word.errors, word.raw_rating or None, word.answer_history or None,
             word.result_history, word.learned_at)
            for word in words
        ))
        return _count_between(conn, first_day, day)
