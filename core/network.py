"""Explicit local WARP proxy with bounded reconnects; never changes client mode."""
import asyncio
import ipaddress
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import aiohttp


class NetworkFailure(RuntimeError):
    pass


class NetworkPolicy:
    def __init__(self, mode='direct', port=40000, log=lambda _: None, progress=lambda **kw: None):
        if mode not in {'direct', 'warp_auto'}:
            raise ValueError('Chế độ mạng không hợp lệ.')
        if not 1 <= int(port) <= 65535:
            raise ValueError('Cổng proxy phải từ 1 đến 65535.')
        self.mode, self.port, self.log, self.progress = mode, int(port), log, progress
        self.reconnects = 0
        self.last_reconnect = None
        self.last_ip = None
        self.sleep = asyncio.sleep
        self.checkpoint = self._noop

    async def _noop(self):
        pass

    @property
    def proxy(self):
        return f'http://127.0.0.1:{self.port}' if self.mode == 'warp_auto' else None

    async def cli(self, command):
        executable = shutil.which('warp-cli')
        if not executable and os.name == 'nt':
            candidate = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Cloudflare/Cloudflare WARP/warp-cli.exe'
            if candidate.is_file(): executable = str(candidate)
        if not executable:
            raise NetworkFailure('Không tìm thấy warp-cli. Cài WARP và thiết lập Local proxy trước.')
        kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        proc = await asyncio.create_subprocess_exec(executable, command, stdin=asyncio.subprocess.DEVNULL,
                                                   stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **kwargs)
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), 15)
        except BaseException:
            if proc.returncode is None: proc.kill()
            await proc.wait()
            raise
        if proc.returncode:
            message = (stderr or stdout).decode('utf-8', errors='replace').strip()[:400]
            raise NetworkFailure(f'WARP {command} thất bại: {message}')
        return stdout.decode('utf-8', errors='replace')

    async def guard(self):
        settings = await self.cli('settings')
        modes = re.findall(r'\bMode:\s*([A-Za-z]+)\b', settings)
        if modes != ['WarpProxy']:
            raise NetworkFailure('Chưa xác nhận WARP ở chế độ Local proxy (WarpProxy). Không tự bật/tắt VPN toàn máy. Hãy chọn Local proxy trong WARP trước.')
        port = re.search(r'\bMode:\s*WarpProxy\s+on port\s+(\d+)', settings)
        if port and int(port.group(1)) != self.port:
            raise NetworkFailure(f'Cổng WARP là {port.group(1)}, nhưng ứng dụng đang chọn {self.port}.')
        if re.search(r'\bSwitch Locked:\s*true\b', settings, re.I):
            raise NetworkFailure('WARP bị quản trị viên khóa kết nối; ứng dụng không tự điều khiển.')

    async def trace(self):
        try:
            async with aiohttp.ClientSession(trust_env=False, timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.get('https://www.cloudflare.com/cdn-cgi/trace', proxy=self.proxy) as response:
                    if response.status != 200: return None
                    values = dict(line.split('=', 1) for line in (await response.text()).splitlines() if '=' in line)
                    if values.get('warp') not in {'on', 'plus'}: return None
                    return str(ipaddress.ip_address(values.get('ip', '')))
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return None

    async def ready(self):
        for attempt in range(5):
            await self.checkpoint()
            current = await self.trace()
            if current: return current
            if attempt < 4: await self.sleep(2)
        raise NetworkFailure('Chưa kiểm tra được IP qua WARP sau khi kết nối; đã giữ tiến độ, không chuyển sang mạng trực tiếp.')

    async def prepare(self):
        if self.mode == 'direct': return
        await self.guard()
        self.last_ip = await self.trace()
        if not self.last_ip:
            await self.checkpoint()
            await self.guard()
            await self.cli('connect')
            self.last_ip = await self.ready()
        self.log(f'[PROXY] WARP 127.0.0.1:{self.port} · IP kiểm tra: {self.last_ip}. Tự kết nối lại tối đa 2 lần/tác vụ.')

    async def reconnect(self, reason):
        if self.mode != 'warp_auto': return False
        if self.reconnects >= 2:
            self.log('[PROXY] Đã dùng 2 lần tự kết nối lại; dừng phục hồi tự động, giữ link và tiến độ.')
            return False
        if self.last_reconnect is not None:
            remaining = max(0, 60 - (time.monotonic() - self.last_reconnect))
            if remaining:
                self.log(f'[PROXY] Nghỉ {remaining:.0f}s trước lần kết nối lại kế tiếp.')
                await self.sleep(remaining)
        await self.checkpoint()
        await self.guard()
        before = await self.trace() or self.last_ip
        self.reconnects += 1
        self.log(f'[PROXY {self.reconnects}/2] {reason} · IP trước: {before or "chưa kiểm tra được"} · đang ngắt/kết nối lại WARP.')
        # Once disconnect is attempted, always attempt reconnection even if stop is requested.
        # Guard again because users may have changed WARP mode in its own UI.
        try:
            await self.cli('disconnect')
        finally:
            await self.guard()
            await self.cli('connect')
            self.last_reconnect = time.monotonic()
        current = await self.ready()
        if before and current != before:
            self.log(f'[ĐÃ ĐỔI IP KIỂM TRA] {before} → {current}. Thử lại chương/phần đang lỗi.')
        elif before:
            self.log(f'[IP KHÔNG ĐỔI] {current}. WARP đã kết nối lại; thử lại nhưng không bảo đảm hết bị chặn.')
        else:
            self.log(f'[PROXY ĐÃ KẾT NỐI] IP kiểm tra: {current}; không có IP trước để so sánh.')
        self.last_ip = current
        return True
