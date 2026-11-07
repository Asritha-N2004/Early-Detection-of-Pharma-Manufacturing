"""Relational domain and provenance indexes with existing-record backfill."""
from alembic import op
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.app.database import Base,Configuration,Reading,Record
from backend.app import domain
import json
revision='0002'
down_revision='0001'
def upgrade():
    bind=op.get_bind();Base.metadata.create_all(bind)
    config=bind.execute(select(Configuration.__table__).where(Configuration.id=='processes')).mappings().first()
    if config:domain.sync_processes(bind,json.loads(config['payload']))
    with Session(bind=bind) as db:
        for row in db.query(Reading).yield_per(500):
            exists=bind.execute(select(domain.ReadingContext.reading_id).where(domain.ReadingContext.reading_id==row.id)).first()
            if not exists:domain.reading_projection(bind,row)
        for kind in ['workflow','quality','anomaly','prediction','risk','deviation','model','report','execution_log']:
            for row in db.query(Record).filter_by(kind=kind).yield_per(500):domain.document_projection(bind,row)
def downgrade():
    raise RuntimeError('Forward-only migration preserves manufacturing evidence.')
