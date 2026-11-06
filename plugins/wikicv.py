"""WikiCV: traverse chapters and every numbered part using the site's own UI."""
import hashlib
from pathlib import Path
from urllib.parse import urlparse, urljoin, urldefrag

from bs4 import BeautifulSoup
from plugins.base import BaseCrawler
from core.storage import atomic_text, atomic_json, read_json
from core.cleanup import cleanup_completed_story
from core.browser import BrowserSession
from core.http_reader import HttpChapterSession, AutoChapterSession
import utils


def normalized(url):
    return urldefrag(url)[0].strip()


def part_numbers(soup):
    values = set()
    for node in soup.select('a.chapter-part[data-pn]'):
        try:
            value = int(node['data-pn'])
        except ValueError as exc:
            raise RuntimeError('Số phần không hợp lệ; dừng để tránh thiếu nội dung.') from exc
        if value < 0:
            raise RuntimeError('Số phần âm không hợp lệ.')
        values.add(value)
    if values and sorted(values) != list(range(max(values) + 1)):
        raise RuntimeError('Danh sách phần bị thiếu số; chưa thể ghép chương.')
    return sorted(values) or [0]


def clean_content(soup):
    body = soup.select_one('#bookContentBody')
    if body is None:
        raise RuntimeError('Không tìm thấy #bookContentBody; chưa lưu chương này.')
    body = BeautifulSoup(str(body), 'html.parser')
    for node in body.select('script, style, iframe, noscript, form, button, .tpm-unit, .adsbygoogle, .chapter-part, [id^="tpads_"]'):
        node.decompose()
    for node in body.find_all('br'):
        node.replace_with('\n')
    # Block boundaries, preserve inline words and text outside <p> as well.
    for node in body.find_all(['p', 'div']):
        node.insert_before('\n\n')
        node.insert_after('\n\n')
    text = body.get_text().strip()
    import re
    text = re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+', '\n\n', text)
    if not text:
        raise RuntimeError('Phần truyện rỗng; chưa đánh dấu hoàn tất.')
    return text


class WikiCVCrawler(BaseCrawler):
    display_name = 'WikiCV · đủ các phần'
    priority = 200
    browser_factory = None
    supports_resume = True

    def can_handle(self, url):
        return (urlparse(url).hostname or '').lower() in ('wikicv.org', 'www.wikicv.org')

    def get_supported_sources(self):
        return [{'name': 'WikiCV', 'domain': 'wikicv.org', 'provider': 'HTTP / Chromium tùy chọn · nhiều phần'}]

    async def start_download(self, url, save_folder):
        url = normalized(url)
        key = hashlib.sha256(url.encode()).hexdigest()[:12]
        state_path = Path(save_folder) / '.noveldownloader' / f'wikicv-{key}.json'
        state = read_json(state_path, {'url': url, 'current_url': url, 'index': 1, 'done': [], 'parts': {}})
        # ND_COPIED_FOLDER_FIX_1
        if state.get('folder') and not Path(state['folder']).resolve().is_relative_to(Path(save_folder).resolve()):
            raise RuntimeError('Tiến độ còn trỏ ra ngoài nơi lưu đã chọn. Chạy công cụ Sửa nơi lưu trước khi tiếp tục; chưa tạo thư mục cũ.')
        if state.get('completed'):
            # Verify files before reporting success on a rerun.
            if all(Path(x).is_file() for x in state.get('files', [])) and state.get('files'):
                cleanup_completed_story(state_path, state, self.log)
                return {'completed': True, 'output_path': state['folder'], 'current': len(state['files'])}
            raise RuntimeError('Một số tệp đã tải bị xóa. Chọn thư mục lưu mới để tải lại đầy đủ.')
        mode = self.options.get('connection_mode', 'auto')
        factory = self.browser_factory or {'auto': AutoChapterSession, 'http': HttpChapterSession}.get(mode, BrowserSession)
        self.report_progress(current=state['index'] - 1)
        self.log(f'[KHÔI PHỤC] Bắt đầu tại mục {state["index"]} · {state["current_url"]}')
        async with factory(self) as browser:
            visited = set()
            current = state['current_url']
            while current:
                await self.checkpoint()
                if current in visited:
                    raise RuntimeError('Liên kết chương tạo vòng lặp; dừng để tránh tải trùng.')
                visited.add(current)
                self.track_url(current)
                self.log(f'[ĐANG TẢI] Mục {state["index"]} · {current}')
                soup = BeautifulSoup(await browser.get(current), 'html.parser')
                if soup.title and 'site unavailable' in soup.title.get_text().lower():
                    raise RuntimeError(f'Máy chủ trả về Site Unavailable: {current}. Giữ nguyên tiến độ để thử lại khi kết nối ổn định.')
                if soup.select_one('#bookContentBody') is None:
                    # Catalog link: follow a real chapter link, never invent an endpoint.
                    anchor = soup.select_one('a#btnRead, a.btn-read, .chapter-list a[href*="/truyen/"], #chapterList a[href*="/truyen/"]')
                    if not anchor:
                        raise RuntimeError('Đây chưa phải trang chương đọc được. Hãy dán link chương đầu để bắt đầu.')
                    current = normalized(urljoin(current, anchor['href']))
                    if not self.can_handle(current):
                        raise RuntimeError('Liên kết chương dẫn sang nguồn khác.')
                    state['current_url'] = current
                    atomic_json(state_path, state)
                    continue
                title_tag = soup.select_one('#bookContent .book-title')
                title = title_tag.get_text(' ', strip=True) if title_tag else 'Truyện WikiCV'
                folder = Path(state.get('folder') or Path(save_folder) / f'{utils.safe_filename(title)[:100]}_{key}')
                folder.mkdir(parents=True, exist_ok=True)
                state['folder'] = str(folder.resolve())
                author = next((x.get_text(' ', strip=True).removeprefix('Tác giả:').strip()
                               for x in soup.select('.book-title') if x.get_text().strip().startswith('Tác giả:')), '')
                utils.save_metadata(str(folder), title, author=author, url=url)
                chapter_node = soup.select_one('.chapter-name')
                chapter = chapter_node.get_text(' ', strip=True) if chapter_node else f'Chương {state["index"]}'
                parts = part_numbers(soup)
                self.log(f'[CHƯƠNG] {chapter} · {len(parts)} phần · {current}')
                self.report_progress(chapter_title=chapter, parts_total=len(parts))
                chapter_key = hashlib.sha256(current.encode()).hexdigest()[:16]
                cache = folder / '.parts' / chapter_key
                cache.mkdir(parents=True, exist_ok=True)
                text_parts = []
                next_anchor = soup.select_one('#btnNextChapter')
                next_href = next_anchor.get('href', '').strip() if next_anchor else ''
                next_url = normalized(urljoin(current, next_href)) if next_href and not next_href.startswith(('#', 'javascript:')) else None
                if next_url and not self.can_handle(next_url):
                    raise RuntimeError('Chương sau dẫn sang nguồn khác; chưa xác nhận hoàn tất.')
                atomic_json(state_path, state)
                for pn in parts:
                    await self.checkpoint()
                    self.track_url(current, pn)
                    self.log(f'[PHẦN {pn + 1}/{len(parts)}] {chapter} · {current}')
                    part_path = cache / f'{pn}.txt'
                    records = state.setdefault('parts', {}).setdefault(chapter_key, {})
                    cached = part_path.read_text(encoding='utf-8') if part_path.exists() else ''
                    digest = hashlib.sha256(cached.encode()).hexdigest()
                    if cached and records.get(str(pn)) == digest:
                        text = cached
                        self.log(f'Đã có: {chapter} · Phần {pn + 1}/{len(parts)}')
                    else:
                        active = soup.select_one('a.chapter-part.active')
                        active_pn = int(active.get('data-pn', 0)) if active else 0
                        if active_pn != pn:
                            soup = BeautifulSoup(await browser.part(pn), 'html.parser')
                        text = clean_content(soup)
                        if text in text_parts:
                            raise RuntimeError(f'Phần {pn + 1} trùng hệt phần trước; dừng để tránh ghép sai.')
                        atomic_text(part_path, text)
                        records[str(pn)] = hashlib.sha256(text.encode()).hexdigest()
                        atomic_json(state_path, state)
                        self.log(f'[ĐÃ LƯU PHẦN] {pn + 1}/{len(parts)} · {len(text):,} ký tự')
                    if text in text_parts:
                        raise RuntimeError(f'Phần {pn + 1} trùng hệt phần đã lưu; chưa ghép chương.')
                    text_parts.append(text)
                    self.report_progress(title=title, status=f'{chapter} · Phần {pn + 1}/{len(parts)}',
                                         current=state['index'] - 1, output_path=str(folder),
                                         detail='Chỉ ghép tệp chương khi đã có đủ mọi phần.')
                target = folder / f'{state["index"]:04d}_{utils.safe_filename(chapter)[:130]}.txt'
                existing = list(folder.glob(f'{state["index"]:04d}_*.txt'))
                if existing and (len(existing) != 1 or existing[0] != target):
                    raise RuntimeError(f'Mục {state["index"]} có tệp cũ khác tên hoặc trùng số. Giữ nguyên tệp, dừng để đối chiếu: {existing}')
                if target.exists():
                    if not target.is_file() or target.is_symlink() or not target.stat().st_size:
                        raise RuntimeError(f'Tệp chương cũ không hợp lệ; chưa ghi đè: {target}')
                    self.log(f'[GIỮ TỆP CŨ] {target.name} · không ghi đè nội dung đã chỉnh sửa')
                else:
                    atomic_text(target, chapter + '\n\n' + '\n\n'.join(text_parts))
                state.setdefault('files', []).append(str(target.resolve()))
                state.setdefault('file_hashes', {})[str(target.resolve())] = hashlib.sha256(target.read_bytes()).hexdigest()
                state['done'].append(current)
                state['index'] += 1
                state['current_url'] = next_url
                state['completed'] = next_url is None
                atomic_json(state_path, state)
                self.log(f'Đã lưu đủ {len(parts)} phần: {target.name}')
                self.report_progress(current=state['index'] - 1, status=f'Đã lưu {state["index"] - 1} chương/trang', output_path=str(folder))
                if next_url:
                    self.log(f'[CHƯƠNG TIẾP] {next_url}')
                else:
                    self.log('[HOÀN TẤT] Đã tới trang cuối và lưu đủ các phần.')
                current = next_url
        cleanup_completed_story(state_path, state, self.log)
        return {'completed': True, 'output_path': state['folder'], 'current': state['index'] - 1}
