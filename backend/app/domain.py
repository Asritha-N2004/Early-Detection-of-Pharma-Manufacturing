"""Normalized domain indexes alongside immutable analytical evidence documents."""
import json
import hashlib
from sqlalchemy import String, Text, Float, Integer, Boolean, ForeignKey, UniqueConstraint, event, select
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base, Record, Reading, now, canonical

class Role(Base):
    __tablename__ = 'roles'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str] = mapped_column(Text)
class Permission(Base):
    __tablename__ = 'permissions'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str] = mapped_column(Text)
class RolePermission(Base):
    __tablename__ = 'role_permissions'
    role_id: Mapped[str] = mapped_column(ForeignKey('roles.id'), primary_key=True)
    permission_id: Mapped[str] = mapped_column(ForeignKey('permissions.id'), primary_key=True)
class ManufacturingProcess(Base):
    __tablename__ = 'manufacturing_processes'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated: Mapped[str] = mapped_column(String)
class ProcessParameter(Base):
    __tablename__ = 'process_parameters'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    process_id: Mapped[str] = mapped_column(ForeignKey('manufacturing_processes.id'), index=True)
    name: Mapped[str] = mapped_column(String)
    low: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String)
    __table_args__ = (UniqueConstraint('process_id', 'name'),)
class Equipment(Base):
    __tablename__ = 'equipment'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    process_id: Mapped[str] = mapped_column(ForeignKey('manufacturing_processes.id'), index=True)
    identifier: Mapped[str] = mapped_column(String)
    created: Mapped[str] = mapped_column(String)
class Batch(Base):
    __tablename__ = 'batches'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    process_id: Mapped[str] = mapped_column(ForeignKey('manufacturing_processes.id'), index=True)
    identifier: Mapped[str] = mapped_column(String)
    created: Mapped[str] = mapped_column(String)
class ReadingContext(Base):
    __tablename__ = 'reading_contexts'
    reading_id: Mapped[str] = mapped_column(ForeignKey('sensor_readings.id'), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey('batches.id'), index=True)
    equipment_id: Mapped[str] = mapped_column(ForeignKey('equipment.id'), index=True)
    parameter_id: Mapped[str] = mapped_column(ForeignKey('process_parameters.id'), index=True)
class EquipmentEvent(Base):
    __tablename__ = 'equipment_events'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    equipment_id: Mapped[str] = mapped_column(ForeignKey('equipment.id'), index=True)
    timestamp: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String)
    evidence: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String)
    synthetic: Mapped[bool] = mapped_column(Boolean)

class DocumentIndex:
    id: Mapped[str] = mapped_column(ForeignKey('analytical_records.id'), primary_key=True)
    created: Mapped[str] = mapped_column(String, index=True)
class DataQualityEvent(DocumentIndex, Base):
    __tablename__ = 'data_quality_events'
    reason: Mapped[str] = mapped_column(String, index=True)
    process_id: Mapped[str | None] = mapped_column(ForeignKey('manufacturing_processes.id'), nullable=True)
class AgentWorkflow(DocumentIndex, Base):
    __tablename__ = 'agent_workflows'
    process_id: Mapped[str] = mapped_column(ForeignKey('manufacturing_processes.id'), index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey('batches.id'), index=True)
    status: Mapped[str] = mapped_column(String, index=True)
class AnomalyEvent(DocumentIndex, Base):
    __tablename__ = 'anomaly_events'
    workflow_id: Mapped[str] = mapped_column(ForeignKey('agent_workflows.id'), index=True)
    parameter: Mapped[str] = mapped_column(String)
    score: Mapped[float] = mapped_column(Float)
class Prediction(DocumentIndex, Base):
    __tablename__ = 'predictions'
    workflow_id: Mapped[str] = mapped_column(ForeignKey('agent_workflows.id'), index=True)
    parameter: Mapped[str] = mapped_column(String)
    horizon: Mapped[int] = mapped_column(Integer)
    early_warning: Mapped[bool] = mapped_column(Boolean)
class DeviationRecord(DocumentIndex, Base):
    __tablename__ = 'deviation_records'
    workflow_id: Mapped[str] = mapped_column(ForeignKey('agent_workflows.id'), index=True)
    status: Mapped[str] = mapped_column(String, index=True)
    risk_class: Mapped[str] = mapped_column(String, index=True)
class RootCauseHypothesis(Base):
    __tablename__ = 'root_cause_hypotheses'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    deviation_id: Mapped[str] = mapped_column(ForeignKey('deviation_records.id'), index=True)
    cause: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text)
class RiskAssessment(DocumentIndex, Base):
    __tablename__ = 'risk_assessments'
    workflow_id: Mapped[str | None] = mapped_column(ForeignKey('agent_workflows.id'), nullable=True, index=True)
    severity: Mapped[int] = mapped_column(Integer)
    occurrence: Mapped[int] = mapped_column(Integer)
    detectability: Mapped[int] = mapped_column(Integer)
    rpn: Mapped[int] = mapped_column(Integer)
    classification: Mapped[str] = mapped_column(String)
class AgentExecutionLog(DocumentIndex, Base):
    __tablename__ = 'agent_execution_logs'
    workflow_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    agent: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
class InvestigationRecord(Base):
    __tablename__ = 'investigation_records'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    deviation_id: Mapped[str] = mapped_column(ForeignKey('deviation_records.id'), unique=True)
    recommendations: Mapped[str] = mapped_column(Text)
    updated: Mapped[str] = mapped_column(String)
class ModelRegistry(DocumentIndex, Base):
    __tablename__ = 'model_registry'
    process_id: Mapped[str] = mapped_column(ForeignKey('manufacturing_processes.id'), index=True)
    name: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String, unique=True)
    approval_status: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String)
class ModelEvaluation(Base):
    __tablename__ = 'model_evaluations'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(ForeignKey('model_registry.id'), index=True)
    created: Mapped[str] = mapped_column(String)
    metrics: Mapped[str] = mapped_column(Text)
class GeneratedReport(DocumentIndex, Base):
    __tablename__ = 'generated_reports'
    family: Mapped[str] = mapped_column(String)
    format: Mapped[str] = mapped_column(String)
    generated_by: Mapped[str] = mapped_column(String)

def key(process, name):
    return hashlib.sha256(f'{process}:{name}'.encode()).hexdigest()
def upsert(connection, model, values):
    table = model.__table__
    identity = values['id']
    exists = connection.execute(select(table.c.id).where(table.c.id == identity)).first()
    connection.execute(table.update().where(table.c.id == identity).values(**values) if exists else table.insert().values(**values))

def sync_processes(connection, items):
    for p in items:
        table=ManufacturingProcess.__table__
        old=connection.execute(select(table).where(table.c.id==p['id'])).mappings().first()
        upsert(connection, ManufacturingProcess, {'id':p['id'],'name':p['name'],'version':old['version'] if old else 1,'updated':now()})
        for param in p['parameters']:
            upsert(connection, ProcessParameter, {'id':key(p['id'],param['name']),'process_id':p['id'],**{k:param[k] for k in ['name','low','high','unit']}})

def reading_projection(connection, row):
    batch=key(row.process,row.batch);equipment=key(row.process,row.equipment)
    for model,id,name in [(Batch,batch,row.batch),(Equipment,equipment,row.equipment)]:
        if not connection.execute(select(model.__table__.c.id).where(model.__table__.c.id==id)).first():
            connection.execute(model.__table__.insert().values(id=id,process_id=row.process,identifier=name,created=row.timestamp))
    connection.execute(ReadingContext.__table__.insert().values(reading_id=row.id,batch_id=batch,equipment_id=equipment,parameter_id=key(row.process,row.parameter)))

@event.listens_for(Reading,'after_insert')
def reading_insert(mapper,connection,target):
    reading_projection(connection,target)

def document_projection(connection, row):
    p=json.loads(row.payload);common={'id':row.id,'created':row.created};kind=row.kind
    model=None;values={}
    if kind=='quality':
        model=DataQualityEvent;values={'reason':p['reason'],'process_id':p.get('original',{}).get('process')}
    elif kind=='workflow':
        model=AgentWorkflow;values={'process_id':p['process'],'batch_id':key(p['process'],p['batch']),'status':p['status']}
    elif kind=='anomaly':
        model=AnomalyEvent;values={k:p[k] for k in ['workflow_id','parameter','score']}
    elif kind=='prediction':
        model=Prediction;values={'workflow_id':p['workflow_id'],'parameter':p['parameter'],'horizon':p['horizon_minutes'],'early_warning':p['early_warning']}
    elif kind=='deviation':
        model=DeviationRecord;values={'workflow_id':p['workflow_id'],'status':p['status'],'risk_class':p['risk']['classification']}
    elif kind=='risk':
        model=RiskAssessment;values={k:p[k] for k in ['severity','occurrence','detectability','rpn','classification']};values['workflow_id']=p.get('workflow_id')
    elif kind=='execution_log':
        model=AgentExecutionLog;values={'workflow_id':p.get('workflow_id'),'agent':p.get('agent','orchestrator'),'status':p['status']}
    elif kind=='model':
        model=ModelRegistry;values={k:p[k] for k in ['name','version','approval_status','status']};values['process_id']=p['process']
    elif kind=='report':
        model=GeneratedReport;values={'family':p.get('family','deviation'),'format':p['format'],'generated_by':p['generated_by']}
    if model:
        upsert(connection,model,{**common,**values})
    if kind=='deviation':
        for i,h in enumerate(p.get('hypotheses',[])):
            upsert(connection,RootCauseHypothesis,{'id':f'{row.id}:{i}','deviation_id':row.id,'cause':h['cause'],'evidence':h['evidence']})
        upsert(connection,InvestigationRecord,{'id':row.id,'deviation_id':row.id,'recommendations':canonical(p.get('recommendations',[])),'updated':now()})
    if kind=='model':
        upsert(connection,ModelEvaluation,{'id':row.id,'model_id':row.id,'created':row.created,'metrics':canonical(p['metrics'])})

@event.listens_for(Record,'after_insert')
@event.listens_for(Record,'after_update')
def record_event(mapper,connection,target):
    document_projection(connection,target)

def initialize_domain(db):
    config=db.get(__import__('backend.app.database',fromlist=['Configuration']).Configuration,'processes')
    if config:sync_processes(db.connection(),json.loads(config.payload))
    permissions={'read':'Read analytical evidence','analyze':'Run analytical agents','review':'Review AI recommendations and model versions','configure':'Change controlled configuration','users':'Manage local users','models':'Train and activate model versions'}
    for id,desc in permissions.items():
        if not db.get(Permission,id):db.add(Permission(id=id,description=desc))
    for role,allowed in {'viewer':['read'],'reviewer':['read','analyze','review'],'admin':list(permissions)}.items():
        if not db.get(Role,role):db.add(Role(id=role,description=role.title()))
        db.flush()
        for permission in allowed:
            if not db.get(RolePermission,(role,permission)):db.add(RolePermission(role_id=role,permission_id=permission))
    from .security_models import UserRoleBinding
    from .database import User
    db.flush()
    for user in db.query(User):
        binding=db.get(UserRoleBinding,user.id)
        if not binding:db.add(UserRoleBinding(user_id=user.id,role_id=user.role))
