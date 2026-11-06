"""Visible, persistent browser. Verification is performed by the user only."""
import asyncio
import os
from pathlib import Path
from plugins.base import challenge_page, VerificationRequired
from core.network import NetworkFailure


class BrowserSession:
    def __init__(self, crawler, connection_mode=None):
        self.crawler = crawler
        self.connection_mode = connection_mode or crawler.options.get('connection_mode', 'browser')
        self.context = self.page = self.playwright = None
        self.network_failed = False
        self.part_retry_after = None

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
        def failed(request):
            if request.resource_type in {'document', 'xhr', 'fetch'}:
                self.network_failed = True
        self.page.on('requestfailed', failed)
        def response_received(response):
            if response.status == 403 and response.request.resource_type in {'xhr', 'fetch'}:
                self.network_failed = True
                self.part_retry_after = response.headers.get('retry-after')
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
                from plugins.base import retry_after
                delay = retry_after(response.headers.get('retry-after'), 10 * 2**attempt)
                self.crawler.log(f'HTTP {status}; nghỉ {delay:.0f}s trước khi thử lại.')
                await self.crawler.sleep_check_stop(delay)
                continue
            if status == 403 and not challenge_page(html) and attempt < 3 and self.crawler.network.proxy:
                from plugins.base import retry_after
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
        await self.crawler.throttle()
        page = self.page
        self.network_failed = False
        self.part_retry_after = None
        selector = f'a.chapter-part[data-pn="{part_number}"]'
        before = await page.locator('#bookContentBody').inner_html()
        await page.locator(selector).first.click()
        try:
            await page.wait_for_function('''({pn, before}) => {
                const body = document.querySelector('#bookContentBody');
                const active = document.querySelector('a.chapter-part.active');
                return body && active && active.dataset.pn === String(pn) && body.innerHTML !== before;
            }''', arg={'pn': part_number, 'before': before}, timeout=30000)
        except Exception as exc:
            if challenge_page(await page.content()):
                await self.verify(page.url)
            if self.network_failed:
                from plugins.base import retry_after
                await self.crawler.sleep_check_stop(retry_after(self.part_retry_after, 15))
                raise NetworkFailure(f'Mất kết nối khi tải Phần {part_number + 1}; sẽ khôi phục từ phần đã lưu.') from exc
            raise RuntimeError(f'Chưa xác nhận được nội dung Phần {part_number + 1}. Đã giữ tiến độ, hãy thử lại.') from exc
        # Let the final DOM update settle; never accept a loading placeholder.
        previous = await page.locator('#bookContentBody').inner_html()
        for _ in range(12):
            await self.crawler.sleep_check_stop(.5)
            current = await page.locator('#bookContentBody').inner_html()
            text = (await page.locator('#bookContentBody').inner_text()).strip()
            loading = text.casefold().strip('.…! ') in {'loading', 'đang tải', 'đang tải nội dung', 'vui lòng chờ'}
            if current == previous and current != before and text and not loading and not self.network_failed:
                return await page.content()
            previous = current
        raise RuntimeError(f'Nội dung Phần {part_number + 1} chưa ổn định; hãy thử lại.')
