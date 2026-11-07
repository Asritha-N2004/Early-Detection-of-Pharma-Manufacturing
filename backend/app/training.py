"""Chronological held-out batch comparison; next-reading event targets."""
import os, uuid, hashlib
from pathlib import Path
import joblib, numpy as np, pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import precision_score,recall_score,f1_score,average_precision_score,roc_auc_score,confusion_matrix
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from .database import Reading,Record,Configuration,canonical,now
from .model_runtime import store_artifact

def train_models(db,process_id=None,actor='system'):
 configuration=db.get(Configuration,'models');cfg=__import__('json').loads(configuration.payload) if configuration else {}
 seed=cfg.get('random_seed',42);estimators=cfg.get('tree_estimators',60);threshold=cfg.get('probability_threshold',.5)
 rows=db.query(Reading).order_by(Reading.timestamp).all()
 if len(rows)<100:
  from fastapi import HTTPException
  raise HTTPException(422,'At least 100 readings across four chronological batches required')
 frame=pd.DataFrame([{'batch':r.batch,'process':r.process,'timestamp':r.timestamp,'parameter':r.parameter,'value':r.value,'label':__import__('json').loads(r.original).get('label')} for r in rows])
 frame=frame[frame.label.isin([0,1])]
 if frame.empty:
  from fastapi import HTTPException
  raise HTTPException(422,'Binary deviation labels are required for research training')
 eligible=frame.groupby(['process','batch']).timestamp.nunique()
 eligible={index for index,count in eligible.items() if count>=12}
 frame=frame[[ (p,b) in eligible for p,b in zip(frame.process,frame.batch) ]]
 if frame.empty:
  from fastapi import HTTPException
  raise HTTPException(422,'At least four labeled batches with 12 aligned samples each are required')
 # Train one process: parameter schemas cannot be mixed across processes.
 process=process_id or frame.groupby('process').size().idxmax();frame=frame[frame.process==process]
 if frame.empty:
  from fastapi import HTTPException
  raise HTTPException(422,'Selected process has no labeled training data')
 wide=frame.pivot_table(index=['batch','timestamp'],columns='parameter',values='value').sort_index()
 labels=frame.groupby(['batch','timestamp']).label.max().reindex(wide.index)
 target=labels.groupby(level=0).shift(-1)
 future_timestamp=pd.Series(wide.index.get_level_values('timestamp'),index=wide.index).groupby(level=0).shift(-1)
 valid=target.notna()&wide.notna().all(axis=1);wide=wide[valid];target=target[valid].astype(int)
 batch_order=frame.groupby('batch').timestamp.min().sort_values().index.tolist()
 if len(batch_order)<4:
  from fastapi import HTTPException
  raise HTTPException(422,'Four distinct batches required for train / validation / test separation')
 train_batches=batch_order[:-2];validation_batch=batch_order[-2];test_batch=batch_order[-1]
 tr=wide.index.get_level_values('batch').isin(train_batches);va=wide.index.get_level_values('batch')==validation_batch;te=wide.index.get_level_values('batch')==test_batch
 validation_start=frame[frame.batch==validation_batch].timestamp.min();test_start=frame[frame.batch==test_batch].timestamp.min()
 tr=tr&(future_timestamp.reindex(wide.index)<validation_start).to_numpy()
 va=va&(future_timestamp.reindex(wide.index)<test_start).to_numpy()
 if min(tr.sum(),va.sum(),te.sum())<10 or len(np.unique(target[tr]))<2:
  from fastapi import HTTPException
  raise HTTPException(422,'Insufficient labeled samples or classes')
 candidates={'random_forest':RandomForestClassifier(n_estimators=estimators,random_state=seed,class_weight='balanced'),'gradient_boosting':GradientBoostingClassifier(n_estimators=estimators,random_state=seed)}
 try:
  from xgboost import XGBClassifier
  candidates['xgboost']=XGBClassifier(n_estimators=estimators,max_depth=cfg.get('xgboost_max_depth',3),random_state=seed,n_jobs=1)
 except ImportError:pass
 result=[]
 for name,model in candidates.items():
  model.fit(wide[tr],target[tr]);raw=model.predict_proba(wide[te])[:,1];calibrator=None
  if target[va].nunique()==2:
   calibrator=LogisticRegression(C=10,random_state=42).fit(model.predict_proba(wide[va])[:,1].reshape(-1,1),target[va])
  prob=calibrator.predict_proba(raw.reshape(-1,1))[:,1] if calibrator is not None else raw
  pred=prob>=threshold;y=target[te]
  tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
  metrics={'precision':float(precision_score(y,pred,zero_division=0)),'recall':float(recall_score(y,pred,zero_division=0)),'f1':float(f1_score(y,pred,zero_division=0)),'pr_auc':float(average_precision_score(y,prob)) if y.sum() else None,'roc_auc':float(roc_auc_score(y,prob)) if y.nunique()>1 else None,'false_positive_rate':float(fp/max(tn+fp,1)),'false_negative_rate':float(fn/max(tp+fn,1))}
  metrics['brier_score']=float(brier_score_loss(y,prob)) if calibrator is not None else None
  bins=[]
  for lo in np.arange(0,1,.2):
   mask=(prob>=lo)&(prob<lo+.2 if lo<.8 else prob<=1)
   if mask.any():bins.append({'predicted_mean':float(prob[mask].mean()),'observed_rate':float(y.to_numpy()[mask].mean()),'count':int(mask.sum())})
  metrics['calibration_bins']=bins
  from .validation_metrics import event_timing
  metrics['event_timing']=event_timing(wide[te].index.get_level_values('timestamp').tolist(),labels.reindex(wide[te].index).to_numpy(),pred)
  metrics['batch_level']={'batch':test_batch,'samples':int(te.sum()),'true_positive':int(tp),'false_positive':int(fp),'false_negative':int(fn),'true_negative':int(tn)}
  baseline={c:{'mean':float(wide.loc[tr,c].mean()),'std':float(wide.loc[tr,c].std())} for c in wide.columns}
  id=str(uuid.uuid4());path,digest=store_artifact(db,id,{'model':model,'calibrator':calibrator,'baseline':baseline,'features':wide.columns.tolist(),'process':process,'probability_threshold':threshold,'training_configuration':cfg})
  explanations={}
  try:
   import shap
   attribution=np.asarray(shap.TreeExplainer(model).shap_values(wide[te].iloc[:40]))
   if attribution.ndim==3:attribution=attribution[:,:,1]
   explanations={'method':'TreeSHAP','mean_absolute_contribution':dict(zip(wide.columns,np.abs(attribution).mean(axis=0).tolist())),'sample_count':min(int(te.sum()),40),'notice':'Model attribution, not causal evidence.'}
  except (ImportError,ValueError,TypeError) as exc:explanations={'status':'unavailable','error_type':type(exc).__name__}
  drift={c:float(abs(wide.loc[te,c].mean()-wide.loc[tr,c].mean())/max(wide.loc[tr,c].std(),1e-6)) for c in wide.columns}
  payload={'name':name,'version':id,'process':process,'training_date':now(),'dataset':'ingested labeled data','dataset_sha256':hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest(),'train_batches':train_batches,'validation_batch':validation_batch,'test_batch':test_batch,'metrics':metrics,'validation_f1':float(f1_score(target[va],model.predict(wide[va]),zero_division=0)),'test_samples':int(te.sum()),'status':'research','approval_status':'unapproved','artifact':path,'horizon':'next observed sample within batch','attribution':dict(zip(wide.columns,model.feature_importances_.tolist())),'shap':explanations,'distribution_shift':{'method':'absolute standardized mean difference, training versus held-out batch','parameters':drift,'flag_threshold':1.0,'flagged':[k for k,v in drift.items() if v>=1]},'limitations':['Synthetic held-out batch evaluation; not external validation.','Probabilities uncalibrated.','Trained research models are not used by the online linear forecasting agent.','Detection latency and lead time not yet evaluated.']}
  payload.update(task='prediction',training_configuration=cfg,probability_threshold=threshold,artifact_sha256=digest,trained_by=actor,calibration={'method':'validation_batch_sigmoid' if calibrator is not None else 'unavailable','batch':validation_batch,'notice':'Calibration applies to validation distribution; not a regulated-use approval.'})
  payload['limitations']=['Synthetic held-out evaluation, not external process validation.','Validation-batch calibration is distribution-dependent.','Activation requires explicit authorized approval.']
  db.add(Record(id=id,kind='model',created=now(),payload=canonical(payload)));result.append({'id':id,**payload})
 from .approved_anomaly import fit_ensemble
 anomaly=fit_ensemble(db,wide,labels,tr,va,te,process,train_batches,validation_batch,test_batch,actor)
 if anomaly:result.append(anomaly)
 return result
