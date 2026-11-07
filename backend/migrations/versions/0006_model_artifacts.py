"""Durable model artifacts shared by API instances and workers."""
from alembic import op
from backend.app.database import ModelArtifact
revision='0006'
down_revision='0005'

def upgrade():
    ModelArtifact.__table__.create(op.get_bind(),checkfirst=True)

def downgrade():
    raise RuntimeError('Forward-only migration preserves trained artifacts.')
