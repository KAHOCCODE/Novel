"""Declarative source adapter: extend sources without changing the application."""
import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse, urljoin, urldefrag
import aiohttp
from bs4 import BeautifulSoup
from plugins.base import BaseCrawler
from core.storage import atomic_json, atomic_text, read_json
import utils

PROFILE_PATH = Path(__file__).resolve().parent / 'sources.json'


class ConfigurableCrawler(BaseCrawler):
    display_name = 'Nguồn tự cấu hình (CSS)'
    priority = 5

    def __init__(self, log_callback):
        super().__init__(log_callback)
        self.profiles = read_json(PROFILE_PATH, [])
        for p in self.profiles:
            if not all(p.get(k) for k in ('name', 'domains', 'content', 'next', 'chapter_title')):
                raise ValueError('sources.json thiếu name/domains/content/next/chapter_title')
            if not isinstance(p['domains'], list):
                raise ValueError('domains phải là danh sách tên miền.')

    def profile(self, url):
        host = (urlparse(url).hostname or '').lower()
        return next((p for p in self.profiles if host in p['domains']), None)

    def can_handle(self, url):
        return self.profile(url) is not None

    def get_supported_sources(self):
        return [{'name': p['name'], 'domain': ', '.join(p['domains']), 'provider': 'Cấu hình riêng · cần kiểm tra'} for p in self.profiles]

    async def start_download(self, url, save_folder):
        p = self.profile(url)
        key = hashlib.sha256(url.encode()).hexdigest()[:12]
        folder = Path(save_folder) / (utils.safe_filename(p['name']) + '_' + key)
        folder.mkdir(parents=True, exist_ok=True)
        state_path = folder / 'resume.json'
        state = read_json(state_path, {'url': url, 'index': 1, 'seen': []})
        if state['url'] is None:
            return {'completed': True, 'output_path': str(folder)}
        async with aiohttp.ClientSession() as session:
            while state['url']:
                await self.checkpoint()
                current = state['url']
                if current in state['seen']:
                    raise RuntimeError('Vòng lặp chương; kiểm tra selector next của nguồn.')
                soup = await self.fetch_soup(session, current)
                body = soup.select_one(p['content'])
                heading = soup.select_one(p['chapter_title'])
                if not body or not heading:
                    raise RuntimeError('Không tìm thấy nội dung/tiêu đề. Kiểm tra cấu hình CSS và link chương.')
                if soup.select('a.chapter-part'):
                    raise RuntimeError('Nguồn có nhiều phần động; cần plugin riêng để tránh thiếu nội dung.')
                for garbage in body.select(p.get('remove', 'script, style, iframe, button, form')):
                    garbage.decompose()
                for br in body.find_all('br'):
                    br.replace_with('\n')
                text = body.get_text('\n\n', strip=True)
                title = heading.get_text(' ', strip=True)
                if not text:
                    raise RuntimeError('Nội dung rỗng; chưa lưu chương.')
                nxt = soup.select_one(p['next'])
                href = (nxt.get('href') or '').strip() if nxt else ''
                next_url = urldefrag(urljoin(current, href))[0] if href and not href.startswith(('#', 'javascript:')) else None
                if next_url and self.profile(next_url) != p:
                    raise RuntimeError('Link chương sau nằm ngoài các tên miền đã cấu hình.')
                target = folder / f'{state["index"]:04d}_{utils.safe_filename(title)[:130]}.txt'
                atomic_text(target, title + '\n\n' + text)
                state['seen'].append(current)
                state.update(url=next_url, index=state['index'] + 1)
                atomic_json(state_path, state)
                self.report_progress(current=state['index'] - 1, status=title, output_path=str(folder))
                self.log('Đã lưu: ' + target.name)
        return {'completed': True, 'output_path': str(folder), 'current': state['index'] - 1}
