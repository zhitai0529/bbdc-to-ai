from __future__ import annotations

from contextlib import closing
from dataclasses import replace
from datetime import date
from pathlib import Path
import sqlite3
import tempfile
import unittest

from src.config import load_config
from src.pipeline import PipelineResult, export_cached_day, process_payload

DAY = date(2026, 11, 20)


def row(word: str, day: int, ah: str, rh: str, meaning: str = '示例释义') -> dict[str, str | int]:
    return {'wd': word, 'ut': f'2026-11-{day:02d} 12:00:00', 'st': 4,
            'ah': ah, 'rh': rh, 'meaning': meaning}


class ReviewHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.config = replace(load_config(), root=root, state_dir=root / 'state', output_dir=root / 'output')

    def export(self, rows: list[dict[str, str | int]], day: int = 20) -> PipelineResult:
        return process_payload(rows, self.config, DAY.replace(day=day), announce=False)

    def test_window_includes_today_and_six_prior_days_without_counting_duplicates(self) -> None:
        self.export([row('expired', 13, '110', 'B')], 13)
        self.export([row('recur', 14, '210', 'D'), row('stay known', 14, '110', 'B'),
                     row('unconfirmed prior', 14, '999', 'C')], 14)
        self.export([row('first time', 21, '110', 'B')], 21)
        current = [row('Recur', 20, '110', 'B'), row('first time', 20, '110', 'B'),
                   row('stay known', 20, '0', 'A'), row('expired', 20, '110', 'B'),
                   row('unconfirmed prior', 20, '110', 'B')]
        for _ in range(2):
            result = self.export(current + [row('recur', 20, '110', 'B')])
            categories = {word.spelling: word.level for word in result.words}
            self.assertEqual(categories, {'expired': 'fuzzy', 'first time': 'fuzzy', 'recur': 'hard',
                                          'stay known': 'mastered', 'unconfirmed prior': 'hard'})
            text = result.output.read_text(encoding='utf-8')
            self.assertIn('其中跨天惯犯自动提级：2 个', text)
            self.assertIn('近 7 天内有 2 个学习日标为模糊或顽固', text)
            self.assertIsNone(result.unknown_report)
        with closing(sqlite3.connect(self.config.history_path)) as db:
            rows = db.execute('SELECT word, category, wrong_count, rating, ah, rh, updated_at FROM daily_word_log '
                              'WHERE study_date = ? ORDER BY word', (DAY.isoformat(),)).fetchall()
            self.assertEqual(len(rows), 5)
            self.assertIn(('recur', 'fuzzy', 0, 'B', '110', 'B', '2026-11-20T12:00:00+08:00'), rows)
        self.config = replace(self.config, escalation_window_days=6, fuzzy_escalation_threshold=2)
        result = self.export(current)
        self.assertTrue(all(word.escalation_count == 0 for word in result.words))
        self.config = replace(self.config, escalation_window_days=7, fuzzy_escalation_threshold=3)
        result = self.export(current)
        self.assertTrue(all(word.escalation_count == 0 for word in result.words))

    def test_report_counts_groups_merges_batches_and_limits_examples(self) -> None:
        self.config = replace(self.config, write_unknown_codes_report=True)
        group = [row(f'unknown {suffix}', 20, '0#110,999', 'A#BC', '难辨 | 释义') for suffix in 'abcdef']
        self.export(group[:3])
        result = self.export(group[3:] + [group[0], row('different group', 20, '999', 'AC')])
        self.assertEqual(result.unknown_report.name, '2026-11-20_unknown_codes.md')
        text = result.unknown_report.read_text(encoding='utf-8')
        self.assertLess(text.index('| 999 | BC | C | 6 |'), text.index('| 999 | AC | C | 1 |'))
        self.assertIn('unknown a（难辨 &#124; 释义）', text)
        self.assertIn('unknown e（', text)
        self.assertNotIn('unknown f（', text)
        self.assertEqual(len(result.parsed.unknown_codes[('999', 'BC', 'C')]), 4)
        review = result.output.read_text(encoding='utf-8')
        self.assertIn('| unknown a | 难辨 &#124; 释义 | 复习不会 | 1 | C | ah/rh 编码未确认，按基础顽固词默认记错 1 次 |',
                      review)
        self.assertIn('其中 7 个词的 ah/rh 编码未确认', review)
        with closing(sqlite3.connect(self.config.history_path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM daily_word_log WHERE category='hard' AND wrong_count=1")
                             .fetchone(), (7,))

    def test_config_rule_reclassifies_cached_words_and_removes_resolved_report(self) -> None:
        self.config = replace(self.config, write_unknown_codes_report=True)
        target = row('check me', 20, '999', 'BC')
        first = self.export([target])
        self.assertTrue(first.unknown_report.is_file())
        source = self.config.root / 'config.yaml'
        source.write_bytes((Path(__file__).resolve().parents[1] / 'config.yaml').read_bytes())
        rules_file = self.config.root / 'rules.yaml'
        rules_file.write_text(
            "code_rules:\n"
            "  - {ah: '999', ratings: ['C'], category: fuzzy, recognition: '通用记录'}\n"
            "  - {ah: '999', rh: 'BC', ratings: ['C'], category: hard, recognition: '已核对', wrong_count: 2}\n",
            encoding='utf-8',
        )
        changed = load_config(source)
        self.config = replace(changed, state_dir=self.config.state_dir, output_dir=self.config.output_dir,
                              write_unknown_codes_report=True)
        second = self.export([row('other word', 20, '999', 'AC')])
        self.assertEqual({word.spelling: word.level for word in second.words},
                         {'check me': 'hard', 'other word': 'fuzzy'})
        self.assertIsNone(second.unknown_report)
        self.assertFalse(first.unknown_report.exists())
        with closing(sqlite3.connect(self.config.history_path)) as db:
            self.assertEqual(db.execute("SELECT category, wrong_count FROM daily_word_log WHERE word='check me'").fetchone(),
                             ('hard', 2))

    def test_newer_unknown_code_is_not_overwritten_by_older_known_category(self) -> None:
        previous = row('shift', 20, '110', 'B')
        unknown = row('shift', 20, '999', 'C')
        unknown['ut'] = '2026-11-20 13:00:00'
        self.export([previous])
        self.export([unknown])
        result = self.export([previous])
        self.assertEqual(result.words[0].level, 'hard')
        self.assertEqual(result.words[0].recognition, '复习不会')
        self.assertIsNone(result.unknown_report)

    def test_default_export_keeps_words_and_removes_old_report_for_the_same_day(self) -> None:
        result = self.export([row('default hard', 20, '999', 'C')])
        self.assertIsNone(result.unknown_report)
        report = result.output.with_name('2026-11-20_unknown_codes.md')
        self.assertFalse(report.exists())
        self.config = replace(self.config, write_unknown_codes_report=True)
        old = self.export([row('other day', 19, '999', 'C')], day=19)
        enabled = export_cached_day(self.config, DAY)
        self.assertEqual(enabled.unknown_report, report)
        self.assertTrue(report.is_file())

        result = export_cached_day(replace(self.config, write_unknown_codes_report=False), DAY)
        self.assertIsNone(result.unknown_report)
        self.assertFalse(report.exists())
        self.assertTrue(old.unknown_report.is_file())
        self.assertIn('| default hard | 示例释义 | 复习不会 | 1 |', result.output.read_text(encoding='utf-8'))
