"""只解密本地副本；逐页验证 SQLCipher HMAC，不修改设备上的数据库。"""
from __future__ import annotations

import hashlib
import hmac
from io import BytesIO
import struct
from typing import Any
import zipfile

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from elftools.elf.elffile import ELFFile

COMMON_SHA256 = '1bc04f6313f8b0263a2074614bd8efd145f26a3fa9ff3e0f27fdf50dcacb4890'


def protocol_from_apk(apk: bytes) -> dict[str, Any]:
    """仅支持已在本机核对的 5.11.8 x86 native 库；版本变化时拒绝猜测。"""
    with zipfile.ZipFile(BytesIO(apk)) as archive:
        common = archive.read('lib/x86/libcommon.so')
    if hashlib.sha256(common).hexdigest() != COMMON_SHA256:
        raise ValueError('App native 库版本未验证；请保留现有数据并重新适配')
    elf = ELFFile(BytesIO(common))
    digest = hashlib.sha256(b'cn.com.langeasy.LangEasyLexis').hexdigest().encode()

    def derive(address: int, length: int) -> str:
        for segment in elf.iter_segments():
            start = segment['p_vaddr']
            if start <= address and address + length <= start + segment['p_filesz']:
                encoded = segment.data()[address - start:address - start + length]
                return bytes(a ^ b for a, b in zip(encoded, digest)).decode('ascii')
        raise ValueError('native 库地址范围无效')

    return {'app_profile': 'android-5.11.8', 'common_sha256': COMMON_SHA256,
            'aes_iv_hex': derive(0x7c0, 16).encode().hex(),
            'db_key': derive(0x9e5, 14), 'dict_key': derive(0x90d, 36)}


def decrypt_database(data: bytes, password: str, version: int = 2) -> bytes:
    if version not in (2, 4):
        raise ValueError('只支持 SQLCipher 2 和 4')
    page_size, reserve, digest, iterations = ((1024, 48, 'sha1', 4000) if version == 2
                                             else (4096, 80, 'sha512', 256000))
    if len(data) < page_size or len(data) % page_size:
        raise ValueError('数据库副本长度无效，可能仍在写入')
    salt = data[:16]
    key = hashlib.pbkdf2_hmac(digest, password.encode(), salt, iterations, 32)
    hmac_key = hashlib.pbkdf2_hmac(digest, key, bytes(b ^ 0x3a for b in salt), 2, 32)
    output = bytearray()
    for offset in range(0, len(data), page_size):
        page = data[offset:offset + page_size]
        first = 16 if offset == 0 else 0
        body_end = page_size - reserve
        tag_start = body_end + 16
        tag_size = hashlib.new(digest).digest_size
        expected = hmac.new(hmac_key, page[first:tag_start] + struct.pack('<I', offset // page_size + 1), digest).digest()
        if not hmac.compare_digest(expected, page[tag_start:tag_start + tag_size]):
            raise ValueError(f'数据库第 {offset // page_size + 1} 页校验失败；未导出部分结果')
        dec = Cipher(algorithms.AES(key), modes.CBC(page[body_end:tag_start])).decryptor()
        plain = dec.update(page[first:body_end]) + dec.finalize()
        output += (b'SQLite format 3\0' if offset == 0 else b'') + plain + bytes(reserve)
    if output[16:18] != struct.pack('>H', page_size):
        raise ValueError('解密后的 SQLite 页头无效')
    return bytes(output)
