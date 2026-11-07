"""Database-backed job claims. PostgreSQL supports multiple worker processes."""
import json,uuid
from datetime import datetime,timedelta,timezone
from sqlalchemy import String,Text,Integer,or_
from sqlalchemy.orm import Mapped,mapped_column
from .database import Base,Session,now,canonical,lock,audit

class WorkflowJob(Base):
    __tablename__='workflow_jobs'
    id:Mapped[str]=mapped_column(String,primary_key=True)
    event_id:Mapped[str]=mapped_column(String,unique=True)
    actor:Mapped[str]=mapped_column(String)
    created:Mapped[str]=mapped_column(String,index=True)
    status:Mapped[str]=mapped_column(String,index=True)
    request:Mapped[str]=mapped_column(Text)
    attempts:Mapped[int]=mapped_column(Integer,default=0)
    lease_until:Mapped[str|None]=mapped_column(String,nullable=True)
    owner:Mapped[str|None]=mapped_column(String,nullable=True)
    result:Mapped[str|None]=mapped_column(Text,nullable=True)

def enqueue(body,actor):
    from fastapi import HTTPException
    with lock,Session.begin() as db:
        prior=db.query(WorkflowJob).filter_by(event_id=body.event_id).first();request=canonical(body.model_dump())
        if prior:
            if prior.request!=request:raise HTTPException(409,'Job event ID reused with different content')
            return {'id':prior.id,'status':prior.status}
        id=str(uuid.uuid4());db.add(WorkflowJob(id=id,event_id=body.event_id,actor=actor,created=now(),status='queued',request=request,attempts=0));audit(db,actor,'workflow.enqueued',{'job_id':id,'event_id':body.event_id})
        return {'id':id,'status':'queued'}

def claim(owner):
    with lock,Session.begin() as db:
        query=db.query(WorkflowJob).filter(or_(WorkflowJob.status=='queued',(WorkflowJob.status=='running')&(WorkflowJob.lease_until<now()))).order_by(WorkflowJob.created)
        if db.bind.dialect.name=='postgresql':query=query.with_for_update(skip_locked=True)
        row=query.first()
        if not row:return None
        changed=db.query(WorkflowJob).filter_by(id=row.id,status=row.status).update({'status':'running','owner':owner,'lease_until':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'attempts':row.attempts+1},synchronize_session=False)
        return {'id':row.id,'request':json.loads(row.request),'actor':row.actor} if changed else None

def work_once(owner=None):
    owner=owner or str(uuid.uuid4());job=claim(owner)
    if not job:return False
    from .main import run_workflow
    from .schemas import Run
    try:
        with lock,Session.begin() as db:result=run_workflow(db,Run(**job['request']),job['actor'])
        status='completed';result={'workflow_id':result['id'],'status':result['status']}
    except Exception as exc:
        status='failed';result={'error_type':type(exc).__name__,'recovery':'Requeue after resolving the error; checkpoints retain completed nodes.'}
    with lock,Session.begin() as db:
        row=db.get(WorkflowJob,job['id'])
        if row.owner==owner:
            row.status=status;row.result=canonical(result);row.lease_until=None;audit(db,job['actor'],'job.'+status,{'job_id':job['id'],**result})
    return True
