from importlib.metadata import distribution
from pathlib import Path
from runpy import run_path
import sys

from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)


project = Path(SPECPATH).resolve().parent
version = run_path(str(project / 'src/version.py'))['VERSION']
file_version = (*map(int, version.split('.')), 0)
metadata = VSVersionInfo(
    ffi=FixedFileInfo(filevers=file_version, prodvers=file_version, fileType=1),
    kids=[
        StringFileInfo([StringTable('080404B0', [
            StringStruct('FileDescription', '不背单词复习助手'),
            StringStruct('FileVersion', version),
            StringStruct('ProductName', 'bbdc-to-ai'),
            StringStruct('ProductVersion', version),
        ])]),
        VarFileInfo([VarStruct('Translation', [0x0804, 1200])]),
    ],
)

notices = [project.joinpath('LICENSE').read_text(encoding='utf-8')]
for package in ('pyinstaller', 'PyYAML', 'rich', 'filelock', 'cryptography', 'pyelftools',
                'tzdata', 'cffi', 'markdown-it-py', 'pygments', 'mdurl', 'pycparser',
                'pywebview', 'pythonnet', 'clr-loader', 'bottle', 'proxy-tools', 'pyperclip'):
    dist = distribution(package)
    for entry in sorted(dist.files or ()):
        if '.dist-info' in entry.parts[0] and entry.name.upper().startswith(
            ('LICENSE', 'COPYING', 'COPYRIGHT', 'NOTICE', 'AUTHORS')
        ):
            notices.append(f'{package} {dist.version} / {entry.name}\n\n'
                           + dist.locate_file(entry).read_text(encoding='utf-8', errors='replace'))
python_home = Path(sys.base_prefix)
for title, source in [('Python', python_home / 'LICENSE.txt'),
                      ('Tcl/Tk', python_home / 'tcl/tk8.6/license.terms')]:
    if source.is_file():
        notices.append(f'{title}\n\n' + source.read_text(encoding='utf-8', errors='replace'))
notices.append((project / 'frontend' / 'NOTICES.txt').read_text(encoding='utf-8'))
notice_file = Path(DISTPATH) / 'THIRD-PARTY-NOTICES.txt'
notice_file.parent.mkdir(parents=True, exist_ok=True)
notice_file.write_text('\n\n' + ('\n\n' + '=' * 72 + '\n\n').join(notices), encoding='utf-8')

analysis = Analysis(
    [str(project / 'packaging/windows_entry.py')],
    pathex=[str(project)],
    # cryptography loads this compiled extension at runtime.
    hiddenimports=['_cffi_backend'],
    datas=[
        (str(project / 'config.example.yaml'), '.'),
        (str(project / 'rules.yaml'), '.'),
        *((str(project / 'frontend' / name), 'frontend') for name in ('index.html', 'bundle.js', 'bundle.css')),
        *collect_data_files('webview', subdir='js'),
        (str(notice_file), '.'),
        *collect_data_files('tzdata'),
    ],
)
archive = PYZ(analysis.pure)
exe = EXE(
    archive,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name='bbdc-to-ai',
    version=metadata,
    icon=str(project / 'packaging/app.ico'),
    console=False,
    strip=False,
    upx=False,
)
