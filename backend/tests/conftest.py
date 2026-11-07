"""Select an isolated database before any application module is imported."""
import os
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
if not os.getenv('TEST_DATABASE_URL'):
    os.environ['DATABASE_URL']='sqlite:///./test-pharma-'+uuid.uuid4().hex+'.db'
else:
    os.environ['DATABASE_URL']=os.environ['TEST_DATABASE_URL']
os.environ['BOOTSTRAP_PASSWORD']='test-only-password-2026'

os.environ['EMBEDDED_WORKER']='0'
