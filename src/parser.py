"""保守的字段映射解析器。字段名候选不是对 bbdc 私有协议的断言。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
import math
import re
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from src.config import Config


@dataclass
class WordRecord:
    spelling: str
    meaning: str = ''
    level: str = 'unclassified'
    recognition: str | None = None
    proficiency: float | None = None
    errors: float | None = None
    learned_at: str | None = None
    timestamp: float | None = None
    date_assumed: bool = False
    evidence: str = ''
    source: str = 'generic'
    raw_rating: str = ''
    answer_history: str = ''
    result_history: str | None = None
    bbdc_state: int | None = None
    bbdc_duration: float | None = None
    escalation_count: int = 0
    unknown_bbdc_code: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParseResult:
    words: list[WordRecord] = field(default_factory=list)
    skipped_undated: int = 0
    skipped_other_date: int = 0
    skipped_invalid_date: int = 0
    candidates: int = 0

    @property
    def unknown_codes(self) -> dict[tuple[str, str | None, str], list[WordRecord]]:
        return collect_unknown_codes(self.words)


def collect_unknown_codes(words: list[WordRecord]) -> dict[tuple[str, str | None, str], list[WordRecord]]:
    groups: dict[tuple[str, str | None, str], list[WordRecord]] = {}
    for word in words:
        if word.unknown_bbdc_code:
            code = word.answer_history, word.result_history, word.raw_rating
            groups.setdefault(code, []).append(word)
    return groups


def at_path(data: Any, path: str) -> Any:
    """点分路径支持列表下标，如 data.items.0.word；不执行表达式。"""
    current = data
    for part in path.split('.'):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def first_field(row: dict[str, Any], paths: list[str]) -> Any:
    for path in paths:
        value = at_path(row, path)
        if value is not None and value != '' and not isinstance(value, (dict, list)):
            return value
    return None


def as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def parse_time(value: Any, timezone: ZoneInfo) -> datetime | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = as_number(value)
        if number is not None and number > 100_000_000:
            # 支持 Unix 秒和毫秒；不擅自解释 stage 等小整数为日期。
            return datetime.fromtimestamp(number / 1000 if number >= 100_000_000_000 else number, timezone)
        text = str(value).strip()
        if not re.match(r'^\d{4}-\d{2}-\d{2}(?:$|[T ])', text):
            return None
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone) if parsed.tzinfo is None else parsed.astimezone(timezone)
    except (ValueError, OverflowError, OSError):
        return None


def walk_records(value: Any, spelling_paths: list[str], depth: int = 0) -> Iterator[dict[str, Any]]:
    if depth > 30:
        return
    if isinstance(value, dict):
        spelling = first_field(value, spelling_paths)
        if isinstance(spelling, str) and re.fullmatch(r"[A-Za-z][A-Za-z '\-]{0,79}", spelling.strip()):
            yield value
            return  # 同一词条的嵌套 word 不再作为第二条记录
        for child in value.values():
            if isinstance(child, (dict, list)):
                yield from walk_records(child, spelling_paths, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from walk_records(child, spelling_paths, depth + 1)


def classify(recognition: Any, proficiency: float | None, errors: float | None,
             rules: dict[str, Any]) -> tuple[str, str]:
    level, evidence = 'unclassified', '缺少已确认的掌握程度信号'
    if recognition is not None:
        text = str(recognition).strip().casefold()
        for mapped_level, values in rules['recognition_values'].items():
            if text in {str(v).strip().casefold() for v in values}:
                level, evidence = mapped_level, f'认识状态 {recognition}'
                break
    if level == 'unclassified' and rules.get('numeric_proficiency_enabled') and proficiency is not None:
        hard, mastered = rules['hard_threshold'], rules['mastered_threshold']
        high = rules.get('higher_is_better', True)
        if (high and proficiency <= hard) or (not high and proficiency >= hard):
            level = 'hard'
        elif (high and proficiency >= mastered) or (not high and proficiency <= mastered):
            level = 'mastered'
        else:
            level = 'fuzzy'
        evidence = f'熟练度 {proficiency:g}'
    # 错误只提高复习优先级，不能将“不认识 + 1 次错”降为模糊。
    if rules.get('error_counts_enabled') and errors is not None:
        if errors >= rules['hard_error_threshold']:
            return 'hard', f'错误次数 {errors:g}'
        if errors >= rules['fuzzy_error_threshold'] and level != 'hard':
            return 'fuzzy', f'错误次数 {errors:g}'
    return level, evidence


def merge_word(previous: WordRecord | None, incoming: WordRecord) -> WordRecord:
    if previous is None:
        return incoming
    # 学习时间较新的记录优先；相同时间按最近收到的快照覆盖，错误数不累加。
    if previous.timestamp is not None and (incoming.timestamp is None or incoming.timestamp < previous.timestamp):
        winner, other = previous, incoming
    else:
        winner, other = incoming, previous
    result = WordRecord(**winner.to_dict())
    if not result.meaning:
        result.meaning = other.meaning
    # 字典补充包没有等级时，不抹掉已经看到的实际学习状态。
    if result.source == 'generic' and result.level == 'unclassified' and other.level != 'unclassified':
        result.level, result.evidence = other.level, other.evidence
        result.recognition, result.proficiency, result.errors = other.recognition, other.proficiency, other.errors
    return result


def parse_payload(payload: Any, config: Config, target_date: date | None = None) -> ParseResult:
    from src.bbdc_schema import is_bbdc, parse_bbdc, study_date
    if is_bbdc(payload):
        return parse_bbdc(payload, config, target_date or study_date(datetime.now(config.timezone)))
    rules, fields = config.parser, config.parser['fields']
    today = target_date or datetime.now(config.timezone).date()
    response_time = first_field(payload, rules.get('response_date_paths', [])) if isinstance(payload, dict) else None
    roots = [at_path(payload, path) for path in rules.get('record_paths', [])] or [payload]
    result = ParseResult()
    deduplicated: dict[str, WordRecord] = {}
    for root in roots:
        for row in walk_records(root, fields['spelling']):
            result.candidates += 1
            raw_time = first_field(row, fields['learned_at'])
            if raw_time is None:
                raw_time = response_time
            learned = parse_time(raw_time, config.timezone)
            if raw_time is not None and learned is None:
                result.skipped_invalid_date += 1
                continue
            if learned is None and not rules.get('include_undated', False):
                result.skipped_undated += 1
                continue
            if learned is not None and learned.date() != today:
                result.skipped_other_date += 1
                continue
            spelling = str(first_field(row, fields['spelling'])).strip()
            recognition = first_field(row, fields['recognition'])
            proficiency = as_number(first_field(row, fields['proficiency']))
            errors = as_number(first_field(row, fields['errors']))
            if errors is not None and errors < 0:
                errors = None
            level, evidence = classify(recognition, proficiency, errors, rules)
            word = WordRecord(spelling, str(first_field(row, fields['meaning']) or ''), level,
                              str(recognition) if recognition is not None else None,
                              proficiency, errors, learned.isoformat() if learned else None,
                              learned.timestamp() if learned else None, learned is None, evidence)
            key = spelling.casefold()
            deduplicated[key] = merge_word(deduplicated.get(key), word)
    result.words = list(deduplicated.values())
    return result
