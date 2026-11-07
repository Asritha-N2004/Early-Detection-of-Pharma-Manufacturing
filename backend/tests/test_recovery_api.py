import uuid
from backend.tests.test_system import client,auth
from backend.tests.test_features import seeded
from backend.app.workflow import AGENTS

def test_failure_is_queryable_and_recovers_same_event(client,auth,seeded,monkeypatch):
    original=AGENTS['root_cause']
    def fail(s):raise RuntimeError('Injected source-history analysis fault')
    monkeypatch.setitem(AGENTS,'root_cause',fail)
    request={'process':'fermentation','batch':seeded+'-5','event_id':uuid.uuid4().hex,'method':'zscore'}
    result=client.post('/api/v1/agents/workflow/run',headers=auth,json=request)
    assert result.status_code==500
    import hashlib
    id=hashlib.sha256(request['event_id'].encode()).hexdigest()
    status=client.get('/api/v1/agents/workflow/'+id,headers=auth)
    assert status.status_code==200 and status.json()['status']=='failed'
    assert status.json()['recoverable']
    monkeypatch.setitem(AGENTS,'root_cause',original)
    resumed=client.post('/api/v1/agents/workflow/'+id+'/recover',headers=auth,json={})
    assert resumed.status_code==200,resumed.text
    assert resumed.json()['status']=='awaiting_human_review' and resumed.json()['deviation_id']
    logs=client.get('/api/v1/agents/execution-logs?workflow_id='+id+'&limit=1000',headers=auth).json()
    assert sum(l.get('agent')=='data_ingestion' and l['status']=='completed' for l in logs)==1
    assert any(l.get('agent')=='root_cause' and l['status']=='failed' for l in logs)
