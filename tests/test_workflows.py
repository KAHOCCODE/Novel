import asyncio
import json
import threading
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from bs4 import BeautifulSoup
from plugins.base import BaseCrawler, DownloadStopped, VerificationRequired, retry_after, challenge_page
from plugins.wikicv import WikiCVCrawler, clean_content, part_numbers
from core.tasks import TaskManager
from core.plugin_manager import PluginManager
from core.storage import read_json

URL = 'https://wikicv.org/truyen/book/chapter-1'

def page(pn=0, next_url=None, text=None):
    return f'''<div id="bookContent"><p class="book-title">Truyện thử</p><p class="book-title">Tác giả: A</p></div>
    <a class="chapter-name">Chương 1</a>
    <a class="chapter-part {'active' if pn == 0 else ''}" data-pn="0">Phần 1</a>
    <a class="chapter-part {'active' if pn == 1 else ''}" data-pn="1">Phần 2</a>
    <div id="bookContentBody"><p>{text or ('Nội dung đầu.' if pn == 0 else 'Nội dung cuối.')}</p></div>
    {f'<a id="btnNextChapter" href="{next_url}">Sau</a>' if next_url else ''}'''

class FakeBrowser:
    fail = False
    calls = []
    def __init__(self, crawler):
        self.crawler = crawler
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    async def get(self, url):
        return page()
    async def part(self, pn):
        type(self).calls.append(pn)
        if self.fail:
            raise RuntimeError('Ngắt mạng phần 2')
        return page(pn)


def crawler(tmp_path):
    c = WikiCVCrawler(lambda x: None)
    c.browser_factory = FakeBrowser
    c.configure_run(data_dir=str(tmp_path))
    return c


def test_multipart_atomic_resume(tmp_path):
    FakeBrowser.calls = []
    FakeBrowser.fail = True
    with pytest.raises(RuntimeError, match='phần 2'):
        asyncio.run(crawler(tmp_path).start_download(URL, str(tmp_path)))
    assert not list(tmp_path.glob('*/0001_*.txt')), 'Must not commit partial chapter'
    cached = next(tmp_path.glob('*/.parts/*/0.txt'))
    logs = []
    FakeBrowser.fail = False
    resumed = crawler(tmp_path)
    resumed.log = logs.append
    result = asyncio.run(resumed.start_download(URL, str(tmp_path)))
    assert result['completed'] is True
    output = next(tmp_path.glob('*/0001_*.txt')).read_text()
    assert output.index('Nội dung đầu.') < output.index('Nội dung cuối.')
    assert output.count('Nội dung đầu.') == 1
    assert any('Đã có:' in line and 'Phần 1' in line for line in logs)
    assert not cached.exists(), 'Cache removed only after complete output exists'
    assert len(list(tmp_path.glob('*/0001_*.txt'))) == 1
    assert asyncio.run(crawler(tmp_path).start_download(URL, str(tmp_path)))['completed']


def test_corrupt_cache_is_refetched(tmp_path):
    FakeBrowser.fail = True
    with pytest.raises(RuntimeError):
        asyncio.run(crawler(tmp_path).start_download(URL, str(tmp_path)))
    next(tmp_path.glob('*/.parts/*/0.txt')).write_text('corrupt')
    FakeBrowser.fail = False
    asyncio.run(crawler(tmp_path).start_download(URL, str(tmp_path)))
    assert 'corrupt' not in next(tmp_path.glob('*/0001_*.txt')).read_text()


def test_no_next_loop_silently_completes(tmp_path):
    class Loop(FakeBrowser):
        async def get(self, url): return page(next_url=URL)
    c = crawler(tmp_path)
    c.browser_factory = Loop
    with pytest.raises(RuntimeError, match='vòng lặp'):
        asyncio.run(c.start_download(URL, str(tmp_path)))


def test_parts_order_and_gap():
    assert part_numbers(BeautifulSoup('<a class="chapter-part" data-pn="1"></a><a class="chapter-part" data-pn="0"></a><a class="chapter-part" data-pn="1"></a>', 'html.parser')) == [0, 1]
    with pytest.raises(RuntimeError):
        part_numbers(BeautifulSoup('<a class="chapter-part" data-pn="2"></a>', 'html.parser'))


def test_clean_preserves_inline_and_unwrapped_text():
    soup = BeautifulSoup('<div id="bookContentBody">Mở đầu<p>Xin <b>chào</b> bạn.<br>Dòng mới.</p>Kết thúc<script>quảng cáo</script></div>', 'html.parser')
    text = clean_content(soup)
    assert 'Xin chào bạn.' in text and 'Kết thúc' in text and 'Mở đầu' in text
    assert 'quảng cáo' not in text


def test_challenge_not_story_text():
    assert challenge_page('<title>Just a moment...</title>')
    assert not challenge_page('<div id="bookContentBody"><p>captcha là một từ.</p></div>')


def test_pause_then_stop():
    c = BaseCrawler(lambda x: None)
    c.stop_event = threading.Event()
    c.configure_run(pause_event=threading.Event())
    c.pause_event.set()
    async def run():
        task = asyncio.create_task(c.checkpoint())
        await asyncio.sleep(.02)
        assert not task.done()
        c.stop_event.set()
        with pytest.raises(DownloadStopped): await task
    asyncio.run(run())

class Response:
    def __init__(self, status, html='OK', headers=None):
        self.status, self.html, self.headers = status, html, headers or {}
    async def text(self, **kw): return self.html
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass

class Session:
    def __init__(self, responses): self.responses = iter(responses); self.count = 0
    def get(self, *args, **kw): self.count += 1; return next(self.responses)


def test_retry_after_and_bounded_retries():
    c = BaseCrawler(lambda x: None)
    waits = []
    async def no_throttle(): pass
    async def sleep(delay): waits.append(delay)
    c.throttle, c.sleep_check_stop = no_throttle, sleep
    session = Session([Response(429, headers={'Retry-After': '11'}), Response(200)])
    assert asyncio.run(c.fetch_response(session, URL)) == (200, 'OK')
    assert waits == [11]
    session = Session([Response(503)] * 4)
    with pytest.raises(RuntimeError, match='4 lần'): asyncio.run(c.fetch_response(session, URL))
    assert session.count == 4
    assert retry_after('bad', 5) == 5


def test_block_does_not_retry():
    c = BaseCrawler(lambda x: None)
    session = Session([Response(403)])
    with pytest.raises(VerificationRequired): asyncio.run(c.fetch_response(session, URL))
    assert session.count == 1


def test_domain_routing_and_catalog():
    logs = []
    pm = PluginManager(logs.append)
    assert not [x for x in logs if 'Không thể nạp' in x]
    assert type(pm.find_handler('https://truyenfull.vision/book/')).__name__ == 'TruyenFullVisionCrawler'
    assert type(pm.find_handler(URL)).__name__ == 'WikiCVCrawler'
    assert pm.find_handler('https://evil.example/?url=https://wikicv.org') is None
    assert pm.source_count() > 20

class Legacy(BaseCrawler):
    display_name = 'Legacy'
    def can_handle(self, url): return True
    async def start_download(self, *a): return None

class Success(Legacy):
    async def start_download(self, *a): return {'completed': True}

class Failure(Legacy):
    async def start_download(self, *a): raise RuntimeError('network failed')

class Registry:
    def __init__(self, cls): self.plugin_map = {'Legacy': cls(lambda x: None)}
    def find_handler(self, url): return self.plugin_map['Legacy']

@pytest.mark.parametrize('cls,expected', [(Legacy, 'needs_review'), (Success, 'completed'), (Failure, 'failed')])
def test_truthful_completion(tmp_path, cls, expected):
    m = TaskManager(tmp_path/'data', Registry(cls))
    t = m.add(URL, str(tmp_path/'out'))
    m.auto_run = True
    m.start_next()
    m.worker.join(timeout=3)
    m.drain()
    assert t['state'] == expected
    if expected == 'failed': assert not m.auto_run
    loaded = TaskManager(tmp_path/'data', Registry(cls))
    assert loaded.tasks[0]['state'] == expected


def test_restart_and_duplicate_queue(tmp_path):
    m = TaskManager(tmp_path/'data', Registry(Legacy))
    t = m.add(URL, str(tmp_path/'out'))
    with pytest.raises(ValueError, match='đã nằm'): m.add(URL, str(tmp_path/'out'))
    t['state'] = 'running'
    m.save()
    restored = TaskManager(tmp_path/'data', Registry(Legacy))
    assert restored.tasks[0]['state'] == 'stopped'
    restored.retry(t['id'])
    assert restored.tasks[0]['state'] == 'queued'
