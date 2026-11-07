"""Visible, persistent browser. Verification is performed by the user only."""
import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from plugins.base import challenge_page, retry_after, VerificationRequired
from core.network import NetworkFailure
from core.wikicv_content import clean_content


class BrowserSession:
    def __init__(self, crawler, connection_mode=None):
        self.crawler = crawler
        self.connection_mode = connection_mode or crawler.options.get('connection_mode', 'browser')
        self.context = self.page = self.playwright = None
        self.network_failed = False
        self.part_retry_after = None
        self.chapter_url = ''

    async def __aenter__(self):
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise RuntimeError('Chưa cài bộ tải phần JavaScript. Chạy CapNhat.bat trong gói cập nhật hoặc CaiTrinhDuyet_TuyChon.bat rồi bấm Tiếp tục tải.') from exc
        local_browser = Path(__file__).resolve().parents[1]/'.browsers'
        if local_browser.is_dir(): os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(local_browser)
        self.playwright = await async_playwright().start()
        try:
            await self._launch()
        except Exception:
            await self.playwright.stop()
            raise RuntimeError('Không mở được Chromium. Chạy CaiTrinhDuyet_TuyChon.bat; đóng phiên trình duyệt tải cũ nếu còn mở.')
        return self

    async def _launch(self):
        profile = Path(self.crawler.options.get('data_dir') or Path(__file__).resolve().parents[1] / '.nd-data') / 'browser-profile'
        launch = dict(headless=self.connection_mode == 'background',
                      viewport={'width': 1150, 'height': 800})
        if self.crawler.network.proxy:
            launch['proxy'] = {'server': self.crawler.network.proxy}
        self.context = await self.playwright.chromium.launch_persistent_context(str(profile), **launch)
        self.page = await self.context.new_page()

        def from_chapter(request):
            return (request.resource_type in {'xhr', 'fetch'}
                    and urlsplit(request.url).hostname == urlsplit(self.chapter_url).hostname)

        def failed(request):
            if from_chapter(request):
                self.network_failed = True

        def response_received(response):
            if response.status == 403 and from_chapter(response.request):
                self.network_failed = True
                self.part_retry_after = response.headers.get('retry-after')

        self.page.on('requestfailed', failed)
        self.page.on('response', response_received)

    async def _reconnect(self, reason):
        if not await self.crawler.network.reconnect(reason): return False
        await self.context.close()
        await self.crawler.checkpoint()
        await self._launch()
        return True

    async def __aexit__(self, *args):
        try:
            if self.context:
                await self.context.close()
        finally:
            if self.playwright:
                await self.playwright.stop()

    async def verify(self, url):
        if self.connection_mode == 'background':
            raise VerificationRequired(f'Cần xác minh: {url}. Đã dừng, không tự mở cửa sổ. Chọn chế độ Trình duyệt hiện cửa sổ nếu muốn xác minh thủ công.')
        signal = self.crawler.options.get('verification_event')
        if signal is None:
            raise VerificationRequired(f'Cần xác minh trên trình duyệt: {url}')
        signal.clear()
        self.crawler.report_progress(state='waiting_verification', status='Cần xác minh trong cửa sổ Chromium',
                                     detail='Hoàn thành xác minh rồi bấm “Đã xác minh” trong ứng dụng.')
        while not signal.is_set():
            await self.crawler.checkpoint()
            await asyncio.sleep(.2)
        self.crawler.report_progress(state='running', status='Đang kiểm tra lại phiên truy cập')

    async def get(self, url, required=None):
        self.chapter_url = url
        for attempt in range(4):
            await self.crawler.throttle()
            self.crawler.log_request(url, attempt + 1)
            try:
                response = await self.page.goto(url, wait_until='domcontentloaded', timeout=45000)
            except Exception as exc:
                if attempt == 3:
                    raise NetworkFailure(f'Không mở được trang sau 4 lần: {url}. Chi tiết Chromium: {exc}') from exc
                await self._reconnect('Lỗi kết nối trình duyệt')
                self.crawler.log(f'Kết nối trình duyệt bị ngắt; thử lại lần {attempt + 2}/4. Chi tiết: {exc}')
                await self.crawler.sleep_check_stop(5 * 2**attempt)
                continue
            status = response.status if response else 200
            self.crawler.log(f'[HTTP {status}] {url}')
            html = await self.page.content()
            if status == 429 or status in (500, 502, 503, 504) and not challenge_page(html):
                delay = retry_after(response.headers.get('retry-after'), 10 * 2**attempt)
                self.crawler.log(f'HTTP {status}; nghỉ {delay:.0f}s trước khi thử lại.')
                await self.crawler.sleep_check_stop(delay)
                continue
            if status == 403 and not challenge_page(html) and attempt < 3 and self.crawler.network.proxy:
                await self.crawler.sleep_check_stop(retry_after(response.headers.get('retry-after') if response else None, 15))
                if await self._reconnect('Nguồn từ chối kết nối hiện tại (403)'):
                    continue
            if status in (401, 403) or challenge_page(html):
                await self.verify(url)
                html = await self.page.content()
                if challenge_page(html):
                    continue
                # Reload through the same browser/profile to verify actual access.
                continue
            if status >= 400:
                raise RuntimeError(f'HTTP {status}: {url}')
            if required:
                await self.page.locator(required).first.wait_for(state='attached', timeout=20000)
            return await self.page.content()
        raise RuntimeError('Máy chủ chưa phản hồi sau các lần thử. Tiến độ được giữ lại.')

    async def part(self, part_number):
        chapter_url = self.chapter_url
        for attempt in range(2):
            html, reason = await self._read_part(part_number)
            if html is not None:
                return html
            if self.network_failed:
                await self.crawler.sleep_check_stop(retry_after(self.part_retry_after, 15))
            if attempt == 0:
                self.crawler.log(f'[THỬ LẠI PHẦN] Phần {part_number + 1}: {reason}. Mở lại trang để tải riêng phần này.')
                await self.get(chapter_url, required='#bookContentBody')

        message = f'Chưa tải được Phần {part_number + 1} sau 2 lượt: {reason}. Đã giữ các phần đã lưu.'
        if self.network_failed:
            raise NetworkFailure(message)
        raise RuntimeError(message)

    async def _read_part(self, part_number):
        await self.crawler.throttle()
        page = self.page
        self.network_failed = False
        self.part_retry_after = None
        selector = f'a.chapter-part[data-pn="{part_number}"]'
        try:
            html = await asyncio.wait_for(page.content(), timeout=5)
        except asyncio.TimeoutError:
            return None, 'Chromium không trả về nội dung'
        soup = BeautifulSoup(html, 'html.parser')
        button = soup.select_one(selector)
        if button is None:
            return None, 'không tìm thấy nút của phần này'
        try:
            before = clean_content(soup)
        except RuntimeError:
            before = None
        chapter_id = button.get('data-id')
        try:
            await asyncio.wait_for(page.locator(selector).first.click(timeout=0), timeout=8)
        except asyncio.TimeoutError:
            return None, 'không bấm được nút tải phần trong 8 giây'

        previous = None
        stable_samples = 0
        reason = 'trang chưa chuyển sang đúng phần'
        for _ in range(36):
            await self.crawler.sleep_check_stop(.5)
            try:
                html = await asyncio.wait_for(page.content(), timeout=5)
            except asyncio.TimeoutError:
                return None, 'Chromium không trả về nội dung'
            soup = BeautifulSoup(html, 'html.parser')
            if soup.select_one('#bookContentBody') is None and challenge_page(html):
                await self.verify(page.url)
                return None, 'cần mở lại trang sau khi xác minh'
            active = soup.select_one('a.chapter-part.active')
            text = None
            if (active and active.get('data-pn') == str(part_number)
                    and active.get('data-id') == chapter_id):
                try:
                    text = clean_content(soup)
                except RuntimeError:
                    reason = 'vùng nội dung đang rỗng'
                if text:
                    loading = ' '.join(text.casefold().split()).strip('.…! ')
                    if text == before or loading in {'loading', 'đang tải', 'đang tải nội dung', 'vui lòng chờ'}:
                        text = None
                        reason = 'trang còn hiện nội dung cũ hoặc thông báo đang tải'
                    else:
                        reason = 'văn bản truyện vẫn đang thay đổi'
            else:
                reason = 'trang chưa chuyển sang đúng phần'
            # Compare the exact text we will save, not markup that can change independently.
            if text is None:
                stable_samples = 0
            elif text == previous:
                stable_samples += 1
            else:
                stable_samples = 1
            if stable_samples >= 3:
                return html, ''
            previous = text

        if self.network_failed:
            reason += ' (có yêu cầu mạng cùng nguồn bị lỗi)'
        return None, reason
