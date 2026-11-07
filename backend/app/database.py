import os, json, hashlib, threading
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, Float, ForeignKey, UniqueConstraint, event,Boolean,LargeBinary
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

class Base(DeclarativeBase): pass
class User(Base):
 __tablename__='users'
 id: Mapped[str]=mapped_column(String,primary_key=True)
 password: Mapped[str]=mapped_column(Text)
 role: Mapped[str]=mapped_column(String)
 active: Mapped[bool]=mapped_column(Boolean,default=True,server_default='1')
class Configuration(Base):
 __tablename__='system_configurations'
 id: Mapped[str]=mapped_column(String,primary_key=True)
 payload: Mapped[str]=mapped_column(Text)
class ModelArtifact(Base):
 __tablename__='model_artifacts'
 digest: Mapped[str]=mapped_column(String(64),primary_key=True)
 data: Mapped[bytes]=mapped_column(LargeBinary)
class Reading(Base):
 __tablename__='sensor_readings'
 __table_args__=(UniqueConstraint('process','batch','equipment','timestamp','parameter'),)
 id: Mapped[str]=mapped_column(String,primary_key=True)
 process: Mapped[str]=mapped_column(String,index=True)
 batch: Mapped[str]=mapped_column(String,index=True)
 equipment: Mapped[str]=mapped_column(String)
 timestamp: Mapped[str]=mapped_column(String,index=True)
 parameter: Mapped[str]=mapped_column(String)
 value: Mapped[float]=mapped_column(Float)
 unit: Mapped[str]=mapped_column(String)
 source: Mapped[str]=mapped_column(String)
 original: Mapped[str]=mapped_column(Text)
class Record(Base):
 """Versioned JSON analytical documents; explicit type and lookup indexes."""
 __tablename__='analytical_records'
 id: Mapped[str]=mapped_column(String,primary_key=True)
 kind: Mapped[str]=mapped_column(String,index=True)
 created: Mapped[str]=mapped_column(String,index=True)
 payload: Mapped[str]=mapped_column(Text)
class Review(Base):
 __tablename__='human_reviews'
 id: Mapped[str]=mapped_column(String,primary_key=True)
 deviation_id: Mapped[str]=mapped_column(ForeignKey('analytical_records.id'),index=True)
 user_id: Mapped[str]=mapped_column(ForeignKey('users.id'))
 created: Mapped[str]=mapped_column(String)
 payload: Mapped[str]=mapped_column(Text)
class Audit(Base):
 __tablename__='audit_logs'
 sequence: Mapped[int]=mapped_column(primary_key=True,autoincrement=True)
 created: Mapped[str]=mapped_column(String)
 actor: Mapped[str]=mapped_column(String)
 action: Mapped[str]=mapped_column(String)
 payload: Mapped[str]=mapped_column(Text)
 previous: Mapped[str]=mapped_column(String)
 digest: Mapped[str]=mapped_column(String)

def now(): return datetime.now(timezone.utc).isoformat()
def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
def database_url(value):
 return value.replace('postgres://','postgresql+psycopg://',1).replace('postgresql://','postgresql+psycopg://',1)
engine=create_engine(database_url(os.getenv('DATABASE_URL','sqlite:///./pharma.db')),pool_pre_ping=True,connect_args={'check_same_thread':False} if os.getenv('DATABASE_URL','sqlite:').startswith('sqlite') else {})
if engine.dialect.name=='sqlite':
 @event.listens_for(engine,'connect')
 def sqlite_integrity(connection,record):
  connection.execute('PRAGMA foreign_keys=ON')
  connection.execute('PRAGMA busy_timeout=30000')
Session=sessionmaker(engine,expire_on_commit=False)
lock=threading.RLock()
def init_db():
 from . import domain, security_models, jobs
 Base.metadata.create_all(engine)
 if engine.dialect.name=='sqlite':
  with engine.begin() as c:
   c.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_logs BEGIN SELECT RAISE(ABORT, 'append only'); END")
   c.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_logs BEGIN SELECT RAISE(ABORT, 'append only'); END")
   c.exec_driver_sql('PRAGMA journal_mode=WAL')
def audit(db,actor,action,payload):
 # Serialize writers across processes through a PostgreSQL advisory transaction lock.
 if engine.dialect.name=='postgresql':
  from sqlalchemy import text
  db.execute(text('SELECT pg_advisory_xact_lock(814252)'))
 prior=db.query(Audit).order_by(Audit.sequence.desc()).first()
 values={'created':now(),'actor':actor,'action':action,'payload':canonical(payload),'previous':prior.digest if prior else '0'*64}
 row=Audit(**values,digest=hashlib.sha256(canonical(values).encode()).hexdigest())
 db.add(row); db.flush()
def verify(db):
 prev='0'*64
 for r in db.query(Audit).order_by(Audit.sequence):
  v={k:getattr(r,k) for k in ['created','actor','action','payload','previous']}
  if r.previous!=prev or hashlib.sha256(canonical(v).encode()).hexdigest()!=r.digest:return False
  prev=r.digest
 return True
