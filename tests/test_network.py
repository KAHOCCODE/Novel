import asyncio
from pathlib import Path
import sys
import threading
from unittest.mock import AsyncMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from core.network import NetworkPolicy, NetworkFailure
from core.tasks import TaskManager
from plugins.base import BaseCrawler, VerificationRequired, DownloadStopped
from plugins.wikicv import WikiCVCrawler
from test_workflows import Registry, FakeBrowser, URL, page


def policy(settings='(user set) Mode: WarpProxy on port 40000', ips=None):
    logs, commands = [], []
    p = NetworkPolicy('warp_auto', log=logs.append)
    async def cli(command):
        commands.append(command)
        return settings if command == 'settings' else 'Success'
    p.cli = cli
    p.trace = AsyncMock(side_effect=ips or ['203.0.113.1'] * 20)
    p.sleep = AsyncMock()
    return p, logs, commands


@pytest.mark.parametrize('mode', ['WarpWithDnsOverHttps', 'TunnelOnly', 'DnsOverHttps', 'unknown'])
def test_never_disconnects_full_device_or_unknown_mode(mode):
    p, logs, commands = policy('Mode: '+mode)
    with pytest.raises(NetworkFailure, match='Local proxy'):
        asyncio.run(p.reconnect('test'))
    assert commands == ['settings']


def test_reconnect_ip_comparison_limits_and_cooldown():
    p, logs, commands = policy(ips=['203.0.113.1', '203.0.113.2', '203.0.113.2', '203.0.113.2'])
    async def run():
        assert await p.reconnect('403')
        assert await p.reconnect('timeout')
        assert not await p.reconnect('timeout')
    asyncio.run(run())
    assert commands.count('disconnect') == commands.count('connect') == 2
    assert any('ĐÃ ĐỔI IP KIỂM TRA' in line for line in logs)
    assert any('IP KHÔNG ĐỔI' in line for line in logs)
    assert p.sleep.await_args.args[0] > 59
    assert p.proxy == 'http://127.0.0.1:40000'


def test_wrong_port_or_admin_lock_does_not_reconnect():
    for settings in ['Mode: WarpProxy on port 4444', 'Mode: WarpProxy\nSwitch Locked: true']:
        p, _, commands = policy(settings)
        with pytest.raises(NetworkFailure): asyncio.run(p.reconnect('test'))
        assert commands == ['settings']


def test_stop_after_disconnect_still_reconnects():
    p, _, commands = policy()
    original = p.cli
    stopped = False
    async def cli(command):
        nonlocal stopped
        value = await original(command)
        if command == 'disconnect': stopped = True
        return value
    async def checkpoint():
        if stopped: raise DownloadStopped()
    p.cli, p.checkpoint = cli, checkpoint
    with pytest.raises(DownloadStopped): asyncio.run(p.reconnect('timeout'))
    assert commands[-1] == 'connect'


def test_direct_never_calls_warp():
    p = NetworkPolicy()
    p.cli = AsyncMock(side_effect=AssertionError('No WARP'))
    async def run():
        await p.prepare()
        assert not await p.reconnect('403')
    asyncio.run(run())
    assert p.proxy is None


class Response:
    def __init__(self, status, html): self.status, self.html, self.headers = status, html, {'Retry-After': '31'}
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def text(self, **kw): return self.html


class Session:
    def __init__(self, responses): self.responses, self.proxies = iter(responses), []
    def get(self, url, **kw):
        self.proxies.append(kw.get('proxy'))
        return next(self.responses)


def test_retry_after_before_reconnect_and_retry_same_url():
    c = BaseCrawler(lambda _: None); c.configure_run(network_mode='warp_auto')
    events = []
    async def sleep(seconds): events.append(('sleep', seconds))
    async def reconnect(reason): events.append(('reconnect', reason)); return True
    c.sleep_check_stop, c.network.reconnect = sleep, reconnect
    c.throttle = AsyncMock()
    session = Session([Response(403, 'Forbidden'), Response(200, 'chapter')])
    assert asyncio.run(c.fetch_response(session, URL)) == (200, 'chapter')
    assert events[0] == ('sleep', 31) and events[1][0] == 'reconnect'
    assert session.proxies == ['http://127.0.0.1:40000'] * 2
    assert c.current_url == URL


def test_captcha_never_triggers_reconnect():
    c = BaseCrawler(lambda _: None); c.configure_run(network_mode='warp_auto')
    c.network.reconnect = AsyncMock(side_effect=AssertionError('Must not reconnect CAPTCHA'))
    c.throttle = AsyncMock()
    with pytest.raises(VerificationRequired):
        asyncio.run(c.fetch_response(Session([Response(403, '<title>Just a moment...</title>')]), URL))


def test_wikicv_auto_resume_failed_part_preserves_completed_part(tmp_path, monkeypatch):
    part_calls = []
    class Browser(FakeBrowser):
        async def part(self, pn):
            part_calls.append(pn)
            if len(part_calls) == 1: raise NetworkFailure('Phần 2 mất mạng')
            return page(pn)
    class Wiki(WikiCVCrawler):
        def __init__(self, log):
            super().__init__(log)
            self.browser_factory = Browser
    monkeypatch.setattr(NetworkPolicy, 'prepare', AsyncMock())
    reconnect = AsyncMock(return_value=True)
    monkeypatch.setattr(NetworkPolicy, 'reconnect', reconnect)
    m = TaskManager(tmp_path/'data', Registry(Wiki))
    t = m.add(URL, str(tmp_path/'out'), network_mode='warp_auto')
    m.auto_run = True; m.start_next(); m.worker.join(3); m.drain()
    assert t['state'] == 'completed'
    assert part_calls == [1, 1] and reconnect.await_count == 1
    output = next((tmp_path/'out').glob('*/0001_*.txt')).read_text()
    assert output.count('Nội dung đầu.') == output.count('Nội dung cuối.') == 1
    assert t['logs'] == [] and t['cleaned']
    assert not list((tmp_path/'out').glob('*/.parts'))
    assert not list((tmp_path/'out').glob('.noveldownloader/*.json'))
    assert TaskManager(tmp_path/'data', Registry(Wiki)).tasks[0]['network_mode'] == 'warp_auto'
