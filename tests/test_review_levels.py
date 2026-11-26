from dataclasses import replace
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.config import PROJECT_ROOT, load_config
from src.pipeline import export_cached_day, process_payload


class ReviewLevelTests(unittest.TestCase):
    def test_existing_configuration_defaults_to_postgrad_and_invalid_level_is_reported(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'config.yaml'
            template = (PROJECT_ROOT / 'config.example.yaml').read_text(encoding='utf-8')
            legacy = template.replace('review_level: postgrad\n', '')
            path.write_text(legacy, encoding='utf-8')
            self.assertEqual(load_config(path).review_level, 'postgrad')

            path.write_text(legacy + '\nreview_level: [unknown]\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'review_level'):
                load_config(path)

    def test_all_presets_export_from_the_same_existing_cache(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = replace(load_config(PROJECT_ROOT / 'config.example.yaml'), root=root,
                             state_dir=root / 'state', output_dir=root / 'output')
            day = date(2026, 11, 25)
            payload = [
                {'word': 'maintain', 'recognition': 'unknown', 'studied_at': day.isoformat()},
                {'word': 'sustain', 'recognition': 'fuzzy', 'studied_at': day.isoformat()},
                {'word': 'well-known-word', 'recognition': 'known', 'studied_at': day.isoformat()},
            ]
            first = process_payload(payload, config, day, announce=False)
            self.assertIsNotNone(first.output)
            cache = (config.state_dir / f'{day}.json').read_bytes()
            for level, label, length, density in (
                ('cet4', '四级', '12～20', '2～3'),
                ('cet6', '六级', '18～28', '3～4'),
                ('postgrad', '考研', '25～40', '4～5'),
            ):
                with self.subTest(level=level):
                    result = export_cached_day(replace(config, review_level=level), day)
                    self.assertEqual(result.output, first.output)
                    markdown = result.output.read_text(encoding='utf-8')
                    self.assertIn(f'阅读练习难度：{label}。', markdown)
                    self.assertIn(f'英文通常为 {length} 词', markdown)
                    self.assertIn(f'每句包含 {density} 个不同目标词', markdown)
                    self.assertIn('今日目标词只加粗，不给中文括注', markdown)
                    self.assertIn('大小写或词形变化不改变其身份', markdown)
                    self.assertIn('含目标词的整个搭配也不作括注', markdown)
                    self.assertIn('只有超出当前档位、确实需要保留的非目标背景词或搭配才加中文括注', markdown)
                    self.assertIn('The museum **retained** two old seismographs（地震仪）', markdown)
                    self.assertNotIn('无论是不是目标词', markdown)
                    self.assertIn('每句通常选 1～2 处难读的从句或修饰短语', markdown)
                    self.assertIn('每句的整句中文翻译仍要保留', markdown)
                    self.assertIn('├── kept in a castle（存放在城堡里的）→', markdown)
                    self.assertIn('| maintain |', markdown)
                    self.assertIn('| sustain |', markdown)
                    self.assertNotIn('well-known-word', markdown)
            self.assertEqual((config.state_dir / f'{day}.json').read_bytes(), cache)
