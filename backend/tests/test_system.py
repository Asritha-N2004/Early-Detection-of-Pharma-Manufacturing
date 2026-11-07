import os,sys,json,uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
import pytest
os.environ.setdefault('DATABASE_URL','sqlite:///./test-pharma.db')
os.environ['BOOTSTRAP_PASSWORD']='test-only-password-2026'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import Session,Audit,Reading,verify
from backend.app.analytics import assess,analyze,METHODS
from backend.app.schemas import Measurement

@pytest.fixture(scope='module')
def client():
 with TestClient(app) as c:yield c
@pytest.fixture(scope='module')
def auth(client):
 r=client.post('/api/v1/auth/login',json={'username':'admin','password':os.environ['BOOTSTRAP_PASSWORD']});assert r.status_code==200
 return {'Authorization':'Bearer '+r.json()['access_token']}
def dataset():
 start=datetime.now(timezone.utc)-timedelta(hours=4)
 return [{'process':'fermentation','batch':'TEST-'+str(BATCH),'equipment':'EQ-TEST','timestamp':(start+timedelta(minutes=t)).isoformat(),'parameter':'temperature','value':37+.02*(t%3) if t<25 else 39+(t-25)*.05,'unit':'°C','source':'synthetic'} for t in range(45)]
BATCH=uuid.uuid4().hex[:8]
def test_health_auth(client):
 assert client.get('/health').json()['status']=='ok'
 assert client.get('/api/v1/processes').status_code==401
 assert client.post('/api/v1/auth/login',json={'username':'admin','password':'wrong'}).status_code==401
def test_data_validation(client,auth):
 rows=dataset();rows.append(rows[0].copy());missing=rows[1]|{'value':None,'timestamp':(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()};rows.append(missing)
 response=client.post('/api/v1/data/ingest',headers=auth,json={'records':rows})
 assert response.status_code==200,response.text
 assert response.json()['accepted']==45
 assert response.json()['duplicates']==1
 assert response.json()['quality_events']>=2
 assert client.post('/api/v1/data/ingest',headers=auth,json={'records':[rows[0]|{'timestamp':'bad'}]}).status_code==422
 assert client.post('/api/v1/data/ingest',headers=auth,json={'records':[rows[0]|{'timestamp':'2020-01-01T00:00:00'}]}).status_code==422
def test_risk_override():
 assert assess(5,5,5)['rpn']==125
 assert assess(1,1,1,patient_safety=True)['classification']=='Critical'
 assert assess(1,1,1)['classification']=='Low'
@pytest.mark.parametrize('method',METHODS+['ensemble'])
def test_algorithms(method):
 f=analyze(dataset(),[{'name':'temperature','low':36,'high':38}],method)
 assert f[0]['flag'] and 0<=f[0]['score']<=1
 assert f[0]['baseline']<38
def test_workflow_review_report_audit(client,auth):
 body={'process':'fermentation','batch':'TEST-'+str(BATCH),'event_id':'test-'+uuid.uuid4().hex,'method':'ensemble'}
 r=client.post('/api/v1/agents/workflow/run',json=body,headers=auth)
 assert r.status_code==200,r.text
 result=r.json();assert result['status']=='awaiting_human_review'
 assert len(result['result']['logs'])==10
 assert result['result']['hypotheses']
 repeated=client.post('/api/v1/agents/workflow/run',json=body,headers=auth)
 assert repeated.json()['id']==result['id']
 assert client.post('/api/v1/agents/workflow/run',json=body|{'horizon':60},headers=auth).status_code==409
 id=result['deviation_id']
 review=client.post('/api/v1/deviations/'+id+'/review',json={'decision':'escalate','notes':'Review calibration records and source measurements.'},headers=auth)
 assert review.status_code==200 and review.json()['confirmed'] is False
 for format in ['json','csv','pdf']:
  report=client.post('/api/v1/reports/generate',json={'deviation_id':id,'format':format},headers=auth)
  assert report.status_code==200
  download=client.get('/api/v1/reports/'+report.json()['id'],headers=auth)
  assert download.status_code==200
  if format=='pdf':assert download.content.startswith(b'%PDF')
 audit=client.get('/api/v1/audit/logs',headers=auth).json()
 assert audit['integrity_verified']
 assert any(a['action']=='report.generated' for a in audit['entries'])
def test_role_protection(client,auth):
 username='viewer'+uuid.uuid4().hex[:7]
 r=client.post('/api/v1/users',json={'username':username,'password':'viewer-test-password','role':'viewer'},headers=auth);assert r.status_code==200
 token=client.post('/api/v1/auth/login',json={'username':username,'password':'viewer-test-password'}).json()['access_token']
 h={'Authorization':'Bearer '+token}
 assert client.post('/api/v1/simulation',headers=h,json={'action':'start'}).status_code==403
 assert client.get('/api/v1/audit/logs',headers=h).status_code==403
def test_simulator(client,auth):
 for action in ['start','pause','step','stop','reset']:
  r=client.post('/api/v1/simulation',headers=auth,json={'action':action,'scenario':'spike'})
  assert r.status_code==200,r.text
 assert r.json()['ticks']==0
def test_config_and_upload(client,auth):
 assert client.post('/api/v1/settings/risk',headers=auth,json={'medium':50,'high':20,'critical':90}).status_code==422
 r=client.post('/api/v1/data/upload',headers=auth,files={'file':('bad.exe',b'bad','text/plain')})
 assert r.status_code==422
 with Session() as db:
  assert verify(db)
  row=db.query(Audit).first();row.action='tampered'
  with pytest.raises(Exception):db.commit()
def test_no_data_workflow(client,auth):
 r=client.post('/api/v1/agents/workflow/run',headers=auth,json={'process':'liquid','batch':'not-present','event_id':str(uuid.uuid4())})
 assert r.status_code==422
