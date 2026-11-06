from urllib.parse import urlparse
# File: plugins/truyenwikidich_net.py
import os
import sys
import asyncio
import aiofiles
import aiohttp
import random
from urllib.parse import urljoin
from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import utils 
from plugins.base import BaseCrawler 

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
]

class TruyenWikiDichNetCrawler(BaseCrawler):
    display_name = 'truyenwikidich.net'

    def get_supported_sources(self):
        return [{"name": self.get_display_name(), "domain": 'truyenwikidich.net', "provider": "Plugin gốc · cần kiểm tra kết quả"}]

    def can_handle(self, url):
        return (urlparse(url or "").hostname or "").lower().removeprefix("www.") in ['truyenwikidich.net']

    async def start_download(self, url, save_folder_root):
        self.log("🚀 [TruyenWikiDich.Net] Bat dau quet...")
        
        current_url = url
        current_index = 1
        
        self.headers.update({
            "Referer": "https://truyenwikidich.net/",
        })

        connector = aiohttp.TCPConnector(limit=5)
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            self.headers["User-Agent"] = random.choice(USER_AGENTS)
            first_soup = await self.fetch_soup(session, url)
            if not first_soup:
                self.log("Loi: Khong truy cap duoc link goc.")
                return

            title_tag = first_soup.select_one("h1, .book-title, .truyen-title")
            if title_tag:
                title = title_tag.get_text(strip=True)
            else:
                title = first_soup.title.string.split("-")[0].strip() if first_soup.title else "Truyen_WikiDichNet"

            safe_title = utils.safe_filename(title)
            story_folder = os.path.join(save_folder_root, safe_title)
            os.makedirs(story_folder, exist_ok=True)
            utils.save_metadata(story_folder, title, url=url)

            self.log(f"Truyen: {title}")
            self.log(f"Luu tai: {story_folder}")

            resume_file = os.path.join(story_folder, "resume_state.txt")
            if os.path.exists(resume_file):
                try:
                    with open(resume_file, "r", encoding="utf-8") as rf:
                        data = rf.read().strip().split("|")
                        if len(data) == 2:
                            current_index = int(data[0])
                            current_url = data[1]
                            self.log(f"Tiep tuc tai tu chuong {current_index} dua tren lich su...")
                except Exception:
                    self.log("Khong the doc file lich su tai, bat dau tu dau.")

            retry_count = 0
            max_retries = 15 

            while current_url:
                self.headers["User-Agent"] = random.choice(USER_AGENTS)
                
                delay = random.uniform(3, 7)
                await self.sleep_check_stop(delay)

                soup = await self.fetch_soup(session, current_url)
                
                # Cập nhật logic: Nếu web bị block (trả về giao diện chặn của Cloudflare), thẻ #bookContentBody sẽ không tồn tại.
                content_div = soup.select_one("#bookContentBody") if soup else None

                # Đưa việc kiểm tra nội dung vào luồng bắt lỗi mạng
                if not soup or not content_div:
                    retry_count += 1
                    if retry_count > max_retries:
                        self.log(f"Loi mang/Bi block lien tuc {max_retries} lan. Vui long thay doi mang (IP) va chay lai. Trang thai da duoc luu tai chuong {current_index}.")
                        break
                    
                    wait_time = 15 * retry_count 
                    self.log(f"⚠️ Bi block hoac loi mang o chuong {current_index}. Cho {wait_time}s de thu lai ({retry_count}/{max_retries}). Ban co the doi mang/IP ngay bay gio...")
                    await self.sleep_check_stop(wait_time)
                    continue # Bỏ qua phần dưới, quay lại tải lại trang này
                
                retry_count = 0 

                chap_tag = soup.select_one(".chapter-title, h2, h1")
                chap_name = chap_tag.get_text(strip=True) if chap_tag else f"Chuong {current_index}"

                for garbage in content_div(["script", "style", "iframe", "div[class*='ads']"]):
                    garbage.decompose()
                
                paragraphs = content_div.find_all("p")
                if paragraphs:
                     content_text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
                else:
                     content_text = content_div.get_text(separator="\n\n", strip=True)

                if len(content_text) > 50:
                    fname = f"{current_index:04d}_{utils.safe_filename(chap_name)}.txt"
                    fpath = os.path.join(story_folder, fname)
                    
                    if not os.path.exists(fpath):
                        async with aiofiles.open(fpath, "w", encoding="utf-8") as f:
                            await f.write(f"{chap_name}\n\n{content_text}")
                        self.log(f"Da tai: [{current_index}] {chap_name}")
                    else:
                        self.log(f"Da ton tai, bo qua: [{current_index}] {chap_name}")
                    
                    current_index += 1
                else:
                    self.log(f"Noi dung qua ngan, bo qua luu file: {current_url}")

                next_btn = soup.select_one("#btnNextChapter")
                
                if next_btn and next_btn.has_attr("href"):
                    next_link = next_btn["href"]
                    
                    if "javascript" in next_link or next_link == "#":
                         self.log("Da den chuong cuoi (Link JS).")
                         if os.path.exists(resume_file):
                             os.remove(resume_file)
                         break

                    current_url = urljoin(current_url, next_link)
                    
                    with open(resume_file, "w", encoding="utf-8") as wf:
                        wf.write(f"{current_index}|{current_url}")
                else:
                    self.log("Da den chuong cuoi (Khong thay nut Next).")
                    if os.path.exists(resume_file):
                        os.remove(resume_file)
                    break

        self.log("TAI XONG!")