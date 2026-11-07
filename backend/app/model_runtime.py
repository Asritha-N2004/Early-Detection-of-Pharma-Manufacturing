"""Approved-model inference, artifact verification, attribution and drift signals."""
import hashlib,os,io
from pathlib import Path
import joblib
from functools import lru_cache
import numpy as np
import pandas as pd

MODEL_ROOT=Path(os.getenv('MODEL_ROOT',str(Path(__file__).resolve().parents[2]/'ml'/'models')))

def store_artifact(db,version,artifact):
    """Store trusted server-trained bytes durably; local files remain supported."""
    stream=io.BytesIO();joblib.dump(artifact,stream);data=stream.getvalue()
    digest=hashlib.sha256(data).hexdigest()
    if os.getenv('MODEL_STORAGE')=='database':
        from .database import ModelArtifact
        if not db.get(ModelArtifact,digest):db.add(ModelArtifact(digest=digest,data=data))
        return 'database:'+digest,digest
    MODEL_ROOT.mkdir(parents=True,exist_ok=True)
    path=MODEL_ROOT/(version+'.joblib');path.write_bytes(data)
    return str(path),digest

def checked_artifact(model):
    if model['artifact'].startswith('database:'):
        digest=model['artifact'][9:]
        if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest) or digest!=model.get('artifact_sha256'):raise ValueError('Model artifact integrity mismatch')
        from .database import ModelArtifact,Session
        with Session() as db:
            row=db.get(ModelArtifact,digest)
            if not row or hashlib.sha256(row.data).hexdigest()!=digest:raise ValueError('Model artifact integrity mismatch')
            MODEL_ROOT.mkdir(parents=True,exist_ok=True)
            path=MODEL_ROOT/(digest+'.joblib')
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                import tempfile
                with tempfile.NamedTemporaryFile(dir=MODEL_ROOT,delete=False) as file:
                    file.write(row.data);temporary=Path(file.name)
                temporary.replace(path)
        return path
    path=Path(model['artifact']).resolve()
    if not path.is_relative_to(MODEL_ROOT.resolve()) or not path.is_file():raise ValueError('Model artifact is outside the trusted registry directory or missing')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!=model.get('artifact_sha256'):raise ValueError('Model artifact integrity mismatch')
    return path

@lru_cache(maxsize=16)
def _load_version(path,digest):
    return joblib.load(path)

def load_artifact(model):
    path=checked_artifact(model)
    return _load_version(str(path),model['artifact_sha256'])

def infer_model(model,readings,drift_threshold=1.0):
    if not model:return {'status':'no_active_model','warning':False,'uncertainty':'No approved model enabled; deterministic forecasts remain available.'}
    if model.get('approval_status')!='approved' or model.get('status')!='active':raise ValueError('Only approved active models may infer')
    artifact=load_artifact(model)
    wide=pd.DataFrame(readings).pivot_table(index='timestamp',columns='parameter',values='value').sort_index()
    features=artifact['features']
    if not set(features).issubset(wide.columns):return {'status':'missing_features','warning':False,'missing_features':sorted(set(features)-set(wide.columns))}
    if wide[features].iloc[-1].isna().any():return {'status':'missing_features','warning':False,'missing_features':wide[features].iloc[-1].index[wide[features].iloc[-1].isna()].tolist(),'uncertainty':'Latest sample is incomplete; older samples are not substituted silently.'}
    complete=wide[features].dropna()
    if complete.empty:return {'status':'missing_features','warning':False}
    x=complete.iloc[-1:];classifier=artifact['model'];raw=float(classifier.predict_proba(x)[0,1]);calibrator=artifact.get('calibrator')
    probability=float(calibrator.predict_proba(np.array([[raw]]))[0,1]) if calibrator is not None else None
    value=probability if probability is not None else raw;threshold=artifact.get('probability_threshold',.5)
    baseline=artifact.get('baseline',{});shift={}
    for c in features:
        stats=baseline.get(c)
        if stats:shift[c]=float(abs(complete[c].tail(30).mean()-stats['mean'])/max(stats['std'],1e-6))
    drift={'method':'rolling mean standardized against training reference','scores':shift,'threshold':drift_threshold,'flagged':[k for k,v in shift.items() if v>=drift_threshold]}
    shap_result={}
    try:
        import shap
        values=np.asarray(shap.TreeExplainer(classifier).shap_values(x))
        if values.ndim==3:values=values[:,:,1]
        shap_result=dict(zip(features,values[0].tolist()))
    except (ValueError,TypeError,ImportError):pass
    return {'status':'complete','model_id':model['id'],'version':model['version'],'category':'potential_next_sample_excursion' if value>=threshold else 'no_predicted_next_sample_excursion','warning':value>=threshold,'decision_threshold':threshold,'calibrated_probability':probability,'uncalibrated_score':raw if probability is None else None,'horizon':'next observed sample; distinct from minute-based trend forecast','uncertainty':'Sigmoid calibration on a separate validation batch; external calibration and real-process validation remain required.' if probability is not None else 'Uncalibrated score; not a deviation probability.','drift':drift,'shap':shap_result,'timestamp':str(complete.index[-1])}
