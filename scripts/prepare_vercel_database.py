"""Migrate only the new project's database, using its ignored env export."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for line in (ROOT/'.env.vercel.production').read_text().splitlines():
    if line.startswith('DATABASE_URL='):
        value=line.partition('=')[2]
        os.environ['DATABASE_URL']=json.loads(value) if value.startswith('"') else value
        break
else:raise RuntimeError('Project DATABASE_URL not found')
os.environ.update(json.loads((ROOT/'.env.vercel.secrets').read_text()))
from alembic.config import Config
from alembic import command
command.upgrade(Config(str(ROOT/'alembic.ini')),'head')
from backend.app.main import init
init()
from backend.app.database import engine
from sqlalchemy import inspect
print('Hosted PostgreSQL initialized; tables:',len(inspect(engine).get_table_names()))
