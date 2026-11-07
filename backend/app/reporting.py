"""Evidence snapshots for all requested report families."""
import json
from collections import Counter
from .database import Reading

def report_content(db,body,getdoc,docs,readings,process):
    family=body.family
    if family in ['deviation','investigation','root_cause','risk']:
        from fastapi import HTTPException
        if not body.deviation_id:raise HTTPException(422,'Select a deviation investigation')
        item=getdoc(db,body.deviation_id,'deviation')[1]
        item['human_reviews']=[{'actor':r.user_id,'created':r.created,**json.loads(r.payload)} for r in db.query(__import__('backend.app.database',fromlist=['Review']).Review).filter_by(deviation_id=body.deviation_id)]
        if family=='root_cause':return {k:item[k] for k in ['id','process','batch','hypotheses','synthetic','human_reviews']}
        if family=='risk':return {k:item[k] for k in ['id','process','batch','risk','synthetic','human_reviews']}
        return item
    if family=='model_performance':
        return {'models':[getdoc(db,body.model_id,'model')[1]] if body.model_id else docs(db,'model',1000),'evidence_type':'Held-out batch research evaluation; approval status shown per model'}
    from fastapi import HTTPException
    if not body.process:raise HTTPException(422,'Select a process for this report family')
    process(db,body.process)
    workflows=[w for w in docs(db,'workflow',10000) if w['process']==body.process and (not body.batch or w['batch']==body.batch)]
    if family=='early_warning':return {'process':body.process,'batch':body.batch,'predictions':[{'workflow_id':w['id'],'created':w['created'],'predictions':w['result']['predictions'],'model':w['result'].get('model_prediction')} for w in workflows],'notice':'Predictions are not confirmed deviations'}
    rows=readings(db,body.process,body.batch,20000)
    summaries=[]
    for parameter in sorted({r['parameter'] for r in rows}):
        values=[r['value'] for r in rows if r['parameter']==parameter]
        summaries.append({'parameter':parameter,'count':len(values),'minimum':min(values),'maximum':max(values),'mean':sum(values)/len(values),'unit':next(r['unit'] for r in rows if r['parameter']==parameter)})
    q=db.query(Reading).filter_by(process=body.process)
    if body.batch:q=q.filter_by(batch=body.batch)
    return {'process':body.process,'batch':body.batch,'total_readings':q.count(),'summarized_recent_readings':len(rows),'window_limit':20000,'batch_count':len({r['batch'] for r in rows}),'parameter_summary':summaries,'workflow_statuses':dict(Counter(w['status'] for w in workflows)),'investigations':[{'id':w['id'],'created':w['created'],'status':w['status']} for w in workflows],'synthetic':bool(rows) and all(r['source']=='synthetic' for r in rows)}
