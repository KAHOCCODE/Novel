# Kiểm tra bản 5.1.1 — 01/10/2026

26 kiểm thử logic đều đạt; đã kiểm tra cú pháp toàn bộ mã Python.

7 kiểm thử mới kiểm tra: chỉ xóa cache được ghi nhận và giữ tệp truyện/thông tin/tệp lạ; giữ cache của truyện chưa xong; giữ cache khi chương bị sửa hoặc bị xóa; giữ phần cache tự chỉnh; xác minh đầy đủ chương cũ trước khi dọn; không đi theo liên kết tệp ra ngoài; nút dọn chỉ loại tác vụ completed và lưu lịch sử/nhật ký.

Bản cập nhật chỉ thay tệp khác giữa 5.1 và 5.1.1, đã thử áp dụng lên bản 5.1 sạch và chạy lại để kiểm tra không thay lần hai.

Chưa thử tải xuyên suốt trên WikiCV thật hoặc chạy bản cập nhật trên Windows thật. Kiểm thử dọn tệp dùng thư mục tạm và dữ liệu mô phỏng. Các kết quả giao diện dưới đây thuộc bản 5.1; bản 5.1.1 chỉ thêm nút Dọn đã xong vào thanh hàng đợi.

---

# Kiểm tra bản 5.1 — 01/10/2026

- 19 kiểm thử logic tự động đều đạt.
- Kiểm tra cú pháp toàn bộ mã Python bằng compileall.
- Giữ các kiểm thử 5.0 về thứ tự phần, cache, ngắt mạng, không lưu chương thiếu, HTTP 429, số lần thử giới hạn, trạng thái hoàn tất và hàng đợi.
- Bổ sung kiểm thử link chương/phần/yêu cầu bị lỗi được ghi đúng và còn sau khi mở lại; tác vụ tiếp tục được ưu tiên trước tác vụ chờ; link gốc không bị thay thế bằng link lỗi.
- Bổ sung kiểm thử chế độ HTTP không gọi BrowserSession, từ chối lưu chương thiếu phần động, chuyển cách tải vẫn dùng cùng checkpoint/cache, chế độ nền không mở cửa sổ để xác minh, không nhận nhầm nội dung Phần 1 thành Phần 2.
- Chạy giao diện Tk 8.6 trên màn hình ảo Linux ở 1280×720 và 940×620; kiểm tra kích thước nhật ký, phóng/thu, vị trí nút lưu tùy chọn, cửa sổ nguồn và việc thêm tác vụ chờ không đổi nhật ký khỏi tác vụ đang chạy.
- `GIAO_DIEN.png` là ảnh chụp giao diện thật với tác vụ và nhật ký kiểm thử minh họa, không phải bằng chứng đã tải truyện đó trên mạng.

Chưa xác minh tải xuyên suốt trên WikiCV thật: truy cập từ môi trường kiểm tra trả “Site Unavailable”. Không khẳng định đã thử thành công HTTP nhiều phần động, phiên Chromium chạy nền, CAPTCHA hoặc tất cả các nguồn thật.

Chưa chạy các tệp BAT trên Windows thật. Việc không mở cửa sổ của chế độ nền được cấu hình bằng `headless=True`; luồng dừng khi cần xác minh có kiểm thử logic, còn khả năng trang cho phép phiên nền phải kiểm tra thực tế.

Bản này không có API HTTP phỏng đoán cho nút phần JavaScript của WikiCV. Với `href="#!"` mà không có link trực tiếp, chế độ HTTP dừng minh bạch, giữ phần đã lưu và đề nghị người dùng tự chọn Chromium chạy nền để tiếp tục. Không âm thầm mở trình duyệt và không ghi một chương còn thiếu phần.
