"""中文桌面入口：导出、预览并复制复习提示词，无需终端或 Markdown 编辑器。"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from src.desktop_files import latest_review, load_output_dir, save_output_dir
from src.desktop_mumu import MumuDialogs
from src.desktop_view import ReviewActions, ReviewView
from src.desktop_worker import ExportJob, ExportJobResult
from src.version import VERSION


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
        self.mumu = MumuDialogs(root, self.status.set)
        root.title(f'不背单词复习助手 v{VERSION}')

    def open_latest(self, status: str = '正在查看已保存的复习', *,
                    empty_status: str = '此目录还没有复习文件。首次使用可先点「一键配置 MuMu」，再点「同步 MuMu」。') -> bool:
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
        if self.job is not None:
            if self.job.sync:
                stopping = self.job.request_sync_cancel()
                self.open_button.configure(state='disabled', text='正在停止…' if stopping else '正在收尾…')
                self.status.set('正在停止同步…' if stopping else '同步正在收尾…')
        elif (manager := self.mumu.select_manager()) is not None:
            self.start_export(sync=True, manager=manager)

    def configure_mumu(self) -> None:
        if (self.job is None and (manager := self.mumu.select_manager()) is not None
                and self.mumu.confirm_setup()):
            self.start_export(sync=False, setup=True, manager=manager)

    def start_export(self, *, sync: bool, setup: bool = False, manager: Path | None = None) -> None:
        if self.job is not None:
            return
        try:
            self.job = ExportJob(sync=sync, setup=setup, manager=manager)
        except OSError as exc:
            self.status.set('无法启动后台任务。')
            messagebox.showerror('启动失败', str(exc), parent=self.root)
            return
        self.set_busy(True, sync=sync)
        if setup:
            self.status.set('正在配置 MuMu 并检查连接，请稍候。')
        else:
            self.status.set('正在打开 MuMu 并同步学习记录，请稍候。' if sync
                            else '正在用本机记录导出当前学习日的复习，请稍候。')
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
        if result.status != 'cancelled' and (result.sync or result.setup):
            # MuMu brings its window forward when it launches the app.
            self.root.attributes('-topmost', True)
            self.root.lift()
            self.root.focus_force()
            self.root.after(1500, lambda: self.root.attributes('-topmost', False))
        self.show_result(result)

    def show_result(self, result: ExportJobResult) -> None:
        if result.status == 'cancelled':
            self.status.set(result.message or '同步已停止。需要时可以重新同步。')
        elif result.setup or (result.sync and result.status in ('app_missing', 'mumu_missing', 'error')):
            self.mumu.show_result(result)
        elif result.status == 'exported' and result.output is not None:
            details = ''
            if result.sync and result.new_word_count is not None:
                details = f'本次新增已保存词 {result.new_word_count} 个。'
            if result.target_word_count is not None:
                details += f'复习词表共 {result.target_word_count} 个。'
            if result.latest_saved_at is not None:
                details += f'App 最新记录时间 {result.latest_saved_at:%m/%d %H:%M}。'
            self.open_review(result.output, '同步成功，复习已刷新' if result.sync else '复习已导出', details)
        elif result.sync:
            message = f'{result.day} 同步后没有可导出的学习记录。请在 App 完成一组学习后再同步。'
            if result.last_day:
                message += f'本机最近有记录的学习日为 {result.last_day}。'
            self.status.set(message)
        elif result.status == 'no_records':
            message = f'本机还没有 {result.day} 的学习记录。点「同步 MuMu」可以从 App 同步。'
            if result.last_day:
                message += f'本机最近有记录的学习日为 {result.last_day}。'
            self.status.set(message)
        else:
            self.status.set('这次没有导出成功。')
            messagebox.showwarning('导出未完成', result.message or '请检查保存位置后重试。', parent=self.root)

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
        if self.job.sync and not self.job.setup:
            self.job.request_sync_cancel()
        else:
            self.job.request_cancel()


def legacy_main(argv: Sequence[str] | None = None, *, startup_warning: str | None = None) -> None:
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
    if startup_warning:
        root.after_idle(window.status.set, startup_warning)
    root.mainloop()


def main(argv: Sequence[str] | None = None, *, startup_warning: str | None = None) -> None:
    from src.flutter_window import binary, run_window
    if binary().is_file():
        run_window(argv, startup_warning=startup_warning)
        return
    try:
        from webview.platforms.winforms import renderer
        if renderer != 'edgechromium':
            raise RuntimeError('此电脑尚未安装 Microsoft Edge WebView2 Runtime')
        from src.dashboard import main as open_dashboard
        open_dashboard(argv, startup_warning=startup_warning)
    except (ImportError, OSError, RuntimeError) as exc:
        legacy_main(argv, startup_warning=f'已进入兼容界面。打开深色看板需要 WebView2：{exc}')


if __name__ == '__main__':
    main()
