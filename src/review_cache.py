"""保存和加载每日词表。缓存保留提级前的记录。"""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path

from src.bbdc_schema import classify_bbdc
from src.config import Config
from src.parser import WordRecord, merge_word
from src.storage import write_json


class ReviewCache:
    def __init__(self, config: Config, day: date) -> None:
        self.config = config
        self.day = day
        self.path = config.state_dir / f'{day.isoformat()}.json'
        settings = {'schema': 2, 'parser': config.parser, 'timezone': str(config.timezone)}
        self.fingerprint = hashlib.sha256(
            json.dumps(settings, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    def load(self) -> dict[str, WordRecord]:
        try:
            with self.path.open(encoding='utf-8') as handle:
                state = json.load(handle)
        except FileNotFoundError:
            return {}
        if (not isinstance(state, dict) or state.get('version') != 1 or state.get('date') != self.day.isoformat()
                or state.get('fingerprint') != self.fingerprint or not isinstance(state.get('words'), list)):
            raise ValueError('每日缓存格式或配置已变化。请使用新的 state_dir 后重放原始包；旧缓存已保留。')
        words: dict[str, WordRecord] = {}
        for entry in state['words']:
            word = WordRecord(**entry)
            if word.level not in {'hard', 'fuzzy', 'mastered', 'unclassified'}:
                raise ValueError('每日缓存包含未知等级，请更换 state_dir 后重放')
            if word.source == 'bbdc-android-5.11.8':
                classify_bbdc(word, self.config)
            words[word.spelling.casefold()] = word
        return words

    def save(self, words: list[WordRecord]) -> None:
        write_json(self.path, {
            'version': 1, 'date': self.day.isoformat(), 'fingerprint': self.fingerprint,
            'words': [word.to_dict() for word in words],
        })


def merge_reviews(words: dict[str, WordRecord], incoming: list[WordRecord]) -> int:
    new_word_count = 0
    for word in incoming:
        key = word.spelling.casefold()
        previous = words.get(key)
        if previous is None:
            new_word_count += 1
        words[key] = merge_word(previous, word)
    return new_word_count
