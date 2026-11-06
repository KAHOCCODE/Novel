"""Small, user-facing projections of task state and the diagnostic journal."""
import re

URL = re.compile(r'https?://[^\s]+')
TIME = re.compile(r'^(\d{2}:\d{2}:\d{2})\s+(.*)$')


def short_error(text):
    text = URL.sub('', str(text or '')).strip(' :·\n')
    text = re.sub(r'^(?:NetworkFailure|RuntimeError|Error|TimeoutError):\s*', '', text)
    if 'ERR_NO_SUPPORTED_PROXIES' in text:
        return 'Chromium không nhận cấu hình proxy. Kiểm tra kết nối trong Cài đặt.'
    if 'ERR_' in text or 'Không mở được trang sau' in text:
        return 'Không kết nối được trang bằng Chromium. Tiến độ đã được giữ lại.'
    if 'JavaScript' in text and 'HTTP trực tiếp' in text:
        return 'Trang dùng JavaScript. Chọn cách tải Tự động trong Cài đặt rồi thử lại.'
    if 'xác minh' in text or 'VerificationRequired' in text:
        return 'Nguồn yêu cầu xác minh. Chọn Chromium hiện cửa sổ trong Cài đặt để xác minh.'
    return text[:220] or 'Tải chưa thành công. Tiến độ đã được giữ lại.'


def selected_action(task, active_id):
    if not task:
        return None
    state = task['state']
    if active_id:
        return ('Đã xác minh', 'verify') if state == 'waiting_verification' and task['id'] == active_id else None
    if state in {'failed', 'stopped', 'needs_review'}:
        return ('Tải tiếp', 'retry')
    if state == 'held':
        return ('Đưa vào hàng đợi', 'enqueue')
    return None


def activity_lines(lines, technical=False):
    if technical:
        return [(None, line, 'error' if '[LỖI]' in line else 'normal') for line in lines[-250:]]
    # A retry starts a new readable session; older attempts remain in technical view.
    start = next((i for i in range(len(lines)-1, -1, -1) if '[BẮT ĐẦU]' in lines[i]), 0)
    result = []
    for line in lines[start:]:
        match = TIME.match(line)
        stamp, text = match.groups() if match else ('', line)
        tag = 'normal'
        if text.startswith('[BẮT ĐẦU]'):
            text = 'Bắt đầu tải.'
        elif text.startswith('[KHÔI PHỤC]'):
            number = re.search(r'mục (\d+)', text)
            text = f'Tiếp tục từ mục {number[1]}.' if number else 'Đọc lại tiến độ đã lưu.'
        elif text.startswith('[TỰ ĐỘNG]'):
            text = 'Chuyển sang bộ tải JavaScript.'
        elif text.startswith('Đã lưu đủ '):
            text = 'Đã lưu ' + text.partition(': ')[2]
            tag = 'success'
        elif text.startswith('[ĐÃ LƯU PHẦN]'):
            parts = re.search(r'(\d+)/(\d+)', text)
            if not parts or parts[2] == '1':
                continue
            text = text.replace('[ĐÃ LƯU PHẦN]', 'Đã lưu phần', 1).strip()
            tag = 'success'
        elif text.startswith('Đã có:'):
            parts = re.search(r'Phần (\d+/\d+)', text)
            if not parts:
                continue
            text = f'Dùng lại phần {parts[1]} đã lưu.'
        elif text.startswith('[TẠM DỪNG]'):
            text = 'Đã tạm dừng.'
        elif text.startswith('[TIẾP TỤC] Đã tiếp tục'):
            text = 'Tiếp tục tải.'
        elif text.startswith('[DỪNG]'):
            text = 'Đã dừng. Tiến độ được giữ lại.'
        elif text.startswith('[HOÀN TẤT]'):
            text = 'Đã tải xong.'
            tag = 'success'
        elif text.startswith('[THỬ LẠI]'):
            number = re.search(r'lần (\d+/\d+)', text)
            text = 'Kết nối gián đoạn · thử lại' + (f' {number[1]}.' if number else '.')
            tag = 'warn'
        elif text.startswith('Kết nối trình duyệt bị ngắt'):
            text = text.partition(' Chi tiết:')[0]
            tag = 'warn'
        elif text.startswith(('[HTTP ', '[KẾT NỐI]', '[NGHỈ]', '[CHƯƠNG]', '[PHẦN ',
                              '[ĐANG TẢI]', '[CHƯƠNG TIẾP]', '[LINK ', '[YÊU CẦU ',
                              '[THƯ MỤC]', '[CHẾ ĐỘ ', '[TIẾP TỤC]', '[CÓ LỖI]',
                              '[ĐÃ DỪNG]', '[LỖI]')):
            continue
        else:
            text = URL.sub('', text).strip(' ·:')
            if not text:
                continue
        if not result or result[-1][1] != text:
            result.append((stamp, text, tag))
    return result[-150:]
