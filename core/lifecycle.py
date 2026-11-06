"""Delete only named application-owned data; never walk arbitrary download trees."""
import hashlib,re,shutil
from pathlib import Path
from urllib.parse import urldefrag,urlparse
from core.storage import read_json

def remove_owned_tree(path, parent):
    path,parent=Path(path),Path(parent).resolve()
    if path.is_symlink() or not path.resolve().is_relative_to(parent) or path.resolve()==parent:
        raise ValueError('Từ chối xóa liên kết/thư mục ngoài vùng dữ liệu: '+str(path))
    if path.exists():
        for p in path.rglob('*'):
            if p.is_symlink() or not p.resolve().is_relative_to(path.resolve()):raise ValueError('Có liên kết ngoài trong '+str(path))
        shutil.rmtree(path)

def clean_task(task,data_dir):
    if task['state']!='completed':raise ValueError('Chỉ dọn truyện đã hoàn tất.')
    root=Path(task['folder']).resolve()
    if (urlparse(task['url']).hostname or '').lower() in ('wikicv.org','www.wikicv.org'):
        key=hashlib.sha256(urldefrag(task['url'])[0].strip().encode()).hexdigest()[:12]
        cp=root/'.noveldownloader'/f'wikicv-{key}.json'
        if cp.is_symlink() or not cp.resolve().is_relative_to(root):raise ValueError('Tiến độ nằm ngoài nơi lưu.')
        if cp.exists():
            state=read_json(cp,{})
            folder=Path(state.get('folder','')).resolve()
            if not state.get('completed') or not state.get('files') or folder==root or not folder.is_relative_to(root):
                raise ValueError('Chưa đủ bằng chứng hoàn tất; giữ tiến độ.')
            for name in state['files']:
                p=Path(name)
                if p.is_symlink() or p.resolve().parent!=folder or not p.is_file() or not p.stat().st_size:
                    raise ValueError('Thiếu chương hoặc tệp chương rỗng; chưa dọn: '+str(p))
            # User explicitly requests removal of all parts, including orphan parts.
            # Edited final TXT remains untouched; hashes need not match the downloaded original.
            remove_owned_tree(folder/'.parts',folder)
            meta=folder/'thong_tin_truyen.txt'
            if meta.is_symlink():raise ValueError('Thông tin truyện là liên kết ngoài.')
            meta.unlink(missing_ok=True)
            cp.unlink()
            try:cp.parent.rmdir()
            except OSError:pass
    tid=task['id']
    if not re.fullmatch(r'[0-9a-f]{32}',tid):raise ValueError('Mã tác vụ không hợp lệ.')
    data=Path(data_dir)
    for suffix in ('.log','.last-error.txt'):
        p=data/(tid+suffix)
        if p.is_symlink():raise ValueError('Nhật ký là liên kết ngoài.')
        p.unlink(missing_ok=True)
    remove_owned_tree(data/'sessions'/tid,data)
    task['logs']=[];task['cleaned']=True;task.pop('cleanup_error',None)

def bytes_used(path):
    path=Path(path)
    if not path.exists():return 0
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file() and not p.is_symlink())
