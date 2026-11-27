from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.config import PROJECT_ROOT, load_config
from src.parser import WordRecord
from src.range_review import export_range_review
from src.review_cache import ReviewCache


END = date(2026, 11, 27)


class RangeReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.config = replace(load_config(PROJECT_ROOT / 'config.example.yaml'), root=root,
                              state_dir=root / 'state', output_dir=root / 'output', review_level='cet4')

    def save(self, days_back: int, *records: WordRecord) -> Path:
        cache = ReviewCache(self.config, END - timedelta(days=days_back))
        cache.save(list(records))
        return cache.path

    def test_export_merges_only_weak_occurrences_and_preserves_source_files(self) -> None:
        paths = [
            self.save(0, WordRecord('revise', level='fuzzy'), WordRecord('maintain', level='mastered')),
            self.save(2, WordRecord('Revise', '修订', level='hard'), WordRecord('retain', level='fuzzy')),
            self.save(3, WordRecord('revise', level='mastered'), WordRecord('recall', level='fuzzy')),
            self.save(4, WordRecord('recover', level='hard')),
            self.save(5, WordRecord('outside', level='hard')),
            self.save(-1, WordRecord('future', level='hard')),
        ]
        self.config.output_dir.mkdir()
        daily = self.config.output_dir / f'{END}_bbdc_review.md'
        daily.write_text('daily edited review', encoding='utf-8')
        self.config.history_path.parent.mkdir(exist_ok=True)
        self.config.history_path.write_bytes(b'existing history')
        untouched = {path: path.read_bytes() for path in [*paths, daily, self.config.history_path]}

        three = export_range_review(self.config, END, 3)
        five = export_range_review(self.config, END, 5)

        self.assertEqual(three['start_day'], '2026-11-25')
        self.assertEqual(three['end_day'], '2026-11-27')
        self.assertEqual(three['missing_days'], ['2026-11-26'])
        self.assertEqual(three['word_count'], 2)
        self.assertEqual(five['start_day'], '2026-11-23')
        self.assertEqual(five['missing_days'], ['2026-11-26'])
        self.assertEqual(five['word_count'], 4)
        self.assertIn('未找到词条记录的学习日：2026-11-26', three['markdown'])
        self.assertIn('阅读练习难度：四级。', three['markdown'])
        self.assertIn('本次目标词只加粗，不给中文括注', three['markdown'])
        for result in (three, five):
            self.assertEqual((self.config.output_dir / result['filename']).read_text(encoding='utf-8'),
                             result['markdown'])
            hard, fuzzy = result['markdown'].split('### fuzzy_words', maxsplit=1)
            self.assertIn('| revise | 修订 | 2026-11-25（顽固）、2026-11-27（模糊） |', hard)
            self.assertNotIn('| revise |', fuzzy)
            self.assertIn('| retain |', fuzzy)
            for excluded in ('maintain', 'outside', 'future'):
                self.assertNotIn(f'| {excluded} |', result['markdown'])
        self.assertNotIn('| recall |', three['markdown'])
        self.assertIn('| recall |', five['markdown'])
        self.assertIn('| recover |', five['markdown'])
        self.assertEqual({path: path.read_bytes() for path in untouched}, untouched)

    def test_repeating_range_export_preserves_previous_file(self) -> None:
        self.save(0, WordRecord('verify', level='hard'))
        earlier = export_range_review(self.config, END, 3)
        path = self.config.output_dir / earlier['filename']
        path.write_text('manually edited range review', encoding='utf-8')

        again = export_range_review(self.config, END, 3)

        self.assertNotEqual(earlier['filename'], again['filename'])
        self.assertEqual(path.read_text(encoding='utf-8'), 'manually edited range review')

    def test_invalid_range_and_missing_or_corrupt_cache_leave_no_export(self) -> None:
        for invalid in (1, 4, 3.0, '5', True):
            with self.subTest(days=invalid), self.assertRaisesRegex(ValueError, '近 3 天或近 5 天'):
                export_range_review(self.config, END, invalid)
        with self.assertRaisesRegex(ValueError, '无法向前取足'):
            export_range_review(self.config, date.min, 3)
        with self.assertRaisesRegex(ValueError, '没有本机词条缓存'):
            export_range_review(self.config, END, 3)
        self.save(0, WordRecord('known', level='mastered'), WordRecord('unknown', level='unclassified'))
        with self.assertRaisesRegex(ValueError, '没有顽固词或模糊词'):
            export_range_review(self.config, END, 3)
        self.save(2, WordRecord('reserve', level='hard')).write_text('{', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '无法读取 2026-11-25 的本机词条缓存'):
            export_range_review(self.config, END, 3)
        self.assertFalse(self.config.output_dir.exists())
