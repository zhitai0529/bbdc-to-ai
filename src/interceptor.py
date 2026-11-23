"""mitmproxy Addon：精确域名边界、JSON 备份、可选自动流水线。"""
from __future__ import annotations

from datetime import datetime
import json
import re
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlsplit

# mitmdump -s 以文件方式导入；显式加入项目根目录。
project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from mitmproxy import ctx, exceptions, http
from rich.console import Console
from src.config import Config, load_config
from src.envelope import EncryptedPayloadError, unwrap_payload
from src.bbdc_schema import is_bbdc
from src.pipeline import process_payload
from src.storage import save_raw

console = Console()


def is_target_host(host: str, domains: tuple[str, ...] = ('bbdc.cn', 'beingfine.cn')) -> bool:
    host = host.lower().rstrip('.')
    return any(host == domain or host.endswith('.' + domain) for domain in domains)


def reject_nonfinite(value: str) -> Any:
    raise ValueError(f'不支持的 JSON 常量：{value}')


class BBDCInterceptor:
    def __init__(self) -> None:
        self.config: Config | None = None

    def load(self, loader: Any) -> None:
        loader.add_option('bbdc_config', str, str(Path(project_root) / 'config.yaml'), 'bbdc-to-ai 配置文件')

    def configure(self, updated: set[str]) -> None:
        if self.config is None or 'bbdc_config' in updated:
            try:
                self.config = load_config(ctx.options.bbdc_config)
            except Exception as exc:
                raise exceptions.OptionsError(f'bbdc-to-ai 配置无效：{exc}') from exc

    def running(self) -> None:
        if self.config:
            console.print(f'[bold cyan]bbdc-to-ai 已启动，模式：{self.config.mode}[/bold cyan]')
            console.print(f'原始备份：{self.config.raw_dump_dir}', markup=False)
            console.print(f'目标域名：{", ".join(self.config.target_domains)}；按 Ctrl+C 停止。', markup=False)

    def response(self, flow: http.HTTPFlow) -> None:
        if self.config is None or flow.response is None or not is_target_host(flow.request.pretty_host, self.config.target_domains):
            return
        mime = flow.response.headers.get('content-type', '').split(';', 1)[0].strip().lower()
        if mime != 'application/json':
            return
        try:
            # get_content 会解压 gzip/br 等，原始 HTTP 响应不作改动。
            body = flow.response.get_content(strict=True)
            if body is None:
                return
            if len(body) > self.config.max_response_bytes:
                console.print('[yellow]目标 JSON 超出 max_response_bytes，已跳过；可调整配置。[/yellow]')
                return
            payload = json.loads(body, parse_constant=reject_nonfinite)
            now = datetime.now(self.config.timezone)
            backup = save_raw(self.config.raw_dump_dir, flow.request.path, payload, now)
            console.print(f'✓ JSON 已备份：{backup.name}', style='green', markup=False)
            # sniffer 也检查封装，使抓包成功与学习数据解析成功明确区分。
            try:
                decoded = unwrap_payload(payload, self.config.root / '.local_setup/protocol.json')
                if self.config.mode == 'auto':
                    result = process_payload(decoded, self.config)
                    if result.parsed.candidates == 0:
                        console.print('[dim]此包没有可识别的单词拼写字段，仅保留备份。[/dim]')
            except EncryptedPayloadError as exc:
                # 响应封装不兼容时，仍可检查已成功上传的独立 stat 字段。
                console.print(str(exc), style='yellow', markup=False)
            # 真实同步接口也会把已学记录放在 POST stat 中；只读指定字段，不保存认证参数。
            path = urlsplit(flow.request.path).path
            if (flow.request.method == 'POST' and re.fullmatch(r'/v3/bb/user-stat/process(?:/\d+)?/?', path)
                    and flow.response.status_code == 200 and isinstance(payload, dict)
                    and payload.get('result_code') == 200):
                stat = flow.request.urlencoded_form.get('stat', '')
                if stat and len(stat.encode()) <= self.config.max_response_bytes:
                    uploaded = json.loads(stat, parse_constant=reject_nonfinite)
                    if is_bbdc(uploaded):
                        save_raw(self.config.raw_dump_dir, '/sync_request/learning_records', uploaded, now)
                        if self.config.mode == 'auto':
                            process_payload(uploaded, self.config)
        except Exception as exc:
            # 不在日志输出 URL 查询、响应全文或 token；坏包不能打断代理。
            console.print(f'处理失败（代理继续运行）：{type(exc).__name__}', style='red', markup=False)
            if isinstance(exc, (OSError, ValueError)):
                console.print('请检查磁盘权限、JSON 格式或缓存配置；原始备份若已写入会保留。', style='yellow')


addons = [BBDCInterceptor()]
