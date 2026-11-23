"""Android 5.11.8 复习历史适配与未知编码回退。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import re
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    from src.config import Config
    from src.parser import ParseResult, WordRecord


def records(payload: Any, depth: int = 0) -> Iterator[dict[str, Any]]:
    if depth > 25:
        return
    if isinstance(payload, dict):
        if all(k in payload for k in ('wd', 'st', 'ut')) and ('rh' in payload or 'ah' in payload):
            yield payload
        else:
            for child in payload.values():
                if isinstance(child, (dict, list)):
                    yield from records(child, depth + 1)
    elif isinstance(payload, list):
        for child in payload:
            yield from records(child, depth + 1)


def is_bbdc(payload: Any) -> bool:
    return next(records(payload), None) is not None


def study_date(now: datetime) -> date:
    """该版本 App 的 SQL 明确使用当地时间减 4 小时。"""
    return (now - timedelta(hours=4)).date()


def meaning_text(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    try:
        items = json.loads(value)
        if isinstance(items, list):
            return '；'.join(f"{item.get('p', '')} {item.get('i', '')}".strip()
                            for item in items if isinstance(item, dict))
    except (ValueError, TypeError):
        pass
    return value


def classify_bbdc(word: WordRecord, config: Config) -> None:
    """从保留的原始输入分类，也可在规则改动后重新分类每日缓存。"""
    ah, rh, rating = word.answer_history, word.result_history, word.raw_rating
    rule = config.code_rules.get((ah, rating, rh)) or config.code_rules.get((ah, rating, None))
    limit = config.manual_mastered_max_duration
    manual = (word.bbdc_state == 9 and word.bbdc_duration is not None
              and limit is not None and word.bbdc_duration <= limit)
    legacy_manual = word.bbdc_state is None and word.recognition == '手工标熟' and limit is not None
    word.escalation_count = 0
    word.unknown_bbdc_code = rule is None and not (manual or legacy_manual)
    if rule is not None:
        word.level, word.recognition, word.errors = rule.category, rule.recognition, rule.wrong_count
        label = '初学编码' if rating in '0123456789' and rating else '复习评分'
        word.evidence = f'{label} {rating or "未提供"}；本轮 ah={ah or "空"}（{rule.recognition}）'
    elif manual or legacy_manual:
        word.level, word.recognition, word.errors = 'mastered', '手工标熟', None
        word.evidence = f'App 已标熟状态，标熟时长阈值 {limit}'
    else:
        word.level, word.recognition, word.errors = 'hard', '复习不会', 1
        word.evidence = 'ah/rh 编码未确认，按基础顽固词默认记错 1 次'


def parse_bbdc(payload: Any, config: Config, target_date: date) -> ParseResult:
    from src.parser import ParseResult, WordRecord, merge_word, parse_time
    result = ParseResult()
    merged: dict[str, WordRecord] = {}
    for row in records(payload):
        result.candidates += 1
        spelling = row.get('wd')
        if not isinstance(spelling, str) or not re.fullmatch(r"[A-Za-z][A-Za-z '\-…\.()’]{0,99}", spelling):
            continue
        # state=1 的首次下载/同步也有 updatetime，绝不能算为今日学习。
        if row.get('st') not in (3, 4, 9):
            continue
        updated = parse_time(row.get('ut'), config.timezone)
        if updated is None:
            result.skipped_invalid_date += 1
            continue
        if study_date(updated) != target_date:
            result.skipped_other_date += 1
            continue
        history = str(row['rh'] if row.get('rh') is not None else '').rsplit('#', 1)[-1]
        answer = str(row['ah'] if row.get('ah') is not None else '').rsplit('#', 1)[-1].rsplit(',', 1)[-1]
        rating = history[-1:]
        duration = row.get('duration', row.get('du', 0))
        proficiency = float(ord(rating) - ord('A') + 1) if rating in tuple('ABCDEF') else None
        word = WordRecord(spelling=spelling, meaning=meaning_text(row.get('meaning', '')),
                          proficiency=proficiency, learned_at=updated.isoformat(), timestamp=updated.timestamp(),
                          source='bbdc-android-5.11.8', raw_rating=rating, answer_history=answer,
                          result_history=history, bbdc_state=row['st'],
                          bbdc_duration=duration if isinstance(duration, (int, float)) else None)
        classify_bbdc(word, config)
        key = spelling.casefold()
        merged[key] = merge_word(merged.get(key), word)
    result.words = list(merged.values())
    return result
