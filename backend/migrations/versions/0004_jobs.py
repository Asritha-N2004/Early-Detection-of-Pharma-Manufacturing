"""Durable worker queue with lease ownership."""
from alembic import op
from backend.app.jobs import WorkflowJob
revision='0004'
down_revision='0003'
def upgrade():WorkflowJob.__table__.create(op.get_bind(),checkfirst=True)
def downgrade():raise RuntimeError('Do not discard historical jobs; use a reviewed forward migration.')
