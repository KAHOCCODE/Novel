"""All new application data stays beside the selected installation."""
import os
import tempfile
from pathlib import Path
from core.storage import read_json, atomic_json

def legacy_dir():
    return Path(os.environ.get('APPDATA', Path.home()/'.local/share'))/'NovelDownloader5'

def prepare_data(root):
    target=Path(os.environ.get('NOVEL_DOWNLOADER_DATA') or Path(root)/'.nd-data').resolve()
    target.mkdir(parents=True,exist_ok=True)
    old=legacy_dir()
    marker=target/'migration.json'
    if target!=old.resolve() and not marker.exists():
        for name in ('settings.json','tasks.json'):
            if not (target/name).exists() and (old/name).is_file():
                value=read_json(old/name, {} if name=='settings.json' else [])
                if name=='tasks.json':
                    for task in value:task['logs']=task.get('logs',[])[-250:]
                atomic_json(target/name,value)
        atomic_json(marker,{'legacy':str(old),'imported':True})
    temp=target/'runtime';temp.mkdir(exist_ok=True)
    tempfile.tempdir=str(temp)
    os.environ['TMP']=os.environ['TEMP']=os.environ['TMPDIR']=str(temp)
    return target
