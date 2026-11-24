"""Windows WebView adapter for the shared desktop commands."""
from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

from src.desktop_api import DesktopAPI
from src.runtime import PROJECT_ROOT
from src.version import VERSION


class DashboardAPI(DesktopAPI):
    _window = None

    def copy(self, content: str) -> None:
        import pyperclip

        if content:
            pyperclip.copy(content)

    def _choose(self, initial: str = '') -> Path | None:
        import webview

        selection = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=initial)
        return Path(selection[0]) if selection else None


def page_html() -> str:
    folder = PROJECT_ROOT / 'frontend'
    template = (folder / 'index.html').read_text(encoding='utf-8')
    css = (folder / 'bundle.css').read_text(encoding='utf-8')
    js = (folder / 'bundle.js').read_text(encoding='utf-8').replace('</script', r'<\/script')
    return template.replace('/* bundled css */', css).replace('/* bundled js */', js)


def main(argv: Sequence[str] | None = None, *, startup_warning: str | None = None) -> None:
    parser = argparse.ArgumentParser(description='不背单词复习助手')
    parser.add_argument('--export', action='store_true')
    parser.add_argument('--open-latest', action='store_true')
    args = parser.parse_args(argv)
    open_window(DashboardAPI(startup_warning, args.export, args.open_latest))


def open_window(api: DashboardAPI, ready: Callable | None = None) -> None:
    import webview

    webview.settings['ALLOW_FILE_URLS'] = False
    window = webview.create_window(f'不背单词复习助手 v{VERSION}', html=page_html(), js_api=api,
                                   width=1380, height=900, min_size=(860, 600), background_color='#0B0F19')
    api._window = window
    window.events.closing += lambda: api._close(window.hide)
    webview.start(ready, (window,), gui='edgechromium')
