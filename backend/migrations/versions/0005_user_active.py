"""Disable access without deleting attributable identities or review history."""
from alembic import op
from sqlalchemy import Boolean,inspect,text
revision='0005'
down_revision='0004'
def upgrade():
    bind=op.get_bind()
    if 'active' not in {c['name'] for c in inspect(bind).get_columns('users')}:
        op.add_column('users',__import__('sqlalchemy').Column('active',Boolean(),nullable=False,server_default=text('true')))
def downgrade():raise RuntimeError('Preserve historical identities using a forward migration.')
