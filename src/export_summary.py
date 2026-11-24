"""Read the aggregate section of a previously exported review for display."""
from __future__ import annotations

from datetime import date
import re
from typing import Any


_COUNTS = re.compile(
    r'- 今日去重词汇：(\d{1,9}) 个；顽固词：(\d{1,9}) 个；模糊词：(\d{1,9}) 个。'
)
_MASTERED = re.compile(
    r'- (?:本轮直接认识或已标熟(?:或初学未答错)?|已熟练掌握)：(\d{1,9}) 个，已剔除(?:[，。].*)?'
)
_PROMOTED = re.compile(r'- 其中跨天惯犯自动提级：(\d{1,9}) 个。')
_UNCONFIRMED = re.compile(r'- 掌握程度未确认：(\d{1,9}) 个[，。].*')


def read_export_summary(content: str, day: date) -> dict[str, Any] | None:
    """Recognize the generated Markdown header and leave absent metrics unknown."""
    heading = f'# {day.isoformat()} 不背单词每日纠结词复习 Prompt'
    lines = content.splitlines()
    header = next((line for line in lines if line.startswith('# ')), '')
    if header != heading:
        return None
    counts = mastered = promoted = unconfirmed = None
    in_scope = False
    for line in lines:
        line = line.strip()
        if line.startswith('## '):
            if in_scope:
                break
            in_scope = line == '## 本次数据范围'
        if not in_scope:
            continue
        if match := _COUNTS.fullmatch(line):
            counts = tuple(map(int, match.groups()))
        elif match := _MASTERED.fullmatch(line):
            mastered = int(match[1])
        elif match := _PROMOTED.fullmatch(line):
            promoted = int(match[1])
        elif match := _UNCONFIRMED.fullmatch(line):
            unconfirmed = int(match[1])
    if counts is None or mastered is None:
        return None
    total, hard, fuzzy = counts
    remainder = total - hard - fuzzy - mastered
    if (total <= 0 or remainder < 0 or (unconfirmed is not None and remainder != unconfirmed)
            or (promoted is not None and promoted > hard)):
        return None
    return dict(day=day.isoformat(), total=total, hard=hard, fuzzy=fuzzy,
                mastered=mastered, promoted=promoted, latest=None, export_summary=True)
