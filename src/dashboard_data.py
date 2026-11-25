"""Read-only projections of the local study history for the desktop dashboard."""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
import sqlite3
from typing import Any

from src.bbdc_schema import study_date
from src.config import Config
from src.desktop_files import review_path as review_path
from src.export_summary import read_export_summary
from src.history import count_prior_days
from src.parser import WordRecord, collect_unknown_codes
from src.pipeline import escalate
from src.review_cache import ReviewCache
from src.version import VERSION


def history_series(conn: sqlite3.Connection, day: date, config: Config) -> list[dict]:
    """Compute each day's promotions using only information available on that day."""
    first = date.fromordinal(max(1, day.toordinal() - 167))
    lookback = min(config.escalation_window_days - 1, day.toordinal() - 1)
    history_start = date.fromordinal(max(1, first.toordinal() - lookback))
    rows = conn.execute("""
        WITH recent AS (
            SELECT study_date, category, updated_at,
                   SUM(category IN ('hard','fuzzy')) OVER (
                       PARTITION BY word ORDER BY julianday(study_date)
                       RANGE BETWEEN ? PRECEDING AND CURRENT ROW
                   ) AS hits
            FROM daily_word_log WHERE study_date BETWEEN ? AND ?
        )
        SELECT study_date AS day, COUNT(*) AS total, SUM(category='mastered') AS mastered,
               SUM(category='hard' OR (category='fuzzy' AND hits>=?)) AS hard,
               SUM(category='fuzzy' AND hits<?) AS fuzzy,
               SUM(category='fuzzy' AND hits>=?) AS promoted, MAX(updated_at) AS latest
        FROM recent WHERE study_date>=? GROUP BY study_date ORDER BY study_date
    """, (lookback, history_start.isoformat(), day.isoformat(),
          *([config.fuzzy_escalation_threshold] * 3), first.isoformat()))
    return [dict(row) for row in rows]


def dashboard(config: Config, selection: str | None = None) -> dict[str, Any]:
    try:
        return _snapshot(config, selection, use_history=True)
    except sqlite3.Error as exc:
        # Keep existing Markdown and the settings page accessible when SQLite is unavailable.
        data = _snapshot(config, selection, use_history=False)
        data['warning'] = (
            f'历史库暂时无法读取。可以继续查看已有复习文件。请关闭其他正在导出的窗口后重试。'
            f'读取错误为 {exc}。 {data["warning"]}'
        ).strip()
        return data


def _snapshot(config: Config, selection: str | None, *, use_history: bool) -> dict[str, Any]:
    today = study_date(datetime.now(config.timezone))
    day = date.fromisoformat(selection) if selection else today
    dates = {today.isoformat(), day.isoformat()}
    exports: dict[date, Path] = {}
    for path in config.output_dir.glob('????-??-??_bbdc_review.md'):
        try:
            exported_day = date.fromisoformat(path.name[:10])
        except ValueError:
            continue
        if path.is_file():
            exports[exported_day] = path
            dates.add(exported_day.isoformat())
    series: list[dict] = []
    repeats: list[dict] = []
    stored: list[WordRecord] = []
    sidebar = None
    if use_history and config.history_path.is_file():
        with closing(sqlite3.connect(config.history_path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            dates.update(row[0] for row in conn.execute('SELECT DISTINCT study_date FROM daily_word_log'))
            series = history_series(conn, day, config)
            sidebar = conn.execute("""
                SELECT COUNT(*) AS total, SUM(category='mastered') AS mastered,
                       (SELECT MAX(updated_at) FROM daily_word_log WHERE study_date<=?) AS latest
                FROM daily_word_log WHERE study_date=?
            """, (today.isoformat(), today.isoformat())).fetchone()
            first = date.fromordinal(max(1, day.toordinal() - config.escalation_window_days + 1)).isoformat()
            repeats = [dict(row) for row in conn.execute("""
                SELECT word, COUNT(*) AS days, MAX(study_date) AS last_day
                FROM daily_word_log WHERE study_date BETWEEN ? AND ? AND category IN ('hard','fuzzy')
                GROUP BY word HAVING COUNT(*) >= 2 ORDER BY days DESC, last_day DESC, word
            """, (first, day.isoformat()))]
            stored = [WordRecord(spelling=row['word'], level=row['category'], errors=row['wrong_count'],
                                 learned_at=row['updated_at']) for row in conn.execute(
                'SELECT word, category, wrong_count, updated_at FROM daily_word_log WHERE study_date=?',
                (day.isoformat(),))]
    warning = ''
    try:
        cached = ReviewCache(config, day).load()
    except (ValueError, TypeError, OSError) as exc:
        cached = {}
        warning = f'词条缓存暂时无法读取。可先打开已有复习文件。读取错误为 {exc}。'
    words = list(cached.values()) or stored
    counts = Counter(count_prior_days(config.history_path, day, config.escalation_window_days)
                     if use_history else {})
    counts.update(w.spelling.casefold() for w in words if w.level in ('hard', 'fuzzy'))
    final = [escalate(w, counts, config) for w in words]
    totals = Counter(w.level for w in final)
    stats = dict(day=day.isoformat(), total=len(words), hard=totals['hard'], fuzzy=totals['fuzzy'],
                 mastered=totals['mastered'], promoted=sum(bool(w.escalation_count) for w in final),
                 latest=max((w.learned_at for w in words if w.learned_at), default=None))
    if words:
        series = [row for row in series if row['day'] != day.isoformat()] + [stats]
    errors = [dict(word=w.spelling, wrong=w.errors, promoted=bool(w.escalation_count))
              for w in sorted(final, key=lambda w: (-(w.errors if w.errors is not None else -1), w.spelling))
              if w.level == 'hard']
    unknown = [dict(ah=ah, rh=rh, rating=rating, count=len(group),
                    examples='、'.join(w.spelling for w in group[:5]))
               for (ah, rh, rating), group in sorted(collect_unknown_codes(words).items(),
                                                     key=lambda pair: -len(pair[1]))]
    try:
        prompt = review_path(config.output_dir, day).read_text(encoding='utf-8-sig')
    except FileNotFoundError:
        prompt = None
    except (OSError, UnicodeError) as exc:
        prompt = None
        warning = f'{warning} 复习文件暂时无法读取。请检查导出目录及文件编码。读取错误为 {exc}。'.strip()
    rows_by_day = {row['day']: row for row in series}
    first_visible = date.fromordinal(max(1, day.toordinal() - 167))
    # Keep the exported summaries in the view model. They cannot restore the
    # omitted words or the original categories needed by the history database.
    for exported_day, path in exports.items():
        key = exported_day.isoformat()
        if key in rows_by_day or (not first_visible <= exported_day <= day and exported_day != today):
            continue
        try:
            if exported_day == day:
                header = prompt[:64 * 1024] if prompt is not None else ''
            else:
                with path.open(encoding='utf-8-sig') as stream:
                    header = stream.read(64 * 1024)
        except (OSError, UnicodeError):
            continue
        if summary := read_export_summary(header, exported_day):
            if exported_day == today:
                latest = sidebar['latest'] if sidebar else None
                sidebar = {**summary, 'latest': latest}
            if first_visible <= exported_day <= day:
                rows_by_day[key] = summary
    return dict(version=VERSION, today=today.isoformat(), day=day.isoformat(), dates=sorted(dates, reverse=True),
                series=[rows_by_day[key] for key in sorted(rows_by_day)], stats=rows_by_day.get(day.isoformat()),
                errors=errors, repeats=repeats, unknown=unknown,
                codes_available=bool(cached), window=config.escalation_window_days, warning=warning,
                sidebar=stats if day == today and words else dict(sidebar) if sidebar else None,
                prompt=prompt, folder=str(config.output_dir), review_level=config.review_level)
