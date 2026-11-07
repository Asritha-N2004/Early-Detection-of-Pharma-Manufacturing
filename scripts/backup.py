"""Non-destructive database backup with checksums; restore to a separate database.

Stop writers for a consistent cross-database SQLite snapshot. PostgreSQL uses pg_dump.
Never prints connection strings or credentials.
"""
import os,sys,json,hashlib,sqlite3,subprocess
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse,unquote
from sqlalchemy.engine import make_url

def backup(destination):
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=False)
    url=make_url(os.getenv('DATABASE_URL','sqlite:///./pharma.db'));files=[]
    if url.drivername.startswith('sqlite'):
        main=Path(url.database).resolve();sources=[main,Path(str(main).replace('.db','-workflows.db'))]
        for source in sources:
            if not source.exists():continue
            target=destination/source.name
            with sqlite3.connect(source) as src,sqlite3.connect(target) as dst:src.backup(dst)
            files.append(target)
    else:
        env={**os.environ,'PGPASSWORD':url.password or ''};target=destination/'pharma.dump'
        subprocess.run(['pg_dump','--host',url.host or 'localhost','--port',str(url.port or 5432),'--username',url.username or 'pharma','--dbname',url.database,'--format=custom','--file',str(target)],env=env,check=True)
        files.append(target)
    artifact_dir=Path('ml/models')
    import shutil
    if artifact_dir.exists():
        for source in artifact_dir.glob('*.joblib'):
            target=destination/'models'/source.name;target.parent.mkdir(exist_ok=True);shutil.copy2(source,target);files.append(target)
    manifest={'created':datetime.now(timezone.utc).isoformat(),'database_type':url.get_backend_name(),'notice':'Protect backups as sensitive records. Test restore into a separate qualified environment.','files':{str(f.relative_to(destination)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest
def verify_backup(destination):
    root=Path(destination).resolve();manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files'].items():
        path=(root/name).resolve()
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:return False
    return True
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('destination');parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    print('Backup verification:',verify_backup(args.destination)) if args.verify else print('Backup created; file count:',len(backup(args.destination)['files']))
