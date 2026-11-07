"""Initial prototype schema and append-only audit enforcement."""
from alembic import op
from backend.app.database import Base
revision='0001'
down_revision=None
def upgrade():
 bind=op.get_bind();Base.metadata.create_all(bind)
 if bind.dialect.name=='postgresql':
  op.execute("CREATE FUNCTION prevent_audit_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Audit records are append only'; END; $$ LANGUAGE plpgsql")
  op.execute('CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation()')
def downgrade():
 raise RuntimeError('Destructive downgrade disabled: preserve historical records and use reviewed forward migrations.')
