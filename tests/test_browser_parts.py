import asyncio
import hashlib

import pytest
from bs4 import BeautifulSoup

from core.browser import BrowserSession
from core.http_reader import AutoChapterSession
from core.storage import atomic_json
from core.wikicv_content import clean_content
from plugins.wikicv import WikiCVCrawler


URL = 'https://wikicv.org/truyen/test/trang-1742'


class ChapterPage:
    def __init__(self, browser, stalls):
        self.browser = browser
        self.stalls = stalls
        self.number = 0
        self.samples = 0
        self.first = self
        self.url = URL

    def locator(self, selector):
        self.target = int(selector.split('"')[1])
        return self

    async def click(self, *, timeout):
        self.number = self.target
        self.samples = 0
        # An auxiliary fetch can fail without affecting the part content.
        self.browser.network_failed = self.number == 4 and not self.stalls

    async def content(self):
        self.samples += 1
        buttons = ''.join(
            f'<a class="chapter-part {"active" if n == self.number else ""}" href="#!" '
            f'data-id="chapter-1742" data-pn="{n}" data-action="loadChapterPart">Phần {n + 1}</a>'
            for n in range(7)
        )
        story = 'Đang tải…' if self.stalls and self.number == 4 else f'Nội dung phần {self.number + 1}'
        return (f'<h1 class="chapter-name">Trang 1742</h1>{buttons}{buttons}'
                f'<div id="bookContentBody"><p>{story}</p><div class="tpm-unit">Ad {self.samples}</div></div>')


@pytest.mark.parametrize('recover', [True, False])
def test_wikicv_retries_missing_part_without_losing_saved_parts(tmp_path, monkeypatch, recover):
    loads = []

    class BrowserFixture(BrowserSession):
        async def __aenter__(self):
            return self

        async def get(self, url, required=None):
            self.chapter_url = url
            loads.append(url)
            self.page = ChapterPage(self, stalls=len(loads) == 1 or not recover)
            return await self.page.content()

    async def fetch(*args, **kwargs):
        return 200, await ChapterPage(None, stalls=False).content()

    async def no_wait(*args, **kwargs):
        pass

    monkeypatch.setattr(AutoChapterSession, 'browser_factory', BrowserFixture)
    logs = []
    crawler = WikiCVCrawler(logs.append)
    crawler.configure_run(connection_mode='auto')
    crawler.fetch_response = fetch
    crawler.sleep_check_stop = no_wait

    key = hashlib.sha256(URL.encode()).hexdigest()
    story = tmp_path / 'Truyen'
    cache = story / '.parts' / key[:16]
    cache.mkdir(parents=True)
    records = {}
    for n in range(4):
        saved = f'Nội dung phần {n + 1}'
        (cache / f'{n}.txt').write_text(saved, encoding='utf-8')
        records[str(n)] = hashlib.sha256(saved.encode()).hexdigest()
    atomic_json(tmp_path / '.noveldownloader' / f'wikicv-{key[:12]}.json', {
        'url': URL, 'current_url': URL, 'index': 1742, 'done': [],
        'folder': str(story), 'parts': {key[:16]: records},
    })

    if recover:
        assert asyncio.run(crawler.start_download(URL, str(tmp_path)))['completed']
        output = (story / '1742_Trang 1742.txt').read_text(encoding='utf-8')
        assert output.split('\n\n')[1:] == [f'Nội dung phần {n}' for n in range(1, 8)]
    else:
        with pytest.raises(RuntimeError, match='Phần 5 sau 2 lượt'):
            asyncio.run(crawler.start_download(URL, str(tmp_path)))
        assert not list(story.glob('1742_*.txt'))
        assert sorted(p.name for p in cache.iterdir()) == ['0.txt', '1.txt', '2.txt', '3.txt']

    assert loads == [URL, URL]
    assert sum('Đã có:' in line for line in logs) == 4
    assert any('[THỬ LẠI PHẦN] Phần 5:' in line for line in logs)
