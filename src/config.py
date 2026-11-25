"""配置加载；所有相对路径均相对于 config.yaml，而非启动目录。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import math
import yaml

from src.review_levels import DEFAULT_REVIEW_LEVEL, ReviewLevel, parse_review_level
from src.runtime import PROJECT_ROOT as PROJECT_ROOT, default_config_path


@dataclass(frozen=True)
class CodeRule:
    category: str
    recognition: str
    wrong_count: int | None


def load_code_rules(path: Path) -> tuple[dict[tuple[str, str, str | None], CodeRule], int | None]:
    with path.open(encoding='utf-8-sig') as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or not isinstance(data.get('code_rules'), list):
        raise ValueError('rules.yaml 的 code_rules 必须是列表')
    manual_limit = data.get('manual_mastered_max_duration', 90)
    if manual_limit is not None and (type(manual_limit) is not int or manual_limit < 0):
        raise ValueError('manual_mastered_max_duration 必须为非负整数或 null')
    rules: dict[tuple[str, str, str | None], CodeRule] = {}
    for index, entry in enumerate(data['code_rules'], 1):
        location = f'rules.yaml 的第 {index} 条 code_rules'
        if not isinstance(entry, dict):
            raise ValueError(f'{location}必须是对象')
        ah, rh, ratings = entry.get('ah'), entry.get('rh'), entry.get('ratings')
        category, recognition = entry.get('category'), entry.get('recognition')
        wrong_count = entry.get('wrong_count')
        if not isinstance(ah, str) or (rh is not None and not isinstance(rh, str)):
            raise ValueError(f'{location}的 ah / rh 必须是带引号的文本')
        if (not isinstance(ratings, list) or not ratings
                or any(not isinstance(rating, str) or len(rating) > 1 for rating in ratings)):
            raise ValueError(f'{location}的 ratings 必须是单字符评分列表，缺评分用空字符串')
        if category not in ('hard', 'fuzzy', 'mastered') or not isinstance(recognition, str) or not recognition.strip():
            raise ValueError(f'{location}须填写有效的 category 和 recognition')
        if wrong_count is not None and (type(wrong_count) is not int or wrong_count < 0):
            raise ValueError(f'{location}的 wrong_count 必须是非负整数或 null')
        rule = CodeRule(category, recognition, wrong_count)
        for rating in ratings:
            key = ah, rating, rh
            if key in rules:
                raise ValueError(f'{location}重复定义 ah={ah!r}, rh={rh!r}, rating={rating!r}')
            rules[key] = rule
    return rules, manual_limit


@dataclass(frozen=True)
class Config:
    root: Path
    mode: str
    listen_host: str
    listen_port: int
    timezone: ZoneInfo
    raw_dump_dir: Path
    state_dir: Path
    output_dir: Path
    max_response_bytes: int
    parser: dict[str, Any]
    target_domains: tuple[str, ...] = ('bbdc.cn', 'beingfine.cn')
    escalation_window_days: int = 7
    fuzzy_escalation_threshold: int = 2
    code_rules: dict[tuple[str, str, str | None], CodeRule] = field(default_factory=dict)
    manual_mastered_max_duration: int | None = 90
    write_unknown_codes_report: bool = False
    review_level: ReviewLevel = DEFAULT_REVIEW_LEVEL

    @property
    def history_path(self) -> Path:
        return self.root / 'data/history.db'


def load_config(path: Path | str | None = None) -> Config:
    source = Path(path) if path is not None else default_config_path()
    source = source.resolve()
    with source.open(encoding='utf-8-sig') as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError('config.yaml 必须是对象')
    mode = data.get('mode', 'sniffer')
    domains = data.get('target_domains', ['bbdc.cn', 'beingfine.cn'])
    if not isinstance(domains, list) or not domains or any(
        not isinstance(d, str) or not d or '/' in d or '*' in d or ':' in d for d in domains
    ):
        raise ValueError('target_domains 必须为域名列表，不含协议、通配符或端口')
    if mode not in {'sniffer', 'auto'}:
        raise ValueError('mode 必须是 sniffer 或 auto')
    port = data.get('listen_port', 8888)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('listen_port 必须是 1~65535 的整数')
    limit = data.get('max_response_bytes', 20 * 1024 * 1024)
    if type(limit) is not int or limit <= 0:
        raise ValueError('max_response_bytes 必须是正整数')
    window = data.get('escalation_window_days', 7)
    threshold = data.get('fuzzy_escalation_threshold', 2)
    for key, value in (('escalation_window_days', window), ('fuzzy_escalation_threshold', threshold)):
        if type(value) is not int or value <= 0:
            raise ValueError(f'{key} 必须是正整数')
    write_unknown_report = data.get('write_unknown_codes_report', False)
    if type(write_unknown_report) is not bool:
        raise ValueError('write_unknown_codes_report 必须是布尔值')
    review_level = parse_review_level(data.get('review_level', DEFAULT_REVIEW_LEVEL))
    code_path = source.with_name('rules.yaml')
    code_rules, manual_limit = load_code_rules(code_path if code_path.exists() else PROJECT_ROOT / 'rules.yaml')
    rules = data.get('parser')
    if not isinstance(rules, dict) or not isinstance(rules.get('fields'), dict):
        raise ValueError('parser.fields 必须配置字段映射')
    for key in ('spelling', 'meaning', 'recognition', 'proficiency', 'errors', 'learned_at'):
        aliases = rules['fields'].get(key)
        if not isinstance(aliases, list) or not all(isinstance(v, str) and v for v in aliases):
            raise ValueError(f'parser.fields.{key} 必须是字段路径列表')
    for key in ('record_paths', 'response_date_paths'):
        if not isinstance(rules.get(key, []), list) or not all(isinstance(v, str) and v for v in rules.get(key, [])):
            raise ValueError(f'parser.{key} 必须是路径列表')
    for key in ('include_undated', 'numeric_proficiency_enabled', 'higher_is_better', 'error_counts_enabled'):
        if type(rules.get(key, False)) is not bool:
            raise ValueError(f'parser.{key} 必须是布尔值')
    for key in ('hard_threshold', 'mastered_threshold', 'hard_error_threshold', 'fuzzy_error_threshold'):
        value = rules.get(key)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f'parser.{key} 必须是有限数字')
    if rules['numeric_proficiency_enabled']:
        hard, mastered = rules['hard_threshold'], rules['mastered_threshold']
        if (rules['higher_is_better'] and hard >= mastered) or (not rules['higher_is_better'] and hard <= mastered):
            raise ValueError('熟练度阈值顺序与 higher_is_better 不一致')
    if not 0 < rules['fuzzy_error_threshold'] <= rules['hard_error_threshold']:
        raise ValueError('错误次数阈值必须满足 0 < fuzzy <= hard')
    values = rules.get('recognition_values', {})
    seen: set[str] = set()
    for level in ('hard', 'fuzzy', 'mastered'):
        entries = values.get(level) if isinstance(values, dict) else None
        if not isinstance(entries, list) or any(not isinstance(v, (str, int, float)) or isinstance(v, bool) for v in entries):
            raise ValueError(f'recognition_values.{level} 必须为文字或数字列表')
        normalized = {str(v).strip().casefold() for v in entries}
        if seen & normalized:
            raise ValueError('recognition_values 各分组不能重复')
        seen |= normalized

    def resolve(key: str, fallback: str) -> Path:
        value = data.get(key, fallback)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'{key} 必须是路径字符串')
        candidate = Path(value).expanduser()
        return (source.parent / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()

    return Config(source.parent, mode, str(data.get('listen_host', '0.0.0.0')), port,
                  ZoneInfo(data.get('timezone', 'Asia/Shanghai')),
                  resolve('raw_dump_dir', './raw_dumps'), resolve('state_dir', './.bbdc_state'),
                  resolve('output_dir', './output'), limit, rules,
                  tuple(d.lower().rstrip('.') for d in domains), window, threshold, code_rules, manual_limit,
                  write_unknown_codes_report=write_unknown_report, review_level=review_level)
