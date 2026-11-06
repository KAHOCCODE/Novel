# Bản 5.3 — hàng đợi, nơi lưu và dọn sạch

Xem HUONG_DAN_5_3.md cho giao diện và quy tắc lưu/dọn hiện tại. Các mô tả lưu lịch sử/log bên dưới là của bản cũ, không còn áp dụng trong 5.3.

# Novel Downloader 5.1.1

Bản cập nhật nhỏ từ 5.1, bổ sung dọn tác vụ đã hoàn tất và cache WikiCV.

## Mới trong 5.1.1: dọn sau khi hoàn tất

- **Dọn đã xong**: bỏ các tác vụ có trạng thái Hoàn tất khỏi hàng đợi. Giữ nguyên truyện và các tệp nhật ký. Lưu bản ghi lịch sử vào `completed-history.json` trong thư mục dữ liệu ứng dụng. Tác vụ đang chạy, đang chờ, lỗi, đã dừng hoặc Cần kiểm tra kết quả không bị dọn.
- **WikiCV tự dọn cache**: sau khi toàn bộ truyện hoàn tất, kiểm tra tất cả tệp chương trước khi xóa từng phần `.parts` do ứng dụng tạo. Không xóa nguyên thư mục bằng cách quét tùy ý. Tệp lạ hoặc cache đã chỉnh sửa được giữ lại.
- Giữ tệp chương, `thong_tin_truyen.txt`, nhật ký và một tệp trạng thái hoàn tất nhỏ để nhận diện truyện đã tải. Dữ liệu tạm của truyện tải dở/lỗi được giữ để tải tiếp.
- Nếu thiếu hoặc thay đổi một tệp chương, không tự dọn cache của truyện đó.
- Bản này dọn dữ liệu tạm, **không tự xóa lời văn, tiêu đề, tác giả hoặc thể loại trong nội dung truyện**.
- Các plugin khác vẫn dùng cách lưu riêng; bản này không quét xóa tệp tùy ý của chúng.

Cập nhật từ 5.1: đóng ứng dụng, chạy `CapNhat_5_1_len_5_1_1.pyw`, chọn thư mục 5.1 rồi cập nhật. Không cần tải lại cả bộ ứng dụng hay cài lại thư viện. Bản cập nhật sao lưu trước và dừng nếu phát hiện mã nguồn đã tự sửa.

Các hướng dẫn 5.1 dưới đây vẫn áp dụng.

## Nâng cấp từ 5.0, giữ truyện đang tải dở

1. Dừng hàng đợi và đóng hẳn bản 5.0. Không chạy hai bản cùng lúc.
2. Giải nén bản 5.1 vào thư mục mới, chạy `CaiDat.bat`, sau đó chạy `ChayUngDung.bat`.
3. Hàng đợi vẫn được đọc từ `%APPDATA%\NovelDownloader5`. Các đường dẫn xuất trong tác vụ cũ được giữ nguyên.
4. Chọn tác vụ đã dừng và bấm **Tiếp tục tải**. WikiCV dùng lại con trỏ và các phần đã lưu trong đúng thư mục cũ. Không tạo tác vụ mới bằng link lỗi nếu muốn giữ nguyên danh tính, số thứ tự và lịch sử của tác vụ đang tải.
5. Không xóa thư mục truyện, `.noveldownloader` hoặc `.parts`. Bản 5.1 tương thích cấu trúc checkpoint WikiCV của 5.0.

Tác vụ cũ chưa có lựa chọn cách tải được đặt về **HTTP**. Đây là thay đổi có chủ ý để không tự chạy Chromium. Có thể đổi cách tải trong Tùy chọn như hướng dẫn bên dưới.

Cài mới cần Python 3.10 trở lên, khuyến nghị Python 3.12 trên Windows. Đây là mã nguồn Python, chưa đóng gói thành EXE.

## Ba cách tải

Vào **Tùy chọn → Cách tải**:

| Chế độ | Có chạy Chromium? | Có hiện cửa sổ? | Trường hợp sử dụng |
| --- | --- | --- | --- |
| HTTP · không chạy Chrome | Không | Không | Trang có nội dung đọc trực tiếp trong HTML |
| Chromium chạy nền · không cửa sổ | Có | Không | Trang/phần cần JavaScript; bạn không muốn cửa sổ trình duyệt |
| Chromium hiện cửa sổ · xác minh | Có | Có | Cần tự xác minh trên trình duyệt |

**Mặc định là HTTP.** `CaiDat.bat` không tải hoặc cài Chromium. Hai chế độ Chromium chỉ dùng khi bạn chọn và đã chạy `CaiTrinhDuyet_TuyChon.bat`.

WikiCV có trang nhiều phần dùng nút JavaScript `href="#!"`, không cung cấp link phần trực tiếp. HTTP không tự đoán API: nếu không lấy được phần tiếp theo theo link thật, tác vụ dừng, giữ phần đã có và không ghi chương thiếu. Chọn **Chromium chạy nền** để tiếp tục xử lý nút phần như bản 5.0, nhưng không bật cửa sổ Chrome.

Để đổi một tác vụ có sẵn: chọn tác vụ đã dừng/lỗi, mở **Tùy chọn**, chọn cách tải, đánh dấu **Áp dụng cách tải và thời gian nghỉ cho tác vụ đang chọn**, rồi **Lưu tùy chọn → Tiếp tục tải**. Thư mục và link gốc của tác vụ không bị đổi.

Nếu Chromium chạy nền gặp yêu cầu xác minh, ứng dụng dừng và ghi link lỗi; không tự bật cửa sổ. Chỉ chọn chế độ hiện cửa sổ nếu bạn muốn xác minh bằng tay. Việc đổi mạng không bảo đảm xử lý được mọi loại lỗi hoặc CAPTCHA.

FanFicFare sử dụng bộ tải riêng, không chuyển sang Chromium theo tùy chọn này. Lựa chọn định dạng gộp và nội dung trưởng thành chỉ áp dụng cho FanFicFare; plugin gốc xuất TXT từng chương/trang.

## Giao diện mới

- Bỏ thanh bên lớn. Phần thêm truyện chỉ còn ô link, nút dán/thêm và trạng thái nhận diện.
- Chọn thư mục, plugin, định dạng, nhịp tải, cách tải trong cửa sổ **Tùy chọn**.
- Hàng đợi nằm trên, nhật ký chiếm phần lớn vùng dưới. Kéo đường phân cách để thay đổi chiều cao.
- **Phóng nhật ký** tạm ẩn hàng đợi; **Hiện hàng đợi** đưa hàng đợi trở lại.
- **Theo tác vụ đang chạy** được bật mặc định. Khi thêm link mới trong lúc tải, nhật ký vẫn theo truyện đang chạy. Bấm một dòng hàng đợi để xem riêng tác vụ đó sẽ tắt chế độ theo dõi; đánh dấu lại để trở về tác vụ đang chạy.
- **Tự cuộn** có thể tắt để đọc dòng cũ mà không bị kéo về cuối.
- Nhật ký có màu phân biệt lỗi, thử lại, link và nội dung đã lưu.
- **Lưu log** xuất toàn bộ nhật ký trên đĩa, không chỉ các dòng đang hiện.

## Nhật ký và tiếp tục sau khi đổi mạng

Nhật ký ghi các bước: bắt đầu, link gốc, thư mục, khôi phục mốc, link chương đang tải, số phần, HTTP, thời gian nghỉ, số lần thử lại, phần đã lưu, tệp đã ghép, link chương tiếp và kết quả.

Khi lỗi, các dòng cuối gồm:

```text
[LỖI] Mô tả lỗi cụ thể
[LINK LỖI CUỐI] https://.../chuong-dang-tai · Phần 2
[YÊU CẦU LỖI] https://... (nếu khác link chương)
[TIẾP TỤC] Hướng dẫn chạy lại từ tiến độ đã lưu
```

Ô **Link hiện tại / lỗi** vẫn giữ link đó, có nút **Chép link**. Link và phần lỗi được lưu trong dữ liệu tác vụ và tệp `<mã-tác-vụ>.last-error.txt`; đóng/mở ứng dụng không làm mất thông tin đã lưu.

Quy trình sau lỗi mạng:

1. Đổi mạng hoặc khôi phục kết nối nếu cần.
2. Chọn đúng dòng tác vụ có lỗi.
3. Bấm **Tiếp tục tải**. Tác vụ này được ưu tiên trước các truyện còn chờ và hàng đợi bắt đầu chạy ngay.

WikiCV tiếp tục cùng checkpoint; phần đã có và hợp lệ được dùng lại. Các plugin cũ có khả năng khôi phục khác nhau; không khẳng định mọi nguồn đều bỏ qua chương đã tải. FanFicFare phát link chương trước mỗi lượt lấy nội dung, nhưng chạy lại không bảo đảm bỏ qua chương cũ.

**Dừng** dừng tác vụ và cả hàng đợi. **Tạm dừng** dừng ở điểm kiểm tra tiếp theo; yêu cầu mạng đang chạy có thể vẫn hoàn thành. FanFicFare chưa hỗ trợ tạm dừng tại chỗ. Đóng ứng dụng sẽ chờ tác vụ dừng an toàn.

## WikiCV nhiều phần

Vẫn lưu từng phần riêng và kiểm tra đủ trước khi ghép tệp chương. Không đổi cấu trúc lưu của bản 5.0. Một trang “Đệ 393–399 chương” tạo một tệp chứa toàn bộ các phần của trang; chưa tự tách các chương con thành từng tệp.

Nên dùng link chương đầu muốn tải. Chỉ một số kiểu mục lục được nhận diện; khi không tìm được link đọc, ứng dụng yêu cầu link chương.

HTTP 429 tôn trọng `Retry-After`; lỗi kết nối/máy chủ được thử có giới hạn. Khi đã lỗi, hàng đợi dừng để bạn kiểm tra và tiếp tục thủ công. Không chạy nhiều tác vụ cùng lúc hoặc tự xoay mạng.

## Sửa riêng plugin

Vào **Nguồn & plugin → Mở plugin**, sửa đúng tệp nguồn rồi bấm **Nạp lại plugin** khi không có tác vụ đang chạy.

- `plugins/wikicv.py`: phân tích và lưu chương/phần WikiCV.
- `plugins/base.py`: kết nối HTTP chung, nhịp tải, thử lại, theo dõi link.
- `core/http_reader.py`: đọc HTTP thuần, không khởi chạy trình duyệt.
- `core/browser.py`: Chromium chạy nền hoặc hiện cửa sổ.
- `core/tasks.py`: hàng đợi, trạng thái, nhật ký và link lỗi.
- `main.py`: giao diện.

Plugin mới kế thừa `BaseCrawler`, triển khai `can_handle(url)` và `async start_download(url, save_folder)`; gọi `await self.checkpoint()` trong vòng lặp, `self.track_url(url, part)` trước khi xử lý chương/phần, `self.log(...)` để ghi nhật ký. `part` đếm từ 0; giao diện nhật ký hiển thị đếm từ 1.

Dùng `fetch_soup`/`fetch_response` để nhận cơ chế kết nối chung. Chỉ trả `{"completed": True, "output_path": str(folder)}` khi đã xác nhận hoàn tất. Plugin cũ trả `None` được đánh dấu **Cần kiểm tra kết quả**, không báo tải đủ.

Có thể thêm nguồn HTML đơn giản bằng `plugins/sources.json`, tham khảo `sources.example.json`. Nguồn JavaScript đặc thù cần plugin riêng. Danh mục nguồn nhận diện không phải danh sách website đã được kiểm thử tải thành công.

## Dữ liệu

Dữ liệu ứng dụng: `%APPDATA%\NovelDownloader5` trên Windows; `~/.local/share/NovelDownloader5` trên Linux/macOS. Có thể thay bằng biến `NOVEL_DOWNLOADER_DATA` để kiểm thử riêng.

Giao diện giữ 1.500 dòng gần nhất mỗi tác vụ; tệp `.log` giữ toàn bộ dòng ghi trong bản này. Nhật ký và checkpoint cũ được giữ lại. Hồ sơ Chromium, nếu dùng, ở `browser-profile`; không chia sẻ hồ sơ chứa phiên đăng nhập.

Linux/macOS: cài thư viện từ `requirements.txt`, cần Tk hệ thống rồi chạy `python main.py`. Nếu cần Chromium, cài thêm `requirements-browser.txt` và chạy `python -m playwright install chromium`.

## Kiểm thử

`python -m pip install pytest` rồi `python -m pytest -q tests`.

Xem `KIEM_THU.md` để biết phạm vi đã kiểm thử và phần chưa xác minh trên website thật.
