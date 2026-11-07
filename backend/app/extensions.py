"""Model governance, configurable agents, source history and complete report families."""
import json,uuid,hashlib
from datetime import datetime
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field,model_validator
from .database import Session,Configuration,Record,User,audit,canonical,now,lock
from .domain import Equipment,EquipmentEvent,Role,Permission,RolePermission,key
from .model_runtime import checked_artifact

def router_for(current,permit,docs,getdoc,save,process,readings):
    router=APIRouter(prefix='/api/v1')
    def verified_artifact(item):
        try:return checked_artifact(item)
        except (KeyError,ValueError,OSError) as exc:raise HTTPException(409,'Model artifact integrity check failed or this is a legacy artifact. Retrain before approval or activation.') from exc
    @router.get('/agents/workflows')
    def workflows(process_id:str|None=None,batch:str|None=None,limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0),u=Depends(current)):
        with Session() as db:
            items=docs(db,'workflow',10000)
            return [w for w in items if (not process_id or w['process']==process_id) and (not batch or w['batch']==batch)][offset:offset+limit]
    from .schemas import Run
    from .jobs import WorkflowJob,enqueue
    @router.post('/agents/workflow/enqueue')
    def queue_workflow(body:Run,u=Depends(permit('admin','reviewer'))):
        with Session() as db:process(db,body.process)
        return enqueue(body,u['id'])
    @router.get('/agents/jobs')
    def jobs(limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0),u=Depends(current)):
        with Session() as db:return [{'id':j.id,'created':j.created,'status':j.status,'attempts':j.attempts,'event_id':j.event_id,'result':json.loads(j.result) if j.result else None} for j in db.query(WorkflowJob).order_by(WorkflowJob.created.desc()).offset(offset).limit(limit)]
    @router.post('/agents/jobs/{id}/retry')
    def retry_job(id:str,u=Depends(permit('admin','reviewer'))):
        with lock,Session.begin() as db:
            job=db.get(WorkflowJob,id)
            if not job:raise HTTPException(404,'Job not found')
            if job.status!='failed':raise HTTPException(409,'Only failed jobs may be requeued')
            job.status='queued';job.owner=None;job.lease_until=None;audit(db,u['id'],'job.requeued',{'job_id':id})
        return {'id':id,'status':'queued'}
    @router.post('/agents/workflow/{id}/recover')
    def recover_workflow(id:str,u=Depends(permit('admin','reviewer'))):
        from .main import run_workflow
        from .workflow import build_graph
        from .checkpoints import saver
        snapshot=build_graph(id).get_state({'configurable':{'thread_id':id}})
        if not snapshot.values:raise HTTPException(404,'No recoverable checkpoint')
        if any(t.interrupts for t in snapshot.tasks):raise HTTPException(409,'Use the authorized deviation review endpoint to resume a human checkpoint')
        if not snapshot.next:raise HTTPException(409,'Workflow is already complete')
        request=snapshot.values.get('request_context')
        if not request:raise HTTPException(409,'Legacy checkpoint requires the original request')
        with lock,Session.begin() as db:
            result=run_workflow(db,Run(**request),u['id']);audit(db,u['id'],'workflow.recovered',{'workflow_id':id,'status':result['status']})
        return result
    class ModelDecision(BaseModel):
        action:Literal['approve','reject','activate','retire']
        rationale:str=Field(min_length=10,max_length=4000)
    @router.post('/models/{id}/review')
    def model_review(id:str,body:ModelDecision,u=Depends(permit('admin','reviewer'))):
        with lock,Session.begin() as db:
            row,item=getdoc(db,id,'model');before={k:item.get(k) for k in ['approval_status','status']}
            if body.action=='approve':
                verified_artifact(item)
                if not item.get('metrics') or item.get('test_samples',0)<10:raise HTTPException(409,'Held-out evaluation required')
                item.update(approval_status='approved',approved_by=u['id'],approved_at=now(),approval_rationale=body.rationale)
            elif body.action=='reject':item.update(approval_status='rejected',status='inactive')
            elif body.action=='activate':
                if u['role']!='admin':raise HTTPException(403,'Administrator required to activate models')
                if item['approval_status']!='approved':raise HTTPException(409,'Approve model before activation')
                verified_artifact(item)
                for m in docs(db,'model',10000):
                    if m['process']==item['process'] and m.get('task','prediction')==item.get('task','prediction') and m.get('status')=='active':
                        other=db.get(Record,m['id']);data=json.loads(other.payload);data['status']='inactive';other.payload=canonical(data)
                item['status']='active'
            else:item['status']='retired'
            item.pop('id');item.pop('created');row.payload=canonical(item)
            audit(db,u['id'],'model.'+body.action,{'model_id':id,'before':before,'after':{k:item.get(k) for k in ['approval_status','status']},'rationale':body.rationale})
            return {'id':id,**item}

    @router.get('/settings')
    def settings(u=Depends(permit('admin'))):
        with Session() as db:return {r.id:json.loads(r.payload) for r in db.query(Configuration)}
    @router.get('/risk/configuration')
    def risk_configuration(u=Depends(current)):
        with Session() as db:return json.loads(db.get(Configuration,'risk').payload)
    class AgentSettings(BaseModel):
        timeout_seconds:float=Field(default=60,ge=.1,le=300)
        drift_threshold:float=Field(default=1,gt=0,le=10)
        communication_gap_seconds:int=Field(default=180,ge=5,le=86400)
        prediction_horizon:int=Field(default=15,ge=1,le=120)
        forecast_coverage:float=Field(default=.9,ge=.5,le=.99)
    @router.post('/settings/agents')
    def agent_settings(body:AgentSettings,u=Depends(permit('admin'))):
        with lock,Session.begin() as db:
            old=db.get(Configuration,'agents');before=json.loads(old.payload) if old else None
            if old:old.payload=canonical(body.model_dump())
            else:db.add(Configuration(id='agents',payload=canonical(body.model_dump())))
            audit(db,u['id'],'configuration.agents',{'before':before,'after':body.model_dump()})
        return body
    @router.get('/monitoring/configuration')
    def monitoring_configuration(u=Depends(current)):
        with Session() as db:
            row=db.get(Configuration,'agents')
            return json.loads(row.payload) if row else AgentSettings().model_dump()
    class ModelSettings(BaseModel):
        random_seed:int=Field(default=42,ge=0,le=2147483647)
        tree_estimators:int=Field(default=60,ge=10,le=500)
        xgboost_max_depth:int=Field(default=3,ge=1,le=12)
        contamination:float=Field(default=.05,ge=.001,le=.25)
        svm_nu:float=Field(default=.05,ge=.001,le=.5)
        autoencoder_iterations:int=Field(default=120,ge=50,le=1000)
        probability_threshold:float=Field(default=.5,ge=.05,le=.95)
        anomaly_threshold:float=Field(default=.65,ge=.1,le=.99)
    @router.post('/settings/models')
    def model_settings(body:ModelSettings,u=Depends(permit('admin'))):
        with lock,Session.begin() as db:
            row=db.get(Configuration,'models');before=json.loads(row.payload) if row else None
            if row:row.payload=canonical(body.model_dump())
            else:db.add(Configuration(id='models',payload=canonical(body.model_dump())))
            audit(db,u['id'],'configuration.models',{'before':before,'after':body.model_dump(),'effect':'Future training only; approved active artifacts are unchanged'})
        return body
    class UserRole(BaseModel):
        role:Literal['viewer','reviewer','admin']
        reason:str=Field(min_length=10,max_length=2000)
    @router.get('/users')
    def users(u=Depends(permit('admin'))):
        with Session() as db:return [{'username':r.id,'role':r.role,'active':r.active} for r in db.query(User)]
    class UserAccess(BaseModel):
        active:bool
        reason:str=Field(min_length=10,max_length=2000)
    @router.post('/users/{id}/access')
    def user_access(id:str,body:UserAccess,u=Depends(permit('admin'))):
        from .security_models import UserSession
        with lock,Session.begin() as db:
            user=db.get(User,id)
            if not user:raise HTTPException(404,'User not found')
            if id==u['id'] and not body.active:raise HTTPException(409,'Self-deactivation is disabled')
            user.active=body.active
            if not body.active:db.query(UserSession).filter_by(user_id=id).update({'revoked':True})
            audit(db,u['id'],'user.access_changed',{'user':id,**body.model_dump()})
        return {'username':id,'active':body.active}
    @router.get('/roles')
    def roles(u=Depends(permit('admin'))):
        with Session() as db:return [{'id':r.id,'description':r.description,'permissions':[p.permission_id for p in db.query(RolePermission).filter_by(role_id=r.id)]} for r in db.query(Role)]
    @router.post('/users/{id}/role')
    def user_role(id:str,body:UserRole,u=Depends(permit('admin'))):
        with lock,Session.begin() as db:
            user=db.get(User,id)
            if not user:raise HTTPException(404,'User not found')
            if id==u['id'] and body.role!='admin':raise HTTPException(409,'Self-demotion is disabled; another administrator must review')
            from .security_models import UserRoleBinding
            old=user.role;user.role=body.role;db.merge(UserRoleBinding(user_id=id,role_id=body.role));audit(db,u['id'],'user.role_changed',{'user':id,'before':old,'after':body.role,'reason':body.reason})
        return {'username':id,'role':body.role}

    class SourceEvent(BaseModel):
        process:str
        equipment:str=Field(min_length=1,max_length=80)
        timestamp:datetime
        category:Literal['maintenance','calibration','material','operator_observation','equipment_fault']
        evidence:str=Field(min_length=10,max_length=10000)
        synthetic:bool=True
        @model_validator(mode='after')
        def timestamp_check(self):
            if self.timestamp.tzinfo is None:raise ValueError('Timezone is required')
            return self
    @router.post('/equipment/events')
    def add_event(body:SourceEvent,u=Depends(permit('admin','reviewer'))):
        with lock,Session.begin() as db:
            process(db,body.process);eid=key(body.process,body.equipment)
            if not db.get(Equipment,eid):db.add(Equipment(id=eid,process_id=body.process,identifier=body.equipment,created=now()));db.flush()
            id=str(uuid.uuid4());db.add(EquipmentEvent(id=id,equipment_id=eid,timestamp=body.timestamp.isoformat(),category=body.category,evidence=body.evidence,actor=u['id'],synthetic=body.synthetic))
            audit(db,u['id'],'equipment.evidence_added',{'id':id,**body.model_dump(mode='json')})
        return {'id':id,**body.model_dump(mode='json'),'actor':u['id']}
    @router.get('/equipment/events')
    def events(process_id:str|None=None,limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0),u=Depends(current)):
        with Session() as db:
            q=db.query(EquipmentEvent,Equipment).join(Equipment,EquipmentEvent.equipment_id==Equipment.id)
            if process_id:q=q.filter(Equipment.process_id==process_id)
            return [{'id':e.id,'process':eq.process_id,'equipment':eq.identifier,'timestamp':e.timestamp,'category':e.category,'evidence':e.evidence,'actor':e.actor,'synthetic':e.synthetic} for e,eq in q.order_by(EquipmentEvent.timestamp.desc()).offset(offset).limit(limit)]

    @router.get('/monitoring/catalog')
    def catalog(process_id:str,u=Depends(current)):
        from .database import Reading
        with Session() as db:
            process(db,process_id)
            return {'batches':[r[0] for r in db.query(Reading.batch).filter_by(process=process_id).distinct().order_by(Reading.batch)],'equipment':[r[0] for r in db.query(Reading.equipment).filter_by(process=process_id).distinct()]}
    @router.get('/monitoring/drift')
    def drift(process_id:str|None=None,u=Depends(current)):
        with Session() as db:
            items=docs(db,'workflow',1000)
            return [{'workflow_id':r['id'],'created':r['created'],'process':r['process'],'batch':r['batch'],'model_id':r['result'].get('model_prediction',{}).get('model_id'),'drift':r['result'].get('model_prediction',{}).get('drift')} for r in items if (not process_id or r['process']==process_id) and r['result'].get('model_prediction',{}).get('drift')]
    @router.get('/agents/contracts')
    def contracts(u=Depends(current)):
        from .workflow import AGENTS,State,CONTRACTS,ValidState
        return [{'agent':name,**CONTRACTS[name],'input_schema':{k:ValidState.model_json_schema()['properties'][k] for k in CONTRACTS[name]['inputs']},'output_schema':{k:ValidState.model_json_schema()['properties'][k] for k in CONTRACTS[name]['outputs']},'output_policy':'Validated typed-state updates only','permitted_tools':['Read detached manufacturing evidence','Deterministic calculation'],'forbidden_actions':['equipment control','batch release','GMP deviation approval'],'trigger':'Conditional analytical graph','error_strategy':'Retry transient failures twice; journal failure; resume durable checkpoint','timeout':'Configured deadline; late pure-computation result discarded'} for name in AGENTS]
    @router.get('/agents/graph')
    def graph(u=Depends(current)):
        from .workflow import build_graph
        compiled=build_graph('graph-inspection')
        data=compiled.get_graph().to_json()
        return data
    @router.get('/agents/workflow/{id}/checkpoint')
    def checkpoint(id:str,u=Depends(current)):
        from .workflow import build_graph
        snapshot=build_graph(id).get_state({'configurable':{'thread_id':id}})
        if not snapshot.values:raise HTTPException(404,'No persisted checkpoint')
        return {'workflow_id':id,'next':list(snapshot.next),'status':snapshot.values.get('status'),'created_at':snapshot.created_at,'interrupts':[{'node':t.name,'values':[i.value for i in t.interrupts]} for t in snapshot.tasks if t.interrupts],'input_readings':len(snapshot.values.get('readings',[])),'request_digest':snapshot.values.get('request_digest')}
    return router
