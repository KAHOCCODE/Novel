import asyncio
import hashlib
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.cleanup import cleanup_completed_story
from core.storage import atomic_json, read_json
from core.tasks import TaskManager
from test_workflows import Registry, Legacy, FakeBrowser, crawler, URL


def state_fixture(tmp_path):
    folder=tmp_path/'story'; folder.mkdir()
    out=folder/'0001_Chuong.txt';out.write_text('Chương 1\n\nNội dung.',encoding='utf-8')
    key=hashlib.sha256(URL.encode()).hexdigest()[:16]
    cache=folder/'.parts'/key;cache.mkdir(parents=True)
    part=cache/'0.txt';part.write_text('Nội dung.',encoding='utf-8')
    state=dict(completed=True, folder=str(folder.resolve()), files=[str(out.resolve())],
               file_hashes={str(out.resolve()):hashlib.sha256(out.read_bytes()).hexdigest()},
               parts={key:{'0':hashlib.sha256(part.read_bytes()).hexdigest()}}, done=[URL])
    path=tmp_path/'resume.json';atomic_json(path,state)
    return state,path,out,part


def test_cleanup_only_completed_known_cache(tmp_path):
    state,path,out,part=state_fixture(tmp_path)
    extra=part.parent/'my-note.txt';extra.write_text('user note')
    meta=out.parent/'thong_tin_truyen.txt';meta.write_text('Tác giả: A')
    saved=out.read_bytes()
    assert cleanup_completed_story(path,state,lambda _:None)==1
    assert not part.exists() and extra.read_text()=='user note' and meta.is_file()
    assert out.read_bytes()==saved and read_json(path,{})['completed']
    assert cleanup_completed_story(path,state,lambda _:None)==0


def test_incomplete_story_retains_all_cache(tmp_path):
    state,path,out,part=state_fixture(tmp_path);state['completed']=False
    assert cleanup_completed_story(path,state,lambda _:None)==0 and part.exists()


def test_modified_or_missing_final_keeps_cache(tmp_path):
    state,path,out,part=state_fixture(tmp_path);out.write_text('edited')
    assert cleanup_completed_story(path,state,lambda _:None)==0 and part.exists()
    out.unlink()
    assert cleanup_completed_story(path,state,lambda _:None)==0 and part.exists()


def test_modified_cache_is_not_deleted(tmp_path):
    state,path,out,part=state_fixture(tmp_path);part.write_text('my edit')
    assert cleanup_completed_story(path,state,lambda _:None)==0 and part.read_text()=='my edit'


def test_legacy_completed_output_validated_before_cleanup(tmp_path):
    state,path,out,part=state_fixture(tmp_path);state.pop('file_hashes')
    assert cleanup_completed_story(path,state,lambda _:None)==1
    assert read_json(path,{})['file_hashes'] and not part.exists()


def test_symlink_outside_story_not_deleted(tmp_path):
    state,path,out,part=state_fixture(tmp_path)
    external=tmp_path/'external.txt';external.write_bytes(part.read_bytes());part.unlink();part.symlink_to(external)
    assert cleanup_completed_story(path,state,lambda _:None)==0
    assert external.exists() and part.is_symlink()


def test_queue_cleanup_deletes_success_logs_without_archive(tmp_path):
    m=TaskManager(tmp_path/'data',Registry(Legacy))
    tasks=[]
    for i,status in enumerate(['completed','failed','stopped','queued','running','needs_review']):
        t=m.add(URL+f'/{i}',str(tmp_path/'out'));t['state']=status;tasks.append(t)
        (m.data_dir/f'{t["id"]}.log').write_text('log')
    m.active_id=tasks[4]['id']
    assert m.clear_completed()==1
    assert [t['state'] for t in m.tasks]==['failed','stopped','queued','running','needs_review']
    assert not (m.data_dir/f'{tasks[0]["id"]}.log').exists()
    assert (m.data_dir/f'{tasks[1]["id"]}.log').read_text()=='log'
    assert not (m.data_dir/'completed-history.json').exists()
    assert m.clear_completed()==0
    assert len(TaskManager(m.data_dir,Registry(Legacy)).tasks)==5
