"""Attributable revocable sessions and explicit user-role links."""
from alembic import op
from sqlalchemy import select
from backend.app.database import Base,User
from backend.app.security_models import UserSession,UserRoleBinding
revision='0003'
down_revision='0002'
def upgrade():
    bind=op.get_bind();Base.metadata.create_all(bind)
    from backend.app.domain import Role
    for role in ['admin','reviewer','viewer']:
        if not bind.execute(select(Role.id).where(Role.id==role)).first():bind.execute(Role.__table__.insert().values(id=role,description=role.title()))
    for user in bind.execute(select(User.id,User.role)).mappings():
        if not bind.execute(select(UserRoleBinding.user_id).where(UserRoleBinding.user_id==user['id'])).first():
            bind.execute(UserRoleBinding.__table__.insert().values(user_id=user['id'],role_id=user['role']))
def downgrade():raise RuntimeError('Forward-only migration preserves attributable session records.')
