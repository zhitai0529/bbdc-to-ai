from importlib.metadata import distribution
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files


project = Path(SPECPATH).resolve().parent

notices = [project.joinpath('LICENSE').read_text(encoding='utf-8')]
for package in ('pyinstaller', 'PyYAML', 'rich', 'filelock', 'cryptography', 'pyelftools',
                'tzdata', 'cffi', 'markdown-it-py', 'pygments', 'mdurl', 'pycparser'):
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
    icon=str(project / 'packaging/app.ico'),
    console=False,
    strip=False,
    upx=False,
)
