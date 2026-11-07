"""Bounded UI QA on a disposable copy of an already-created synthetic test database.

No production account creation or production database changes. Stop this process and
remove .qa-runtime after browser QA. Uses the existing test-suite identity only.
"""
import os,sqlite3
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sources=sorted((p for p in root.glob('test-pharma-*.db') if '-workflows' not in p.name),key=lambda p:p.stat().st_mtime,reverse=True)
if not sources:raise RuntimeError('Run the isolated test suite before UI fixture verification')
source=sources[0];target=root/'.qa-runtime';target.mkdir(exist_ok=True)
for src,dst in [(source,target/'qa.db'),(Path(str(source).replace('.db','-workflows.db')),target/'checkpoints.db')]:
    if src.exists():
        with sqlite3.connect(src) as inp,sqlite3.connect(dst) as out:inp.backup(out)
os.environ['DATABASE_URL']='sqlite:///'+str(target/'qa.db')
os.environ['CHECKPOINT_DATABASE_URL']='sqlite:///'+str(target/'checkpoints.db')
os.environ['BOOTSTRAP_PASSWORD']=''
os.environ['EMBEDDED_WORKER']='0'
os.environ['DEPLOYMENT_MODE']='demo'
import sys
sys.path.insert(0,str(root))
import uvicorn
print('Disposable synthetic test fixture only. Main application database is untouched.',flush=True)
uvicorn.run('backend.app.main:app',host='127.0.0.1',port=8012)
