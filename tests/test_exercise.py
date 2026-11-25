from __future__ import annotations

from dataclasses import replace
from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from src.config import PROJECT_ROOT, load_config
from src.exercise import EXERCISE_TYPES, exercise_types, export_exercise
from src.parser import WordRecord
from src.review_cache import ReviewCache
from src.review_levels import REVIEW_LEVELS


DAY = date(2026, 11, 25)


class ExerciseTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        template = load_config(PROJECT_ROOT / 'config.example.yaml')
        self.config = replace(template, root=root, state_dir=root / 'state', output_dir=root / 'output',
                              raw_dump_dir=root / 'raw')
        self.cache = ReviewCache(self.config, DAY)

    def test_exports_distinct_templates_and_files_for_every_level_and_type(self) -> None:
        self.cache.save([WordRecord('verify', '核实', level='hard')])
        options = exercise_types()
        self.assertEqual(len(options), 6)
        self.assertEqual({option['id'] for option in options}, set(EXERCISE_TYPES))
        for level, profile in REVIEW_LEVELS.items():
            for option in options:
                kind = option['id']
                with self.subTest(level=level, kind=kind):
                    result = export_exercise(self.config, DAY, level, kind)
                    self.assertEqual(result['filename'], f'{DAY}_bbdc_exercise_{level}_{kind}.md')
                    self.assertEqual(result['day'], str(DAY))
                    self.assertEqual(result['level'], level)
                    self.assertEqual(result['type'], kind)
                    self.assertEqual(result['word_count'], 1)
                    saved = (self.config.output_dir / result['filename']).read_text(encoding='utf-8')
                    self.assertEqual(saved, result['markdown'])
                    self.assertIn(f'档位为{profile.label}。', saved)
                    self.assertIn('最多出 1 题', saved)
                    self.assertIn('会提示任何一道题答案的括注都移到答案区', saved)
                    self.assertIn('第一次回复只出题，等待我作答', saved)
                    for other_kind, exercise in EXERCISE_TYPES.items():
                        self.assertEqual(exercise.instructions in saved, other_kind == kind)
        self.assertEqual(len(list(self.config.output_dir.glob('*.md'))), 18)

    def test_uses_only_selected_days_candidates_without_rewriting_review_or_history(self) -> None:
        self.cache.save([
            WordRecord('known', '已掌握', level='mastered'),
            WordRecord('uncertain', '', level='unclassified'),
            WordRecord('verify', '核实', level='hard', errors=2),
            WordRecord('fortification', '<b>工事</b>\n```', level='hard', errors=5),
            *[WordRecord(f'fuzzy {count:02}', level='fuzzy', errors=count) for count in range(14)],
        ])
        previous = DAY.replace(day=24)
        ReviewCache(self.config, previous).save([WordRecord('yesterday', level='hard')])
        self.config.output_dir.mkdir()
        daily_review = self.config.output_dir / f'{DAY}_bbdc_review.md'
        daily_review.write_text('existing daily review', encoding='utf-8')
        self.config.history_path.parent.mkdir()
        self.config.history_path.write_bytes(b'existing history placeholder')
        untouched_paths = [self.cache.path, daily_review, self.config.history_path]
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in untouched_paths}

        result = export_exercise(self.config, DAY, 'cet4', 'cloze')

        self.assertEqual(result['word_count'], 12)
        self.assertIn('最多出 5 题', result['markdown'])
        words = json.loads(result['markdown'].split('```json\n', 1)[1].rsplit('\n```', 1)[0])
        self.assertEqual(words[0], {'word': 'fortification', 'meaning': '<b>工事</b>\n```'})
        self.assertEqual(words[1], {'word': 'verify', 'meaning': '核实'})
        self.assertEqual(words[2:], [{'word': f'fuzzy {count:02}', 'meaning': None}
                                     for count in range(13, 3, -1)])
        self.assertEqual({path: (path.read_bytes(), path.stat().st_mtime_ns)
                          for path in untouched_paths}, before)
        self.assertFalse(self.config.raw_dump_dir.exists())

    def test_reports_missing_empty_invalid_and_unwritable_data(self) -> None:
        with self.assertRaisesRegex(ValueError, '没有.*词条缓存'):
            export_exercise(self.config, DAY, 'cet4', 'cloze')
        self.cache.save([WordRecord('known', level='mastered')])
        with self.assertRaisesRegex(ValueError, '没有顽固词或模糊词'):
            export_exercise(self.config, DAY, 'cet4', 'cloze')
        with self.assertRaisesRegex(ValueError, '有效的题型'):
            export_exercise(self.config, DAY, 'cet4', '../../outside')
        with self.assertRaisesRegex(ValueError, 'review_level'):
            export_exercise(self.config, DAY, 'unknown', 'cloze')
        self.cache.path.write_text('{', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '无法读取.*词条缓存'):
            export_exercise(self.config, DAY, 'cet4', 'cloze')
        self.cache.save([WordRecord('verify', level='hard')])
        with patch('src.exercise.atomic_write', side_effect=PermissionError):
            with self.assertRaisesRegex(ValueError, '无法保存练习 Markdown'):
                export_exercise(self.config, DAY, 'cet4', 'cloze')
        self.assertFalse(self.config.output_dir.exists())
