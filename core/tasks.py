import asyncio
import queue
import threading
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from core.storage import read_json, atomic_json
from plugins.base import DownloadStopped, VerificationRequired

LABELS = {'held': 'Để sau', 'queued': 'Chờ lượt', 'running': 'Đang tải', 'paused': 'Tạm dừng',
          'waiting_verification': 'Cần xác minh', 'stopping': 'Đang dừng', 'stopped': 'Đã dừng',
          'completed': 'Hoàn tất', 'failed': 'Có lỗi', 'needs_review': 'Cần kiểm tra kết quả'}
ACTIVE = {'running', 'paused', 'waiting_verification', 'stopping'}


class TaskManager:
    def __init__(self, data_dir, plugins):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / 'tasks.json'
        self.plugins = plugins
        self.events = queue.Queue()
        self.tasks = read_json(self.path, [])
        for task in self.tasks:
            task.setdefault('connection_mode', 'http')
            task.setdefault('current_url', task['url'])
            task['logs'] = task.get('logs', [])[-250:]
            if (urlparse(task['url']).hostname or '').lower().removeprefix('www.') == 'tinhngoncoc.net' and task['state'] != 'completed':
                task.update(state='held', status='Nguồn đã gỡ · có thể bỏ tác vụ', detail='Tịnh Ngôn Cốc không còn được hỗ trợ.')
            if task['state'] in ACTIVE:
                task['state'] = 'stopped'
                task['detail'] = 'Phiên trước đã đóng. Bấm Thử lại / tiếp tục để chạy.'
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.verification_event = threading.Event()
        self.worker = None
        self.active_id = None
        self.auto_run = False
        self.notice = None
        self.save()

    def save(self):
        atomic_json(self.path, self.tasks)

    def add(self, url, folder, plugin='Tự động', output_format='TXT · từng chương', interval=3, allow_mature=False, browser_mode=False, connection_mode='http', network_mode='direct', warp_port=40000):
        from core.network import NetworkPolicy
        NetworkPolicy(network_mode, warp_port)
        parsed = urlparse(url)
        if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Dán đường dẫn http/https hợp lệ, không chứa tài khoản hoặc mật khẩu.')
        if (parsed.hostname or '').lower().removeprefix('www.') == 'tinhngoncoc.net':
            raise ValueError('Nguồn Tịnh Ngôn Cốc đã được gỡ.')
        if not folder.strip():
            raise ValueError('Hãy chọn thư mục lưu.')
        handler = self.plugins.find_handler(url) if plugin == 'Tự động' else self.plugins.plugin_map.get(plugin)
        if not handler or not handler.can_handle(url):
            raise ValueError('Chưa có plugin phù hợp. Xem Nguồn & plugin hoặc thêm cấu hình nguồn riêng.')
        plugin_name = next(k for k, v in self.plugins.plugin_map.items() if v is handler)
        if any(t['url'] == url and t['folder'] == str(Path(folder).resolve()) and t['state'] in ACTIVE | {'queued'} for t in self.tasks):
            raise ValueError('Link này đã nằm trong hàng đợi tại cùng thư mục.')
        Path(folder).mkdir(parents=True, exist_ok=True)
        task = dict(id=uuid.uuid4().hex, url=url, folder=str(Path(folder).resolve()), plugin=plugin_name,
                    state='queued', title=parsed.hostname, status='Chờ bắt đầu', detail='', current=0,
                    fraction=0, output_format=output_format, interval=interval, allow_mature=allow_mature,
                    browser_mode=browser_mode, connection_mode=connection_mode, network_mode=network_mode, warp_port=int(warp_port), current_url=url, request_url='', failure_url='', logs=[], created=datetime.now().isoformat(timespec='seconds'))
        self.tasks.append(task)
        self.save()
        return task

    def get(self, task_id):
        return next((t for t in self.tasks if t['id'] == task_id), None)

    def start_next(self):
        if not self.auto_run or self.active_id or (self.worker and self.worker.is_alive()):
            return
        task = next((t for t in self.tasks if t['state'] == 'queued'), None)
        if task is None:
            return
        handler = self.plugins.plugin_map.get(task['plugin'])
        if handler is None:
            task.update(state='failed', status='Nguồn đã bị gỡ', detail='Bỏ tác vụ này hoặc chọn nguồn khác.')
            self.auto_run = False
            self.save()
            return
        self.active_id = task['id']
        self.stop_event.clear()
        self.pause_event.clear()
        self.verification_event.clear()
        task.update(state='running', status='Đang kết nối', detail='')
        self.save()
        self.worker = threading.Thread(target=self._run, args=(task.copy(), type(handler)), daemon=True)
        self.worker.start()

    def _run(self, task, crawler_class):
        tid = task['id']
        def emit(kind, payload):
            self.events.put((tid, kind, payload))
        handler = None
        try:
            handler = crawler_class(lambda message: emit('log', str(message)))
            handler.stop_event = self.stop_event
            emit('log', f'[BẮT ĐẦU] {task["plugin"]} · chế độ {task.get("connection_mode", "http")}')
            emit('log', f'[LINK GỐC] {task["url"]}')
            emit('log', f'[THƯ MỤC] {task["folder"]}')
            handler.configure_run(connection_mode=task.get('connection_mode', 'http'), output_format=task['output_format'], allow_mature=task['allow_mature'],
                                  request_interval=task['interval'], pause_event=self.pause_event,
                                  network_mode=task.get('network_mode', 'direct'), warp_port=task.get('warp_port', 40000),
                                  verification_event=self.verification_event, data_dir=str(self.data_dir/'sessions'/tid),
                                  progress_callback=lambda p: emit('progress', p))
            async def download():
                if task.get('connection_mode', 'http') in {'background', 'browser'} and handler.__class__.__name__ not in {'WikiCVCrawler', 'FanFicFarePublicCrawler'}:
                    from core.browser import BrowserSession
                    async with BrowserSession(handler) as browser:
                        handler.browser = browser
                        return await handler.start_download(task['url'], task['folder'])
                return await handler.start_download(task['url'], task['folder'])
            async def execute():
                from core.network import NetworkFailure
                if handler.network.proxy and handler.__class__.__name__ == 'FanFicFarePublicCrawler':
                    raise NetworkFailure('FanFicFare chưa hỗ trợ tự kết nối lại WARP. Tác vụ đã dừng trước khi tải; chọn mạng trực tiếp hoặc plugin chuyên biệt.')
                await handler.network.prepare()
                while True:
                    try:
                        return await download()
                    except NetworkFailure as exc:
                        if not getattr(handler, 'supports_resume', False): raise
                        if not await handler.network.reconnect(str(exc)): raise
                        await handler.checkpoint()
                        emit('log', '[TỰ TIẾP TỤC] Đọc lại mốc chương/phần đã lưu sau khi kết nối lại proxy.')
            result = asyncio.run(execute())
            if self.stop_event.is_set():
                emit('end', {'state': 'stopped', 'status': 'Đã dừng'})
            elif isinstance(result, dict) and result.get('completed'):
                emit('end', dict(result, state='completed', status='Đã tải xong', fraction=1))
            else:
                emit('end', {'state': 'needs_review', 'status': 'Plugin cũ đã kết thúc',
                             'detail': 'Plugin chưa trả xác nhận đủ chương. Mở thư mục và nhật ký để kiểm tra.'})
        except DownloadStopped:
            emit('end', {'state': 'stopped', 'status': 'Đã dừng; dữ liệu đã lưu được giữ lại'})
        except Exception as exc:
            failed_url = (getattr(handler, 'current_url', '') or task.get('current_url') or task['url'])
            request_url = getattr(handler, 'request_url', '') or failed_url
            part = getattr(handler, 'current_part', None)
            emit('log', f'[LỖI] {type(exc).__name__}: {exc}')
            emit('log', f'[LINK LỖI CUỐI] {failed_url}' + (f' · Phần {part + 1}' if part is not None else ''))
            if request_url != failed_url:
                emit('log', f'[YÊU CẦU LỖI] {request_url}')
            emit('log', '[TIẾP TỤC] Sau khi kết nối ổn định, chọn tác vụ và bấm Tiếp tục tải. WikiCV giữ nguyên mốc và các phần đã lưu.')
            emit('end', {'state': 'failed', 'status': 'Nguồn yêu cầu xác minh' if isinstance(exc, VerificationRequired) else 'Tải chưa thành công',
                         'detail': str(exc), 'failure_url': failed_url, 'failure_request_url': request_url, 'failure_part': part})

    def drain(self):
        changed = False
        while True:
            try:
                tid, kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            task = self.get(tid)
            if task is None:
                continue
            changed = True
            if kind == 'log':
                line = f'{datetime.now():%H:%M:%S}  {payload}'
                task['logs'].append(line)
                task['logs'] = task['logs'][-250:]
                log_path = self.data_dir / f'{tid}.log'
                if log_path.exists() and log_path.stat().st_size > 512_000:
                    log_path.write_text('\n'.join(task['logs'][-200:])+'\n', encoding='utf-8')
                with log_path.open('a', encoding='utf-8') as f:
                    f.write(line + '\n')
            else:
                allowed = {'state', 'status', 'detail', 'title', 'current', 'total', 'fraction', 'output_path', 'current_url', 'request_url', 'current_part', 'failure_url', 'failure_request_url', 'failure_part', 'wait_remaining', 'wait_reason', 'chapter_title', 'parts_total'}
                task.update({k: v for k, v in payload.items() if k in allowed})
                if kind == 'end':
                    summary = f"[{LABELS[task['state']].upper()}] {task.get('status', '')}"
                    task['logs'].append(f'{datetime.now():%H:%M:%S}  {summary}')
                    with (self.data_dir / f'{tid}.log').open('a', encoding='utf-8') as f:
                        f.write(f'{datetime.now():%Y-%m-%d %H:%M:%S}  {summary}\n')
                    if task['state'] == 'failed':
                        from core.storage import atomic_text
                        atomic_text(self.data_dir / f'{tid}.last-error.txt',
                                    f"Link chương bị lỗi: {task.get('failure_url', '')}\n"
                                    f"Phần (đếm từ 1): {task.get('failure_part') + 1 if task.get('failure_part') is not None else ''}\n"
                                    f"Yêu cầu: {task.get('failure_request_url', '')}\nLỗi: {task.get('detail', '')}\n"
                                    f"Link gốc: {task['url']}\nThư mục: {task['folder']}\n")
                    task['wait_remaining'] = 0
                    if task['state'] == 'completed':
                        # Commit completion before deleting its resume checkpoint.
                        self.save()
                        try:
                            from core.lifecycle import clean_task
                            clean_task(task, self.data_dir)
                            task['status'] = 'Hoàn tất · đã dọn dữ liệu tạm'
                        except Exception as exc:
                            task['cleanup_error'] = str(exc)
                            task['status'] = 'Đã tải xong · cần dọn dữ liệu tạm'
                    self.active_id = None
                    self.notice = (task['status'] + (': ' + task['detail'] if task.get('detail') else ''), task['state'] in {'failed', 'needs_review'})
            if kind == 'end' and task['state'] in {'failed', 'needs_review'}:
                # Do not keep hammering a blocked host via the next queued task.
                self.auto_run = False
        if changed:
            self.save()
        self.start_next()
        return changed

    def pause(self):
        task = self.get(self.active_id)
        if not task or task['state'] not in {'running', 'paused'}:
            return
        plugin = self.plugins.plugin_map.get(task['plugin'])
        if not getattr(plugin, 'supports_pause', True):
            raise ValueError('Plugin FanFicFare chưa hỗ trợ tạm dừng. Bạn có thể dừng tác vụ rồi chạy lại.')
        if self.pause_event.is_set():
            self.pause_event.clear()
            task['state'] = 'running'
        else:
            self.pause_event.set()
            task['state'] = 'paused'
        self.events.put((task['id'], 'log', '[TẠM DỪNG]' if self.pause_event.is_set() else '[TIẾP TỤC] Đã tiếp tục tác vụ.'))
        self.save()

    def stop(self):
        self.auto_run = False
        if self.active_id:
            self.stop_event.set()
            self.events.put((self.active_id, 'log', '[DỪNG] Người dùng yêu cầu dừng; giữ tiến độ đã lưu.'))
            self.get(self.active_id)['state'] = 'stopping'
            self.save()

    def retry(self, tid):
        task = self.get(tid)
        if task and task['state'] not in ACTIVE | {'queued', 'completed'}:
            task.update(state='queued', status='Chờ tiếp tục từ tiến độ đã lưu', detail='', fraction=0)
            self.tasks.remove(task)
            self.tasks.insert(0, task)
            self.save()

    def remove(self, tid):
        task = self.get(tid)
        if task and task['state'] not in ACTIVE:
            self.tasks.remove(task)
            self.save()

    def hold(self, tid):
        task=self.get(tid)
        if task and task['state'] in {'queued','held'}:
            task['state']='held' if task['state']=='queued' else 'queued'
            self.save()

    def move(self, tid, delta):
        task=self.get(tid)
        if not task or task['state'] in ACTIVE: return
        pos=self.tasks.index(task);new=max(0,min(len(self.tasks)-1,pos+delta))
        self.tasks.insert(new,self.tasks.pop(pos));self.save()

    def clear_completed(self):
        from core.lifecycle import clean_task
        completed=[t for t in self.tasks if t['state']=='completed' and t['id']!=self.active_id]
        failures=[];removed=[]
        for task in completed:
            try:clean_task(task,self.data_dir);removed.append(task['id'])
            except Exception as exc:task['cleanup_error']=str(exc);failures.append(str(exc))
        self.tasks=[t for t in self.tasks if t['id'] not in removed]
        # No archive: the user requested real deletion, not hiding records.
        self.save()
        if failures:raise ValueError('Một số truyện chưa dọn được: '+'; '.join(failures))
        return len(removed)
