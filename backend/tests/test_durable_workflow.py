import time
import uuid
import pytest
from langgraph.types import Command
from backend.app.checkpoints import DatabaseSaver
from backend.app.workflow import build_graph,AGENTS
from backend.tests.test_system import dataset

def state(normal=False):
    rows=dataset()
    if normal:
        for i,r in enumerate(rows):r['value']=37+(.015 if i%2 else -.015)
    return {'readings':rows,'parameters':[{'name':'temperature','low':36,'high':38,'unit':'°C'}],'method':'zscore','horizon':15,'interval_minutes':1.0,'request_digest':'fixture','agent_config':{'timeout_seconds':10}}

def test_checkpoint_survives_reconstruction(tmp_path):
    url='sqlite:///'+str(tmp_path/'durable.db');store=DatabaseSaver(url);id=uuid.uuid4().hex;config={'configurable':{'thread_id':id}}
    graph=build_graph(id,store);result=graph.invoke(state(),config)
    assert result['status']=='awaiting_human_review'
    assert graph.get_state(config).next==('human_review',)
    # A new engine/saver/graph object recovers from persisted bytes, not memory.
    fresh=DatabaseSaver(url);restarted=build_graph(id,fresh)
    result=restarted.invoke(Command(resume={'decision':'more_evidence','actor':'reviewer','notes':'Need equipment calibration and raw source records.'}),config)
    assert restarted.get_state(config).next==('human_review',)
    result=restarted.invoke(Command(resume={'decision':'escalate','actor':'reviewer','notes':'Escalate for quality assessment of source evidence.'}),config)
    assert result['status']=='escalated_to_quality'
    assert restarted.get_state(config).next==()
    assert len(list(fresh.list(config)))>10

def test_failed_node_recovers_without_replaying_completed_nodes(tmp_path,monkeypatch):
    store=DatabaseSaver('sqlite:///'+str(tmp_path/'failed.db'));id=uuid.uuid4().hex;config={'configurable':{'thread_id':id}}
    original=AGENTS['root_cause']
    def fail(s):raise ValueError('injected analytical failure')
    monkeypatch.setitem(AGENTS,'root_cause',fail)
    with pytest.raises(ValueError):build_graph(id,store).invoke(state(),config)
    assert any(l['status']=='failed' for l in store.logs(id))
    monkeypatch.setitem(AGENTS,'root_cause',original)
    result=build_graph(id,store).invoke(None,config)
    assert result['status']=='awaiting_human_review'
    assert sum(l['agent']=='data_ingestion' and l['status']=='completed' for l in store.logs(id))==1

def test_timeout_and_retry_journal(tmp_path,monkeypatch):
    store=DatabaseSaver('sqlite:///'+str(tmp_path/'timeout.db'));id=uuid.uuid4().hex
    def slow(s):time.sleep(.15);return {'summary':'discarded late result'}
    monkeypatch.setitem(AGENTS,'process_monitoring',slow)
    s=state();s['agent_config']={'timeout_seconds':.02}
    with pytest.raises(TimeoutError):build_graph(id,store).invoke(s,{'configurable':{'thread_id':id}})
    assert sum(l['status']=='timed_out' for l in store.logs(id))==2
    assert not any(l['agent']=='process_monitoring' and l['status']=='completed' for l in store.logs(id))

def test_invalid_transition_rejected_and_normal_branch(tmp_path,monkeypatch):
    store=DatabaseSaver('sqlite:///'+str(tmp_path/'normal.db'));id=uuid.uuid4().hex
    result=build_graph(id,store).invoke(state(normal=True),{'configurable':{'thread_id':id}})
    assert result['status']=='monitoring'
    assert not any(l['agent']=='root_cause' for l in store.logs(id))
    monkeypatch.setitem(AGENTS,'process_monitoring',lambda s:{'manufacturing_command':'forbidden'})
    with pytest.raises(ValueError):build_graph('invalid',store).invoke(state(),{'configurable':{'thread_id':'invalid'}})
