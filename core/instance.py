"""One queue writer per data directory; OS releases the lock after a crash."""
import os

def acquire(data):
    handle=open(data/'instance.lock','a+b')
    handle.seek(0);handle.write(b'0');handle.flush();handle.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError('Ứng dụng đang mở với cùng dữ liệu. Hãy dùng cửa sổ đang chạy.')
    return handle
