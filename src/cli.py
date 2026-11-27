"""python -m src.cli inspect/replay；只打印字段结构，不打印字段值。"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
from typing import Any, Iterator

from rich.console import Console
from rich.table import Table

from src.config import load_config
from src.pipeline import process_payload, show_success

console = Console()
KEY_HINTS = ('word', 'spell', 'meaning', 'defin', 'translat', 'stage', 'familiar',
             'level', 'error', 'wrong', 'mistake', 'time', 'date', 'learn', 'review',
             'recogn', 'know', '熟练', '错误', '单词', '释义', '掌握')


def read_payload(path: Path, limit: int) -> Any:
    if path.stat().st_size > limit:
        raise ValueError('文件超过 max_response_bytes 限制')
    with path.open(encoding='utf-8-sig') as handle:
        return json.load(handle)


def structure(value: Any, path: str = '$', depth: int = 0) -> Iterator[tuple[str, str]]:
    """聚合字段路径和类型；不输出实际值，不泄露登录数据。"""
    if depth > 30:
        return
    kind = 'null' if value is None else type(value).__name__
    yield path, kind
    if isinstance(value, dict):
        for key, child in value.items():
            yield from structure(child, f'{path}.{key}', depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from structure(child, f'{path}[]', depth + 1)


def inspect_file(path: Path, limit: int) -> None:
    payload = read_payload(path, limit)
    counts = Counter(structure(payload))
    table = Table(title=f'JSON 字段结构：{path.name}')
    for title in ('字段路径', '类型', '出现次数', '候选'):
        table.add_column(title)
    for (field_path, kind), count in sorted(counts.items()):
        hint = '★' if any(key in field_path.casefold() for key in KEY_HINTS) else ''
        table.add_row(field_path, kind, str(count), hint)
    console.print(table)
    console.print('★ 仅表示名称相关；字段语义、枚举值和数值方向必须结合实际操作确认。')


def main() -> int:
    parser = argparse.ArgumentParser(description='bbdc-to-ai 本地样本工具')
    parser.add_argument('--config', type=Path, help='配置文件，默认项目 config.yaml')
    commands = parser.add_subparsers(dest='command', required=True)
    inspect = commands.add_parser('inspect', help='检查 JSON 字段结构（不显示值）')
    inspect.add_argument('input', type=Path)
    replay = commands.add_parser('replay', help='重放一个 JSON 或目录中全部 JSON')
    replay.add_argument('input', type=Path)
    replay.add_argument('--date', type=date.fromisoformat, help='目标学习日期 YYYY-MM-DD，默认本地今日')
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if args.command == 'inspect':
            inspect_file(args.input, config.max_response_bytes)
            return 0
        if not args.input.exists():
            raise FileNotFoundError('输入路径不存在')
        files = sorted(args.input.glob('*.json')) if args.input.is_dir() else [args.input]
        if not files:
            console.print('[yellow]没有找到 JSON 文件。[/yellow]')
            return 1
        failures = 0
        latest = None
        candidates = undated = other_date = invalid_date = 0
        for source in files:
            try:
                result = process_payload(read_payload(source, config.max_response_bytes), config,
                                         target_date=args.date, announce=False)
                candidates += result.parsed.candidates
                undated += result.parsed.skipped_undated
                other_date += result.parsed.skipped_other_date
                invalid_date += result.parsed.skipped_invalid_date
                if result.output:
                    latest = result
            except Exception as exc:
                failures += 1
                console.print(f'文件 {source.name} 失败：{type(exc).__name__}: {exc}', style='red', markup=False)
        console.print(f'已检查 {len(files)} 个文件；候选 {candidates} 条；缺日期 {undated}，'
                      f'非目标日期 {other_date}，日期无效 {invalid_date}；失败 {failures}。')
        if latest and latest.output:
            show_success(latest.words, latest.output, date.fromisoformat(latest.output.name[:10]),
                         latest.unknown_report, warning=latest.warning)
        else:
            console.print('[yellow]没有符合日期和拼写映射的记录，未生成文件。请先 inspect 检查字段映射。[/yellow]')
        return 1 if failures or latest is None else 0
    except Exception as exc:
        console.print(f'{type(exc).__name__}: {exc}', style='red', markup=False)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
