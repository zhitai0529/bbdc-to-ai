"""按本地学习日期持久化去重，重复同步不重复累加。"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any

from filelock import FileLock
from rich.console import Console
from rich.table import Table

from src.config import Config
from src.exporter import export_unknown_codes, render_review
from src.envelope import unwrap_payload
from src.bbdc_schema import is_bbdc, study_date
from src.history import count_prior_days, log_and_count_recent
from src.parser import ParseResult, WordRecord, parse_payload
from src.review_cache import ReviewCache, merge_reviews
from src.review_protection import ExportChoice, write_daily_review

console = Console()


@dataclass
class PipelineResult:
    parsed: ParseResult
    words: list[WordRecord]
    output: Path | None
    unknown_report: Path | None = None
    new_word_count: int = 0
    copied: bool = False
    warning: str | None = None


def escalate(word: WordRecord, counts: dict[str, int], config: Config) -> WordRecord:
    count = counts.get(word.spelling.casefold(), 0)
    if word.level != 'fuzzy' or count < config.fuzzy_escalation_threshold:
        return word
    reason = f'近 {config.escalation_window_days} 天内有 {count} 个学习日标为模糊或顽固，已自动提级为顽固词'
    return replace(word, level='hard', evidence=f'{word.evidence}；{reason}', escalation_count=count)


def process_payload(payload: Any, config: Config, target_date: date | None = None,
                    announce: bool = True) -> PipelineResult:
    decoded = unwrap_payload(payload, config.root / '.local_setup/protocol.json')
    now = datetime.now(config.timezone)
    android = is_bbdc(decoded)
    today = target_date or (study_date(now) if android else now.date())
    parsed = parse_payload(decoded, config, today)
    dictionary_path = config.state_dir / 'dictionary.json'
    missing_meanings = [word for word in parsed.words if not word.meaning]
    if missing_meanings and android and dictionary_path.is_file():
        dictionary = json.loads(dictionary_path.read_text(encoding='utf-8'))
        for word in missing_meanings:
            word.meaning = str(dictionary.get(word.spelling.casefold(), ''))
    if not parsed.words:
        if announce and parsed.candidates:
            console.print(f'[yellow]发现 {parsed.candidates} 条候选；缺日期 {parsed.skipped_undated}，'
                          f'非目标日期 {parsed.skipped_other_date}，日期无效 {parsed.skipped_invalid_date}。[/yellow]')
        return PipelineResult(parsed, [], None)
    result = _merge_and_export(parsed, config, today)
    if announce and result.output is not None:
        show_success(result.words, result.output, today, result.unknown_report, warning=result.warning)
    return result


def export_cached_day(config: Config, day: date, *, choice: ExportChoice | None = None,
                      revision: str | None = None) -> PipelineResult:
    """应用当前规则并重新生成已保存在本机的指定学习日。"""
    return _merge_and_export(ParseResult(), config, day, record_history=False, choice=choice, revision=revision)


def _merge_and_export(parsed: ParseResult, config: Config, day: date, *,
                      record_history: bool = True, choice: ExportChoice | None = None,
                      revision: str | None = None) -> PipelineResult:
    if not parsed.words and not config.state_dir.is_dir():
        return PipelineResult(parsed, [], None)
    config.state_dir.mkdir(parents=True, exist_ok=True)
    cache = ReviewCache(config, day)
    with FileLock(str(config.state_dir / '.pipeline.lock'), timeout=10):
        words = cache.load()
        new_word_count = merge_reviews(words, parsed.words)
        if not words:
            return PipelineResult(parsed, [], None)
        merged = sorted(words.values(), key=lambda item: item.spelling.casefold())
        if record_history:
            counts = log_and_count_recent(config.history_path, day, merged, config.escalation_window_days)
            cache.save(merged)
        else:
            counts = count_prior_days(config.history_path, day, config.escalation_window_days)
            for word in merged:
                if word.level in ('hard', 'fuzzy'):
                    key = word.spelling.casefold()
                    counts[key] = counts.get(key, 0) + 1
        review_words = [escalate(word, counts, config) for word in merged]
        markdown = render_review(review_words, day, review_level=config.review_level)
        destination, copied = write_daily_review(config, day, markdown, choice=choice, revision=revision)
        unknown_report, warning = None, None
        if not copied:
            try:
                unknown_report = export_unknown_codes(merged, config.output_dir, day,
                                                      enabled=config.write_unknown_codes_report)
            except OSError:
                warning = '复习文件已保存，未知编码报告未能更新。请检查报告是否被占用。'
    return PipelineResult(parsed, review_words, destination, unknown_report, new_word_count, copied, warning)


def show_success(words: list[WordRecord], destination: Path, today: date, unknown_report: Path | None = None,
                 *, warning: str | None = None) -> None:
    console.print('[bold green]✓ 已提取学习记录并生成每日复习 Prompt[/bold green]')
    console.print(str(destination), markup=False)
    table = Table(title=f'{today.isoformat()} 已捕获词汇（按拼写去重）')
    table.add_column('等级')
    table.add_column('数量', justify='right')
    for key, label in (('hard', '顽固词'), ('fuzzy', '模糊词'), ('mastered', '熟词（剔除）'),
                       ('unclassified', '待确认（暂不参与）')):
        table.add_row(label, str(sum(word.level == key for word in words)))
    table.add_row('合计', str(len(words)))
    console.print(table)
    console.print(f'其中跨天惯犯自动提级：{sum(word.escalation_count > 0 for word in words)} 个')
    if unknown_report is not None:
        console.print(f'未知编码报告：{unknown_report}', markup=False)
    if warning is not None:
        console.print(warning, style='yellow', markup=False)
