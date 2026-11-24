"""Visual layout and widget state for the Windows review assistant."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk


BACKGROUND = '#eef3f5'
PANEL = '#ffffff'
TEXT = '#172e36'
MUTED = '#4c646d'
BORDER = '#cddbe0'
ACCENT = '#075b54'
ACCENT_HOVER = '#064c46'
SOFT = '#edf6f3'
FONT = 'Microsoft YaHei UI'


@dataclass(frozen=True)
class ReviewActions:
    sync: Callable[[], None]
    setup: Callable[[], None]
    export: Callable[[], None]
    copy: Callable[[], None]
    change_folder: Callable[[], None]
    open_folder: Callable[[], None]


def configure_styles(root: tk.Tk) -> None:
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('Review.TButton', font=(FONT, 10, 'bold'), padding=(13, 8),
                    background=PANEL, foreground=TEXT, bordercolor=BORDER, relief='flat')
    style.map('Review.TButton', background=[('disabled', '#f2f5f6'), ('pressed', '#dcece8'),
                                           ('active', SOFT)], foreground=[('disabled', '#70838c')],
              bordercolor=[('focus', ACCENT)])
    style.configure('Accent.Review.TButton', background=ACCENT, foreground=PANEL, bordercolor=ACCENT)
    style.map('Accent.Review.TButton', background=[('disabled', '#e0ece9'), ('pressed', '#043c37'),
                                                  ('active', ACCENT_HOVER)],
              foreground=[('disabled', '#637b76')], bordercolor=[('focus', TEXT)])
    style.configure('Compact.Review.TButton', padding=(8, 6))
    style.configure('Review.TEntry', padding=(8, 6), foreground=TEXT, bordercolor=BORDER,
                    fieldbackground=SOFT)
    style.map('Review.TEntry', fieldbackground=[('readonly', SOFT)], bordercolor=[('focus', ACCENT)])
    style.configure('Review.Horizontal.TProgressbar', background=ACCENT, troughcolor='#dce9e7',
                    bordercolor=SOFT, lightcolor=ACCENT, darkcolor=ACCENT, thickness=4)
    style.configure('Review.Vertical.TScrollbar', background='#d6e4e7', troughcolor=PANEL,
                    bordercolor=PANEL, arrowcolor=MUTED, width=12)


class ReviewView:
    def __init__(self, root: tk.Tk, output_dir: Path, actions: ReviewActions) -> None:
        root.title('不背单词复习助手')
        root.geometry('1060x720')
        root.configure(background=BACKGROUND)
        configure_styles(root)

        surface = tk.Frame(root, background=BACKGROUND, padx=20, pady=15)
        surface.pack(fill='both', expand=True)
        surface.grid_columnconfigure(0, weight=1)
        surface.grid_rowconfigure(1, weight=1)
        self._build_header(surface)

        workspace = tk.Frame(surface, background=BACKGROUND)
        workspace.grid(row=1, column=0, sticky='nsew')
        workspace.grid_rowconfigure(0, weight=1)
        workspace.grid_columnconfigure(1, weight=1)
        self._build_sidebar(workspace, output_dir, actions)
        self._build_preview(workspace, actions.copy)

        self.status = tk.StringVar(root, value='准备就绪。')
        status_bar = tk.Frame(surface, background=BACKGROUND)
        status_bar.grid(row=2, column=0, sticky='ew', pady=(10, 0))
        self.progress = ttk.Progressbar(status_bar, style='Review.Horizontal.TProgressbar',
                                        length=104, mode='indeterminate', takefocus=False)
        self.status_label = self._label(status_bar, self.status, background=BACKGROUND, foreground=MUTED)
        self.status_label.pack(side='left', fill='x', expand=True)
        self.progress.pack(side='right', padx=(12, 0))
        self.progress.pack_forget()
        status_bar.bind('<Configure>', self._resize_status)
        self.display('')
        surface.update_idletasks()
        root.minsize(max(780, surface.winfo_reqwidth()), max(565, surface.winfo_reqheight() + 25))

    @staticmethod
    def _label(parent: tk.Misc, text: str | tk.StringVar, *, size: int = 10, bold: bool = False,
               foreground: str = TEXT, background: str = PANEL) -> tk.Label:
        label = tk.Label(parent, font=(FONT, size, 'bold' if bold else 'normal'),
                         foreground=foreground, background=background, justify='left', anchor='w',
                         padx=0, pady=0)
        if isinstance(text, tk.StringVar):
            label.configure(textvariable=text)
        else:
            label.configure(text=text)
        return label

    def _build_header(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, background=BACKGROUND)
        header.grid(row=0, column=0, sticky='ew', pady=(0, 15))
        tk.Frame(header, width=4, background=ACCENT).pack(side='left', fill='y', padx=(0, 11), pady=2)
        title = tk.Frame(header, background=BACKGROUND)
        title.pack(side='left', fill='x')
        self._label(title, '不背单词复习助手', size=21, bold=True, background=BACKGROUND).pack(anchor='w')
        self._label(title, '把需要再练的单词整理成 AI 复习提示词。', background=BACKGROUND,
                    foreground=MUTED).pack(anchor='w', pady=(2, 0))

    def _build_sidebar(self, parent: tk.Frame, output_dir: Path, actions: ReviewActions) -> None:
        sidebar = tk.Frame(parent, background=PANEL, highlightbackground=BORDER,
                           highlightthickness=1, padx=14, pady=13)
        sidebar.grid(row=0, column=0, sticky='nsew', padx=(0, 12))
        self._label(sidebar, '学习记录', size=12, bold=True).pack(anchor='w', pady=(0, 9))
        self.open_button = self._action(sidebar, '查看已有复习', '打开 MuMu 并同步学习记录',
                                        actions.sync, primary=True)
        self.setup_button = self._action(sidebar, '一键配置 MuMu', '开启 Root 并检查连接', actions.setup)
        self.export_button = self._action(sidebar, '导出今日复习', '用本机已有记录生成文件', actions.export)
        self.saved_button = self._action(sidebar, '仅看本地文件', '在资源管理器打开导出目录', actions.open_folder)

        location = tk.Frame(sidebar, background=PANEL)
        location.pack(side='bottom', fill='x', pady=(12, 0))
        tk.Frame(location, height=1, background=BORDER).pack(fill='x', pady=(0, 11))
        self._label(location, '保存位置', size=11, bold=True).pack(anchor='w', pady=(0, 6))
        self.location_text = tk.StringVar(sidebar, value=str(output_dir))
        ttk.Entry(location, textvariable=self.location_text, state='readonly', width=24,
                  font=(FONT, 9), style='Review.TEntry').pack(fill='x', pady=(0, 8))
        self.change_button = ttk.Button(location, text='更改保存位置', command=actions.change_folder,
                                        style='Compact.Review.TButton')
        self.change_button.pack(fill='x')

    def _action(self, parent: tk.Frame, title: str, help_text: str, command: Callable[[], object],
                *, primary: bool = False) -> ttk.Button:
        button = ttk.Button(parent, text=title, command=command, width=18,
                            style='Accent.Review.TButton' if primary else 'Review.TButton')
        button.pack(fill='x')
        self._label(parent, help_text, size=9, foreground=MUTED).pack(anchor='w', pady=(3, 8))
        return button

    def _build_preview(self, parent: tk.Frame, copy: Callable[[], None]) -> None:
        panel = tk.Frame(parent, background=PANEL, highlightbackground=BORDER, highlightthickness=1)
        panel.grid(row=0, column=1, sticky='nsew')
        header = tk.Frame(panel, background=PANEL, padx=15, pady=11)
        header.pack(fill='x')
        self._label(header, '复习预览', size=13, bold=True).pack(side='left', anchor='w')
        self.copy_button = ttk.Button(header, text='复制全部内容', command=copy, state='disabled',
                                      style='Accent.Review.TButton')
        self.copy_button.pack(side='right')
        tk.Frame(panel, height=1, background=BORDER).pack(fill='x')

        preview_area = tk.Frame(panel, background=PANEL, padx=6, pady=4)
        preview_area.pack(fill='both', expand=True)
        self.preview = tk.Text(preview_area, wrap='word', width=1, height=1, font=(FONT, 10),
                               padx=13, pady=9, spacing1=2, spacing3=3, background=PANEL,
                               foreground=TEXT, borderwidth=0, relief='flat', highlightthickness=1,
                               highlightbackground=PANEL, highlightcolor=BORDER,
                               selectbackground='#c8e6df', selectforeground=TEXT, undo=False)
        scroll = ttk.Scrollbar(preview_area, orient='vertical', command=self.preview.yview,
                               style='Review.Vertical.TScrollbar')
        self.preview.configure(yscrollcommand=scroll.set, state='disabled')
        scroll.pack(side='right', fill='y')
        self.preview.pack(side='left', fill='both', expand=True)
        self.preview.tag_configure('title', font=(FONT, 16, 'bold'), foreground=ACCENT, spacing3=9)
        self.preview.tag_configure('heading', font=(FONT, 12, 'bold'), foreground=ACCENT,
                                   spacing1=5, spacing3=4)
        self.preview.tag_configure('table', background=SOFT, lmargin1=5, lmargin2=5)
        self.preview.tag_configure('hint', foreground=MUTED, spacing1=8, spacing3=3)

    def _resize_status(self, event: tk.Event) -> None:
        progress_width = self.progress.winfo_reqwidth() + 12 if self.progress.winfo_manager() else 0
        self.status_label.configure(wraplength=max(200, event.width - progress_width))

    def display(self, text: str) -> None:
        self.preview.configure(state='normal')
        self.preview.delete('1.0', 'end')
        if text:
            self.preview.insert('1.0', text)
            for index, line in enumerate(text.splitlines(), 1):
                if line.startswith('# '):
                    tag = 'title'
                elif line.startswith(('## ', '### ')):
                    tag = 'heading'
                elif line.startswith('|'):
                    tag = 'table'
                else:
                    continue
                self.preview.tag_add(tag, f'{index}.0', f'{index}.end')
        else:
            self.preview.insert('1.0', '还没有可预览的内容。', 'hint')
        self.preview.see('1.0')
        self.preview.configure(state='disabled')

    def set_busy(self, busy: bool) -> None:
        state = 'disabled' if busy else 'normal'
        for button in (self.export_button, self.open_button, self.setup_button, self.change_button):
            button.configure(state=state)
        if busy:
            self.progress.pack(side='right', padx=(12, 0))
            self.progress.start(15)
        else:
            self.progress.stop()
            self.progress.pack_forget()
        parent = self.status_label.master
        progress_width = self.progress.winfo_reqwidth() + 12 if busy else 0
        self.status_label.configure(wraplength=max(200, parent.winfo_width() - progress_width))
