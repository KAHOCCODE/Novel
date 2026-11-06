from urllib.parse import urlparse
import os
import re
import sys
import asyncio
import aiofiles
import aiohttp
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import utils  # type: ignore
except Exception:
    import json

    class _UtilsFallback:
        @staticmethod
        def safe_filename(name: str) -> str:
            name = re.sub(r'[\\/:*?"<>|]+', '_', name or '')
            name = re.sub(r'\s+', ' ', name).strip().strip('.')
            return name[:180] or 'untitled'

        @staticmethod
        def save_metadata(folder: str, title: str, **kwargs) -> None:
            meta = {'title': title, **kwargs}
            path = os.path.join(folder, 'metadata.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

    utils = _UtilsFallback()

from plugins.base import BaseCrawler


CHAPTER_RE = re.compile(
    r'^(?:'
    r'第[0-9０-９零〇一二三四五六七八九十百千两]+(?:章|节|卷|回|部|篇|集)[^\n]{0,80}'
    r'|番外[^\n]{0,80}'
    r'|楔子'
    r'|序章'
    r'|尾声'
    r'|后记'
    r'|完结感言'
    r')$'
)

SKIP_LINE_RE = re.compile(
    r'^(?:'
    r'文案：|作品简评：|小说简介：|内容标签：|搜索关键字：|一句话简介：|VIP强推奖章：'
    r'|传送门：|Tips：|目录$|上一页$|下一页$|尾页$|站内求书$|加入收藏$|阅读记录$|52书库App下载$'
    r')'
)

NOISE_CONTAINS = (
    '如果觉得52书库不错',
    '本站内容来源互联网',
    'Top 上一篇',
    '同类穿越重生耽美小说推荐',
    '排行榜单',
    '找书指南',
    '专题推荐',
    'Theme 52shuku.net',
)


class Shuku52Crawler(BaseCrawler):
    display_name = '52shuku.net'

    def get_supported_sources(self):
        return [{"name": self.get_display_name(), "domain": '52shuku.net', "provider": "Plugin gốc · cần kiểm tra kết quả"}]

    site_name = '52ShuKu'

    def can_handle(self, url):
        return (urlparse(url or "").hostname or "").lower().removeprefix("www.") in ['52shuku.net']

    def _normalize_url(self, url: str) -> str:
        return (url or '').split('#', 1)[0].strip()

    def _catalog_url(self, url: str) -> str:
        url = self._normalize_url(url)
        m = re.match(r'^(https?://[^?#]+?)(?:_\d+)?\.html$', url, re.I)
        if not m:
            return url
        return m.group(1) + '.html'

    def _page_number(self, url: str) -> int:
        m = re.search(r'_(\d+)\.html$', url or '', re.I)
        return int(m.group(1)) if m else 1

    def _clean_text(self, text: str) -> str:
        if not text:
            return ''
        text = text.replace('\xa0', ' ').replace('\u3000', ' ')
        text = re.sub(r'\r\n?', '\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _extract_title(self, soup: BeautifulSoup) -> str:
        for p in soup.find_all(['p', 'div', 'span']):
            txt = self._clean_text(p.get_text(' ', strip=True))
            m = re.match(r'^《(.+?)》作者[:：]', txt)
            if m:
                return m.group(1).strip()

        h1 = soup.select_one('h1')
        if h1:
            title = self._clean_text(h1.get_text(' ', strip=True))
            title = re.sub(r'\(\d+\)$', '', title)
            title = re.sub(r'在线阅读.*$', '', title)
            if '_' in title:
                title = title.split('_', 1)[0].strip()
            title = title.strip('《》 ').strip()
            if title:
                return title

        if soup.title and soup.title.string:
            title = self._clean_text(soup.title.string)
            title = re.sub(r'\(\d+\).*$', '', title)
            title = re.sub(r'_.*$', '', title)
            title = title.strip('《》 ').strip()
            if title:
                return title

        return 'Truyen_52ShuKu'

    def _looks_like_catalog(self, soup: BeautifulSoup) -> bool:
        if soup.select_one('article#nr1, article.article-content'):
            return False
        text = soup.get_text(' ', strip=True)
        return '开始阅读' in text or '小说简介' in text

    def _extract_start_url(self, soup: BeautifulSoup, base_url: str) -> str | None:
        candidates = []
        for a in soup.find_all('a', href=True):
            text = self._clean_text(a.get_text(' ', strip=True))
            href = urljoin(base_url, a['href'])
            if not self.can_handle(href):
                continue
            if '开始阅读' in text:
                return href
            if re.fullmatch(r'第\s*\d+\s*页', text):
                page_no = self._page_number(href)
                if page_no > 1:
                    candidates.append((page_no, href))
        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]
        return None

    def _find_article(self, soup: BeautifulSoup):
        return soup.find('article', class_='article-content') or soup.find('article', id='nr1')

    def _next_page_url(self, soup: BeautifulSoup, current_url: str) -> str | None:
        pagination = soup.find('div', class_='pagination2')
        search_root = pagination if pagination else soup

        for a in search_root.find_all('a', href=True):
            text = self._clean_text(a.get_text(' ', strip=True))
            if text in {'下一页', 'Trang tiếp theo', 'Next', '下一章'}:
                href = self._normalize_url(urljoin(current_url, a['href']))
                if href != self._normalize_url(current_url) and self.can_handle(href):
                    return href
        return None

    def _extract_blocks(self, article) -> list[str]:
        if not article:
            return []

        for tag in article.find_all(['script', 'style', 'iframe', 'noscript']):
            tag.decompose()

        for br in article.find_all('br'):
            br.replace_with('\n')
            
        for hr in article.find_all('hr'):
            hr.replace_with('\n---\n')

        raw_text = article.get_text('\n', strip=True)

        blocks: list[str] = []
        for line in raw_text.split('\n'):
            line = self._clean_text(line)
            if not line:
                continue
            if line == '==================':
                continue
            if line == '---':
                blocks.append(line)
                continue
            
            if SKIP_LINE_RE.match(line):
                continue
            if any(noise in line for noise in NOISE_CONTAINS):
                continue
            
            if line in {'目录', '上一页', '下一页', '尾页', 'Trang tiếp theo', 'Next', '下一章', 'Top', '返回顶部'}:
                continue
                
            blocks.append(line)

        return blocks

    def _is_chapter_heading(self, text: str) -> bool:
        text = self._clean_text(text)
        if not text or len(text) > 100:
            return False
        return bool(CHAPTER_RE.match(text))

    async def _flush_chapter(self, story_folder: str, chap_index: int, chap_title: str, lines: list[str]):
        if not chap_title:
            return

        merged_lines: list[str] = []
        prev = None
        for line in lines:
            line = self._clean_text(line)
            if not line:
                continue
            if line == prev:
                continue
            merged_lines.append(line)
            prev = line

        content = '\n\n'.join(merged_lines).strip()
        if len(content) < 20:
            return

        fname = f"{chap_index:04d}_{utils.safe_filename(chap_title)}.txt"
        fpath = os.path.join(story_folder, fname)
        async with aiofiles.open(fpath, 'w', encoding='utf-8') as f:
            await f.write(f"{chap_title}\n\n{content}")
        self.log(f"✅ [{chap_index}] {chap_title}")

    def _save_metadata_compat(self, story_folder: str, title: str, entry_url: str, catalog_url: str):
        try:
            utils.save_metadata(
                story_folder,
                title,
                url=entry_url,
                catalog_url=catalog_url,
                site='52shuku.net',
            )
            return
        except TypeError:
            pass

        try:
            utils.save_metadata(
                story_folder,
                title,
                url=entry_url,
                site='52shuku.net',
            )
            return
        except TypeError:
            pass

        try:
            utils.save_metadata(story_folder, title)
        except Exception as e:
            self.log(f'⚠️ Không lưu được metadata: {e}')

    async def start_download(self, url, save_folder_root):
        self.log(f"🚀 [{self.site_name}] Bắt đầu quét: {url}")

        entry_url = self._normalize_url(url)
        catalog_url = self._catalog_url(entry_url)
        current_url = entry_url

        self.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            ),
            'Referer': 'https://www.52shuku.net/',
        })

        timeout = aiohttp.ClientTimeout(total=25)
        connector = aiohttp.TCPConnector(limit=6, limit_per_host=3, ssl=True)

        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            first_soup = await self.fetch_soup(session, current_url)
            if not first_soup:
                self.log('❌ Không truy cập được link gốc.')
                return

            if self._looks_like_catalog(first_soup):
                start_url = self._extract_start_url(first_soup, current_url)
                if not start_url:
                    self.log('❌ Không tìm thấy link bắt đầu đọc trong trang mục lục.')
                    return
                catalog_url = current_url
                current_url = start_url
                self.log(f'🔗 Đã nhận diện trang mục lục, chuyển sang trang đọc: {current_url}')

                catalog_soup = first_soup
                title = self._extract_title(catalog_soup)
            else:
                title = self._extract_title(first_soup)
                catalog_soup = await self.fetch_soup(session, catalog_url) if catalog_url != current_url else None
                if catalog_soup and self._looks_like_catalog(catalog_soup):
                    title = self._extract_title(catalog_soup) or title
                    start_url = self._extract_start_url(catalog_soup, catalog_url)
                    if start_url:
                        current_url = start_url
                        self.log(f'🔗 Tự động quay về trang bắt đầu đọc: {current_url}')

            safe_title = utils.safe_filename(title)
            story_folder = os.path.join(save_folder_root, safe_title)
            os.makedirs(story_folder, exist_ok=True)
            self._save_metadata_compat(story_folder, title, entry_url, catalog_url)

            self.log(f'📖 Truyện: {title}')
            self.log(f'📂 Lưu tại: {story_folder}')

            visited = set()
            chapter_index = 1
            current_chapter_title = None
            current_lines: list[str] = []
            page_count = 0
            found_any_chapter = False

            while current_url:
                if self.should_stop():
                    self.log('⏹️ Đã nhận lệnh dừng.')
                    break

                current_url = self._normalize_url(current_url)
                if current_url in visited:
                    self.log(f'⚠️ Phát hiện loop URL, dừng tại: {current_url}')
                    break
                visited.add(current_url)
                page_count += 1

                soup = first_soup if page_count == 1 and current_url == entry_url and not self._looks_like_catalog(first_soup) else None
                if soup is None:
                    soup = await self.fetch_soup(session, current_url)
                if not soup:
                    self.log(f'⚠️ Không tải được trang: {current_url}')
                    break

                article = self._find_article(soup)
                if not article:
                    self.log(f'⚠️ Không tìm thấy khối nội dung tại: {current_url}')
                    break

                next_url = self._next_page_url(soup, current_url)

                blocks = self._extract_blocks(article)

                page_new_chapters = 0
                for block in blocks:
                    if self._is_chapter_heading(block):
                        found_any_chapter = True
                        page_new_chapters += 1
                        if current_chapter_title and current_lines:
                            await self._flush_chapter(story_folder, chapter_index, current_chapter_title, current_lines)
                            chapter_index += 1
                        current_chapter_title = block
                        current_lines = []
                        continue

                    if not found_any_chapter:
                        continue

                    if current_chapter_title:
                        current_lines.append(block)

                self.log(f'📄 Trang {self._page_number(current_url)}: {page_new_chapters} chương mới')

                if not next_url:
                    self.log('🏁 Đã đến trang cuối.')
                    break

                await self.sleep_check_stop(0.8)
                current_url = next_url

            if current_chapter_title and current_lines:
                await self._flush_chapter(story_folder, chapter_index, current_chapter_title, current_lines)
            elif not found_any_chapter:
                self.log('⚠️ Không phát hiện được tiêu đề chương nào, chưa lưu file chương.')
                return

        self.log('🏆 HOÀN THÀNH!')