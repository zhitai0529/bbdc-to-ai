"""桌面助手的保存位置和本地复习文件。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

import yaml
from yaml.nodes import MappingNode, ScalarNode

from filelock import FileLock, Timeout

from src.config import Config, load_config
from src.exporter import review_path as review_path
from src.review_levels import parse_review_level
from src.runtime import default_config_path
from src.storage import atomic_write


def load_output_dir(config_path: Path | None = None) -> Path:
    return load_config(config_path).output_dir


def save_review_prompt(config: Config, day: date, original: str, content: str) -> None:
    path = review_path(config.output_dir, day)

    def verify_original() -> None:
        if path.read_text(encoding='utf-8-sig') != original:
            raise ValueError('复习文件已被重新导出或修改，当前草稿还在。'
                             '请先「复制全部内容」备份草稿，再重启助手查看最新文件。')

    try:
        config.state_dir.mkdir(parents=True, exist_ok=True)
        with FileLock(str(config.state_dir / '.pipeline.lock'), timeout=5):
            atomic_write(path, content, before_replace=verify_original)
    except FileNotFoundError as exc:
        raise ValueError('找不到这份复习文件，当前草稿还在。'
                         '请先「复制全部内容」备份草稿，再到导出目录检查文件是否被移动。') from exc
    except Timeout as exc:
        raise ValueError('另一个任务正在写入复习文件。请等它结束后再保存。') from exc
    except (OSError, UnicodeError) as exc:
        raise ValueError('无法保存草稿。请检查导出文件夹是否可写、文件是否为 UTF-8，'
                         '或先复制草稿到其他位置。') from exc


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

    save_config_scalar(source, 'output_dir', str(directory), '保存位置')
    return directory


def save_review_level(level: str, config_path: Path | None = None) -> None:
    value = parse_review_level(level)
    source = (config_path if config_path is not None else default_config_path()).resolve()
    save_config_scalar(source, 'review_level', value, '复习难度')


def save_config_scalar(source: Path, key: str, value: str, label: str) -> None:
    try:
        with FileLock(str(source.parent / '.config.lock'), timeout=5):
            content = source.read_text(encoding='utf-8-sig')
            updated = replace_config_scalar(content, key, value)
            yaml.safe_load(updated)
            if updated != content:
                atomic_write(source, updated)
    except (yaml.YAMLError, UnicodeError) as exc:
        raise ValueError(f'无法更新{label}。请检查 config.yaml 的格式和编码。') from exc
    except Timeout as exc:
        raise ValueError(f'正在保存其他设置，请稍后再更新{label}。') from exc
    except OSError as exc:
        raise ValueError(f'无法更新{label}。请检查配置文件所在文件夹的读写权限。') from exc


def replace_config_scalar(content: str, setting: str, new_value: str) -> str:
    """Replace one top-level scalar while retaining the surrounding YAML text."""
    root = yaml.compose(content, Loader=yaml.SafeLoader)
    if not isinstance(root, MappingNode):
        raise ValueError('config.yaml 必须是对象。')

    value_text = json.dumps(new_value, ensure_ascii=False)
    entries = [(key, value) for key, value in root.value if isinstance(key, ScalarNode) and key.value == setting]
    if len(entries) > 1:
        raise ValueError(f'config.yaml 中有重复的 {setting}，请保留一项。')
    if entries:
        key, value = entries[0]
        start, end = value.start_mark.index, value.end_mark.index
        if not isinstance(value, ScalarNode) or start < key.end_mark.index:
            raise ValueError(f'config.yaml 的 {setting} 必须直接填写一个值。')
        if start == end:
            value_text = ' ' + value_text
        if content[start:end].endswith('\n'):
            value_text += '\n'
        return content[:start] + value_text + content[end:]

    if root.flow_style:
        end = root.end_mark.index - 1
        separator = ', ' if root.value and not content[:end].rstrip().endswith(',') else ''
        return content[:end] + f'{separator}{setting}: {value_text}' + content[end:]

    first_key = root.value[0][0].start_mark
    start = first_key.index
    return content[:start] + f'{setting}: {value_text}\n' + ' ' * first_key.column + content[start:]
