"""Durable LangGraph saver and execution journal on SQLite or PostgreSQL.

Separate transactions keep partial execution evidence after application rollback.
Only the server can write serialized checkpoints; they are never upload formats.
"""
import os
import json
import threading
import uuid
from sqlalchemy import create_engine, String, Text, LargeBinary, Integer, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple, WRITES_IDX_MAP
from .database import now, canonical, database_url

class CheckpointBase(DeclarativeBase):
    pass

class CheckpointRow(CheckpointBase):
    __tablename__ = 'workflow_checkpoints'
    thread: Mapped[str] = mapped_column(String, primary_key=True)
    namespace: Mapped[str] = mapped_column(String, primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(String, primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    type: Mapped[str] = mapped_column(String)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    metadata_json: Mapped[str] = mapped_column(Text)

class WriteRow(CheckpointBase):
    __tablename__ = 'workflow_checkpoint_writes'
    thread: Mapped[str] = mapped_column(String, primary_key=True)
    namespace: Mapped[str] = mapped_column(String, primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    index: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    data: Mapped[bytes] = mapped_column(LargeBinary)

class ExecutionRow(CheckpointBase):
    __tablename__ = 'workflow_execution_journal'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String, index=True)
    created: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[str] = mapped_column(Text)

def checkpoint_url():
    configured = os.getenv('CHECKPOINT_DATABASE_URL')
    if configured:
        return configured
    database = os.getenv('DATABASE_URL', 'sqlite:///./pharma.db')
    return database.replace('.db', '-workflows.db') if database.startswith('sqlite') else database

class DatabaseSaver(BaseCheckpointSaver):
    def __init__(self, url=None):
        super().__init__()
        url = url or checkpoint_url()
        self.engine = create_engine(database_url(url), pool_pre_ping=True, connect_args={'check_same_thread': False, 'timeout': 30} if url.startswith('sqlite') else {})
        CheckpointBase.metadata.create_all(self.engine)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        self.lock = threading.RLock()

    def get_tuple(self, config):
        c = config['configurable']
        with self.lock, self.sessions() as db:
            q = db.query(CheckpointRow).filter_by(thread=c['thread_id'], namespace=c.get('checkpoint_ns', ''))
            if c.get('checkpoint_id'):
                q = q.filter_by(checkpoint_id=c['checkpoint_id'])
            row = q.order_by(CheckpointRow.checkpoint_id.desc()).first()
            if row is None:
                return None
            config = {'configurable': {'thread_id': row.thread, 'checkpoint_ns': row.namespace, 'checkpoint_id': row.checkpoint_id}}
            parent = {'configurable': {**config['configurable'], 'checkpoint_id': row.parent_id}} if row.parent_id else None
            writes = db.query(WriteRow).filter_by(thread=row.thread, namespace=row.namespace, checkpoint_id=row.checkpoint_id).order_by(WriteRow.task_id, WriteRow.index).all()
            return CheckpointTuple(config, self.serde.loads_typed((row.type, row.data)), json.loads(row.metadata_json), parent,
                                   [(w.task_id, w.channel, self.serde.loads_typed((w.type, w.data))) for w in writes])

    def put(self, config, checkpoint, metadata, new_versions):
        c = config['configurable']
        kind, data = self.serde.dumps_typed(checkpoint)
        with self.lock, self.sessions.begin() as db:
            db.merge(CheckpointRow(thread=c['thread_id'], namespace=c.get('checkpoint_ns', ''), checkpoint_id=checkpoint['id'], parent_id=c.get('checkpoint_id'), type=kind, data=data, metadata_json=canonical(metadata)))
        return {'configurable': {'thread_id': c['thread_id'], 'checkpoint_ns': c.get('checkpoint_ns', ''), 'checkpoint_id': checkpoint['id']}}

    def put_writes(self, config, writes, task_id, task_path=''):
        c = config['configurable']
        with self.lock, self.sessions.begin() as db:
            for index, (channel, value) in enumerate(writes):
                index = WRITES_IDX_MAP.get(channel, index)
                key = (c['thread_id'], c.get('checkpoint_ns', ''), c['checkpoint_id'], task_id, index)
                if index >= 0 and db.get(WriteRow, key):
                    continue
                kind, data = self.serde.dumps_typed(value)
                db.merge(WriteRow(thread=key[0], namespace=key[1], checkpoint_id=key[2], task_id=task_id, index=index, channel=channel, type=kind, data=data))

    def list(self, config, *, filter=None, before=None, limit=None):
        with self.lock, self.sessions() as db:
            q = db.query(CheckpointRow)
            if config:
                c = config['configurable']
                q = q.filter_by(thread=c['thread_id'], namespace=c.get('checkpoint_ns', ''))
            if before:
                q = q.filter(CheckpointRow.checkpoint_id < before['configurable']['checkpoint_id'])
            keys = [(r.thread, r.namespace, r.checkpoint_id) for r in q.order_by(CheckpointRow.checkpoint_id.desc()).all()]
        count = 0
        for thread, namespace, id in keys:
            item = self.get_tuple({'configurable': {'thread_id': thread, 'checkpoint_ns': namespace, 'checkpoint_id': id}})
            if filter and any(item.metadata.get(k) != v for k, v in filter.items()):
                continue
            yield item
            count += 1
            if limit is not None and count >= limit:
                return

    def journal(self, workflow_id, payload):
        with self.lock, self.sessions.begin() as db:
            db.add(ExecutionRow(id=str(uuid.uuid4()), workflow_id=workflow_id, created=now(), payload=canonical(payload)))

    def logs(self, workflow_id=None, limit=100, offset=0):
        with self.sessions() as db:
            q = db.query(ExecutionRow)
            if workflow_id:
                q = q.filter_by(workflow_id=workflow_id)
            return [{'id': r.id, 'workflow_id': r.workflow_id, 'created': r.created, **json.loads(r.payload)} for r in q.order_by(ExecutionRow.created.desc()).offset(offset).limit(limit)]

_saver = None
def saver():
    global _saver
    if _saver is None:
        _saver = DatabaseSaver()
    return _saver
