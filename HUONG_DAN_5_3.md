# Novel Downloader 5.3

Cập nhật tại chỗ từ đúng bản NovelDownloader-v5.1(1).zip đã gửi ngày 14/10/2026.
Đóng mọi cửa sổ ứng dụng, chạy CapNhat_NovelDownloader_5_3.pyw và chọn thư mục chứa main.py.
Không cần đổi tên thư mục 5.1, tải lại ZIP hay cài lại môi trường Python.

## Thao tác

- Dán link, Thêm vào hàng đợi, Chạy hàng đợi. Mỗi lần chỉ tải một truyện.
- Chờ lượt: chưa tới lượt; Giãn cách tải / Thử lại + số giây: sẽ tự tiếp tục.
- Tạm dừng: chờ bạn bấm Tiếp tục. Để sau: không tự chạy, kể cả khi hàng đợi đã chạy.
- Cần xác minh: dùng chế độ Chromium hiện cửa sổ, hoàn tất xác minh rồi bấm Đã xác minh.
- Gặp lỗi hoặc plugin chưa xác nhận kết quả: dừng phiên để bạn xử lý; giữ link lỗi và tiến độ.
- Chọn truyện để thấy nơi lưu, link hiện tại/lỗi và thao tác riêng. Nhật ký mở theo nhu cầu.
- Menu Thao tác cho phép xếp thứ tự, mở nơi lưu, xuất log và chuyển nơi lưu.
- Tịnh Ngôn Cốc đã gỡ; tác vụ cũ của nguồn này được để sau, không cản hàng đợi.

## Nơi lưu

Dữ liệu ứng dụng mới nằm ở .nd-data cạnh main.py (trừ khi chủ động cấu hình NOVEL_DOWNLOADER_DATA).
Ví dụ ứng dụng ở F:\NovelDownloader-v5.1 thì hàng đợi, cấu hình và phiên tạm mới nằm cùng ổ F:.
Lần đầu mở sẽ nhập settings.json và tasks.json từ AppData\Roaming\NovelDownloader5 nếu chưa có dữ liệu mới.
Không tự xóa bản cũ trước khi bạn kiểm tra. Dữ liệu & dung lượng có nút dọn dữ liệu bản cũ và báo những mục còn lại.

Đổi nơi lưu mặc định trong Cài đặt chỉ áp dụng cho truyện thêm mới.
Truyện WikiCV tải dở: chọn Thao tác → Chuyển nơi lưu truyện này. Ứng dụng sao chép, kiểm tra, cập nhật tiến độ rồi mới xóa bản cũ.
Nơi đích đã có cùng truyện/tiến độ thì dừng, không tự trộn hoặc ghi đè. Plugin khác cần chuyển theo khả năng riêng, chưa hỗ trợ chuyển tự động.
Không đổi thư mục bằng cách chỉ sửa đường dẫn trong JSON.

## Dọn sạch

WikiCV: sau khi xác nhận hoàn tất và mọi tệp chương vẫn tồn tại, khác rỗng, xóa toàn bộ .parts (kể cả phần mồ côi), thông tin phụ do ứng dụng tạo và checkpoint. Giữ nguyên TXT chương, kể cả đã chỉnh sửa.
Tác vụ hoàn tất: xóa log, link lỗi ghi ra tệp và hồ sơ trình duyệt riêng của tác vụ. Hàng đợi giữ một dòng kết quả nhỏ để mở thư mục.
Dọn hoàn tất: xóa luôn các dòng kết quả, không tạo completed-history.json.
Truyện tải dở hoặc thiếu tệp đầu ra: giữ dữ liệu khôi phục, báo rõ lý do chưa dọn.
Plugin cũ chỉ kết thúc mà không xác nhận tải đủ: trạng thái Cần kiểm tra kết quả, không coi là hoàn tất để xóa dữ liệu.

Nhật ký trên màn hình: 100 dòng cuối. Nhật ký trong hàng đợi: 250 dòng cuối. Tệp log đang chạy giới hạn khoảng 512 KB.
Dữ liệu & dung lượng hiển thị đường dẫn, đo dung lượng và cho phép dọn phiên tạm khi đã dừng.
Trình duyệt dùng chung, môi trường Python và bản sao lưu cập nhật là phần mềm/bản sao lưu, không bị xóa mù quáng. Các đường dẫn liên quan được nêu rõ.

## Giữ lõi tải

Giữ parser WikiCV, thứ tự ghép phần, lưu chương nguyên tử, kiểm tra phần trùng/thiếu và cơ chế không ghi đè chương đã chỉnh.
Khôi phục kết nối WARP từ bản 5.2 vì ZIP có mô-đun nhưng thiếu điểm gọi trong BaseCrawler/TaskManager.
WARP chỉ dùng khi bạn bật trong Cài đặt, yêu cầu warp-cli mode proxy và đúng cổng; không bảo đảm mỗi lần kết nối lại đổi IP, không tự giải CAPTCHA.
FanFicFare chưa hỗ trợ WARP tự kết nối lại; ứng dụng báo lỗi trước khi tải nếu chọn kết hợp này.

## Giới hạn kiểm thử

Có kiểm thử tự động cho multipart, resume, proxy, hủy/tạm dừng, đường dẫn, dữ liệu chỉnh sửa, dọn sạch và cập nhật/hoàn nguyên.
Không thể đảm bảo mọi website luôn hoạt động: cấu trúc và chính sách truy cập của nguồn có thể thay đổi.
