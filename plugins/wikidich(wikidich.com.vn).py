from urllib.parse import urlparse
# File: plugins/wikidich.py
import os
import sys
import asyncio
import aiofiles
import aiohttp
import random
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# Thêm đường dẫn cha để import được file utils.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import utils 
from plugins.base import BaseCrawler 

class WikiDichCrawler(BaseCrawler):
    display_name = 'wikidich.com.vn'

    def get_supported_sources(self):
        return [{"name": self.get_display_name(), "domain": 'wikidich.com.vn', "provider": "Plugin gốc · cần kiểm tra kết quả"}]

    def can_handle(self, url):
        return (urlparse(url or "").hostname or "").lower().removeprefix("www.") in ['wikidich.com.vn']

    async def start_download(self, url, save_folder_root):
        self.log(f"🚀 [WikiDich] Bắt đầu quét...")
        
        current_url = url
        current_index = 1
        
        # Cấu hình Header giống script cũ của bạn để tránh bị chặn
        self.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://wikidich.com.vn/",
        })

        async with aiohttp.ClientSession() as session:
            # --- BƯỚC 1: LẤY THÔNG TIN TRUYỆN ---
            first_soup = await self.fetch_soup(session, url)
            if not first_soup:
                self.log("❌ Không truy cập được link gốc.")
                return

            # Lấy tên truyện (Thường nằm ở thẻ H1 hoặc .cover-title nếu là trang mục lục, 
            # nhưng nếu link vào thẳng chương thì ta tìm tên truyện ở breadcrumb hoặc title)
            title_tag = first_soup.select_one(".book-title, h1, .cover-info h2")
            if not title_tag:
                 # Thử lấy từ thẻ a trong breadcrumb (thường là link thứ 2 hoặc 3)
                 breadcrumb = first_soup.select(".breadcrumb li a")
                 if breadcrumb and len(breadcrumb) > 1:
                     title = breadcrumb[-2].get_text(strip=True) # Lấy phần tử kế cuối
                 else:
                     title = "Truyen_WikiDich"
            else:
                title = title_tag.get_text(strip=True)

            # Tạo folder
            safe_title = utils.safe_filename(title)
            story_folder = os.path.join(save_folder_root, safe_title)
            os.makedirs(story_folder, exist_ok=True)
            utils.save_metadata(story_folder, title, url=url)

            self.log(f"📖 Truyện: {title}")
            self.log(f"📂 Lưu tại: {story_folder}")

            # --- BƯỚC 2: VÒNG LẶP TẢI ---
            while current_url:
                # WikiDich rất hay chặn request nhanh, cần delay ngẫu nhiên như script cũ
                delay = random.uniform(2, 5)
                await self.sleep_check_stop(delay)

                soup = await self.fetch_soup(session, current_url)
                if not soup:
                    self.log(f"⚠️ Lỗi tải trang {current_index}, thử lại sau 5s...")
                    await self.sleep_check_stop(5)
                    # Thử lại lần nữa
                    soup = await self.fetch_soup(session, current_url)
                    if not soup:
                        self.log(f"❌ Bỏ qua chương tại: {current_url}")
                        break

                # A. Lấy Tên Chương
                # WikiDich: Tên chương thường ở .chapter-title hoặc h2
                chap_tag = soup.select_one(".chapter-title, #chapter-title, h2")
                chap_name = chap_tag.get_text(strip=True) if chap_tag else f"Chuong {current_index}"

                # B. Lấy Nội Dung
                # Script cũ dùng: soup.find("div", class_="truyen")
                content_div = soup.select_one("div.truyen")
                
                if content_div:
                    # Xóa rác (quảng cáo, script) trước khi lấy text
                    for garbage in content_div(["script", "style", "div.ads", "iframe"]):
                        garbage.decompose()
                    
                    # Lấy text
                    content_text = content_div.get_text(separator="\n\n", strip=True)
                    
                    # C. Lưu File
                    fname = f"{current_index:04d}_{utils.safe_filename(chap_name)}.txt"
                    fpath = os.path.join(story_folder, fname)
                    
                    async with aiofiles.open(fpath, "w", encoding="utf-8") as f:
                        await f.write(f"{chap_name}\n\n{content_text}")
                    
                    self.log(f"✅ [{current_index}] {chap_name}")
                    current_index += 1
                else:
                    self.log(f"⚠️ Không thấy nội dung: {current_url}")

                # D. Tìm Link Chương Tiếp
                # Script cũ dùng: soup.find("a", class_="next")
                next_btn = soup.select_one("a.next")
                
                if next_btn and next_btn.has_attr("href"):
                    next_link = next_btn["href"]
                    # WikiDich đôi khi để link là javascript:void(0) ở chương cuối
                    if "javascript" in next_link:
                         self.log("🏁 Đã đến chương cuối.")
                         break
                         
                    current_url = urljoin(base_url, next_link) # base_url lấy từ biến global trong script cũ, ở đây ta dùng current_url để join
                else:
                    self.log("🏁 Hoàn thành (Không thấy nút Next).")
                    break

        self.log("🏆 TẢI XONG!")