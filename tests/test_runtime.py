"""Isolated checks for fresh source and frozen configuration bootstrap."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import yaml

from src import runtime
from src.config import load_config
from src.desktop_files import save_output_dir
from src.parser import classify


class RuntimeTests(unittest.TestCase):
    def test_legacy_config_can_omit_optional_parser_flags(self) -> None:
        with TemporaryDirectory() as temporary:
            original = runtime.PROJECT_ROOT / 'config.example.yaml'
            config_path = Path(temporary) / 'config.yaml'
            settings = yaml.safe_load(original.read_text(encoding='utf-8'))
            parser = settings['parser']
            del parser['numeric_proficiency_enabled']
            del parser['higher_is_better']
            config_path.write_text(yaml.safe_dump(settings), encoding='utf-8')
            config = load_config(config_path)
            self.assertEqual(classify(None, 0, None, config.parser)[0], 'unclassified')

            parser['numeric_proficiency_enabled'] = True
            config_path.write_text(yaml.safe_dump(settings), encoding='utf-8')
            config = load_config(config_path)
            self.assertEqual(classify(None, 0, None, config.parser)[0], 'hard')

    def test_packaged_configuration_uses_per_user_folder(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with patch.object(runtime, 'is_packaged', return_value=True), patch.dict(
                'os.environ', {'LOCALAPPDATA': str(root)}
            ):
                settings = load_config()
                app_dir = root / 'bbdc-to-ai'
                self.assertEqual(settings.root, app_dir)
                self.assertEqual(settings.output_dir, app_dir / 'output')
                self.assertEqual(settings.state_dir, app_dir / '.bbdc_state')
                self.assertTrue((app_dir / 'config.yaml').is_file())
                selected = root / 'selected-output'
                selected.mkdir()
                save_output_dir(selected)
                self.assertEqual(load_config().output_dir, selected)

    def test_source_config_created_from_template_only_when_missing(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            template = (runtime.PROJECT_ROOT / 'config.example.yaml').read_bytes()
            (root / 'config.example.yaml').write_bytes(template)
            with patch.object(runtime, 'PROJECT_ROOT', root):
                initial = load_config()
                self.assertEqual(initial.root, root)
                selected = root / 'selected-output'
                selected.mkdir()
                save_output_dir(selected)
                self.assertEqual(load_config().output_dir, selected)


if __name__ == '__main__':
    unittest.main()
