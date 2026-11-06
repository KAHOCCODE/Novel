from urllib.parse import urlparse
# File: plugins/metruyenchu.py
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

class MetruyenchuCrawler(BaseCrawler):
    display_name = 'metruyenchu.com'

    def get_supported_sources(self):
        return [{"name": self.get_display_name(), "domain": 'metruyenchu.com, metruyenchu.net', "provider": "Plugin gốc · cần kiểm tra kết quả"}]

    def can_handle(self, url):
        return (urlparse(url or "").hostname or "").lower().removeprefix("www.") in ['metruyenchu.com', 'metruyenchu.net']

    async def start_download(self, url, save_folder_root):
        self.log(f"🚀 [Metruyenchu] Bắt đầu quét (Fix V2)...")
        
        current_url = url
        current_index = 1
        
        # Cập nhật Header để trông giống người dùng thật hơn
        self.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://metruyenchu.com.vn/"
        })

        async with aiohttp.ClientSession() as session:
            # --- BƯỚC 1: LẤY THÔNG TIN TRUYỆN ---
            first_soup = await self.fetch_soup(session, url)
            if not first_soup:
                self.log("❌ Không truy cập được link gốc.")
                return

            # Lấy tên truyện
            title_tag = first_soup.select_one("h1.current-book a, h1.current-book, h1")
            title = title_tag.get_text(strip=True) if title_tag else "Truyen_Metruyenchu"
            
            # Tạo folder
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
                chap_tag = soup.select_one(".current-chapter a, .chapter-title h2, h2.title")
                chap_name = chap_tag.get_text(strip=True) if chap_tag else f"Chuong_{current_index}"

                # B. Lấy Nội Dung (FIXED: Chọn chính xác .truyen)
                # Ưu tiên .truyen, nếu không có mới tìm .content-chapter
                content_div = soup.select_one(".truyen")
                if not content_div:
                    content_div = soup.select_one("#vungdoc, .chapter-c, .content-chapter")
                
                content_text = ""
                if content_div:
                    # [QUAN TRỌNG] Không xóa thẻ 'div' nữa để tránh xóa nhầm nội dung con
                    # Chỉ xóa script, style, quảng cáo
                    for garbage in content_div(["script", "style", "iframe", "button", "center", "form"]): 
                        garbage.decompose()
                    
                    # Cách 1: Lấy tất cả thẻ p (Chuẩn nhất)
                    paragraphs = content_div.find_all("p")
                    if paragraphs:
                         content_text = "\n\n".join(p.get_text(strip=True) for p in paragraphs)
                    else:
                         # Cách 2: Nếu không có thẻ p, lấy text thuần
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
                    self.log(f"⚠️ Rỗng: {chap_name} (Có thể do Anti-bot hoặc sai cấu trúc)")
                    # Vẫn thử tìm chương tiếp theo dù chương này lỗi

                # D. Tìm Link Chương Tiếp
                # HTML: <a href="..." class="next">Chương tiếp 》</a>
                # Tìm trong toàn bộ soup, không tìm trong content_div nữa
                next_btn = soup.select_one("a.next, a.btn-next, a[rel='next']")
                
                if next_btn and next_btn.has_attr('href'):
                    next_link = next_btn['href']
                    
                    if "javascript" in next_link or "#" == next_link:
                        self.log("🏁 Đã đến chương cuối (Link JS).")
                        break
                    
                    full_next_link = urljoin(current_url, next_link)
                    
                    if full_next_link == current_url:
                        self.log("🏁 Đã đến chương cuối (Link trùng).")
                        break
                        
                    current_url = full_next_link
                else:
                    self.log("🏁 Đã đến chương cuối (Không thấy nút Next).")
                    break
        
        self.log("🏆 HOÀN THÀNH!")