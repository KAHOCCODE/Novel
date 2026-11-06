"""HTTP-only reader; never starts a browser or guesses a dynamic endpoint."""
from urllib.parse import urljoin, urlparse
import aiohttp
from bs4 import BeautifulSoup


class HttpChapterSession:
    def __init__(self, crawler):
        self.crawler = crawler
        self.session = None
        self.url = ''
        self.html = ''

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(), trust_env=True)
        self.crawler.log('[CHẾ ĐỘ HTTP] Tải trực tiếp, không khởi chạy Chrome/Chromium.')
        return self

    async def __aexit__(self, *args):
        await self.session.close()

    async def get(self, url, required=None):
        self.url = url
        _, self.html = await self.crawler.fetch_response(self.session, url, track=False)
        return self.html

    async def part(self, part_number):
        soup = BeautifulSoup(self.html, 'html.parser')
        node = soup.select_one(f'a.chapter-part[data-pn="{part_number}"]')
        href = (node.get('data-url') or node.get('href') or '').strip() if node else ''
        if not href or href.startswith(('#', 'javascript:')):
            raise RuntimeError(
                f'Phần {part_number + 1} được tải bằng JavaScript, trang không cung cấp link HTTP trực tiếp. '
                'Đã giữ phần trước và link lỗi. Chọn “Chromium chạy nền” trong Tùy chọn rồi bấm Tiếp tục tải; '
                'chế độ đó không mở cửa sổ Chrome. Không đánh dấu chương thiếu phần là hoàn tất.')
        target = urljoin(self.url, href)
        if urlparse(target).hostname != urlparse(self.url).hostname or urlparse(target).scheme not in {'http', 'https'}:
            raise RuntimeError('Link phần nằm ngoài nguồn đang tải; chưa lưu chương.')
        _, html = await self.crawler.fetch_response(self.session, target, track=False)
        part = BeautifulSoup(html, 'html.parser')
        if part.select_one('#bookContentBody') is None:
            raise RuntimeError(f'Không có vùng nội dung ở Phần {part_number + 1}: {target}')
        active = part.select_one('a.chapter-part.active')
        if active is None or active.get('data-pn') != str(part_number):
            raise RuntimeError(f'Chưa xác nhận đúng Phần {part_number + 1}: {target}')
        self.html = html
        return html


class AutoChapterSession(HttpChapterSession):
    """HTTP first, reuse a headless browser only for JavaScript chapter parts."""
    browser_factory = None

    def __init__(self, crawler):
        super().__init__(crawler)
        self.browser = None

    async def __aexit__(self, *args):
        try:
            if self.browser is not None:
                await self.browser.__aexit__(*args)
        finally:
            await super().__aexit__(*args)

    async def get(self, url, required=None):
        if self.browser is None:
            return await super().get(url, required)
        self.url = url
        self.html = await self.browser.get(url, required=required)
        return self.html

    async def part(self, part_number):
        if self.browser is None:
            soup = BeautifulSoup(self.html, 'html.parser')
            node = soup.select_one(f'a.chapter-part[data-pn="{part_number}"]')
            href = (node.get('data-url') or node.get('href') or '').strip() if node else ''
            if href and not href.startswith(('#', 'javascript:')):
                return await super().part(part_number)
            if node is None or node.get('data-action') != 'loadChapterPart':
                raise RuntimeError(f'Không tìm thấy nút tải Phần {part_number + 1}. Giữ nguyên tiến độ.')
            from core.browser import BrowserSession
            factory = self.browser_factory or BrowserSession
            candidate = factory(self.crawler, connection_mode='background')
            self.crawler.log('[TỰ ĐỘNG] Trang chia phần dùng JavaScript; chuyển sang Chromium chạy nền, không mở cửa sổ.')
            try:
                await candidate.__aenter__()
                self.browser = candidate
                await candidate.get(self.url, required='#bookContentBody')
            except BaseException:
                # __aenter__ owns cleanup on launch failure; a loaded candidate is ours.
                if self.browser is not None:
                    await candidate.__aexit__(None, None, None)
                    self.browser = None
                raise
        self.html = await self.browser.part(part_number)
        soup = BeautifulSoup(self.html, 'html.parser')
        active = soup.select_one('a.chapter-part.active')
        if not active or active.get('data-pn') != str(part_number) or not soup.select_one('#bookContentBody'):
            raise RuntimeError(f'Chưa xác nhận đúng nội dung Phần {part_number + 1}; giữ nguyên tiến độ.')
        return self.html
