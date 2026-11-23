"""桌面助手的保存位置和本地复习文件。"""
from __future__ import annotations

import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

import yaml
from yaml.nodes import MappingNode, ScalarNode

from src.config import load_config
from src.runtime import default_config_path
from src.storage import atomic_write


def load_output_dir(config_path: Path | None = None) -> Path:
    return load_config(config_path).output_dir


def latest_review(directory: Path) -> Path | None:
    try:
        return max(
            (path for path in directory.iterdir()
             if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}_bbdc_review\.md', path.name) and path.is_file()),
            default=None,
        )
    except FileNotFoundError:
        return None


def save_output_dir(directory: Path, config_path: Path | None = None) -> Path:
    source = (config_path if config_path is not None else default_config_path()).resolve()
    directory = (source.parent / directory.expanduser()).resolve()
    if not directory.is_dir():
        raise ValueError(f'请选择一个存在的文件夹。\n{directory}')
    try:
        with NamedTemporaryFile(dir=directory, prefix='.bbdc-write-'):
            pass
    except OSError as exc:
        raise ValueError(f'无法写入所选文件夹，请选择有写入权限的文件夹。\n{directory}') from exc

    content = source.read_text(encoding='utf-8')
    try:
        updated = replace_output_dir(content, directory)
        yaml.safe_load(updated)
    except yaml.YAMLError as exc:
        raise ValueError('无法更新保存位置。请检查 config.yaml 的格式。') from exc
    if updated != content:
        atomic_write(source, updated)
    return directory


def replace_output_dir(content: str, directory: Path) -> str:
    """只替换顶层 output_dir 的值，保留配置的其余文字。"""
    root = yaml.compose(content, Loader=yaml.SafeLoader)
    if not isinstance(root, MappingNode):
        raise ValueError('config.yaml 必须是对象。')

    value_text = json.dumps(str(directory), ensure_ascii=False)
    entries = [(key, value) for key, value in root.value if isinstance(key, ScalarNode) and key.value == 'output_dir']
    if len(entries) > 1:
        raise ValueError('config.yaml 中有重复的 output_dir，请保留一项。')
    if entries:
        key, value = entries[0]
        start, end = value.start_mark.index, value.end_mark.index
        if not isinstance(value, ScalarNode) or start < key.end_mark.index:
            raise ValueError('config.yaml 的 output_dir 必须直接填写路径。')
        if start == end:
            value_text = ' ' + value_text
        if content[start:end].endswith('\n'):
            value_text += '\n'
        return content[:start] + value_text + content[end:]

    if root.flow_style:
        end = root.end_mark.index - 1
        separator = ', ' if root.value and not content[:end].rstrip().endswith(',') else ''
        return content[:end] + f'{separator}output_dir: {value_text}' + content[end:]

    first_key = root.value[0][0].start_mark
    start = first_key.index
    return content[:start] + f'output_dir: {value_text}\n' + ' ' * first_key.column + content[start:]
