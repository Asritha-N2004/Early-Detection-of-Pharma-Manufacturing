"""Versioned anomaly ensembles: fit once, approve artifact, infer without refitting."""
import hashlib,json,uuid
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM
from sklearn.neural_network import MLPRegressor
from sklearn.covariance import LedoitWolf
from sklearn.metrics import precision_score,recall_score,f1_score,average_precision_score,roc_auc_score,confusion_matrix
from .analytics import METHODS
from .database import Record,Configuration,canonical,now
from .model_runtime import load_artifact,store_artifact
from .features import aligned_frame

def signature(parameters):
    data=[{k:p[k] for k in ['name','low','high','unit']} for p in sorted(parameters,key=lambda p:p['name'])]
    return hashlib.sha256(canonical(data).encode()).hexdigest()

def score_series(bundle,values):
    values=np.asarray(values,dtype=float);y=((values-bundle['center'])/bundle['scale']).reshape(-1,1)
    output={'zscore':np.minimum(np.abs(y[:,0])/6,1)};rolling=[];ewma=[];cusum=[];e=c=0.
    for index,v in enumerate(y[:,0]):
        prior=np.concatenate([bundle['reference'],values[:index]])[-20:]
        rolling.append(min(abs(values[index]-prior.mean())/max(prior.std(),bundle['scale']/2)/6,1))
        e=.3*v+.7*e;c=max(0,c+abs(v)-.5);ewma.append(min(abs(e)/4,1));cusum.append(min(c/20,1))
    output.update(rolling=np.asarray(rolling),ewma=np.asarray(ewma),cusum=np.asarray(cusum))
    for name in ['isolation_forest','lof','one_class_svm']:output[name]=np.clip(.5-bundle['models'][name].decision_function(y),0,1)
    error=np.abs(bundle['models']['autoencoder'].predict(y)-y[:,0]);output['autoencoder']=np.minimum(error/bundle['reconstruction_scale']/4,1)
    return output

def fit_ensemble(db,wide,labels,tr,va,te,process,train_batches,validation_batch,test_batch,actor):
    config=db.get(Configuration,'models');cfg=json.loads(config.payload) if config else {};seed=cfg.get('random_seed',42);estimators=cfg.get('tree_estimators',60);contamination=cfg.get('contamination',.05)
    registry=next(p for p in json.loads(db.get(Configuration,'processes').payload) if p['id']==process)
    parameters=[{**p,'alert_threshold':p.get('alert_threshold',cfg.get('anomaly_threshold',.65))} for p in registry['parameters'] if p['name'] in wide.columns]
    normal=tr & (labels.reindex(wide.index).to_numpy()==0)
    if normal.sum()<10:return None
    reference=wide[normal];bundles={}
    for p in parameters:
        raw=reference[p['name']].to_numpy();center=(p['low']+p['high'])/2;scale=max((p['high']-p['low'])/6,1e-6);x=((raw-center)/scale).reshape(-1,1)
        models={'isolation_forest':IsolationForest(n_estimators=estimators,random_state=seed,contamination=contamination).fit(x),'lof':LocalOutlierFactor(n_neighbors=min(20,len(x)-1),novelty=True,contamination=contamination).fit(x),'one_class_svm':OneClassSVM(nu=cfg.get('svm_nu',.05),gamma='scale').fit(x),'autoencoder':MLPRegressor(hidden_layer_sizes=(3,1,3),max_iter=cfg.get('autoencoder_iterations',120),random_state=seed,solver='lbfgs').fit(x,x.ravel())}
        error=np.abs(models['autoencoder'].predict(x)-x[:,0])
        last_batch=reference.index.get_level_values('batch')[-1];forecast_window=reference.xs(last_batch,level='batch')[p['name']]
        bundles[p['name']]={'center':center,'scale':scale,'reference':raw,'forecast_reference':forecast_window.to_numpy(),'forecast_timestamps':forecast_window.index.tolist(),'models':models,'reconstruction_scale':max(float(np.quantile(error,.95)),.5)}
    means=reference.mean();std=reference.std().clip(lower=1e-6);joint=(reference-means)/std;covariance=LedoitWolf().fit(joint)
    threshold=max(float(np.quantile(covariance.mahalanobis(joint),.99))*1.5,len(parameters)*2.5)
    forest=IsolationForest(n_estimators=estimators,random_state=seed,contamination=contamination).fit(joint)
    artifact={'task':'anomaly','training_configuration':cfg,'parameters':parameters,'features':wide.columns.tolist(),'bundles':bundles,'means':means,'std':std,'covariance':covariance,'forest':forest,'joint_threshold':threshold,'parameter_signature':signature(parameters)}
    test=wide[te];scores={name:[] for name in METHODS};outside=[]
    for p in parameters:
        values=test[p['name']].to_numpy();indicators=score_series(bundles[p['name']],values)
        for name in METHODS:scores[name].append(indicators[name])
        outside.append((values<p['low'])|(values>p['high']))
    actual=labels.reindex(test.index).to_numpy().astype(int);excursion=np.any(outside,axis=0);comparison={}
    ensemble=np.mean([np.asarray(scores[name]) for name in METHODS],axis=0).max(axis=0)
    for name in METHODS+['ensemble']:
        indicator=ensemble if name=='ensemble' else np.asarray(scores[name]).max(axis=0);thresholds=np.array([p['alert_threshold'] for p in parameters]).reshape(-1,1);stack=np.mean([np.asarray(scores[k]) for k in METHODS],axis=0) if name=='ensemble' else np.asarray(scores[name]);pred=excursion|np.any(stack>=thresholds,axis=0)
        tn,fp,fn,tp=confusion_matrix(actual,pred,labels=[0,1]).ravel()
        comparison[name]={'precision':float(precision_score(actual,pred,zero_division=0)),'recall':float(recall_score(actual,pred,zero_division=0)),'f1':float(f1_score(actual,pred,zero_division=0)),'false_positive_rate':float(fp/max(tn+fp,1)),'false_negative_rate':float(fn/max(tp+fn,1)),'pr_auc':float(average_precision_score(actual,indicator)) if actual.sum() else None,'roc_auc':float(roc_auc_score(actual,indicator)) if len(np.unique(actual))==2 else None}
    from .validation_metrics import event_timing
    metrics=comparison['ensemble']|{'event_timing':event_timing(test.index.get_level_values('timestamp').tolist(),actual,excursion|np.any(np.mean([np.asarray(scores[k]) for k in METHODS],axis=0)>=np.array([p['alert_threshold'] for p in parameters]).reshape(-1,1),axis=0)),'algorithm_comparison':comparison,'batch_level':{'batch':test_batch,'samples':len(test)}}
    id=str(uuid.uuid4());path,digest=store_artifact(db,id,artifact)
    payload={'name':'anomaly_ensemble','task':'anomaly','training_configuration':cfg,'version':id,'process':process,'training_date':now(),'dataset':'Normal reference from chronological training batches','dataset_sha256':hashlib.sha256(reference.to_csv().encode()).hexdigest(),'train_batches':train_batches,'validation_batch':validation_batch,'test_batch':test_batch,'test_samples':len(test),'metrics':metrics,'distribution_shift':{'method':'absolute training-normal versus held-out standardized mean difference','parameters':{c:float(abs(test[c].mean()-reference[c].mean())/max(reference[c].std(),1e-6)) for c in reference.columns}},'status':'research','approval_status':'unapproved','artifact':str(path),'artifact_sha256':digest,'trained_by':actor,'horizon':'current-sample detection','calibration':{'method':'uncalibrated anomaly indicators'},'parameter_signature':artifact['parameter_signature'],'limitations':['Synthetic labels derive from engineering ranges; range-rule performance is not independent evidence of learned detection quality.','Scores are not probabilities.','Only labeled normal training samples fit the reference; final test labels are not used to fit detectors.']}
    db.add(Record(id=id,kind='model',created=now(),payload=canonical(payload)))
    return {'id':id,**payload}

def infer_ensemble(model,readings,parameters,method):
    if model.get('approval_status')!='approved' or model.get('status')!='active':raise ValueError('Anomaly artifact must be approved and active')
    artifact=load_artifact(model)
    selected=[p for p in parameters if p['name'] in artifact['features']]
    if signature(selected)!=artifact['parameter_signature']:raise ValueError('Operating configuration changed; retrain and approve the anomaly reference')
    wide=aligned_frame(readings);findings=[]
    for p in selected:
        if p['name'] not in wide.columns:continue
        values=wide[p['name']].dropna()
        if len(values)<3:continue
        bundle=artifact['bundles'][p['name']];scores=score_series(bundle,values.to_numpy());methods={k:float(v[-1]) for k,v in scores.items()};score=float(np.mean(list(methods.values()))) if method=='ensemble' else methods[method]
        latest=float(values.iloc[-1]);reference=bundle['reference'];outside=latest<p['low'] or latest>p['high'];recent=values.tail(12)
        from .forecasting import slope_per_minute
        findings.append({'parameter':p['name'],'timestamp':str(values.index[-1]),'value':latest,'low':p['low'],'high':p['high'],'baseline':float(reference.mean()),'score':score,'methods':methods,'detection_method':method,'model_id':model['id'],'outside_range':outside,'flag':bool(outside or score>=p.get('alert_threshold',artifact.get('training_configuration',{}).get('anomaly_threshold',.65))),'slope_per_sample':float(np.polyfit(np.arange(len(recent)),recent,1)[0]),'slope_per_minute':slope_per_minute(recent.tolist(),recent.index.tolist()),'attribution':float(abs(latest-reference.mean())/bundle['scale']),'reference_count':len(reference),'test_count':len(values),'forecast_reference':bundle.get('forecast_reference',[]).tolist() if hasattr(bundle.get('forecast_reference'), 'tolist') else [],'forecast_reference_timestamps':bundle.get('forecast_timestamps',[]),'uncertainty':'Approved-version uncalibrated indicator, not a deviation probability.','explanation':f"Latest {latest:.4f} versus approved reference mean {reference.mean():.4f}; engineering range {p['low']} to {p['high']}."})
    features=artifact['features']
    if not set(features).issubset(wide.columns) or wide[features].iloc[-1].isna().any():joint={'status':'insufficient_data','flag':False,'explanation':'Latest multivariate sample is incomplete'}
    else:
        x=(wide[features].iloc[-1:]-artifact['means'])/artifact['std'];distance=float(artifact['covariance'].mahalanobis(x)[0]);threshold=artifact['joint_threshold']
        joint={'status':'complete','method':'approved_shrinkage_mahalanobis_and_isolation_forest','parameters':features,'score':float(min(distance/threshold,2)/2),'mahalanobis_squared':distance,'reference_threshold':threshold,'forest_indicator':int(artifact['forest'].predict(x)[0]),'flag':distance>threshold,'model_id':model['id'],'explanation':f'Joint distance {distance:.4f}, approved threshold {threshold:.4f}; uncalibrated screening indicator.'}
    return {'findings':findings,'multivariate':joint}
