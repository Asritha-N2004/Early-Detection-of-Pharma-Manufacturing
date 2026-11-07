import json,uuid,sqlite3
from pathlib import Path
from datetime import datetime,timedelta,timezone
import numpy as np
import pytest
from backend.tests.test_system import client,auth
from backend.app.features import historical_features
from backend.app.validation_metrics import event_timing
from backend.app.database import Session,Record
from backend.app.model_runtime import checked_artifact

def test_disabled_identity_and_password_redaction(client,auth):
    user='disabled_'+uuid.uuid4().hex[:6];password='temporary-local-test-password'
    assert client.post('/api/v1/users',headers=auth,json={'username':user,'password':password,'role':'viewer'}).status_code==200
    token=client.post('/api/v1/auth/login',json={'username':user,'password':password}).json()['access_token']
    assert client.post(f'/api/v1/users/{user}/access',headers=auth,json={'active':False,'reason':'Temporary test identity is no longer required.'}).status_code==200
    assert client.get('/api/v1/processes',headers={'Authorization':'Bearer '+token}).status_code==401
    assert client.post('/api/v1/auth/login',json={'username':user,'password':password}).status_code==401
    secret='secret-'+('x'*80)
    error=client.post('/api/v1/users',headers=auth,json={'username':'invalid','password':secret,'role':'viewer'})
    assert error.status_code==422 and secret not in error.text

def test_risk_scales_and_contract_schemas(client,auth):
    body={'medium':30,'high':90,'critical':180,'severity_scale':6,'occurrence_scale':6,'detectability_scale':6,'critical_parameter_severity':5,'procedure_reference':'DEMO-TEST-UNAPPROVED'}
    assert client.post('/api/v1/settings/risk',headers=auth,json=body).status_code==200
    try:
        r=client.post('/api/v1/risk/assess',headers=auth,json={'severity':6,'occurrence':6,'detectability':6})
        assert r.status_code==200 and r.json()['rpn']==216
        assert client.post('/api/v1/risk/assess',headers=auth,json={'severity':7,'occurrence':6,'detectability':6}).status_code==422
    finally:client.post('/api/v1/settings/risk',headers=auth,json={'medium':20,'high':50,'critical':90})
    contracts=client.get('/api/v1/agents/contracts',headers=auth).json()
    assert len(contracts)==10 and all(isinstance(c['input_schema'],dict) for c in contracts)
    assert any(c['agent']=='risk_assessment' and 'risk' in c['output_schema'] for c in contracts)

def test_model_artifact_tamper_rejected():
    with Session() as db:row=db.query(Record).filter_by(kind='model').first()
    if not row:pytest.skip('Training fixture not available in a targeted run')
    model=json.loads(row.payload);path=checked_artifact(model);original=path.read_bytes()
    try:
        path.write_bytes(original+b'altered')
        with pytest.raises(ValueError,match='integrity'):checked_artifact(model)
    finally:path.write_bytes(original)
    with pytest.raises(ValueError):checked_artifact({**model,'artifact':'../untrusted.joblib'})

def test_temporal_metrics_and_feature_windows():
    start=datetime(2026,1,1,tzinfo=timezone.utc);times=[(start+timedelta(minutes=i)).isoformat() for i in range(10)]
    labels=[0,0,0,0,0,1,1,1,0,0];alerts=[0,0,0,0,1,1,1,1,0,0]
    metrics=event_timing(times,labels,alerts)
    assert metrics['event_count']==1 and metrics['mean_early_warning_lead_seconds']==60
    assert metrics['mean_detection_delay_seconds']==0
    missed=event_timing(times,labels,[0]*10)
    assert missed['event_recall']==0 and missed['mean_detection_delay_seconds'] is None
    rows=[{'timestamp':t,'parameter':'temperature','value':float(i)} for i,t in enumerate(times)]
    features=historical_features(rows[:6],window=4)[0]
    assert features['sample_count']==4 and features['mean']==3.5
    assert abs(features['slope_per_sample']-1)<1e-9
    from backend.app.forecasting import slope_per_minute,residual_envelope
    irregular=[(start+timedelta(minutes=i)).isoformat() for i in [0,1,2,5,7]]
    assert abs(slope_per_minute([0,2,4,10,14],irregular)-2)<1e-9
    regular=[(start+timedelta(minutes=i)).isoformat() for i in range(80)]
    envelope=residual_envelope(np.arange(80)*2,regular,15)
    assert envelope and envelope['calibration_samples']>=40 and envelope['radius']<1e-8

def test_backup_integrity_and_restore(tmp_path,monkeypatch):
    from scripts.backup import backup,verify_backup
    source=tmp_path/'source.db'
    with sqlite3.connect(source) as db:db.execute('CREATE TABLE evidence(id INTEGER, value TEXT)');db.execute("INSERT INTO evidence VALUES(1,'synthetic preserved record')")
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+str(source));monkeypatch.chdir(tmp_path)
    target=tmp_path/'backup';manifest=backup(target)
    assert verify_backup(target) and len(manifest['files'])==1
    with sqlite3.connect(target/'source.db') as restored:assert restored.execute('SELECT value FROM evidence').fetchone()[0]=='synthetic preserved record'
    with (target/'source.db').open('ab') as f:f.write(b'changed')
    assert not verify_backup(target)
