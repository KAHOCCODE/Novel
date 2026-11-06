from urllib.parse import urlparse
# File: plugins/truyenfull_vision.py
import os
import sys
import asyncio
import aiofiles
import aiohttp
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# Thêm đường dẫn cha để import được file utils.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import utils 
from plugins.base import BaseCrawler 

class TruyenFullVisionCrawler(BaseCrawler):
    display_name = 'truyenfull.vision'

    def get_supported_sources(self):
        return [{"name": self.get_display_name(), "domain": 'truyenfull.vision', "provider": "Plugin gốc · cần kiểm tra kết quả"}]

    def can_handle(self, url):
        return (urlparse(url or "").hostname or "").lower().removeprefix("www.") in ['truyenfull.vision']

    async def start_download(self, url, save_folder_root):
        self.log(f"🚀 [TruyenFull.Vision] Bắt đầu quét (Fix xuống dòng)...")
        
        current_url = url
        current_index = 1
        story_folder = ""
        
        # Giả lập trình duyệt
        self.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://truyenfull.vision/"
        })

        async with aiohttp.ClientSession() as session:
            # --- BƯỚC 1: LẤY THÔNG TIN TRUYỆN ---
            first_soup = await self.fetch_soup(session, url)
            if not first_soup:
                self.log("❌ Không truy cập được link gốc.")
                return

            # Lấy tên truyện
            name_input = first_soup.select_one("#ten-truyen")
            if name_input and name_input.get('value'):
                raw_title = name_input['value'].replace("-", " ").title()
                title = raw_title
            else:
                title_tag = first_soup.select_one(".truyen-title, h1")
                title = title_tag.get_text(strip=True) if title_tag else "Truyen_TruyenFullVision"
            
            # Tạo folder lưu truyện
            safe_title = utils.safe_filename(title)
            story_folder = os.path.join(save_folder_root, safe_title)
            os.makedirs(story_folder, exist_ok=True)
            utils.save_metadata(story_folder, title, url=url)

            self.log(f"📖 Truyện: {title}")
            self.log(f"📂 Lưu tại: {story_folder}")

            # --- BƯỚC 2: VÒNG LẶP TẢI TỪNG CHƯƠNG ---
            while current_url:
                soup = await self.fetch_soup(session, current_url)
                if not soup:
                    self.log(f"⚠️ Lỗi mạng chương {current_index}, thử lại sau 2s...")
                    await self.sleep_check_stop(2)
                    continue

                # A. Lấy Tên Chương
                chap_tag = soup.select_one(".chapter-title, .chapter-text")
                if chap_tag:
                    chap_name = chap_tag.get_text(strip=True)
                else:
                    chap_name = f"Chuong_{current_index}"

                # B. Lấy Nội Dung (FIX DỒN CHỮ)
                content_div = soup.select_one("#chapter-c")
                
                content_text = ""
                if content_div:
                    # 1. Xóa rác: script, style, form
                    for garbage in content_div(["script", "style", "iframe", "form", "button"]): 
                        garbage.decompose()
                    
                    # 2. Xóa quảng cáo (div ads)
                    for ads in content_div.select("div[class*='ads'], div[id*='ads']"):
                        ads.decompose()

                    # 3. [FIX QUAN TRỌNG] Thay thế thẻ <br> bằng ký tự xuống dòng
                    # Giúp các đoạn văn không bị dính liền nhau khi dùng get_text
                    for br in content_div.find_all("br"):
                        br.replace_with("\n")

                    # 4. Lấy text với separator="\n\n"
                    # Thay vì chỉ tìm thẻ p, ta lấy toàn bộ text trong div và ngăn cách bằng 2 dòng trống
                    content_text = content_div.get_text(separator="\n\n", strip=True)

                # C. Lưu File
                if content_text and len(content_text) > 50:
                    fname = f"{current_index:04d}_{utils.safe_filename(chap_name)}.txt"
                    fpath = os.path.join(story_folder, fname)
                    async with aiofiles.open(fpath, "w", encoding="utf-8") as f:
                        await f.write(f"{chap_name}\n\n{content_text}")
                    self.log(f"✅ [{current_index}] {chap_name}")
                    current_index += 1
                else:
                    self.log(f"⚠️ Rỗng hoặc Lỗi: {chap_name} - {current_url}")

                # D. Tìm Link Chương Tiếp
                next_btn = soup.select_one("#next_chap")
                
                if next_btn and next_btn.has_attr('href'):
                    next_link = next_btn['href']
                    
                    if "javascript" in next_link or "#" == next_link:
                        self.log("🏁 Đã đến chương cuối (Link JS/Disabled).")
                        break
                    
                    if "disabled" in next_btn.get("class", []):
                        self.log("🏁 Đã đến chương cuối (Class Disabled).")
                        break

                    full_next_link = urljoin(current_url, next_link)
                    
                    if full_next_link == current_url:
                        self.log("🏁 Đã đến chương cuối (Link trùng).")
                        break
                        
                    current_url = full_next_link
                else:
                    self.log("🏁 Đã đến chương cuối (Không thấy nút Next).")
                    break
        
        self.log("🏆 HOÀN THÀNH QUÁ TRÌNH TẢI!")