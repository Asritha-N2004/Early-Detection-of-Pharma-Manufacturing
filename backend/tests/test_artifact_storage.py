import hashlib,uuid
import pytest
from backend.app.database import init_db,Session,ModelArtifact,database_url
from backend.app import model_runtime

def test_postgres_driver_urls():
    assert database_url('postgresql://db/example')=='postgresql+psycopg://db/example'
    assert database_url('postgres://db/example')=='postgresql+psycopg://db/example'
    assert database_url('sqlite:///test.db')=='sqlite:///test.db'

def test_database_artifact_survives_missing_and_corrupt_cache(monkeypatch,tmp_path):
    init_db();monkeypatch.setenv('MODEL_STORAGE','database');monkeypatch.setattr(model_runtime,'MODEL_ROOT',tmp_path)
    bundle={'version':uuid.uuid4().hex,'coefficients':[1,2,3]}
    with Session.begin() as db:location,digest=model_runtime.store_artifact(db,'test',bundle)
    model={'artifact':location,'artifact_sha256':digest}
    assert model_runtime.load_artifact(model)==bundle
    path=tmp_path/(digest+'.joblib');path.write_bytes(b'corrupt cache')
    assert model_runtime.load_artifact(model)==bundle
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    path.unlink()
    assert model_runtime.load_artifact(model)==bundle
    with Session.begin() as db:db.get(ModelArtifact,digest).data=b'corrupt durable artifact'
    with pytest.raises(ValueError,match='integrity'):model_runtime.checked_artifact(model)

def test_database_artifact_rejects_untrusted_key():
    with pytest.raises(ValueError,match='integrity'):
        model_runtime.checked_artifact({'artifact':'database:../../untrusted','artifact_sha256':'../../untrusted'})
