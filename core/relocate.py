"""Copy one WikiCV story and rebase its checkpoint; keep the original intact."""
import copy
import hashlib
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urldefrag, urlparse

from core.storage import read_json, atomic_json


def relocate_task(task, destination):
    if task['state'] in {'running', 'paused', 'waiting_verification', 'stopping'}:
        raise ValueError('Dừng tác vụ trước khi đổi nơi lưu.')
    old = Path(task['folder']).resolve()
    new = Path(destination).resolve()
    updated = copy.deepcopy(task)
    if old == new: return updated
    if new.is_relative_to(old) or old.is_relative_to(new):
        raise ValueError('Chọn thư mục riêng, không lồng trong thư mục lưu cũ và không chứa thư mục cũ.')
    url = urldefrag(task['url'])[0]
    host = (urlparse(url).hostname or '').lower()
    key = hashlib.sha256(url.encode()).hexdigest()[:12]
    checkpoint = old/'.noveldownloader'/f'wikicv-{key}.json'
    new.mkdir(parents=True, exist_ok=True)
    if host not in {'wikicv.org', 'www.wikicv.org'}:
        raise ValueError('Chuyển tiến độ hiện hỗ trợ WikiCV. Plugin khác cần cách chuyển riêng.')
    if not checkpoint.exists():
        if task.get('current', 0) or task.get('output_path'):
            raise ValueError('Không tìm thấy mốc tải cũ. Giữ đường dẫn hiện tại để tránh tải lại từ đầu.')
        updated['folder'] = str(new)
        return updated
    if checkpoint.is_symlink() or not checkpoint.resolve().is_relative_to(old):
        raise ValueError('Mốc tải nằm ngoài thư mục cũ; chưa chuyển.')
    state = read_json(checkpoint, None)
    if not isinstance(state, dict) or state.get('url') != url:
        raise ValueError('Mốc tải không khớp tác vụ; chưa chuyển.')
    target_state = new/'.noveldownloader'/checkpoint.name
    if not target_state.resolve().is_relative_to(new):
        raise ValueError('Nơi lưu tiến độ mới có liên kết ngoài; chưa chuyển.')
    if target_state.exists():
        raise ValueError('Nơi mới đã có tiến độ của truyện này. Chọn thư mục khác để tránh ghi đè.')
    rebased = copy.deepcopy(state)
    source = Path(state['folder']).resolve() if state.get('folder') else None
    target = new/source.name if source else None
    if not source and state.get('files'):
        raise ValueError('Mốc tải thiếu thư mục truyện; chưa chuyển.')
    if source:
        if source == old or not source.is_relative_to(old) or not source.is_dir() or Path(state['folder']).is_symlink():
            raise ValueError('Không tìm thấy thư mục truyện hợp lệ bên trong nơi lưu cũ.')
        if target.exists():
            raise ValueError('Nơi mới đã có thư mục cùng tên truyện. Chọn nơi khác; không ghi đè hoặc trộn dữ liệu.')
        def remap(value):
            path = Path(value).resolve()
            if not path.is_relative_to(source):
                raise ValueError('Mốc tải chứa đường dẫn ngoài thư mục truyện; chưa chuyển.')
            return str(target/path.relative_to(source))
        rebased['folder'] = str(target)
        rebased['files'] = [remap(x) for x in state.get('files', [])]
        rebased['file_hashes'] = {remap(k): v for k, v in state.get('file_hashes', {}).items()}
        for value in state.get('files', []):
            if not Path(value).is_file(): raise ValueError('Thiếu tệp chương cũ; chưa chuyển tiến độ.')
        for p in source.rglob('*'):
            if p.is_symlink() or not p.resolve().is_relative_to(source):
                raise ValueError('Thư mục truyện chứa liên kết ngoài; chưa chuyển.')
        staging = Path(tempfile.mkdtemp(prefix='.nd-copy-', dir=new))
        try:
            staged = staging/'story'
            shutil.copytree(source, staged)
            for p in source.rglob('*'):
                if p.is_file():
                    other = staged/p.relative_to(source)
                    if hashlib.sha256(p.read_bytes()).digest() != hashlib.sha256(other.read_bytes()).digest():
                        raise OSError('Kiểm tra bản sao không khớp; chưa đổi nơi lưu.')
            if target.exists(): raise FileExistsError('Thư mục đích vừa được tạo bởi tiến trình khác; chưa chuyển.')
            staged.rename(target)
        finally:
            shutil.rmtree(staging)
        updated['output_path'] = str(target)
    atomic_json(target_state, rebased)
    updated['folder'] = str(new)
    return updated
