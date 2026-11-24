"""MuMu 安装位置选择和配置提示。"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import webbrowser

from src.desktop_worker import ExportJobResult
from src.mumu_installation import discover_mumu_manager, manager_in_location, remember_mumu_manager

MUMU_DOWNLOAD_URL = 'https://mumu.163.com/'


class MumuDialogs:
    def __init__(self, root: tk.Tk, set_status: Callable[[str], None]) -> None:
        self.root = root
        self.set_status = set_status
        self.manager: Path | None = None

    def select_manager(self) -> Path | None:
        if self.manager is not None and self.manager.is_file():
            return self.manager
        manager = discover_mumu_manager()
        if manager is None:
            manager = self._choose_folder()
        if manager is None:
            return None
        self.manager = manager
        # Save discovery before contacting the device. Missing App and ADB errors
        # do not invalidate a detected Windows installation.
        try:
            remember_mumu_manager(manager)
        except (OSError, ValueError):
            self.set_status('已找到 MuMu，本次可以继续。此电脑暂时无法保存安装位置。')
        return manager

    def _choose_folder(self) -> Path | None:
        browse = messagebox.askyesnocancel(
            '查找 MuMu 安装位置',
            '助手未能自动找到 MuMu。已安装时，可右键桌面上的 MuMu 图标，'
            '点「打开文件所在的位置」，找到需要选择的文件夹。\n\n'
            '是：手动选择安装目录\n否：打开 MuMu 官网下载\n取消：返回助手',
            default='cancel', parent=self.root,
        )
        if browse is False:
            self._open_download()
        if not browse:
            return None
        try:
            folder = filedialog.askdirectory(parent=self.root, title='选择 MuMu 的安装目录', mustexist=True)
        except tk.TclError as exc:
            messagebox.showerror('无法选择 MuMu 安装位置', str(exc), parent=self.root)
            return None
        if not folder:
            return None
        manager = manager_in_location(Path(folder))
        if manager is None:
            messagebox.showwarning(
                '没找到 MuMu 管理程序',
                '请选择 MuMu 安装目录，或桌面快捷方式「打开文件所在的位置」显示的目录。',
                parent=self.root,
            )
        return manager

    def _open_download(self) -> None:
        self.set_status('安装 MuMu 后可以再次配置或同步。')
        try:
            if webbrowser.open(MUMU_DOWNLOAD_URL):
                return
        except (OSError, webbrowser.Error):
            pass
        messagebox.showwarning('打开 MuMu 官网', f'请在浏览器访问 {MUMU_DOWNLOAD_URL}。', parent=self.root)

    def confirm_setup(self) -> bool:
        return messagebox.askokcancel(
            '一键配置 MuMu',
            '助手会开启所选 MuMu 实例的 Root，并检查 ADB 和不背单词版本。'
            '需要重启时会关闭并重新打开该实例，请先结束当前学习。\n\n'
            '配置通过后，在 MuMu 里登录不背单词，再回到助手点「查看已有复习」。',
            parent=self.root,
        )

    def show_result(self, result: ExportJobResult) -> None:
        message = result.message or '操作未完成，请检查 MuMu 后重试。'
        self.set_status(message)
        if result.status == 'configured':
            messagebox.showinfo(
                '配置完成',
                'MuMu、ADB 和不背单词版本检查通过。\n\n'
                '1. 在 MuMu 中打开不背单词，确认已登录自己的账号。\n'
                '2. 回到助手，点击「查看已有复习」同步记录。\n'
                '3. 词表出现后，点击「复制全部内容」，或用「仅看本地文件」打开导出目录。',
                parent=self.root,
            )
        elif result.status == 'app_missing':
            messagebox.showwarning(
                'MuMu 已找到，请安装不背单词',
                f'{message}\n\n请在刚才打开的 MuMu Android 15 实例中安装并打开不背单词，'
                '然后回到助手再点一次刚才的按钮。助手会沿用已找到的安装位置。',
                parent=self.root,
            )
        elif result.status == 'mumu_missing':
            self.manager = None
            messagebox.showwarning(
                'MuMu 安装位置不可用',
                f'{message}\n\n请重新点击按钮，按提示选择 MuMu 的安装目录。', parent=self.root,
            )
        elif result.status == 'error':
            messagebox.showwarning('MuMu 配置未完成', message, parent=self.root)
