import os, io, csv, json, uuid, secrets, hashlib, asyncio, time, math, logging
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import bcrypt, jwt, numpy as np
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import Response, FileResponse,JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from .database import *
from .schemas import *
from .registry import definitions
from .analytics import METHODS, assess
from .workflow import execute
from .domain import initialize_domain, sync_processes, EquipmentEvent, Equipment, key as domain_key
from .checkpoints import saver
from .security_models import UserSession,UserRoleBinding
logger=logging.getLogger('pharmasignal')
logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'))

SECRET=os.getenv('JWT_SECRET') or secrets.token_urlsafe(48)
CONTROLLED=os.getenv('DEPLOYMENT_MODE','demo')=='controlled'
if CONTROLLED and (not os.getenv('JWT_SECRET') or len(SECRET)<32):raise RuntimeError('Set a strong JWT_SECRET in controlled mode')
simulation={'status':'stopped','process':'fermentation','scenario':'normal','interval':3.,'ticks':0,'error':None}
security=HTTPBearer()
rate=defaultdict(deque)

def save(db,kind,payload,id=None):
 row=Record(id=id or str(uuid.uuid4()),kind=kind,created=now(),payload=canonical(payload));db.add(row);db.flush();return {'id':row.id,'created':row.created,**payload}
def docs(db,kind,limit=100,offset=0):
 return [{'id':r.id,'created':r.created,**json.loads(r.payload)} for r in db.query(Record).filter_by(kind=kind).order_by(Record.created.desc()).offset(offset).limit(limit)]
def getdoc(db,id,kind=None):
 r=db.get(Record,id)
 if not r or (kind and r.kind!=kind):raise HTTPException(404,'Record not found')
 return r,{'id':r.id,'created':r.created,**json.loads(r.payload)}
def processes(db):return json.loads(db.get(Configuration,'processes').payload)
def process(db,id):
 p=next((p for p in processes(db) if p['id']==id),None)
 if not p:raise HTTPException(404,'Unknown process')
 return p
def current(request:Request,c:HTTPAuthorizationCredentials=Depends(security)):
 try: claims=jwt.decode(c.credentials,SECRET,algorithms=['HS256'])
 except jwt.PyJWTError:raise HTTPException(401,'Invalid or expired session')
 with Session() as db:
  u=db.get(User,claims['sub'])
  if not u or not u.active:raise HTTPException(401,'Unknown or inactive user')
  session=db.get(UserSession,claims.get('jti',''))
  if not session or session.revoked:raise HTTPException(401,'Session revoked or unknown')
  request.state.user=u.id;request.state.session_id=session.id
  return {'id':u.id,'role':u.role}
def permit(*roles):
 def dependency(u=Depends(current)):
  if u['role'] not in roles:raise HTTPException(403,'Role not authorized')
  return u
 return dependency
def init():
 init_db()
 with lock,Session.begin() as db:
  if not db.get(Configuration,'processes'):db.add(Configuration(id='processes',payload=canonical(definitions())))
  if not db.get(Configuration,'risk'):db.add(Configuration(id='risk',payload=canonical({'medium':20,'high':50,'critical':90})))
  db.flush();initialize_domain(db)
  password=os.getenv('BOOTSTRAP_PASSWORD')
  if password and not db.get(User,'admin'):
   if len(password)<12:raise RuntimeError('BOOTSTRAP_PASSWORD must have at least 12 characters')
   db.add(User(id='admin',password=bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode(),role='admin'))
   db.flush();db.add(UserRoleBinding(user_id='admin',role_id='admin'))
   audit(db,'system','user.bootstrap',{'user':'admin'})
async def simulator_loop():
 while True:
  await asyncio.sleep(.5)
  try:
   await asyncio.to_thread(simulation_tick)
   from .jobs import work_once
   await asyncio.to_thread(work_once)
  except Exception as e:logger.error(canonical({'event':'worker.poll_failed','error_type':type(e).__name__}))
@asynccontextmanager
async def lifespan(app):
 init();task=asyncio.create_task(simulator_loop()) if os.getenv('EMBEDDED_WORKER','1')=='1' else None
 yield
 if task:task.cancel()
app=FastAPI(title='PharmaSignal • Manufacturing Intelligence',version='0.1.0',lifespan=lifespan)
@app.exception_handler(RequestValidationError)
async def validation_error(request:Request,exc:RequestValidationError):
 errors=[{'type':e['type'],'loc':e['loc'],'msg':e['msg']} for e in exc.errors()]
 if request.url.path=='/api/v1/data/ingest' and getattr(request.state,'user',None):
  raw=(await request.body()).decode('utf-8',errors='replace')
  with lock,Session.begin() as db:
   save(db,'quality',{'reason':'schema_rejected','original_text':raw,'validation_errors':errors});audit(db,request.state.user,'data.schema_rejected',{'errors':errors})
 return JSONResponse({'detail':errors},status_code=422)
app.add_middleware(CORSMiddleware,allow_origins=os.getenv('CORS_ORIGINS','http://localhost:5173,http://localhost:8080').split(','),allow_credentials=False,allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type'])
@app.middleware('http')
async def guards(request:Request,call_next):
 started=time.monotonic();request_id=uuid.uuid4().hex
 key=request.client.host if request.client else 'test';q=rate[key];stamp=time.monotonic()
 while q and q[0]<stamp-60:q.popleft()
 if len(q)>=300:return Response('Rate limit exceeded',429)
 q.append(stamp)
 try:length=int(request.headers.get('content-length','0'))
 except ValueError:return Response('Invalid content length',400)
 if length>8_000_000:return Response('Request too large',413)
 response=await call_next(request)
 response.headers['X-Content-Type-Options']='nosniff';response.headers['X-Frame-Options']='DENY'
 response.headers['X-Request-ID']=request_id
 logger.info(canonical({'event':'http.request','request_id':request_id,'method':request.method,'path':request.url.path,'status':response.status_code,'duration_ms':round((time.monotonic()-started)*1000),'actor':getattr(request.state,'user','anonymous')}))
 return response
@app.get('/health')
def health():
 with Session() as db:db.execute(select(1))
 with saver().engine.connect() as connection:connection.execute(select(1))
 return {'status':'ok','database':'connected','checkpoints':'connected','mode':'controlled' if CONTROLLED else 'synthetic demonstration','explanation_mode':'deterministic evidence-grounded fallback'}
class Login(BaseModel):
 username:str=Field(min_length=1,max_length=60)
 password:str=Field(max_length=72)
 @field_validator('username')
 @classmethod
 def clean_username(cls,value):
  value=value.strip()
  if not value:raise ValueError('Enter a username')
  return value
 @field_validator('password')
 @classmethod
 def password_bytes(cls,value):
  if len(value.encode())>72:raise ValueError('Password exceeds 72 UTF-8 bytes')
  return value
@app.post('/api/v1/auth/login')
def login(body:Login):
 with lock,Session.begin() as db:
  u=db.get(User,body.username)
  failures=db.query(Audit).filter(Audit.actor==body.username,Audit.action=='login.failed',Audit.created>(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()).count()
  if failures>=5 or not u or not u.active or not bcrypt.checkpw(body.password.encode(),u.password.encode()):
   audit(db,body.username,'login.failed',{});failure=True
  else:
   failure=False;audit(db,u.id,'login.success',{})
   id=str(uuid.uuid4());expires=datetime.now(timezone.utc)+timedelta(hours=2)
   db.add(UserSession(id=id,user_id=u.id,created=now(),expires=expires.isoformat(),revoked=False))
   token=jwt.encode({'sub':u.id,'jti':id,'exp':expires},SECRET,algorithm='HS256')
 if failure:raise HTTPException(401,'Invalid credentials')
 return {'access_token':token,'role':u.role,'expires_in':7200}
@app.post('/api/v1/auth/logout')
def logout(request:Request,u=Depends(current)):
 with lock,Session.begin() as db:
  db.get(UserSession,request.state.session_id).revoked=True;audit(db,u['id'],'session.revoked',{'session_id':request.state.session_id})
 return {'status':'signed_out'}
class NewUser(BaseModel):
 username:str=Field(min_length=1,max_length=60)
 password:str=Field(min_length=8,max_length=72)
 role:Literal['viewer','reviewer','admin']
 @field_validator('password')
 @classmethod
 def password_bytes(cls,value):
  if len(value.encode())>72:raise ValueError('Password exceeds 72 UTF-8 bytes')
  return value
class Registration(BaseModel):
 model_config=ConfigDict(extra='forbid')
 username:str=Field(min_length=1,max_length=60)
 password:str=Field(min_length=8,max_length=72)
 @field_validator('username')
 @classmethod
 def clean_username(cls,value):
  value=value.strip()
  if not value:raise ValueError('Enter a username')
  return value
 @field_validator('password')
 @classmethod
 def password_bytes(cls,value):
  if len(value.encode())>72:raise ValueError('Password exceeds 72 UTF-8 bytes')
  return value
@app.post('/api/v1/auth/register',status_code=201)
def register(body:Registration):
 try:
  with lock,Session.begin() as db:
   if db.get(User,body.username):raise HTTPException(409,'Username is unavailable. Choose another username or sign in.')
   db.add(User(id=body.username,password=bcrypt.hashpw(body.password.encode(),bcrypt.gensalt()).decode(),role='viewer',active=not CONTROLLED))
   db.flush();db.add(UserRoleBinding(user_id=body.username,role_id='viewer'))
   audit(db,body.username,'user.self_registered',{'username':body.username,'role':'viewer','active':not CONTROLLED})
 except IntegrityError:raise HTTPException(409,'Username is unavailable. Choose another username or sign in.')
 return {'username':body.username,'role':'viewer','active':not CONTROLLED,'message':'Account created. You can sign in now.' if not CONTROLLED else 'Account created. An administrator must activate access before you can sign in.'}
@app.post('/api/v1/users')
def new_user(body:NewUser,u=Depends(permit('admin'))):
 with lock,Session.begin() as db:
  if db.get(User,body.username):raise HTTPException(409,'User exists')
  db.add(User(id=body.username,password=bcrypt.hashpw(body.password.encode(),bcrypt.gensalt()).decode(),role=body.role));db.flush();db.add(UserRoleBinding(user_id=body.username,role_id=body.role));audit(db,u['id'],'user.created',{'username':body.username,'role':body.role})
 return {'username':body.username,'role':body.role}
@app.get('/api/v1/processes')
def list_processes(u=Depends(current)):
 with Session() as db:return processes(db)
@app.get('/api/v1/processes/{id}/parameters')
def parameters(id:str,u=Depends(current)):
 with Session() as db:return process(db,id)['parameters']
class Parameter(BaseModel):
 name:str=Field(pattern=r'^[a-zA-Z0-9_]{1,80}$')
 low:float
 high:float
 unit:str=Field(max_length=30)
 alert_threshold:float=Field(default=.65,gt=0,le=1)
 physical_low:float|None=None
 physical_high:float|None=None
 critical:bool=False
 @model_validator(mode='after')
 def limits(self):
  if not math.isfinite(self.low) or not math.isfinite(self.high) or self.low>=self.high:raise ValueError('finite low < high required')
  if any(v is not None and not math.isfinite(v) for v in [self.physical_low,self.physical_high]):raise ValueError('Physical limits must be finite')
  if self.physical_low is not None and self.physical_low>self.low:raise ValueError('Physical lower bound must include the operating range')
  if self.physical_high is not None and self.physical_high<self.high:raise ValueError('Physical upper bound must include the operating range')
  return self
class ProcessConfig(BaseModel):
 id:str=Field(pattern=r'^[a-zA-Z0-9_]{1,80}$')
 name:str=Field(min_length=1,max_length=100)
 parameters:list[Parameter]=Field(min_length=1,max_length=100)
 @model_validator(mode='after')
 def unique(self):
  if len({p.name for p in self.parameters})!=len(self.parameters):raise ValueError('duplicate parameters')
  return self
@app.post('/api/v1/processes')
def configure(body:ProcessConfig,u=Depends(permit('admin'))):
 with lock,Session.begin() as db:
  items=processes(db);old=next((p for p in items if p['id']==body.id),None)
  items=[p for p in items if p['id']!=body.id]+[body.model_dump()]
  db.get(Configuration,'processes').payload=canonical(items);audit(db,u['id'],'configuration.process',{'before':old,'after':body.model_dump()})
  sync_processes(db.connection(),items)
 return body

def ingest_records(db,records,actor):
 accepted=duplicates=0;issues=[];last={}
 for m in records:
  p=process(db,m.process);param=next((v for v in p['parameters'] if v['name']==m.parameter),None)
  reason=None
  if param is None:reason='unknown_parameter'
  elif param['unit']!=m.unit:reason='unit_mismatch'
  elif m.value is None:reason='missing_value'
  elif param.get('physical_low') is not None and m.value<param['physical_low']:reason='invalid_measurement'
  elif param.get('physical_high') is not None and m.value>param['physical_high']:reason='invalid_measurement'
  raw=m.model_dump(mode='json')
  if reason:
   issues.append(save(db,'quality',{'reason':reason,'original':raw}));continue
  ts=m.timestamp.isoformat();key=(m.process,m.batch,m.equipment,ts,m.parameter)
  digest=hashlib.sha256(canonical(key).encode()).hexdigest()
  if db.get(Reading,digest):
   duplicates+=1;issues.append(save(db,'quality',{'reason':'duplicate','original':raw}));continue
  previous=last.get((m.process,m.batch,m.equipment,m.parameter))
  if previous is None:
   prior=db.query(Reading).filter_by(process=m.process,batch=m.batch,equipment=m.equipment,parameter=m.parameter).order_by(Reading.timestamp.desc()).first()
   previous=datetime.fromisoformat(prior.timestamp) if prior else None
  settings=db.get(Configuration,'agents');gap=json.loads(settings.payload).get('communication_gap_seconds',180) if settings else 180
  if previous and (m.timestamp-previous).total_seconds()>gap:issues.append(save(db,'quality',{'reason':'communication_gap','gap_seconds':(m.timestamp-previous).total_seconds(),'original':raw}))
  last[(m.process,m.batch,m.equipment,m.parameter)]=m.timestamp
  db.add(Reading(id=digest,process=m.process,batch=m.batch,equipment=m.equipment,timestamp=ts,parameter=m.parameter,value=m.value,unit=m.unit,source=m.source,original=canonical(raw)));db.flush();accepted+=1
 audit(db,actor,'data.ingested',{'accepted':accepted,'duplicates':duplicates,'quality_events':len(issues)})
 return {'accepted':accepted,'duplicates':duplicates,'quality_events':len(issues)}
@app.post('/api/v1/data/ingest')
def ingest(body:Ingest,u=Depends(permit('admin'))):
 with lock,Session.begin() as db:return ingest_records(db,body.records,u['id'])
@app.post('/api/v1/data/upload')
async def upload(file:UploadFile=File(...),u=Depends(permit('admin'))):
 if not file.filename or not file.filename.lower().endswith('.csv'):raise HTTPException(422,'CSV required')
 content=await file.read(8_000_001)
 if len(content)>8_000_000:raise HTTPException(413,'CSV size limit 8MB')
 try:
  rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
  for r in rows:
   for k in ['value','label','low','high']:
    if r.get(k)=='':r[k]=None
  body=Ingest(records=rows)
 except (ValueError,UnicodeError,ValidationError) as e:
  with lock,Session.begin() as db:
   save(db,'quality',{'reason':'csv_schema_rejected','filename':file.filename,'original_text':content.decode('utf-8',errors='replace')});audit(db,u['id'],'data.csv_rejected',{'filename':file.filename,'error_type':type(e).__name__})
  raise HTTPException(422,str(e)[:1500])
 return ingest(body,u)
def readings(db,process_id=None,batch=None,limit=1000,offset=0,equipment=None,parameter=None,start=None,end=None):
 q=db.query(Reading)
 if process_id:q=q.filter_by(process=process_id)
 if batch:q=q.filter_by(batch=batch)
 if equipment:q=q.filter_by(equipment=equipment)
 if parameter:q=q.filter_by(parameter=parameter)
 if start:q=q.filter(Reading.timestamp>=start.isoformat())
 if end:q=q.filter(Reading.timestamp<=end.isoformat())
 return [{k:getattr(r,k) for k in ['id','process','batch','equipment','timestamp','parameter','value','unit','source']} for r in q.order_by(Reading.timestamp.desc(),Reading.id).offset(offset).limit(limit)][::-1]
@app.get('/api/v1/data/records')
@app.get('/api/v1/monitoring/history')
@app.get('/api/v1/monitoring/trends')
@app.get('/api/v1/monitoring/live')
def get_readings(process:str|None=None,batch:str|None=None,equipment:str|None=None,parameter:str|None=None,start:datetime|None=None,end:datetime|None=None,limit:int=1000,offset:int=0,u=Depends(current)):
 if any(t and t.tzinfo is None for t in [start,end]):raise HTTPException(422,'Date filters require timezone offsets')
 if start and end and start>end:raise HTTPException(422,'Start must precede end')
 with Session() as db:return readings(db,process,batch,min(max(limit,1),20000),max(offset,0),equipment,parameter,start,end)
@app.get('/api/v1/data/quality')
def quality(limit:int=100,u=Depends(current)):
 with Session() as db:return docs(db,'quality',min(max(limit,1),1000))
def run_workflow(db,body,actor):
 workflow_id=hashlib.sha256(body.event_id.encode()).hexdigest()
 if db.bind.dialect.name=='postgresql':
  from sqlalchemy import text
  db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':int(workflow_id[:15],16)})
 prior=db.get(Record,workflow_id)
 if prior:
  payload=json.loads(prior.payload)
  if Run(**payload['request']).model_dump()!=body.model_dump():raise HTTPException(409,'Event ID reused with different request')
  return {'id':prior.id,'created':prior.created,**payload}
 p=process(db,body.process)
 active=next((m for m in docs(db,'model',1000) if m.get('process')==body.process and m.get('task','prediction')=='prediction' and m.get('approval_status')=='approved' and m.get('status')=='active'),None)
 active_anomaly=next((m for m in docs(db,'model',1000) if m.get('process')==body.process and m.get('task')=='anomaly' and m.get('approval_status')=='approved' and m.get('status')=='active'),None)
 if CONTROLLED and (active is None or active_anomaly is None):raise HTTPException(409,'Controlled inference requires approved active prediction and anomaly models for this process')
 rows=readings(db,body.process,body.batch,20000,equipment=body.equipment)
 batches={r['batch'] for r in rows}
 if not body.batch and len(batches)>1:raise HTTPException(422,'Select one batch to prevent cross-batch reference mixing')
 if not body.equipment and len({r['equipment'] for r in rows})>1:raise HTTPException(422,'Select one equipment identifier to prevent cross-equipment reference mixing')
 if len(rows)<20:raise HTTPException(422,'At least 20 accepted readings required')
 timestamps=sorted({datetime.fromisoformat(r['timestamp']) for r in rows})
 interval=float(np.median([(b-a).total_seconds()/60 for a,b in zip(timestamps,timestamps[1:])])) if len(timestamps)>1 else 1.
 history=[h for h in docs(db,'deviation',1000) if h['process']==body.process][:50]
 equipment_ids={domain_key(body.process,r['equipment']) for r in rows}
 events=[{'id':e.id,'timestamp':e.timestamp,'category':e.category,'evidence':e.evidence,'actor':e.actor,'synthetic':e.synthetic} for e in db.query(EquipmentEvent).filter(EquipmentEvent.equipment_id.in_(equipment_ids)).order_by(EquipmentEvent.timestamp.desc()).limit(50)]
 agent_config=db.get(Configuration,'agents')
 result=execute({'readings':rows,'parameters':p['parameters'],'method':body.method,'horizon':body.horizon,'interval_minutes':interval,'thresholds':json.loads(db.get(Configuration,'risk').payload),'request_digest':hashlib.sha256(canonical(body.model_dump()).encode()).hexdigest(),'active_model':active,'active_anomaly_model':active_anomaly,'historical_events':history,'equipment_events':events,'agent_config':json.loads(agent_config.payload) if agent_config else {},'request_context':body.model_dump()},db,workflow_id,actor)
 payload={'request':body.model_dump(),'process':body.process,'batch':body.batch or rows[-1]['batch'],'equipment':body.equipment or rows[-1]['equipment'],'synthetic':all(r['source']=='synthetic' for r in rows),'result':result,'status':result['status']}
 record=save(db,'workflow',payload,workflow_id)
 for f in result['findings']:
  if f['flag']:save(db,'anomaly',{'workflow_id':workflow_id,'process':body.process,'batch':payload['batch'],**f})
 for prediction in result['predictions']:save(db,'prediction',{'workflow_id':workflow_id,**prediction})
 save(db,'risk',{'workflow_id':workflow_id,**result['risk']})
 if result['status']=='awaiting_human_review':
  deviation=save(db,'deviation',{'workflow_id':workflow_id,'process':body.process,'batch':payload['batch'],'status':'awaiting_human_review','risk':result['risk'],'findings':result['findings'],'hypotheses':result['hypotheses'],'recommendations':result['recommendations'],'synthetic':payload['synthetic'],'confirmed':False})
  record['deviation_id']=deviation['id']
  row=db.get(Record,workflow_id);stored=json.loads(row.payload);stored['deviation_id']=deviation['id'];row.payload=canonical(stored)
 audit(db,actor,'workflow.persisted',{'id':workflow_id,'status':result['status']})
 return record
@app.post('/api/v1/agents/workflow/run')
@app.post('/api/v1/anomaly/detect')
@app.post('/api/v1/prediction/run')
def workflow(body:Run,u=Depends(permit('admin','reviewer'))):
 try:
  with lock,Session.begin() as db:return run_workflow(db,body,u['id'])
 except HTTPException:raise
 except Exception as exc:
  with lock,Session.begin() as db:
   failure={'event_id':body.event_id,'process':body.process,'batch':body.batch,'status':'failed','error_type':type(exc).__name__,'recovery':'Inspect execution failure, correct source/configuration, and submit a new event ID.'}
   save(db,'execution_log',failure);audit(db,u['id'],'workflow.failed',failure)
  raise HTTPException(500,'Workflow failed safely; inspect execution logs. No review or manufacturing action was authorized.')
@app.get('/api/v1/agents/workflow/{id}')
def get_workflow(id:str,u=Depends(current)):
 with Session() as db:
  if db.get(Record,id):return getdoc(db,id,'workflow')[1]
 from .workflow import build_graph
 snapshot=build_graph(id).get_state({'configurable':{'thread_id':id}})
 if not snapshot.values:raise HTTPException(404,'Workflow not found')
 values=dict(snapshot.values);values.pop('readings',None);logs=saver().logs(id,100)
 failed=any(l['status'] in ['failed','timed_out'] for l in logs[:2])
 return {'id':id,'status':'failed' if failed else 'running','result':values,'logs':logs,'recoverable':bool(snapshot.next)}
@app.get('/api/v1/agents/execution-logs')
def execution_logs(limit:int=100,offset:int=0,workflow_id:str|None=None,u=Depends(current)):
 limit=min(max(limit,1),1000);offset=max(offset,0);bound=limit+offset
 entries=saver().logs(workflow_id,bound)
 with Session() as db:
  query=db.query(Record).filter_by(kind='execution_log')
  if workflow_id:query=query.filter(Record.payload.contains('"workflow_id":"'+workflow_id+'"',autoescape=True))
  legacy=[{'id':r.id,'created':r.created,**json.loads(r.payload)} for r in query.order_by(Record.created.desc()).limit(bound)]
 merged={r['id']:r for r in legacy+entries}
 return sorted(merged.values(),key=lambda r:r['created'],reverse=True)[offset:offset+limit]
def list_kind(kind,limit=100,offset=0):
 with Session() as db:return docs(db,kind,min(max(limit,1),1000),max(offset,0))
@app.get('/api/v1/anomaly/results')
def anomalies(limit:int=100,offset:int=0,u=Depends(current)):return list_kind('anomaly',limit,offset)
@app.get('/api/v1/anomaly/{id}')
def anomaly_detail(id:str,u=Depends(current)):
 with Session() as db:return getdoc(db,id,'anomaly')[1]
@app.get('/api/v1/prediction/results')
def predictions(limit:int=100,offset:int=0,u=Depends(current)):return list_kind('prediction',limit,offset)
@app.get('/api/v1/deviations')
def deviations(limit:int=100,offset:int=0,u=Depends(current)):return list_kind('deviation',limit,offset)
@app.get('/api/v1/deviations/{id}')
def deviation_detail(id:str,u=Depends(current)):
 with lock,Session.begin() as db:
  item=getdoc(db,id,'deviation')[1];item['reviews']=[json.loads(r.payload)|{'actor':r.user_id,'created':r.created} for r in db.query(Review).filter_by(deviation_id=id)];audit(db,u['id'],'deviation.viewed',{'deviation_id':id});return item
@app.post('/api/v1/deviations/{id}/review')
@app.post('/api/v1/deviations/{id}/escalate')
def review(id:str,body:HumanReview,request:Request,u=Depends(permit('reviewer','admin'))):
 with lock,Session.begin() as db:
  if db.bind.dialect.name=='postgresql':db.query(Record).filter_by(id=id).with_for_update().first()
  row,item=getdoc(db,id,'deviation')
  review_id=hashlib.sha256(canonical({'deviation':id,'actor':u['id'],**body.model_dump()}).encode()).hexdigest()
  if db.get(Review,review_id):return {'status':item['status'],'confirmed':False,'idempotent':True}
  if request.url.path.endswith('/escalate') and body.decision!='escalate':raise HTTPException(422,'Escalation decision required')
  if item['status'] in ['recommendation_accepted','recommendation_rejected'] and body.decision!='more_evidence':raise HTTPException(409,'Request more evidence before another disposition')
  db.add(Review(id=review_id,deviation_id=id,user_id=u['id'],created=now(),payload=canonical(body.model_dump())))
  item['status']={'accept':'recommendation_accepted','reject':'recommendation_rejected','more_evidence':'additional_evidence_requested','escalate':'escalated_to_quality'}[body.decision]
  item['assigned_reviewer']=u['id'];item.pop('id');item.pop('created');row.payload=canonical(item)
  workflow_row=db.get(Record,item['workflow_id'])
  if workflow_row and saver().get_tuple({'configurable':{'thread_id':item['workflow_id']}}):
   result=execute(None,db,item['workflow_id'],u['id'],resume={**body.model_dump(),'actor':u['id'],'timestamp':now()})
   saved=json.loads(workflow_row.payload);saved['status']=result['status'];saved['result']=result;workflow_row.payload=canonical(saved)
  audit(db,u['id'],'deviation.review',{'deviation_id':id,**body.model_dump()})
 return {'status':item['status'],'confirmed':False,'notice':'Review of AI recommendation only; no batch release or manufacturing authorization.'}
@app.post('/api/v1/risk/assess')
def risk_assessment(body:RiskInput,u=Depends(permit('reviewer','admin'))):
 with lock,Session.begin() as db:
  thresholds=json.loads(db.get(Configuration,'risk').payload)
  if any(getattr(body,k)>thresholds.get(k+'_scale',5) for k in ['severity','occurrence','detectability']):raise HTTPException(422,'Rating exceeds the configured risk scale')
  result=assess(**body.model_dump(),thresholds=thresholds);r=save(db,'risk',result);audit(db,u['id'],'risk.assessed',r);return r
@app.get('/api/v1/risk/assessments')
def risks(limit:int=100,offset:int=0,u=Depends(current)):return list_kind('risk',limit,offset)
class RiskThresholds(BaseModel):
 medium:int=Field(ge=1,le=1000)
 high:int=Field(ge=1,le=1000)
 critical:int=Field(ge=1,le=1000)
 severity_scale:int=Field(default=5,ge=2,le=10)
 occurrence_scale:int=Field(default=5,ge=2,le=10)
 detectability_scale:int=Field(default=5,ge=2,le=10)
 critical_parameter_severity:int=Field(default=4,ge=1,le=10)
 procedure_reference:str=Field(default='DEMO-UNAPPROVED',min_length=1,max_length=200)
 critical_parameters:list[str]=Field(default_factory=lambda:['particle_count','differential_pressure'])
 @model_validator(mode='after')
 def ordered(self):
  if not self.medium<self.high<self.critical:raise ValueError('ascending thresholds required')
  if self.critical>self.severity_scale*self.occurrence_scale*self.detectability_scale:raise ValueError('Threshold exceeds configured maximum RPN')
  if self.critical_parameter_severity>self.severity_scale:raise ValueError('Critical severity trigger exceeds scale')
  return self
@app.post('/api/v1/settings/risk')
def risk_settings(body:RiskThresholds,u=Depends(permit('admin'))):
 with lock,Session.begin() as db:
  config=db.get(Configuration,'risk');old=json.loads(config.payload);config.payload=canonical(body.model_dump());audit(db,u['id'],'configuration.risk',{'before':old,'after':body.model_dump()})
 return body
@app.get('/api/v1/audit/logs')
def audit_logs(limit:int=100,offset:int=0,u=Depends(permit('admin','reviewer'))):
 with Session() as db:return {'integrity_verified':verify(db),'entries':[{k:getattr(a,k) for k in ['sequence','created','actor','action','payload','previous','digest']} for a in db.query(Audit).order_by(Audit.sequence.desc()).offset(max(offset,0)).limit(min(max(limit,1),1000))]}
class ReportRequest(BaseModel):
 deviation_id:str|None=None
 family:Literal['deviation','early_warning','batch_monitoring','investigation','root_cause','risk','process_performance','model_performance']='deviation'
 process:str|None=None
 batch:str|None=None
 model_id:str|None=None
 format:Literal['json','csv','pdf']='json'
@app.post('/api/v1/reports/generate')
def generate_report(body:ReportRequest,u=Depends(permit('reviewer','admin'))):
 with lock,Session.begin() as db:
  from .reporting import report_content
  item=report_content(db,body,getdoc,docs,readings,process)
  report=save(db,'report',{'family':body.family,'format':body.format,'content':item,'generated_by':u['id'],'notice':'AI-generated decision-support report; authorized human review required. Synthetic status is recorded in source evidence.','limitations':['Hypotheses are not established causes.','Missing source evidence must be obtained from authorized personnel.','Not a GMP-approved investigation or electronic signature.']});audit(db,u['id'],'report.generated',{'id':report['id'],'family':body.family});return report
@app.get('/api/v1/reports')
def reports(limit:int=100,offset:int=0,u=Depends(current)):return list_kind('report',limit,offset)
@app.get('/api/v1/reports/{id}')
def report_download(id:str,u=Depends(current)):
 with lock,Session.begin() as db:
  item=getdoc(db,id,'report')[1];audit(db,u['id'],'report.downloaded',{'report_id':id,'format':item['format']})
 if item['format']=='json':return item
 if item['format']=='csv':
  buffer=io.StringIO();writer=csv.writer(buffer);writer.writerow(['AI GENERATED — HUMAN REVIEW REQUIRED']);writer.writerow(['field','value'])
  for k,v in item['content'].items():writer.writerow([k,json.dumps(v,ensure_ascii=False)])
  return Response(buffer.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="report-{id}.csv"'})
 from .pdf_reports import render_report
 return Response(render_report(item),media_type='application/pdf',headers={'Content-Disposition':f'attachment; filename="report-{id}.pdf"'})
@app.get('/api/v1/models')
@app.get('/api/v1/models/performance')
def models(limit:int=100,offset:int=0,u=Depends(current)):return list_kind('model',limit,offset)
class TrainingRequest(BaseModel):
 process:str|None=None
@app.post('/api/v1/models/train')
def train(body:TrainingRequest|None=None,u=Depends(permit('admin'))):
 from .training import train_models
 with lock,Session.begin() as db:
  result=train_models(db,process_id=body.process if body else None,actor=u['id']);audit(db,u['id'],'model.trained',{'ids':[m['id'] for m in result]});return result
@app.get('/api/v1/dashboard')
def dashboard(u=Depends(current)):
 from .domain import Batch,DeviationRecord,Prediction as PredictionIndex,AgentWorkflow
 from sqlalchemy import func
 with Session() as db:
  open_status=['awaiting_human_review','additional_evidence_requested','escalated_to_quality']
  total=db.query(DeviationRecord).count()
  distribution=[{'classification':level,'count':count} for level,count in db.query(DeviationRecord.risk_class,func.count()).group_by(DeviationRecord.risk_class)]
  health=[]
  for p in processes(db):
   count=db.query(DeviationRecord).join(AgentWorkflow,DeviationRecord.workflow_id==AgentWorkflow.id).filter(AgentWorkflow.process_id==p['id'],DeviationRecord.status.in_(open_status)).count()
   health.append({'process':p['id'],'open_investigations':count,'readings':db.query(Reading).filter_by(process=p['id']).count()})
  return {'batches':db.query(Batch).count(),'processes':db.query(Reading.process).distinct().count(),'readings':db.query(Reading).count(),'anomalies':db.query(Record).filter_by(kind='anomaly').count(),'predictions':db.query(PredictionIndex).filter_by(early_warning=True).count(),'investigations':db.query(DeviationRecord).filter(DeviationRecord.status.in_(open_status)).count(),'critical':db.query(DeviationRecord).filter_by(risk_class='Critical').filter(DeviationRecord.status.in_(open_status)).count(),'recent':docs(db,'deviation',8),'models':docs(db,'model',20),'risk_distribution':distribution,'process_health':health,'simulation':simulation_state(db),'summary':'AI-generated deterministic summary: '+str(total)+' potential deviation investigations recorded. Authorized human assessment is required.','mode':'SYNTHETIC DEMONSTRATION - NOT VALIDATED','explanation_mode':'deterministic evidence-grounded fallback; no external LLM configured'}

def simulation_state(db):
 row=db.get(Configuration,'simulation')
 return json.loads(row.payload) if row else {**simulation,'run_id':uuid.uuid4().hex,'last_tick':None}

def simulation_tick(force=False):
 with lock,Session.begin() as db:
  query=db.query(Configuration).filter_by(id='simulation')
  if db.bind.dialect.name=='postgresql':query=query.with_for_update()
  row=query.first()
  if not row:return None
  state=json.loads(row.payload)
  if not force and state['status']!='running':return None
  stamp=datetime.now(timezone.utc)
  if not force and state.get('last_tick') and (stamp-datetime.fromisoformat(state['last_tick'])).total_seconds()<state['interval']:return None
  p=process(db,state['process']);tick=state['ticks'];rng=np.random.default_rng(42+tick);records=[]
  batch='SIM-'+p['id']+'-'+state['run_id'][:6]
  for i,param in enumerate(p['parameters']):
   width=param['high']-param['low'];v=(param['low']+param['high'])/2+rng.normal(0,width*.04)
   if i==0 and state['scenario']=='spike':v=param['high']+width*.7
   if i==0 and state['scenario']=='drift':v+=width*min(tick*.025,1)
   if i<2 and state['scenario']=='equipment_fault':v=param['high']+width*.5
   if i==0 and state['scenario']=='sensor_failure':v=None
   records.append(Measurement(process=p['id'],batch=batch,equipment='SIM-EQ-01',timestamp=stamp,parameter=param['name'],value=v,unit=param['unit'],source='synthetic',label=int(v is not None and (v<param['low'] or v>param['high']))))
  result=ingest_records(db,records,'simulator')
  if state['scenario']=='equipment_fault' and tick==0:
   db.add(EquipmentEvent(id=str(uuid.uuid4()),equipment_id=domain_key(p['id'],'SIM-EQ-01'),timestamp=stamp.isoformat(),category='equipment_fault',evidence='SYNTHETIC scenario: simulated actuator instability; no real equipment connection.',actor='simulator',synthetic=True))
  state['ticks']+=1;state['last_tick']=stamp.isoformat();row.payload=canonical(state)
  if tick>=8 and tick%4==0:run_workflow(db,Run(process=p['id'],batch=batch,event_id=f"sim-{state['run_id']}-{tick}"),'simulator')
  return result

@app.get('/api/v1/simulation')
def simulation_status(u=Depends(current)):
 with Session() as db:return simulation_state(db)

@app.post('/api/v1/simulation')
def simulation_control(body:SimulationInput,u=Depends(permit('admin'))):
 with lock,Session.begin() as db:
  process(db,body.process);state=simulation_state(db)
  if body.action=='reset':state.update(status='stopped',ticks=0,error=None,run_id=uuid.uuid4().hex,last_tick=None)
  elif body.action!='step':state['status']={'start':'running','pause':'paused','stop':'stopped'}[body.action]
  state.update(process=body.process,scenario=body.scenario,interval=body.interval)
  row=db.get(Configuration,'simulation')
  if row:row.payload=canonical(state)
  else:db.add(Configuration(id='simulation',payload=canonical(state)))
  audit(db,u['id'],'simulation.'+body.action,body.model_dump())
 if body.action=='step':simulation_tick(force=True)
 with Session() as db:return simulation_state(db)

from .extensions import router_for
app.include_router(router_for(current,permit,docs,getdoc,save,process,readings))
