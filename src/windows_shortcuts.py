"""Read and update Windows desktop shortcuts through the Shell Link API."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import ctypes
from pathlib import Path
import re
import stat
import sys
from uuid import UUID

APP_NAME = '不背单词复习助手'
OWNED_NAMES = {f'{APP_NAME}.lnk', '不背单词－查看复习.lnk', '不背单词－导出复习.lnk'}
APP_EXE = re.compile(r'bbdc-to-ai(?:-windows-x64)?(?:[-_ ]v?\d+\.\d+\.\d+)?(?: \(\d+\))?\.exe', re.I)
SOURCE_ARGS = re.compile(r'^\s*-m\s+src\.desktop(?:\s|$)', re.I)
CLSID_SHELL_LINK = '00021401-0000-0000-c000-000000000046'
IID_SHELL_LINK = '000214f9-0000-0000-c000-000000000046'
IID_PERSIST_FILE = '0000010b-0000-0000-c000-000000000046'


def _guid(identifier: str) -> ctypes.Array:
    return (ctypes.c_ubyte * 16).from_buffer_copy(UUID(identifier).bytes_le)


def _known_folder(identifier: str, fallback: str) -> Path:
    if sys.platform == 'win32':
        shell = ctypes.WinDLL('shell32')
        memory = ctypes.WinDLL('ole32')
        guid = _guid(identifier)
        buffer = ctypes.c_void_p()
        lookup = shell.SHGetKnownFolderPath
        lookup.argtypes = (ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
        lookup.restype = ctypes.c_int32
        memory.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
        memory.CoTaskMemFree.restype = None
        try:
            if lookup(ctypes.byref(guid), 0, None, ctypes.byref(buffer)) == 0 and buffer.value:
                return Path(ctypes.wstring_at(buffer))
        finally:
            if buffer.value:
                memory.CoTaskMemFree(buffer)
    return Path.home() / fallback


def desktop_directory() -> Path:
    return _known_folder('b4bfcc3a-db2c-424c-b029-7fe99a87c641', 'Desktop')


def downloads_directory() -> Path:
    return _known_folder('374de290-123f-4565-9164-39c4925e467b', 'Downloads')


def _check(result: int, operation: str) -> None:
    if result < 0:
        raise OSError(f'Windows 快捷方式操作失败（{operation}，0x{result & 0xffffffff:08X}）。')


def _method(interface: ctypes.c_void_p, index: int, type_: type, *params: type):
    # COM interface methods are called with the interface pointer as the first argument.
    vtable = ctypes.cast(interface, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    return ctypes.WINFUNCTYPE(type_, ctypes.c_void_p, *params)(vtable[index])


def _call(interface: ctypes.c_void_p, index: int, operation: str, params: tuple[type, ...], *args) -> None:
    result = _method(interface, index, ctypes.c_int32, *params)(interface, *args)
    _check(result, operation)


@contextmanager
def _com() -> Iterator[ctypes.WinDLL]:
    ole = ctypes.WinDLL('ole32')
    ole.CoInitializeEx.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    ole.CoInitializeEx.restype = ctypes.c_int32
    ole.CoUninitialize.argtypes = ()
    ole.CoUninitialize.restype = None
    status = ole.CoInitializeEx(None, 2)
    if status != -2147417850:  # RPC_E_CHANGED_MODE: the caller already initialized COM.
        _check(status, 'CoInitializeEx')
    try:
        yield ole
    finally:
        if status >= 0:
            ole.CoUninitialize()


@contextmanager
def _shell_link(ole: ctypes.WinDLL) -> Iterator[tuple[ctypes.c_void_p, ctypes.c_void_p]]:
    link = ctypes.c_void_p()
    persist = ctypes.c_void_p()
    ole.CoCreateInstance.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
                                     ctypes.POINTER(ctypes.c_void_p))
    ole.CoCreateInstance.restype = ctypes.c_int32
    clsid = _guid(CLSID_SHELL_LINK)
    iid = _guid(IID_SHELL_LINK)
    _check(ole.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(link)),
           'CoCreateInstance')
    try:
        iid = _guid(IID_PERSIST_FILE)
        _call(link, 0, 'QueryInterface', (ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)),
              ctypes.byref(iid), ctypes.byref(persist))
        try:
            yield link, persist
        finally:
            _method(persist, 2, ctypes.c_uint32)(persist)
    finally:
        _method(link, 2, ctypes.c_uint32)(link)


def read_link(ole: ctypes.WinDLL, file: Path) -> tuple[Path, str, Path]:
    with _shell_link(ole) as (link, persist):
        _call(persist, 5, 'Load', (ctypes.c_wchar_p, ctypes.c_uint32), str(file), 0)
        target, arguments, directory = (ctypes.create_unicode_buffer(32768) for _ in range(3))
        _call(link, 3, 'GetPath', (ctypes.c_wchar_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32),
              target, len(target), None, 4)
        _call(link, 10, 'GetArguments', (ctypes.c_wchar_p, ctypes.c_int), arguments, len(arguments))
        _call(link, 8, 'GetWorkingDirectory', (ctypes.c_wchar_p, ctypes.c_int), directory, len(directory))
        return Path(target.value), arguments.value, Path(directory.value)


def write_link(ole: ctypes.WinDLL, file: Path, target: Path, arguments: str = '', *, preserve: bool = False) -> None:
    with _shell_link(ole) as (link, persist):
        if preserve:
            _call(persist, 5, 'Load', (ctypes.c_wchar_p, ctypes.c_uint32), str(file), 0)
        _call(link, 20, 'SetPath', (ctypes.c_wchar_p,), str(target))
        _call(link, 9, 'SetWorkingDirectory', (ctypes.c_wchar_p,), str(target.parent))
        _call(link, 11, 'SetArguments', (ctypes.c_wchar_p,), arguments)
        _call(link, 17, 'SetIconLocation', (ctypes.c_wchar_p, ctypes.c_int), str(target), 0)
        _call(persist, 6, 'Save', (ctypes.c_wchar_p, ctypes.c_int), str(file), 1)


def update_desktop_shortcuts(target: Path, *, desktop_dir: Path | None = None) -> tuple[Path, ...]:
    if sys.platform != 'win32':
        return ()
    target = target.resolve(strict=True)
    if not target.is_file():
        raise FileNotFoundError('新版 EXE 不存在，无法更新桌面快捷方式。')
    desktop = desktop_dir if desktop_dir is not None else desktop_directory()
    retired: list[Path] = []
    found = False
    with _com() as ole:
        for file in desktop.glob('*.lnk'):
            try:
                if file.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    continue
                previous, arguments, working_dir = read_link(ole, file)
            except OSError:
                continue
            old_exe = previous.is_absolute() and APP_EXE.fullmatch(previous.name)
            old_source = (file.name in OWNED_NAMES and previous.name.casefold() in ('pythonw.exe', 'python.exe')
                          and SOURCE_ARGS.match(arguments))
            if previous != target and not old_exe and not old_source:
                continue
            match = re.search(r'(?:^|\s)(--export|--open-latest)(?:\s|$)', arguments)
            kept_arguments = match[1] if match else ''
            if (previous, working_dir, arguments) != (target, target.parent, kept_arguments):
                write_link(ole, file, target, kept_arguments, preserve=True)
                if old_exe and previous != target:
                    retired.append(previous)
            found = True
        if not found:
            link = desktop / f'{APP_NAME}.lnk'
            sequence = 1
            while link.exists() or link.is_symlink():
                link = desktop / f'{APP_NAME} (bbdc-to-ai {sequence}).lnk'
                sequence += 1
            write_link(ole, link, target)
    return tuple(dict.fromkeys(retired))
