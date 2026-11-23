"""识别真实 Android 5.11.8 响应封装；不把加密正文当成空词表。"""
from __future__ import annotations

import json
import base64
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7


class EncryptedPayloadError(ValueError):
    """HTTPS 已解密，但 data_body 仍有应用层加密。"""


def unwrap_payload(payload: Any, protocol_file: Path | None = None) -> Any:
    if not isinstance(payload, dict) or 'data_body' not in payload:
        return payload
    if payload.get('data_encrypted') not in (None, 0, False, '0'):
        if not protocol_file or not protocol_file.is_file():
            raise EncryptedPayloadError('检测到应用层加密 data_body；请先运行 MuMu 数据导出以初始化本地协议配置')
        protocol = json.loads(protocol_file.read_text(encoding='utf-8'))
        secret = payload.get('v3_security', {}).get('secret', '')
        if not isinstance(secret, str) or len(secret.encode()) not in (16, 24, 32):
            raise EncryptedPayloadError('加密响应未提供可用的正文解密参数，已保留原始包')
        try:
            iv = bytes.fromhex(protocol['aes_iv_hex'])
            cipher = Cipher(algorithms.AES(secret.encode()), modes.CBC(iv)).decryptor()
            padded = cipher.update(base64.b64decode(payload['data_body'], validate=True)) + cipher.finalize()
            unpad = PKCS7(128).unpadder()
            return json.loads(unpad.update(padded) + unpad.finalize())
        except Exception as exc:
            raise EncryptedPayloadError('应用层正文解密失败；保留原始包，请检查 App 版本兼容性') from exc
    body = payload['data_body']
    if isinstance(body, str):
        return json.loads(body)
    return body
