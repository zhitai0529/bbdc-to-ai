"""中文桌面入口：导出、预览并复制复习提示词，无需终端或 Markdown 编辑器。"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import webbrowser

from src.desktop_files import latest_review, load_output_dir, save_output_dir
from src.desktop_view import ReviewActions, ReviewView
from src.desktop_worker import ExportJob, ExportJobResult
from src.mumu_installation import discover_mumu_manager, manager_in_location, remember_mumu_manager


MUMU_DOWNLOAD_URL = 'https://mumu.163.com/'


class ReviewWindow(ReviewView):
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.output_dir = load_output_dir()
        self.job: ExportJob | None = None
        self.closing = False
        self.content = ''
        root.protocol('WM_DELETE_WINDOW', self.close)
        super().__init__(root, self.output_dir, ReviewActions(
            sync=self.sync_and_view, setup=self.configure_mumu, export=self.export, copy=self.copy,
            change_folder=self.change_folder, open_folder=self.open_folder,
        ))

    def open_latest(self, status: str = '正在查看已保存的复习', *,
                    empty_status: str = '此目录还没有复习文件。首次使用可先点「一键配置 MuMu」，再点「查看已有复习」。') -> bool:
        try:
            path = latest_review(self.output_dir)
        except OSError:
            self.clear_preview()
            self.status.set('无法读取保存位置，请检查文件夹是否可以访问。')
            return False
        if path is None:
            self.clear_preview()
            self.status.set(empty_status)
            return False
        return self.open_review(path, status)

    def clear_preview(self) -> None:
        self.content = ''
        self.copy_button.configure(state='disabled')
        self.display('')

    def open_review(self, path: Path, status: str, details: str = '') -> bool:
        try:
            self.content = path.read_text(encoding='utf-8-sig')
        except (OSError, UnicodeError):
            self.clear_preview()
            self.status.set('复习文件暂时无法读取，请确认保存文件夹可以访问后重试。')
            return False
        self.display(self.content)
        self.copy_button.configure(state='normal')
        self.status.set(f'{status}（{path.name[:10]}）。{details}现在可以复制给 AI。')
        return True

    def change_folder(self) -> None:
        if self.job is not None:
            return
        try:
            initial_dir = self.output_dir if self.output_dir.is_dir() else Path.home()
            selected = filedialog.askdirectory(parent=self.root, title='选择复习文件保存位置',
                                               initialdir=str(initial_dir), mustexist=True)
            if not selected:
                return
            updated = save_output_dir(Path(selected))
        except (OSError, ValueError, tk.TclError) as exc:
            messagebox.showerror('无法更改保存位置', str(exc), parent=self.root)
            return
        self.output_dir = updated
        self.location_text.set(str(updated))
        self.open_latest('保存位置已更改，正在查看该目录的复习',
                         empty_status='保存位置已更改。下次导出会保存到这里。')

    def export(self) -> None:
        self.start_export(sync=False)

    def sync_and_view(self) -> None:
        if self.job is None and self.ensure_mumu_manager():
            self.start_export(sync=True)

    def configure_mumu(self) -> None:
        if self.job is not None or not self.ensure_mumu_manager():
            return
        confirmed = messagebox.askokcancel(
            '一键配置 MuMu',
            '助手会开启所选 MuMu 实例的 Root，并检查 ADB 和不背单词版本。'
            '需要重启时会关闭并重新打开该实例，请先结束当前学习。\n\n'
            '配置通过后，在 MuMu 里登录不背单词，再回到助手点「查看已有复习」。',
            parent=self.root,
        )
        if confirmed:
            self.start_export(sync=False, setup=True)

    def ensure_mumu_manager(self) -> bool:
        if discover_mumu_manager() is not None:
            return True

        self.status.set('请手动选择 MuMu 安装目录。')
        browse = messagebox.askyesnocancel(
            '查找 MuMu 安装位置',
            '助手未能自动找到 MuMu 安装目录。已安装时，可右键桌面上的 MuMu 图标，'
            '点「打开文件所在的位置」，找到需要选择的文件夹。\n\n'
            '是：手动选择安装目录\n'
            '否：打开 MuMu 官网下载\n'
            '取消：返回助手',
            default='cancel', parent=self.root,
        )
        if browse is False:
            self.open_mumu_download()
            return False
        if browse is None:
            return False
        try:
            folder = filedialog.askdirectory(parent=self.root, title='选择 MuMu 的安装目录', mustexist=True)
            if not folder:
                return False
            manager = manager_in_location(Path(folder))
            if manager is None:
                messagebox.showwarning(
                    '没找到 MuMu 管理程序',
                    '请选择 MuMu 安装目录，或桌面快捷方式「打开文件所在的位置」显示的目录。',
                    parent=self.root,
                )
                return False
            remember_mumu_manager(manager)
        except (OSError, ValueError, tk.TclError) as exc:
            messagebox.showerror('无法保存 MuMu 安装位置', str(exc), parent=self.root)
            return False
        return True

    def open_mumu_download(self) -> None:
        self.status.set('安装 MuMu 后可以再次配置或同步。')
        try:
            if webbrowser.open(MUMU_DOWNLOAD_URL):
                return
        except (OSError, webbrowser.Error):
            pass
        messagebox.showwarning('打开 MuMu 官网', f'请在浏览器访问 {MUMU_DOWNLOAD_URL}。', parent=self.root)

    def start_export(self, *, sync: bool, setup: bool = False) -> None:
        if self.job is not None:
            return
        try:
            self.job = ExportJob(sync=sync, setup=setup)
        except OSError as exc:
            self.status.set('无法启动后台任务。')
            messagebox.showerror('启动失败', str(exc), parent=self.root)
            return
        self.set_busy(True)
        if setup:
            self.status.set('正在配置 MuMu 并检查连接，请稍候。')
        else:
            self.clear_preview()
            self.status.set('正在打开 MuMu 并同步学习记录，请稍候。' if sync
                            else '正在用本机记录导出今日复习，请稍候。')
        self.root.after(200, self.poll)

    def poll(self) -> None:
        if self.job is None:
            return
        result = self.job.poll()
        if result is None:
            self.root.after(200, self.poll)
            return
        self.job = None
        if self.closing:
            if result.status == 'error' and result.message:
                messagebox.showwarning('关闭助手', result.message, parent=self.root)
            self.root.destroy()
            return
        self.set_busy(False)
        self.show_result(result)
        if result.sync or result.setup:
            # MuMu brings its window forward when it launches the app.
            self.root.attributes('-topmost', True)
            self.root.lift()
            self.root.focus_force()
            self.root.after(1500, lambda: self.root.attributes('-topmost', False))

    def show_result(self, result: ExportJobResult) -> None:
        if result.setup:
            message = result.message or '本次未完成配置，可以重新点击「一键配置 MuMu」。'
            self.status.set(message)
            if result.status == 'configured':
                messagebox.showinfo(
                    '配置完成',
                    'MuMu、ADB 和不背单词版本检查通过。\n\n'
                    '1. 在 MuMu 中打开不背单词，确认已登录自己的账号。\n'
                    '2. 回到助手，点击「查看已有复习」同步记录。\n'
                    '3. 词表出现后，点击「复制全部内容」，或用「仅看本地文件」打开导出目录。',
                    parent=self.root,
                )
            elif result.status == 'error':
                messagebox.showwarning('MuMu 配置未完成', message, parent=self.root)
        elif result.status == 'exported' and result.output is not None:
            details = ''
            if result.sync and result.new_word_count is not None:
                details = f'本次新增已保存词 {result.new_word_count} 个。'
            if result.target_word_count is not None:
                details += f'复习词表共 {result.target_word_count} 个。'
            if result.latest_saved_at is not None:
                details += f'App 最新记录时间 {result.latest_saved_at:%m/%d %H:%M}。'
            self.open_review(result.output, '同步成功，复习已刷新' if result.sync else '今日复习已导出', details)
        elif result.sync:
            message = result.message or '同步后未找到可导出的学习记录。'
            if not self.open_latest(f'{message} 正在查看本地复习', empty_status=message):
                self.status.set(message)
        elif result.status == 'no_records':
            self.status.set(f'本机还没有 {result.day} 的学习记录。')
            last_record = f'本机最近有记录的学习日是 {result.last_day}。\n\n' if result.last_day else ''
            self.display(last_record + '点「查看已有复习」可以同步 App 并导出。')
        else:
            self.status.set('这次没有导出成功。')
            self.display(result.message or '请检查保存位置后重试。')

    def copy(self) -> None:
        if self.content:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.content)
            self.root.update_idletasks()
            self.status.set('已复制！切换到你用的 AI 聊天窗口，在输入框按 Ctrl+V，然后点击发送。')

    def open_folder(self) -> None:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            os.startfile(self.output_dir)
        except OSError:
            messagebox.showerror('无法打开', f'请手动打开文件夹：\n{self.output_dir}', parent=self.root)

    def close(self) -> None:
        if self.job is None:
            self.root.destroy()
            return
        self.closing = True
        self.root.withdraw()
        self.job.request_cancel()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description='不背单词中文复习助手')
    parser.add_argument('--export', action='store_true', help='打开后使用本机记录导出今日复习')
    parser.add_argument('--open-latest', action='store_true', help='打开本地最近的复习文件（默认）')
    args = parser.parse_args(argv)
    root = tk.Tk()
    try:
        window = ReviewWindow(root)
    except Exception:
        root.withdraw()
        messagebox.showerror('启动失败', '无法读取工具配置，请检查 config.yaml 是否保留在原来的文件夹里。', parent=root)
        root.destroy()
        return
    if args.export:
        root.after(300, window.export)
    else:
        root.after_idle(window.open_latest)
    root.mainloop()


if __name__ == '__main__':
    main()
