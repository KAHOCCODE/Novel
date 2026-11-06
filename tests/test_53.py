import asyncio,hashlib,json,threading
from pathlib import Path
import pytest
from core.lifecycle import clean_task
from core.local_data import prepare_data
from core.tasks import TaskManager
from core.relocate import relocate_task
from core.storage import atomic_json,read_json
from plugins.base import BaseCrawler
from core.plugin_manager import PluginManager
from test_workflows import Registry,Legacy,URL

def fixture(tmp_path):
    root=tmp_path/'out';story=root/'Story';story.mkdir(parents=True)
    final=story/'0001_chapter.txt';final.write_text('user edited story')
    parts=story/'.parts'/'orphan';parts.mkdir(parents=True);(parts/'0.txt').write_text('cached')
    (story/'thong_tin_truyen.txt').write_text('metadata')
    key=hashlib.sha256(URL.encode()).hexdigest()[:12];cp=root/'.noveldownloader'/f'wikicv-{key}.json'
    state=dict(url=URL,folder=str(story),files=[str(final)],file_hashes={str(final):'old hash'},completed=True,index=2,parts={})
    atomic_json(cp,state)
    task=dict(id='a'*32,state='completed',folder=str(root),url=URL,logs=['old log'])
    data=tmp_path/'data';data.mkdir();(data/(task['id']+'.log')).write_text('log')
    return task,data,cp,story,final

def test_complete_removes_all_orphans_preserves_edited_txt(tmp_path):
    t,d,cp,story,final=fixture(tmp_path);clean_task(t,d)
    assert list(story.iterdir())==[final]
    assert final.read_text()=='user edited story'
    assert not cp.exists() and not list(d.glob('*.log')) and t['logs']==[]
    clean_task(t,d) # safe repeated cleanup

def test_missing_output_retains_recovery(tmp_path):
    t,d,cp,story,final=fixture(tmp_path);final.unlink()
    with pytest.raises(ValueError,match='Thiếu chương'):clean_task(t,d)
    assert cp.exists() and (story/'.parts').exists()

def test_cleanup_rejects_outside_symlink(tmp_path):
    t,d,cp,story,final=fixture(tmp_path);outside=tmp_path/'private.txt';outside.write_text('keep')
    (story/'.parts'/'link').symlink_to(outside)
    with pytest.raises(ValueError):clean_task(t,d)
    assert outside.read_text()=='keep' and cp.exists()

def test_hold_order_persists_restart(tmp_path):
    m=TaskManager(tmp_path/'data',Registry(Legacy));a=m.add(URL,str(tmp_path/'out'));b=m.add(URL+'/2',str(tmp_path/'out'))
    m.hold(a['id']);m.move(b['id'],-1)
    restored=TaskManager(m.data_dir,Registry(Legacy))
    assert [t['id'] for t in restored.tasks]==[b['id'],a['id']]
    assert restored.tasks[1]['state']=='held'
    restored.auto_run=True;restored.start_next();restored.worker.join(2);restored.drain()
    assert restored.tasks[1]['state']=='held' and not restored.auto_run

def test_wait_countdown_clears_after_stop(tmp_path):
    c=BaseCrawler(lambda _:None);events=[];c.configure_run(progress_callback=lambda p:events.append(p))
    asyncio.run(c.sleep_check_stop(.025))
    assert events[0]['wait_remaining']==1 and events[-1]['wait_remaining']==0

def test_migration_only_once_preserves_dest_and_limits_logs(tmp_path,monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile,'tempdir',str(tmp_path))
    monkeypatch.setenv('APPDATA',str(tmp_path/'legacy'));monkeypatch.delenv('NOVEL_DOWNLOADER_DATA',raising=False)
    old=tmp_path/'legacy'/'NovelDownloader5';old.mkdir(parents=True)
    atomic_json(old/'tasks.json',[dict(logs=['x']*1000)])
    atomic_json(old/'settings.json',dict(folder='F:/Downloads'))
    new=prepare_data(tmp_path/'app');assert len(read_json(new/'tasks.json',[])[0]['logs'])==250
    atomic_json(new/'settings.json',dict(folder='G:/New'))
    prepare_data(tmp_path/'app');assert read_json(new/'settings.json',{})['folder']=='G:/New'

def test_removed_source_cannot_fallback():
    pm=PluginManager(lambda _:None)
    assert pm.find_handler('https://tinhngoncoc.net/book/') is None
    assert not any('tinhngoncoc' in str(x).lower() for x in pm.get_source_catalog())

def test_relocation_rebases_and_rejects_collision(tmp_path):
    t,d,cp,story,final=fixture(tmp_path);t.update(state='stopped',output_path=str(story),current=1)
    moved=relocate_task(t,tmp_path/'new')
    st=read_json(tmp_path/'new'/'.noveldownloader'/cp.name,{})
    assert st['folder']==moved['output_path'] and str(tmp_path/'new') in st['files'][0]
    assert Path(st['files'][0]).read_text()=='user edited story'
    with pytest.raises(ValueError):relocate_task(t,tmp_path/'new')
