"""从电脑上的学习记录缓存导出 Markdown。"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date, datetime
import json
from pathlib import Path

from src.bbdc_schema import study_date
from src.config import load_config
from src.pipeline import export_cached_day, show_success


def last_cached_day(directory: Path, before: date) -> date | None:
    latest = None
    for path in directory.glob('????-??-??.json'):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if day < before and (latest is None or day > latest) and path.is_file():
            latest = day
    return latest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='从电脑上的学习记录缓存导出每日复习')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--date', type=date.fromisoformat, help='学习日，默认按当地凌晨 4 点切换')
    parser.add_argument('--json', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        day = args.date or study_date(datetime.now(config.timezone))
        result = export_cached_day(config, day)
        if result.output is None:
            latest = last_cached_day(config.state_dir, day)
            if args.json:
                print(json.dumps({'status': 'no_records', 'day': day.isoformat(),
                                  'last_day': latest.isoformat() if latest else None}, ensure_ascii=False))
            else:
                print(f'本机没有 {day} 的学习记录。请先在助手中点「同步 MuMu」。')
                if latest:
                    print(f'本机最近有记录的学习日是 {latest}。')
            return 2
        if args.json:
            count = sum(word.level in ('hard', 'fuzzy') for word in result.words)
            latest_saved = max((word.learned_at for word in result.words if word.learned_at), default=None)
            print(json.dumps({'status': 'exported', 'output': str(result.output),
                              'new_word_count': result.new_word_count, 'target_word_count': count,
                              'latest_saved_at': latest_saved}, ensure_ascii=False))
        else:
            show_success(result.words, result.output, day, result.unknown_report)
    except Exception as exc:
        if args.json:
            print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=False))
        else:
            print(f'导出失败：{exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
