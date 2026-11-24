"""按学习日从 MuMu 导出，可供命令行和桌面助手调用。"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
import tempfile
from typing import Any

from rich.console import Console

from src.bbdc_schema import meaning_text, study_date
from src.config import Config, load_config
from src.mumu_adb import Adb, PACKAGE as PACKAGE
from src.mumu_connection import open_mumu
from src.mumu_diagnostics import SyncError
from src.mumu_snapshot import copy_database, enrich_meanings, read_learning_rows, read_protocol
from src.mumu_snapshot import snapshot_rows as snapshot_rows
from src.parser import parse_time
from src.pipeline import process_payload
from src.storage import save_raw, write_json

console = Console()


class NoStudyRecords(ValueError):
    def __init__(self, day: date, last_day: date | None) -> None:
        self.day, self.last_day = day, last_day
        message = f'这台安卓设备上没有 {day} 的已保存学习记录。'
        if last_day is not None:
            message += f'最近有记录的学习日是 {last_day}。'
        super().__init__(message)


@dataclass(frozen=True)
class SnapshotExport:
    path: Path
    new_word_count: int
    target_word_count: int
    latest_saved_at: str | None


def initialize_protocol(adb: Adb, config: Config) -> dict[str, Any]:
    return read_protocol(adb, config.root / '.local_setup/protocol.json')


def select_day(rows: list[dict[str, Any]], config: Config, now: datetime,
               target: date | None, latest: bool) -> tuple[date, list[dict[str, Any]]]:
    days: dict[date, list[dict[str, Any]]] = {}
    for row in rows:
        updated = parse_time(row['ut'], config.timezone)
        if updated is not None:
            days.setdefault(study_date(updated), []).append(row)
    day = target or study_date(now)
    if day not in days:
        last_day = max(days, default=None)
        if latest and target is None and last_day is not None:
            return last_day, days[last_day]
        raise NoStudyRecords(day, last_day)
    return day, days[day]


def export_study_day(adb: Adb, config: Config, target: date | None = None, latest: bool = False,
                     *, announce: bool = True, scratch_dir: Path | None = None) -> SnapshotExport:
    now = datetime.now(config.timezone)
    adb.prepare_database_access()
    protocol = initialize_protocol(adb, config)
    if announce:
        console.print('正在读取安卓设备的学习记录……', style='cyan')
    with tempfile.TemporaryDirectory(prefix='bbdc-ai-', dir=scratch_dir) as directory:
        folder = Path(directory)
        database = copy_database(adb, 'LangEasyLexis.db', protocol['db_key'], 2, folder)
        rows = read_learning_rows(database)
        day, selected = select_day(rows, config, now, target, latest)
        enrich_meanings(adb, rows, protocol['dict_key'], folder,
                        config.root / '.local_setup/dictionary-lookups.json')
    write_json(config.state_dir / 'dictionary.json',
               {row['wd'].casefold(): meaning_text(row['meaning']) for row in rows if row['meaning']})
    if announce and target is None and day != study_date(now):
        console.print(f'当前学习日没有记录。导出最近有记录的学习日 {day}。', style='yellow')
    payload = {'_bbdc_profile': 'android-5.11.8', 'study_date': day.isoformat(), 'records': selected}
    save_raw(config.raw_dump_dir, '/local_snapshot/learning_records', payload, now)
    result = process_payload(payload, config, day, announce=announce)
    if not result.output:
        raise ValueError(f'{day} 的记录未找到可导出的词条。')
    target_count = sum(word.level in ('hard', 'fuzzy') for word in result.words)
    latest_saved = max((word.learned_at for word in result.parsed.words if word.learned_at), default=None)
    return SnapshotExport(result.output, result.new_word_count, target_count, latest_saved)


def export_snapshot(adb: Adb, config: Config, target: date | None = None, latest: bool = False,
                    *, announce: bool = True) -> Path:
    return export_study_day(adb, config, target, latest, announce=announce).path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='从自己的安卓设备导出真实学习记录（只读）')
    parser.add_argument('--adb')
    parser.add_argument('--serial')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--date', type=date.fromisoformat)
    parser.add_argument('--latest', action='store_true', help='当前学习日无记录时导出最近学习日，保留真实日期')
    parser.add_argument('--sync-mumu', action='store_true', help='启动 MuMu 并在不背单词中同步后再导出')
    parser.add_argument('--json', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--scratch-dir', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--mumu-manager', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.sync_mumu and (args.serial or args.adb):
        parser.error('--sync-mumu 会选择 MuMu 实例，请勿同时指定 --serial 或 --adb')
    if args.mumu_manager and not args.sync_mumu:
        parser.error('--mumu-manager 需要配合 --sync-mumu 使用')
    try:
        config = load_config(args.config)
        if args.sync_mumu:
            from src.mumu_sync import sync_learning_records
            adb = open_mumu(args.scratch_dir, manager=args.mumu_manager)
            sync_learning_records(adb)
        else:
            adb = Adb(args.adb, args.serial)
        result = export_study_day(adb, config, args.date, args.latest,
                                  announce=not args.json, scratch_dir=args.scratch_dir)
    except NoStudyRecords as exc:
        if args.json:
            print(json.dumps({'status': 'no_records', 'day': exc.day.isoformat(),
                              'last_day': exc.last_day.isoformat() if exc.last_day else None}, ensure_ascii=False))
        else:
            console.print(str(exc), style='yellow', markup=False)
        return 2
    except SyncError as exc:
        if args.json:
            reply = {'status': exc.status, 'message': str(exc)}
            if exc.reason is not None:
                reply['reason'] = exc.reason
            print(json.dumps(reply, ensure_ascii=False))
        else:
            console.print(str(exc), style='yellow', markup=False)
        return exc.exit_code
    except Exception as exc:
        if args.json:
            print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=False))
        else:
            console.print(f'导出失败：{type(exc).__name__}: {exc}', style='red', markup=False)
        return 1
    if args.json:
        print(json.dumps({'status': 'exported', 'output': str(result.path),
                          'new_word_count': result.new_word_count, 'target_word_count': result.target_word_count,
                          'latest_saved_at': result.latest_saved_at}, ensure_ascii=False))
    else:
        console.print(f'本次新增已保存词 {result.new_word_count} 个，复习词表共 {result.target_word_count} 个。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
