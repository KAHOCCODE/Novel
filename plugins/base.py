import asyncio
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import aiohttp
from bs4 import BeautifulSoup
from core.network import NetworkPolicy, NetworkFailure


class VerificationRequired(RuntimeError):
    pass


class DownloadStopped(asyncio.CancelledError):
    pass


def retry_after(value, default):
    try:
        return max(0, float(value))
    except (ValueError, TypeError):
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return default


def challenge_page(html):
    soup = BeautifulSoup(html or '', 'html.parser')
    if soup.select_one('#bookContentBody, #chapter-c, article.article-content'):
        return False
    title = soup.title.get_text(' ', strip=True).lower() if soup.title else ''
    return bool(soup.select_one('#challenge-form, #cf-challenge-running, .g-recaptcha, .h-captcha')) or any(
        s in title for s in ('just a moment', 'attention required', 'verify you are human', 'security verification'))


class BaseCrawler:
    display_name = None
    priority = 100
    supports_exact_progress = False
    supports_pause = True

    def __init__(self, log_callback):
        self.log = log_callback
        self.stop_event = None
        self.pause_event = None
        self.progress_callback = None
        self.options = {}
        self.request_interval = 2.0
        self._last_request = 0
        self.current_url = ''
        self.request_url = ''
        self.current_part = None
        self.network = NetworkPolicy(log=self.log, progress=self.report_progress)
        self.headers = {'User-Agent': 'NovelDownloader/5.0 (personal reading client)'}

    def can_handle(self, url):
        return False

    def get_display_name(self):
        return self.display_name or self.__class__.__name__

    def get_supported_sources(self):
        return [{'name': self.get_display_name(), 'domain': 'Plugin chuyên biệt', 'provider': 'Plugin gốc'}]

    def configure_run(self, **options):
        self.options = options
        self.network = NetworkPolicy(options.get('network_mode', 'direct'), options.get('warp_port', 40000), self.log, self.report_progress)
        async def proxy_sleep(seconds):
            self._wait_reason = 'Chờ proxy'
            return await self.sleep_check_stop(seconds)
        self.network.sleep = proxy_sleep
        self.network.checkpoint = self.checkpoint
        self.progress_callback = options.get('progress_callback')
        self.pause_event = options.get('pause_event')
        self.request_interval = max(1.0, float(options.get('request_interval', 2)))

    def report_progress(self, **payload):
        if self.progress_callback:
            self.progress_callback(payload)

    def track_url(self, url, part=None):
        self.current_url = url
        self.current_part = part
        self.report_progress(current_url=url, current_part=part)

    def log_request(self, url, attempt=1):
        self.request_url = url
        self.report_progress(request_url=url)
        self.log(f'[KẾT NỐI] Lần {attempt}/4 · {url}')

    def should_stop(self):
        return self.stop_event is not None and self.stop_event.is_set()

    async def checkpoint(self):
        if self.should_stop():
            raise DownloadStopped()
        while self.pause_event is not None and self.pause_event.is_set():
            if self.should_stop():
                raise DownloadStopped()
            await asyncio.sleep(.15)

    async def sleep_check_stop(self, seconds, step=.2):
        remaining = max(0, seconds)
        last = None
        try:
            while remaining > 0:
                await self.checkpoint()
                shown = int(remaining + .999)
                if shown != last:
                    self.report_progress(wait_remaining=shown, wait_reason=getattr(self, '_wait_reason', 'Chờ thử lại'))
                    last = shown
                begin = time.monotonic()
                await asyncio.sleep(min(step, remaining))
                remaining -= time.monotonic() - begin
            await self.checkpoint()
        finally:
            self.report_progress(wait_remaining=0, wait_reason='')
        return False

    async def throttle(self):
        await self.checkpoint()
        delay = max(0, self.request_interval - (time.monotonic() - self._last_request))
        if delay > .2:
            self.log(f'[NGHỈ] {delay:.1f}s trước lượt tải tiếp theo.')
        self._wait_reason = 'Giãn cách tải'
        await self.sleep_check_stop(delay)
        self._last_request = time.monotonic()

    async def fetch_response(self, session, url, timeout=30, allow_redirects=True, track=True):
        if track:
            self.track_url(url)
        if getattr(self, "browser", None) is not None:
            return 200, await self.browser.get(url)
        last_error = None
        for attempt in range(4):
            await self.throttle()
            self.log_request(url, attempt + 1)
            try:
                async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=timeout),
                                       allow_redirects=allow_redirects, proxy=self.network.proxy) as response:
                    html = await response.text(errors='replace')
                    status = response.status
                    self.log(f'[HTTP {status}] {url}')
                    if status == 403 and not challenge_page(html) and attempt < 3 and self.network.proxy:
                        self._wait_reason = 'Nguồn từ chối · chờ proxy'
                        await self.sleep_check_stop(retry_after(response.headers.get('Retry-After'), 15))
                        if await self.network.reconnect('Nguồn từ chối kết nối hiện tại (403)'):
                            continue
                    if status in (401, 403) or challenge_page(html):
                        raise VerificationRequired(f'Nguồn yêu cầu xác minh hoặc từ chối truy cập ({status}): {url}')
                    if status == 429 or status in (500, 502, 503, 504):
                        delay = retry_after(response.headers.get('Retry-After'), min(60, 5 * 2**attempt))
                        last_error = RuntimeError(f'HTTP {status}: {url}')
                    elif status != 200:
                        raise RuntimeError(f'HTTP {status}: {url}')
                    else:
                        return status, html
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                delay = min(60, 5 * 2**attempt)
                if attempt < 3:
                    await self.network.reconnect(f'Lỗi kết nối: {type(exc).__name__}')
            if attempt < 3:
                self.log(f'[THỬ LẠI] {last_error} · nghỉ {delay:.0f}s · lần {attempt + 2}/4 · {url}')
                self._wait_reason = f'Thử lại {attempt + 2}/4'
                await self.sleep_check_stop(delay)
        error_type = NetworkFailure if isinstance(last_error, (aiohttp.ClientError, asyncio.TimeoutError)) else RuntimeError
        raise error_type(f'Không tải được sau 4 lần thử: {url}. {last_error}')

    async def fetch_soup(self, session, url, timeout=30, allow_redirects=True):
        _, html = await self.fetch_response(session, url, timeout, allow_redirects)
        return BeautifulSoup(html, 'html.parser')

    async def start_download(self, url, save_folder):
        raise NotImplementedError
