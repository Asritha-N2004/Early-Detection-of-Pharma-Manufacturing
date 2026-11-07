import json,uuid
from datetime import datetime,timedelta,timezone
import pytest
import numpy as np
from backend.tests.test_system import client,auth
from backend.app.database import Session,Record,Reading
from backend.app.domain import ReadingContext,ModelRegistry,AgentWorkflow,DeviationRecord,ProcessParameter,RolePermission
from backend.app.analytics import multivariate_analyze

@pytest.fixture(scope='module')
def seeded(client,auth):
    prefix='FEATURE-'+uuid.uuid4().hex[:6];rows=[]
    for b in range(6):
        for t in range(40):
            for parameter,unit,center,width in [('temperature','°C',37,2),('pH','pH',7.1,.6)]:
                abnormal=t>=25
                value=center+width*(.02*(t%3) if not abnormal else .8)
                rows.append({'process':'fermentation','batch':f'{prefix}-{b}','equipment':'FEATURE-EQ','timestamp':(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(days=b,minutes=t)).isoformat(),'parameter':parameter,'unit':unit,'value':value,'source':'synthetic','label':int(abnormal)})
    r=client.post('/api/v1/data/ingest',json={'records':rows},headers=auth);assert r.status_code==200,r.text
    return prefix

def test_governed_model_runtime(client,auth,seeded,monkeypatch):
    settings={'random_seed':42,'tree_estimators':40,'xgboost_max_depth':2,'contamination':.05,'svm_nu':.05,'autoencoder_iterations':100,'probability_threshold':.55,'anomaly_threshold':.65}
    assert client.post('/api/v1/settings/models',headers=auth,json=settings).status_code==200
    trained=client.post('/api/v1/models/train',headers=auth,json={});assert trained.status_code==200,trained.text
    model=trained.json()[0];id=model['id']
    assert model['calibration']['method']=='validation_batch_sigmoid'
    assert model['metrics']['event_timing']['event_count']>=1
    assert model['artifact_sha256']
    assert model['training_configuration']['tree_estimators']==40
    assert client.post(f'/api/v1/models/{id}/review',headers=auth,json={'action':'activate','rationale':'Verify explicit approval is required first.'}).status_code==409
    for action in ['approve','activate']:
        r=client.post(f'/api/v1/models/{id}/review',headers=auth,json={'action':action,'rationale':'Reviewed held-out synthetic evaluation and artifact integrity.'});assert r.status_code==200,r.text
    result=client.post('/api/v1/agents/workflow/run',headers=auth,json={'process':'fermentation','batch':seeded+'-5','event_id':uuid.uuid4().hex,'method':'zscore'})
    assert result.status_code==200,result.text
    runtime=result.json()['result']['model_prediction'];assert runtime['model_id']==id
    assert 0<=runtime['calibrated_probability']<=1
    assert runtime['decision_threshold']==.55
    assert runtime['shap'] and runtime['drift']
    checkpoint=client.get('/api/v1/agents/workflow/'+result.json()['id']+'/checkpoint',headers=auth)
    assert checkpoint.json()['next']==['human_review']
    import backend.app.main as main
    monkeypatch.setattr(main,'CONTROLLED',True)
    request={'process':'fermentation','batch':seeded+'-5','event_id':uuid.uuid4().hex,'method':'ensemble'}
    assert client.post('/api/v1/agents/workflow/run',headers=auth,json=request).status_code==409
    anomaly=next(m for m in trained.json() if m.get('task')=='anomaly')
    for action in ['approve','activate']:
        r=client.post('/api/v1/models/'+anomaly['id']+'/review',headers=auth,json={'action':action,'rationale':'Synthetic-only verification of approved frozen anomaly ensemble.'});assert r.status_code==200,r.text
    controlled=client.post('/api/v1/agents/workflow/run',headers=auth,json=request)
    assert controlled.status_code==200,controlled.text
    assert all(f['model_id']==anomaly['id'] for f in controlled.json()['result']['findings'])
    assert controlled.json()['result']['multivariate']['method'].startswith('approved_')
    with Session() as db:
        assert db.query(ModelRegistry).filter_by(id=id).one().status=='active'
        assert db.query(ReadingContext).count()==db.query(Reading).count()
        assert db.query(AgentWorkflow).count()>0

def test_reports_review_and_evidence(client,auth,seeded):
    e=client.post('/api/v1/equipment/events',headers=auth,json={'process':'fermentation','equipment':'FEATURE-EQ','timestamp':'2026-01-06T00:00:00+00:00','category':'calibration','evidence':'SYNTHETIC calibration check: reference thermometer comparison is pending.','synthetic':True});assert e.status_code==200,e.text
    run=client.post('/api/v1/agents/workflow/run',headers=auth,json={'process':'fermentation','batch':seeded+'-5','event_id':uuid.uuid4().hex}).json();id=run['deviation_id']
    assert any(h.get('equipment_evidence') for h in run['result']['hypotheses'])
    decision={'decision':'more_evidence','notes':'Obtain calibration source record before reviewing the recommendation.'}
    assert client.post(f'/api/v1/deviations/{id}/review',headers=auth,json=decision).status_code==200
    assert client.post(f'/api/v1/deviations/{id}/review',headers=auth,json=decision).json()['idempotent']
    decision={'decision':'accept','notes':'Accept investigation recommendation only; no manufacturing authorization.'}
    assert client.post(f'/api/v1/deviations/{id}/review',headers=auth,json=decision).status_code==200
    for family in ['deviation','investigation','root_cause','risk','early_warning','batch_monitoring','process_performance','model_performance']:
        for format in ['json','csv','pdf']:
            r=client.post('/api/v1/reports/generate',headers=auth,json={'family':family,'format':format,'deviation_id':id,'process':'fermentation','batch':seeded+'-5'})
            assert r.status_code==200,r.text
            assert client.get('/api/v1/reports/'+r.json()['id'],headers=auth).status_code==200
    assert len(client.get('/api/v1/agents/graph',headers=auth).json()['nodes'])>=12

def test_durable_job_claim_and_simulator_state(client,auth,seeded):
    from backend.app.jobs import claim,work_once,WorkflowJob
    request={'process':'fermentation','batch':seeded+'-5','event_id':uuid.uuid4().hex,'method':'zscore'}
    r=client.post('/api/v1/agents/workflow/enqueue',headers=auth,json=request);assert r.status_code==200,r.text
    assert client.post('/api/v1/agents/workflow/enqueue',headers=auth,json=request).json()['id']==r.json()['id']
    first=claim('worker-a');assert first and claim('worker-b') is None
    with Session.begin() as db:db.get(WorkflowJob,first['id']).lease_until='2000-01-01T00:00:00+00:00'
    replacement=claim('worker-b');assert replacement['id']==first['id']
    with Session.begin() as db:db.get(WorkflowJob,first['id']).status='queued'
    assert work_once('worker-c')
    assert next(j for j in client.get('/api/v1/agents/jobs',headers=auth).json() if j['id']==first['id'])['status']=='completed'
    r=client.post('/api/v1/simulation',headers=auth,json={'action':'reset','scenario':'equipment_fault'});assert r.status_code==200
    for _ in range(10):
        r=client.post('/api/v1/simulation',headers=auth,json={'action':'step','scenario':'equipment_fault'});assert r.status_code==200,r.text
    assert client.get('/api/v1/simulation',headers=auth).json()['ticks']==10
    assert client.get('/api/v1/equipment/events?process_id=fermentation',headers=auth).json()

def test_revocation_configuration_filters(client,auth,seeded):
    username='session_'+uuid.uuid4().hex[:7];password='local-session-test-password'
    assert client.post('/api/v1/users',headers=auth,json={'username':username,'password':password,'role':'viewer'}).status_code==200
    r=client.post('/api/v1/auth/login',json={'username':username,'password':password});headers={'Authorization':'Bearer '+r.json()['access_token']}
    assert client.post('/api/v1/auth/logout',headers=headers,json={}).status_code==200
    assert client.get('/api/v1/dashboard',headers=headers).status_code==401
    assert client.post('/api/v1/settings/agents',headers=auth,json={'timeout_seconds':30,'communication_gap_seconds':120,'drift_threshold':1.5,'prediction_horizon':30}).status_code==200
    assert client.get('/api/v1/settings',headers=auth).json()['agents']['timeout_seconds']==30
    r=client.get('/api/v1/data/records',headers=auth,params={'process':'fermentation','batch':seeded+'-0','equipment':'FEATURE-EQ','parameter':'pH','start':'2026-01-01T00:10:00+00:00','end':'2026-01-01T00:20:00+00:00'})
    assert r.status_code==200 and len(r.json())==11
    assert client.get('/api/v1/data/records?start=2026-01-01',headers=auth).status_code==422

def test_joint_relationship_shift_and_intervals():
    rng=np.random.default_rng(42);rows=[]
    for t in range(80):
        x=rng.normal(0,.2);y=x+rng.normal(0,.005) if t<55 else -x
        for name,value in [('a',x),('b',y)]:rows.append({'timestamp':str(t).zfill(3),'parameter':name,'value':value})
    rows[-2]['value']=.4;rows[-1]['value']=-.4
    result=multivariate_analyze(rows,[{'name':'a'},{'name':'b'}])
    assert result['flag'] and result['reference_samples']<len(rows)/2
