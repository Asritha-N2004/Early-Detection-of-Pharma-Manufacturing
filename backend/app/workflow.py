"""Read-only analytical agents with durable state and an attributed human gate."""
import time, copy
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import TypedDict
from pydantic import BaseModel, ConfigDict, Field
from langgraph.graph import StateGraph, START, END
from langgraph.types import RetryPolicy, interrupt, Command
from .analytics import analyze, predict, assess
from .database import Record, audit, now, canonical
from .checkpoints import saver

class State(TypedDict, total=False):
    readings:list[dict]
    parameters:list[dict]
    findings:list[dict]
    predictions:list[dict]
    hypotheses:list[dict]
    risk:dict
    recommendations:list[str]
    status:str
    logs:list[dict]
    horizon:int
    method:str
    interval_minutes:float
    summary:str
    thresholds:dict
    request_digest:str
    historical_events:list[dict]
    equipment_events:list[dict]
    multivariate:dict
    active_model:dict|None
    active_anomaly_model:dict|None
    model_prediction:dict
    human_decision:dict
    agent_config:dict
    request_context:dict
    decision_context:dict

class ValidState(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    readings:list[dict]=Field(default_factory=list)
    parameters:list[dict]=Field(default_factory=list)
    findings:list[dict]=Field(default_factory=list)
    predictions:list[dict]=Field(default_factory=list)
    hypotheses:list[dict]=Field(default_factory=list)
    risk:dict=Field(default_factory=dict)
    recommendations:list[str]=Field(default_factory=list)
    status:str='created'
    logs:list[dict]=Field(default_factory=list)
    horizon:int=15
    method:str='ensemble'
    interval_minutes:float=1.0
    summary:str=''
    thresholds:dict=Field(default_factory=dict)
    request_digest:str=''
    historical_events:list[dict]=Field(default_factory=list)
    equipment_events:list[dict]=Field(default_factory=list)
    multivariate:dict=Field(default_factory=dict)
    active_model:dict|None=None
    active_anomaly_model:dict|None=None
    model_prediction:dict=Field(default_factory=dict)
    human_decision:dict=Field(default_factory=dict)
    agent_config:dict=Field(default_factory=dict)
    request_context:dict=Field(default_factory=dict)
    decision_context:dict=Field(default_factory=dict)

def ingestion(s):return {'status':'validated'}
def monitoring(s):
    from .features import historical_features
    features=historical_features(s['readings'])
    return {'summary':f"{len(s['readings'])} validated readings; {len(s.get('historical_events',[]))} historical findings and {len(s.get('equipment_events',[]))} equipment records retrieved; {len(features)} historical feature windows engineered. Operating limits are configured demonstration ranges."}
def anomaly(s):
    if s.get('active_anomaly_model'):
        from .approved_anomaly import infer_ensemble
        return infer_ensemble(s['active_anomaly_model'],s['readings'],s['parameters'],s['method'])
    from .analytics import multivariate_analyze
    return {'findings':analyze(s['readings'],s['parameters'],s['method']),'multivariate':multivariate_analyze(s['readings'],s['parameters'])}
def prediction(s):
    from .model_runtime import infer_model
    return {'predictions':predict(s['findings'],s['horizon'],s['interval_minutes'],s.get('agent_config',{}).get('forecast_coverage',.9)),'model_prediction':infer_model(s.get('active_model'),s['readings'],s.get('agent_config',{}).get('drift_threshold',1.0))}
def root(s):
    import numpy as np
    import pandas as pd
    from .domain import EquipmentEvent,key
    from .database import Session
    keys={key(r['process'],r['equipment']) for r in s['readings'] if r.get('process') and r.get('equipment')}
    evidence=s.get('equipment_events',[])
    if keys and s.get('request_context'):
        with Session() as db:evidence=[{'id':e.id,'timestamp':e.timestamp,'category':e.category,'evidence':e.evidence,'actor':e.actor,'synthetic':e.synthetic} for e in db.query(EquipmentEvent).filter(EquipmentEvent.equipment_id.in_(keys)).order_by(EquipmentEvent.timestamp.desc()).limit(50)]
    ranked=sorted(s['findings'],key=lambda x:x['attribution'],reverse=True)[:4]
    wide=pd.DataFrame(s['readings']).pivot_table(index='timestamp',columns='parameter',values='value').sort_index()
    correlations=wide.corr(min_periods=8);hypotheses=[]
    for f in ranked:
        if not f['flag']:continue
        links=[{'parameter':name,'pearson_r':round(float(value),4),'paired_observations':int(wide[[f['parameter'],name]].dropna().shape[0])} for name,value in correlations[f['parameter']].items() if name!=f['parameter'] and np.isfinite(value) and abs(value)>=.6]
        onset=wide.index[wide[f['parameter']].lt(f['low'])|wide[f['parameter']].gt(f['high'])].tolist()
        hypotheses.append({'cause':f"Investigate {f['parameter']} process or sensor instability",'evidence':f['explanation'],'supporting_parameters':[f['parameter']]+[a['parameter'] for a in links],'correlated_changes':links,'first_observed_excursion':onset[0] if onset else None,'historical_event_ids':[h['id'] for h in s.get('historical_events',[]) if any(a.get('parameter')==f['parameter'] and a.get('flag') for a in h.get('findings',[]))],'equipment_evidence':s.get('equipment_events',[]),'evidence_strength':'screening association only','limitations':['Association and earlier timestamps do not establish causation.','Equipment records are submitted evidence; completeness is not assured.']})
    if s.get('multivariate',{}).get('flag') and not hypotheses:
        hypotheses.append({'cause':'Investigate changed multivariable relationships','evidence':s['multivariate']['explanation'],'supporting_parameters':s['multivariate'].get('parameters',[]),'correlated_changes':[],'limitations':['Multivariate scoring is not causal proof or a probability.']})
    for forecast in s.get('predictions',[]):
        if forecast['early_warning'] and not any(forecast['parameter'] in h['supporting_parameters'] for h in hypotheses):hypotheses.append({'cause':'Investigate gradual '+forecast['parameter']+' drift','evidence':f"Linear forecast {forecast['forecast']:.4f} over {forecast['horizon_minutes']} minutes indicates a potential range excursion, not an observed deviation.",'supporting_parameters':[forecast['parameter']],'limitations':[forecast['uncertainty']]})
    if s.get('model_prediction',{}).get('drift',{}).get('flagged'):
        hypotheses.append({'cause':'Investigate model input distribution shift','evidence':str(s['model_prediction']['drift']),'supporting_parameters':s['model_prediction']['drift']['flagged'],'limitations':['Distribution shift can invalidate model calibration; this is not a confirmed process root cause.']})
    if s.get('model_prediction',{}).get('status')=='missing_features':
        hypotheses.append({'cause':'Investigate incomplete predictive-model inputs','evidence':'Required latest measurements are missing: '+', '.join(s['model_prediction'].get('missing_features',[])),'supporting_parameters':s['model_prediction'].get('missing_features',[]),'limitations':['A complete predictive assessment is unavailable; do not infer process stability from missing evidence.']})
    for h in hypotheses:
        h['equipment_evidence']=evidence
        if s.get('model_prediction',{}).get('shap'):h['model_attribution']=s['model_prediction']['shap']
    from .process_knowledge import hypothesis
    from datetime import datetime
    parameter_map={p['name']:p for p in s['parameters']}
    for h in hypotheses:
        if not h.get('first_observed_excursion'):continue
        primary=h['supporting_parameters'][0];p=parameter_map[primary];rule=hypothesis(s['readings'][0].get('process',''),primary);h['cause']=rule['cause'];h['knowledge_rule']=rule
        values=wide[primary].dropna();normal=values.between(p['low'],p['high']);h['period_comparison']={'normal_mean':float(values[normal].mean()) if normal.any() else None,'abnormal_mean':float(values[~normal].mean()) if (~normal).any() else None,'normal_samples':int(normal.sum()),'abnormal_samples':int((~normal).sum())}
        for link in h.get('correlated_changes',[]):
            other=parameter_map.get(link['parameter'])
            if not other:continue
            onset=wide.index[wide[link['parameter']].lt(other['low'])|wide[link['parameter']].gt(other['high'])].tolist()
            link['first_observed_excursion']=onset[0] if onset else None
            if onset:
                minutes=(datetime.fromisoformat(h['first_observed_excursion'])-datetime.fromisoformat(onset[0])).total_seconds()/60
                link['preceded_by_minutes']=minutes;link['temporal_relation']='preceded current excursion' if minutes>0 else 'same time or later; no upstream ordering established'
    return {'hypotheses':hypotheses,'equipment_events':evidence}
def risk(s):
    count=sum(f['flag'] for f in s['findings']);recurrence=len(s.get('historical_events',[]));thresholds=s.get('thresholds',{});critical_names=set(thresholds.get('critical_parameters',['particle_count','differential_pressure']))|{p['name'] for p in s['parameters'] if p.get('critical')}
    return {'risk':assess(min(thresholds.get('severity_scale',5),2+count),min(thresholds.get('occurrence_scale',5),1+recurrence//2),min(3,thresholds.get('detectability_scale',5)),critical_parameter=any(f['parameter'] in critical_names and f['flag'] for f in s['findings']),thresholds=s.get('thresholds'))|{'recurrence_count':recurrence,'product_quality_impact':'Potential; requires investigation','batch_impact':'Batch under assessment','patient_safety_relevance':'Not established; quality assessment required','process_criticality':'Critical-parameter override evaluated','rating_basis':'Configurable screening rubric; no manufacturing authorization'}}
def investigation(s):
    return {'recommendations':['Verify sensor calibration and original source records.','Compare batch stage, maintenance and upstream material records.','Investigate temporal associations without inferring causation.','Assign an authorized quality reviewer; obtain missing evidence.']+(['No equipment-history evidence is available; request maintenance records.'] if not s.get('equipment_events') else ['Verify retrieved equipment evidence against source records.'])}
def abnormal(s):return any(f['flag'] for f in s.get('findings',[])) or any(p['early_warning'] for p in s.get('predictions',[])) or s.get('multivariate',{}).get('flag',False) or s.get('model_prediction',{}).get('warning',False) or bool(s.get('model_prediction',{}).get('drift',{}).get('flagged')) or s.get('model_prediction',{}).get('status')=='missing_features'
def decision(s):
    output={'status':'awaiting_human_review' if abnormal(s) else 'monitoring'}
    if not s.get('risk'):output['risk']=assess(1,1,1,thresholds=s.get('thresholds'))
    if not s.get('hypotheses'):output['hypotheses']=[]
    if not s.get('recommendations'):output['recommendations']=[]
    sources={'observed_parameter_flags':sum(f['flag'] for f in s.get('findings',[])),'multivariate_flag':s.get('multivariate',{}).get('flag',False),'trend_early_warnings':sum(p['early_warning'] for p in s.get('predictions',[])),'model_warning':s.get('model_prediction',{}).get('warning',False),'drift_flags':s.get('model_prediction',{}).get('drift',{}).get('flagged',[])}
    output['decision_context']={**sources,'policy':'Any abnormal or uncertainty signal routes to human review. Current observations and future predictions have different horizons; retain both when they differ.','manufacturing_authorization':False}
    return output

def report(s):return {'summary':s['summary'].split(' AI-generated')[0]+' AI-generated screening only. Hypotheses require investigation. Human disposition: '+s.get('human_decision',{}).get('decision','pending')+'.'}
def quality(s):return {}
AGENTS={'data_ingestion':ingestion,'process_monitoring':monitoring,'anomaly_detection':anomaly,'predictive':prediction,'root_cause':root,'risk_assessment':risk,'investigation':investigation,'decision_support':decision,'report_generation':report,'quality_audit':quality}

CONTRACTS={
 'data_ingestion':{'role':'Validate accepted measurement provenance','inputs':['readings','parameters'],'outputs':['status']},
 'process_monitoring':{'role':'Summarize historical evidence and engineer trailing features','inputs':['readings','parameters','historical_events','equipment_events'],'outputs':['summary']},
 'anomaly_detection':{'role':'Screen univariate and multivariate abnormal patterns','inputs':['readings','parameters','method'],'outputs':['findings','multivariate']},
 'predictive':{'role':'Forecast horizon excursions and apply approved classifiers','inputs':['findings','readings','horizon','interval_minutes','active_model'],'outputs':['predictions','model_prediction']},
 'root_cause':{'role':'Rank evidence-backed investigation hypotheses','inputs':['findings','readings','historical_events','equipment_events','model_prediction'],'outputs':['hypotheses','equipment_events']},
 'risk_assessment':{'role':'Calculate configurable FMEA-inspired risk','inputs':['findings','parameters','historical_events','thresholds'],'outputs':['risk']},
 'investigation':{'role':'Identify missing evidence and investigation questions','inputs':['findings','hypotheses','equipment_events'],'outputs':['recommendations']},
 'decision_support':{'role':'Route potential findings for authorized human review','inputs':['findings','predictions','multivariate','model_prediction'],'outputs':['status','risk','hypotheses','recommendations','decision_context']},
 'report_generation':{'role':'Generate a grounded labeled preliminary summary','inputs':['summary','human_decision'],'outputs':['summary']},
 'quality_audit':{'role':'Complete traceable analytical execution','inputs':['status'],'outputs':[]}
}


def human_review_gate(s):
    review=interrupt({'type':'human_review','status':s['status'],'risk':s['risk'],'notice':'Review AI recommendations only. No batch release or process control.'})
    if not isinstance(review,dict) or review.get('decision') not in ['accept','reject','more_evidence','escalate'] or not review.get('actor') or len(review.get('notes',''))<10:raise ValueError('Attributed authorized review and rationale required')
    return {'human_decision':review,'status':{'accept':'recommendation_accepted','reject':'recommendation_rejected','more_evidence':'additional_evidence_requested','escalate':'escalated_to_quality'}[review['decision']]}

def build_graph(workflow_id,store=None):
    store=store or saver();graph=StateGraph(State)
    def wrap(name,fn):
        def run(s):
            timeout=float(s.get('agent_config',{}).get('timeout_seconds',60));started=time.monotonic()
            store.journal(workflow_id,{'agent':name,'status':'running','timestamp':now(),'input_keys':list(s)})
            executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='analytical-agent')
            try:
                output=executor.submit(fn,copy.deepcopy(s)).result(timeout=timeout)
                if not isinstance(output,dict) or not set(output).issubset(CONTRACTS[name]['outputs']):raise ValueError('Agent output violates its transition contract')
                ValidState.model_validate({**s,**output})
                store.journal(workflow_id,{'agent':name,'status':'completed','duration_ms':round((time.monotonic()-started)*1000),'timestamp':now(),'input_summary':{'readings':len(s.get('readings',[])),'parameters':len(s.get('parameters',[]))},'output_keys':list(output),'output_summary':{k:len(v) if isinstance(v,list) else v for k,v in output.items() if k not in ['summary','multivariate','model_prediction']}})
                return output
            except Exception as exc:
                store.journal(workflow_id,{'agent':name,'status':'timed_out' if isinstance(exc,FutureTimeout) else 'failed','error_type':type(exc).__name__,'timestamp':now(),'duration_ms':round((time.monotonic()-started)*1000)})
                raise
            finally:executor.shutdown(wait=False,cancel_futures=True)
        return run
    for name,fn in AGENTS.items():graph.add_node(name,wrap(name,fn),retry_policy=RetryPolicy(max_attempts=2,initial_interval=.05,retry_on=(TimeoutError,ConnectionError)))
    graph.add_node('human_review',human_review_gate);graph.add_node('reviewed_report',wrap('report_generation',report))
    graph.add_edge(START,'data_ingestion')
    for a,b in [('data_ingestion','process_monitoring'),('process_monitoring','anomaly_detection'),('anomaly_detection','predictive')]:graph.add_edge(a,b)
    graph.add_conditional_edges('predictive',lambda s:'investigate' if abnormal(s) else 'normal',{'investigate':'root_cause','normal':'decision_support'})
    for a,b in [('root_cause','risk_assessment'),('risk_assessment','investigation'),('investigation','decision_support'),('decision_support','report_generation'),('report_generation','quality_audit')]:graph.add_edge(a,b)
    graph.add_conditional_edges('quality_audit',lambda s:'review' if s['status']=='awaiting_human_review' else 'end',{'review':'human_review','end':END})
    graph.add_conditional_edges('human_review',lambda s:'evidence' if s['human_decision']['decision']=='more_evidence' else 'finish',{'evidence':'root_cause','finish':'reviewed_report'})
    graph.add_edge('reviewed_report',END)
    return graph.compile(checkpointer=store)

def execute(state,db,workflow_id,actor,resume=None):
    store=saver();graph=build_graph(workflow_id,store);config={'configurable':{'thread_id':workflow_id},'recursion_limit':60};snapshot=graph.get_state(config)
    if snapshot.values and state and snapshot.values.get('request_digest')!=state.get('request_digest'):
        from .schemas import Run
        previous=snapshot.values.get('request_context');incoming=state.get('request_context')
        if not previous or not incoming or Run(**previous).model_dump()!=Run(**incoming).model_dump():raise ValueError('Workflow event fingerprint mismatch')
    if resume is not None:
        waiting=any(t.interrupts for t in snapshot.tasks)
        previous=snapshot.values.get('human_decision',{})
        if not waiting and resume.get('decision')=='more_evidence':
            graph.update_state(config,{'status':'awaiting_human_review'},as_node='quality_audit');graph.invoke(None,config);waiting=True
        if waiting:result=graph.invoke(Command(resume=resume),config)
        elif all(previous.get(k)==resume.get(k) for k in ['actor','decision','notes']):result=dict(snapshot.values)
        else:raise ValueError('Workflow is not waiting for human review')
    elif snapshot.values:result=dict(snapshot.values) if any(t.interrupts for t in snapshot.tasks) or not snapshot.next else graph.invoke(None,config)
    else:
        ValidState.model_validate(state);result=graph.invoke(state,config)
    result.pop('__interrupt__',None);result=dict(result);result.pop('readings',None)
    completed=[l for l in store.logs(workflow_id,1000) if l['status']=='completed'];result['logs']=list(reversed(completed))
    result['checkpoint']={'thread_id':workflow_id,'next':list(graph.get_state(config).next),'durable':True}
    for log in completed:
        if not db.get(Record,log['id']):db.add(Record(id=log['id'],kind='execution_log',created=log['created'],payload=canonical(log)))
    audit(db,actor,'workflow.checkpoint',{'workflow_id':workflow_id,'status':result['status'],'next':result['checkpoint']['next']})
    return result
