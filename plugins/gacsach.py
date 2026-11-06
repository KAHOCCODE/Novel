from urllib.parse import urlparse
import os
import sys
import asyncio
import aiofiles
import aiohttp
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# Thêm đường dẫn cha để import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import utils 
from plugins.base import BaseCrawler 

class GacSachCrawler(BaseCrawler):
    display_name = 'gacsach.com'

    def get_supported_sources(self):
        return [{"name": self.get_display_name(), "domain": 'gacsach.com', "provider": "Plugin gốc · cần kiểm tra kết quả"}]

    def can_handle(self, url):
        return (urlparse(url or "").hostname or "").lower().removeprefix("www.") in ['gacsach.com']

    async def start_download(self, url, save_folder_root):
        domain = "gacsach.org"
        self.log(f"🚀 [GacSach] Bắt đầu quét: {url}")
        
        current_url = url
        current_index = 1
        
        # Header giả lập
        self.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://gacsach.org/"
        })

        async with aiohttp.ClientSession() as session:
            # --- BƯỚC 1: LẤY THÔNG TIN TRUYỆN ---
            first_soup = await self.fetch_soup(session, url)
            if not first_soup:
                self.log("❌ Không truy cập được link gốc.")
                return

            # Lấy tên truyện (Xử lý tiêu đề Drupal)
            h1_tag = first_soup.select_one("h1.title, h1")
            full_title = h1_tag.get_text(strip=True) if h1_tag else "Truyen_GacSach"
            
            # Tách tên truyện: "Tên Truyện - Chương X" -> lấy "Tên Truyện"
            if " - " in full_title:
                title = full_title.split(" - ")[0].strip()
            else:
                title = full_title

            # Tạo folder
            safe_title = utils.safe_filename(title)
            story_folder = os.path.join(save_folder_root, safe_title)
            os.makedirs(story_folder, exist_ok=True)
            utils.save_metadata(story_folder, title, url=url)

            self.log(f"📖 Truyện: {title}")
            self.log(f"📂 Lưu tại: {story_folder}")

            # --- BƯỚC 2: VÒNG LẶP ---
            while current_url:
                soup = await self.fetch_soup(session, current_url)
                if not soup:
                    self.log(f"⚠️ Lỗi mạng chương {current_index}, thử lại sau 2s...")
                    await self.sleep_check_stop(2)
                    continue

                # A. Lấy Tên Chương
                page_title = soup.select_one("h1.title, h1").get_text(strip=True)
                if " - " in page_title:
                    chap_name = page_title.split(" - ")[-1].strip()
                else:
                    chap_name = page_title

                if len(chap_name) < 3:
                    chap_name = f"Chuong_{current_index}"

                # B. Lấy Nội Dung
                # Selector: .field-item.even (Content chính) hoặc .truyen
                content_div = soup.select_one(".field-item.even, .content .node .content, .truyen")
                
                content_text = ""
                if content_div:
                    # 1. Xóa rác
                    for tag in content_div(["script", "style", "form", "iframe", "noscript"]): 
                        tag.decompose()
                    
                    # 2. Xóa các dòng quảng cáo/watermark chứa domain
                    # Tìm thẻ span hoặc p có chứa chữ "gacsach"
                    for elem in content_div.find_all(["span", "p", "div"]):
                        if "gacsach" in elem.get_text().lower():
                            elem.decompose()

                    # 3. Lấy text (Giữ cấu trúc đoạn văn)
                    paragraphs = content_div.find_all("p")
                    if paragraphs:
                        lines = []
                        for p in paragraphs:
                            txt = p.get_text(strip=True)
                            # Bỏ qua dòng rỗng hoặc chỉ có tên truyện lặp lại
                            if txt and txt != title: 
                                lines.append(txt)
                        content_text = "\n\n".join(lines)
                    else:
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
                    self.log(f"⚠️ Rỗng/Lỗi: {chap_name}")

                # D. Tìm Link Chương Tiếp (Đã cập nhật theo yêu cầu)
                # Ưu tiên #idnx, sau đó đến .page-next
                next_btn = soup.select_one("#idnx, a.page-next, li.pager-next a, a[rel='next']")
                
                if next_btn and next_btn.has_attr('href'):
                    next_link = next_btn['href']
                    full_next_link = urljoin(current_url, next_link)
                    
                    if full_next_link == current_url or "#" in next_link:
                         self.log("🏁 Link trùng hoặc vô hiệu, dừng.")
                         break
                        
                    current_url = full_next_link
                else:
                    self.log("🏁 Đã đến chương cuối (Không thấy nút Next).")
                    break
        
        self.log("🏆 HOÀN THÀNH!")