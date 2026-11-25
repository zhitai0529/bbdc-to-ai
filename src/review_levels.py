"""Difficulty presets for the reading exercise in the exported AI prompt."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast


ReviewLevel = Literal['cet4', 'cet6', 'postgrad']
DEFAULT_REVIEW_LEVEL: ReviewLevel = 'postgrad'


@dataclass(frozen=True)
class ReviewLevelProfile:
    label: str
    sentence_structure: str
    target_words: str


REVIEW_LEVELS: dict[ReviewLevel, ReviewLevelProfile] = {
    'cet4': ReviewLevelProfile(
        '四级',
        '英文通常为 12～20 词。语境词优先用常见的日常、校园或工作表达。'
        '用容易辨认的主谓结构，最多加一个简单从句或一个非谓语修饰成分，避免嵌套、倒装和多层插入。',
        '2～3',
    ),
    'cet6': ReviewLevelProfile(
        '六级',
        '英文通常为 18～28 词。语境可用六级阅读中常见的说明或议论表达。'
        '可以有一到两个同级从句或非谓语修饰成分，保持指代清楚，避免层层嵌套。',
        '3～4',
    ),
    'postgrad': ReviewLevelProfile(
        '考研',
        '英文通常为 25～40 词。语境可用考研阅读中常见的学术说明或社会议论。'
        '可以用多分句、最多两层从句嵌套和必要的插入成分，保持主干完整、逻辑关系清楚。',
        '4～5',
    ),
}


def parse_review_level(value: object) -> ReviewLevel:
    if not isinstance(value, str) or value not in REVIEW_LEVELS:
        raise ValueError('review_level 必须为 cet4（四级）、cet6（六级）或 postgrad（考研）。')
    return cast(ReviewLevel, value)
