import asyncio
import threading
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from core.tasks import TaskManager
from core.http_reader import HttpChapterSession
from plugins.wikicv import WikiCVCrawler
from plugins.base import BaseCrawler, VerificationRequired
from core.browser import BrowserSession
from test_workflows import Registry, Legacy, URL, page, FakeBrowser, crawler


def test_failure_preserves_exact_chapter_part_and_request(tmp_path):
    failed = URL + '/later-chapter'
    class NetworkError(Legacy):
        async def start_download(self, *args):
            self.track_url(failed, 1)
            self.request_url = failed + '?part=1'
            self.log('[THỬ LẠI] mất mạng')
            raise RuntimeError('connection reset')
    m = TaskManager(tmp_path/'data', Registry(NetworkError))
    t = m.add(URL, str(tmp_path/'out'))
    m.auto_run = True; m.start_next(); m.worker.join(3); m.drain()
    assert t['failure_url'] == failed
    assert t['failure_part'] == 1
    assert t['failure_request_url'] == failed + '?part=1'
    text=(tmp_path/'data'/f'{t["id"]}.log').read_text()
    assert '[LINK LỖI CUỐI]' in text and failed in text and 'Phần 2' in text
    assert (tmp_path/'data'/f'{t["id"]}.last-error.txt').is_file()
    restored=TaskManager(tmp_path/'data', Registry(NetworkError))
    assert restored.tasks[0]['failure_url'] == failed
    # A retry is prioritized ahead of already queued tasks; seed URL never changes.
    restored.add(URL+'/other',str(tmp_path/'out'))
    restored.retry(t['id'])
    assert restored.tasks[0]['id'] == t['id'] and restored.tasks[0]['url'] == URL


def test_http_only_does_not_open_browser(tmp_path, monkeypatch):
    def no_browser(*args, **kw): raise AssertionError('Browser must never launch in HTTP mode')
    monkeypatch.setattr(BrowserSession, '__init__', no_browser)
    c=WikiCVCrawler(lambda _: None);c.configure_run(connection_mode='http')
    single=page().replace('class="chapter-part ', 'class="ignored ')
    async def fake_fetch(session,url,**kw): return 200,single
    c.fetch_response=fake_fetch
    assert asyncio.run(c.start_download(URL,str(tmp_path)))['completed']


def test_http_dynamic_parts_fail_without_incomplete_output(tmp_path):
    c=WikiCVCrawler(lambda _: None);c.configure_run(connection_mode='http')
    async def fake_fetch(session,url,**kw): return 200,page()
    c.fetch_response=fake_fetch
    with pytest.raises(RuntimeError,match='JavaScript'):
        asyncio.run(c.start_download(URL,str(tmp_path)))
    assert not list(tmp_path.glob('*/0001_*.txt'))
    assert c.current_url == URL and c.current_part == 1
    assert list(tmp_path.glob('*/.parts/*/0.txt'))
    # Switching transport keeps the exact same checkpoint/cache identity.
    c.browser_factory=FakeBrowser;FakeBrowser.fail=False
    c.configure_run(connection_mode='background')
    assert asyncio.run(c.start_download(URL,str(tmp_path)))['completed']


def test_background_verification_never_opens_window():
    c=BaseCrawler(lambda _:None);c.configure_run(connection_mode='background')
    with pytest.raises(VerificationRequired,match='không tự mở cửa sổ'):
        asyncio.run(BrowserSession(c).verify(URL))


def test_http_linked_part_requires_matching_active_number():
    c=BaseCrawler(lambda _:None)
    async def fake_fetch(*args,**kw): return 200,page(0)
    c.fetch_response=fake_fetch
    reader=HttpChapterSession(c);reader.url=URL
    reader.html=page().replace('data-pn="1"','data-pn="1" data-url="/part2"')
    with pytest.raises(RuntimeError,match='Chưa xác nhận'):
        asyncio.run(reader.part(1))
