"""Remove only verified application cache, after the entire story completes."""
import hashlib
from pathlib import Path
from core.storage import atomic_json


def sha(data):
    return hashlib.sha256(data).hexdigest()


def cleanup_completed_story(state_path, state, log):
    if not state.get('completed') or not state.get('files'):
        return 0
    try:
        return _cleanup(state_path, state, log)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log(f'[DỌN DẸP] Chưa dọn được tệp tạm: {exc}. Tệp truyện được giữ nguyên.')
        return 0


def _cleanup(state_path, state, log):
    folder = Path(state['folder']).resolve()
    files = [Path(name) for name in state['files']]
    hashes = dict(state.get('file_hashes', {}))
    # Validate EVERY output before deleting ANY cache. Legacy 5.1 outputs can be
    # validated by reconstructing their bodies from the recorded ordered parts.
    for i, path in enumerate(files):
        if path.is_symlink() or path.resolve().parent != folder or not path.is_file():
            log('[DỌN DẸP] Giữ tệp tạm vì một tệp chương bị thiếu hoặc nằm ngoài thư mục truyện.')
            return 0
        data = path.read_bytes()
        expected = hashes.get(str(path.resolve()))
        if expected is None:
            urls = state.get('done', [])
            if i >= len(urls):
                log('[DỌN DẸP] Giữ tệp tạm vì chưa đủ dữ liệu kiểm tra chương cũ.')
                return 0
            key = sha(urls[i].encode())[:16]
            records = state.get('parts', {}).get(key, {})
            numbers = sorted(int(n) for n in records)
            if not numbers or numbers != list(range(len(numbers))):
                return 0
            content = []
            for n in numbers:
                part = folder/'.parts'/key/f'{n}.txt'
                if part.is_symlink() or not part.resolve().is_relative_to(folder) or not part.is_file():
                    return 0
                raw = part.read_bytes()
                if sha(raw) != records[str(n)]: return 0
                content.append(raw.decode('utf-8'))
            body = data.decode('utf-8').partition('\n\n')[2]
            if body != '\n\n'.join(content):
                log('[DỌN DẸP] Giữ tệp tạm vì nội dung chương cũ không khớp đủ các phần.')
                return 0
            expected = sha(data)
            hashes[str(path.resolve())] = expected
        if sha(data) != expected:
            log('[DỌN DẸP] Giữ tệp tạm vì tệp chương đã thay đổi sau khi tải.')
            return 0
    state['file_hashes'] = hashes
    # Persist proof first, so interrupted cleanup can resume safely.
    atomic_json(state_path, state)
    count = 0
    parts = state.setdefault('parts', {})
    for key, records in list(parts.items()):
        if len(key) != 16 or any(c not in '0123456789abcdef' for c in key):
            continue
        cache = folder/'.parts'/key
        if cache.is_symlink() or not cache.resolve().is_relative_to(folder):
            continue
        for number, expected in list(records.items()):
            if not str(number).isdigit(): continue
            path = cache/f'{number}.txt'
            if path.is_symlink(): continue
            if not path.exists():
                del records[number]
            elif path.is_file() and sha(path.read_bytes()) == expected:
                path.unlink(); count += 1; del records[number]
        if not records:
            del parts[key]
        try: cache.rmdir()
        except OSError: pass  # Never remove unrelated contents.
    try: (folder/'.parts').rmdir()
    except OSError: pass
    if not parts:
        state.pop('done', None)
        state['cleanup_completed'] = True
    atomic_json(state_path, state)
    log(f'[DỌN DẸP] Đã xóa {count} tệp phần lưu đệm; giữ chương truyện, thông tin truyện và mốc hoàn tất.')
    return count
