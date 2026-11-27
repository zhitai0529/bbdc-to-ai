"""Exercise the real WebView2 bridge with a disposable study history on Windows."""
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import sys
import time
from unittest.mock import patch

from src.bbdc_schema import study_date
from src.config import load_config
from src.dashboard import DashboardAPI, open_window
from src.desktop_files import review_path
from src.desktop_worker import ExportJobResult
from src.pipeline import process_payload
from src.runtime import PROJECT_ROOT


def main() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        config = replace(load_config(PROJECT_ROOT / 'config.example.yaml'), root=root,
                         state_dir=root / 'cache', output_dir=root / '学习笔记' / '英语复习')
        today = study_date(datetime.now(config.timezone))
        vocabulary = ['approximate','ambiguous','abstract','persistent','comprehend','argument',
                      'inevitable','coherent','vague','obscure','reliable','represent']
        for i in range(30):
            day = today - timedelta(days=29-i)
            rows = []
            for j, word in enumerate(vocabulary[:6+i%7]):
                ah, rh = [('110','B'),('210','D'),('999','C'),('0','A'),('0','A')][(j+i)%5]
                rows.append(dict(wd=word, ah=ah, rh=rh, st=4, ut=f'{day} 12:00:00'))
            process_payload(rows, config, day, announce=False)
        errors = []
        sync_cancel_requested = Event()
        sync_stopped = Event()
        manager = root / 'MuMuManager.exe'
        manager.touch()

        def exercise(win):
            def until(expression):
                end = time.monotonic()+12
                while time.monotonic()<end:
                    if win.evaluate_js(expression):
                        return
                    time.sleep(.1)
                raise AssertionError(f'{expression}: {win.evaluate_js("document.body.innerText")[:700]}')

            def click(selector):
                win.evaluate_js(f"document.querySelector({selector!r}).click()")

            try:
                until("document.querySelectorAll('#kpis canvas').length===4 && !document.querySelector('#dates').disabled")
                assert win.evaluate_js("document.querySelector('#preview').hidden")
                assert win.evaluate_js("document.querySelectorAll('.heatcell').length") == 168
                assert win.evaluate_js("document.documentElement.scrollWidth <= innerWidth")
                if len(sys.argv) > 1:
                    from System import Action
                    from System.IO import File
                    from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
                    stream = File.Create(str(Path(sys.argv[1]).resolve()))
                    tasks = []
                    def capture():
                        browser = win.native.Controls[0].CoreWebView2
                        tasks.append(browser.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, stream))
                    win.native.Invoke(Action(capture))
                    tasks[0].Wait(5000)
                    stream.Close()
                click('[data-view=preview]')
                until("document.querySelector('#markdown h1')?.textContent.includes('每日纠结词')")
                click('#sourceMode')
                win.evaluate_js("var e=document.querySelector('#source'); e.value+='\\nUI smoke'; e.dispatchEvent(new Event('input'))")
                click('[data-action=sync]')
                until("document.querySelector('#syncLabel').textContent === '停止同步'")
                assert not win.evaluate_js("document.querySelector('[data-action=sync]').disabled")
                click('[data-action=sync]')
                until("document.querySelector('#syncLabel').textContent === '正在停止…'")
                assert win.evaluate_js("document.querySelector('[data-action=sync]').disabled")
                assert sync_cancel_requested.wait(timeout=4)
                sync_worker.request_sync_cancel.assert_called_once_with()
                sync_stopped.set()
                until("document.querySelector('#status').textContent.includes('同步已停止')")
                assert not win.evaluate_js("document.querySelector('#modal').open")
                assert win.evaluate_js("document.querySelector('#source').value.endsWith('UI smoke')")
                click('[data-action=copy]')
                until("document.querySelector('[data-action=copy]').textContent.includes('已复制')")
                assert clipboard.call_args.args[0].endswith('UI smoke')
                click('[data-action=save]')
                until("document.querySelector('#status').textContent.includes('修改已保存')")
                click('#renderMode')
                until("document.querySelector('#markdown').textContent.includes('UI smoke')")
                click('[data-action=export]')
                until("document.querySelector('#modal').open && document.querySelector('#modalTitle').textContent.includes('重新导出')")
                click('#choices button:first-child')
                until("!document.querySelector('#modal').open && !document.querySelector('[data-action=export]').disabled")
                assert review_path(config.output_dir, today).read_text(encoding='utf-8').endswith('UI smoke')

                win.evaluate_js("var d=document.querySelector('#dates');d.selectedIndex=1;d.dispatchEvent(new Event('change'))")
                until("document.querySelector('#status').textContent.includes('已切换')")
                exercise_day = win.evaluate_js("document.querySelector('#dates').value")
                sync_worker.poll.side_effect = lambda: ExportJobResult(
                    'exported', True, output=review_path(config.output_dir, today),
                    new_word_count=1, target_word_count=4,
                )
                click('[data-action=sync]')
                until("!document.querySelector('[data-action=latest]').hidden && !document.querySelector('[data-action=latest]').disabled")
                assert win.evaluate_js("document.querySelector('#dates').value") == exercise_day

                click('[data-action=range]')
                until("document.querySelector('#modalTitle').textContent === '导出多日薄弱词'")
                click('#choices button:last-child')
                until("document.querySelector('#modalMarkdown h1')?.textContent.includes('多日薄弱词')")
                range_day = today - timedelta(days=1)
                range_file, = config.output_dir.glob(f'{range_day - timedelta(days=2)}_to_{range_day}_bbdc_range_review_*.md')
                click('#choices button:last-child')
                until("document.querySelector('#status').textContent.includes('已复制多日')")
                assert clipboard.call_args.args[0] == range_file.read_text(encoding='utf-8')

                click('[data-action=latest]')
                until(f"document.querySelector('#dates').value === '{today}'")
                win.evaluate_js("var d=document.querySelector('#dates');d.selectedIndex=1;d.dispatchEvent(new Event('change'))")
                until("document.querySelector('#status').textContent.includes('已切换')")
                click('[data-view=exercise]')
                until("!document.querySelector('#exercise').hidden && !document.querySelector('#generateExercise').disabled")
                assert win.evaluate_js("document.querySelector('[data-action=copy]').hidden")
                win.evaluate_js("var l=document.querySelector('#exerciseLevel');l.value='cet4';l.dispatchEvent(new Event('change'))")
                click('#generateExercise')
                until("!document.querySelector('#exercisePreview').hidden")
                first = config.output_dir / f'{exercise_day}_bbdc_exercise_cet4_main_clause.md'
                assert first.is_file()
                click('#copyExercise')
                until("document.querySelector('#exerciseStatus').textContent.includes('已复制练习提示词')")
                assert clipboard.call_args.args[0] == first.read_text(encoding='utf-8')
                win.evaluate_js("var t=document.querySelector('#exerciseType');t.value='cloze';t.dispatchEvent(new Event('change'))")
                assert win.evaluate_js("document.querySelector('#exercisePreview').hidden")
                click('#generateExercise')
                until("!document.querySelector('#exercisePreview').hidden")
                second = config.output_dir / f'{exercise_day}_bbdc_exercise_cet4_cloze.md'
                assert second.is_file() and first.is_file()
                win.evaluate_js("var d=document.querySelector('#dates');d.selectedIndex=0;d.dispatchEvent(new Event('change'))")
                until("document.querySelector('#exercisePreview').hidden")
                click('[data-view=history]')
                until("document.querySelector('#repeats tbody tr') !== null")
                click('[data-view=settings]')
                until("document.querySelector('#path').value.length>0 && !document.querySelector('#settings').hidden")
                click('[data-action=setup]')
                until("document.querySelector('#modal').open")
                click('#choices button')
                until("!document.querySelector('#modal').open")
            except Exception as exc:
                errors.append(exc)
            finally:
                win.destroy()

        with patch('src.desktop_api.load_config', return_value=config), patch('pyperclip.copy') as clipboard, \
                patch('src.desktop_jobs.discover_mumu_manager', return_value=manager), \
                patch('src.desktop_jobs.remember_mumu_manager'), patch('src.desktop_jobs.ExportJob') as worker:
            sync_worker = worker.return_value
            sync_worker.scratch.name = str(root / 'worker')
            sync_worker.sync = True
            sync_worker.setup = False
            def request_sync_cancel() -> bool:
                sync_cancel_requested.set()
                return True
            sync_worker.request_sync_cancel.side_effect = request_sync_cancel
            sync_worker.poll.side_effect = lambda: ExportJobResult('cancelled', True) if sync_stopped.is_set() else None
            open_window(DashboardAPI(), exercise)
        if errors:
            raise errors[0]
    print('WebView2 dashboard smoke test passed.')


if __name__ == '__main__':
    main()
