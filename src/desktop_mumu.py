"""MuMu 安装位置选择和配置提示。"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import webbrowser

from src.desktop_worker import ExportJobResult
from src.mumu_diagnostics import MUMU_DOWNLOAD_URL, recovery_actions
from src.mumu_installation import discover_mumu_manager, manager_in_location, remember_mumu_manager


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
        self._remember(manager)
        return manager

    def _remember(self, manager: Path) -> None:
        self.manager = manager
        # Save discovery before contacting the device. Missing App and ADB errors
        # do not invalidate a detected Windows installation.
        try:
            remember_mumu_manager(manager)
        except (OSError, ValueError):
            self.set_status('已找到 MuMu，本次可以继续。此电脑暂时无法保存安装位置。')
    def _choose_folder(self, message: str = '助手未能自动找到 MuMu。') -> Path | None:
        browse = messagebox.askyesnocancel(
            '查找 MuMu 安装位置',
            f'{message}\n\n已安装时，可右键桌面上的 MuMu 图标，'
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
        self.set_status('安装或更新 MuMu 后，请启动 Android 15 实例，再回到助手继续。')
        try:
            if webbrowser.open(MUMU_DOWNLOAD_URL):
                return
        except (OSError, webbrowser.Error):
            pass
        messagebox.showwarning('打开 MuMu 官网', f'请在浏览器访问 {MUMU_DOWNLOAD_URL}。', parent=self.root)

    def confirm_setup(self) -> bool:
        return messagebox.askokcancel(
            '一键配置 MuMu',
            '1. 打开 MuMu 多开器，启动要用的 Android 15 实例。'
            '如果新建实例时没有 Android 15 选项，请从官网更新 Windows 版 MuMu。\n\n'
            '2. 在该实例内安装「不背单词」5.11.8 x86。\n\n'
            '3. 结束当前学习后点「确定」。助手会检查连接和 App 版本，需要开启 Root 时会重启该实例。',
            parent=self.root,
        )

    def show_result(self, result: ExportJobResult) -> None:
        action = '一键配置 MuMu' if result.setup else '同步 MuMu'
        defaults = {
            'configured': '请在 MuMu 里打开并登录不背单词，回到助手点「同步 MuMu」。',
            'app_missing': f'请在目标 Android 15 实例安装「不背单词」5.11.8 x86，打开并登录后重试「{action}」。',
            'mumu_missing': '之前找到的 MuMu 安装位置已不可用。',
        }
        message = result.message or defaults.get(
            result.status, f'「{action}」未完成。请打开目标实例，等 Android 桌面出现后重试。',
        )
        recovery = recovery_actions(result.status, result.reason)
        self.set_status(message)
        if result.status == 'configured':
            messagebox.showinfo('配置完成', message, parent=self.root)
        elif result.status == 'app_missing':
            messagebox.showwarning('MuMu 已找到，请安装不背单词', message, parent=self.root)
        elif 'locate' in recovery:
            if result.status == 'mumu_missing':
                self.manager = None
            manager = self._choose_folder(message)
            if manager is not None:
                self._remember(manager)
                self.set_status(f'已选择 MuMu 安装目录。启动目标 Android 15 实例后，再点「{action}」。')
        elif 'download' in recovery:
            if messagebox.askyesno(f'{action}未完成', f'{message}\n\n现在打开 MuMu 官网吗？', parent=self.root):
                self._open_download()
        elif result.status == 'error':
            title = 'MuMu 配置未完成' if result.setup else 'MuMu 同步未完成'
            messagebox.showwarning(title, message, parent=self.root)
