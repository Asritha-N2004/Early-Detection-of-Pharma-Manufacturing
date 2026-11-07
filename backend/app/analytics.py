"""Deterministic analytics; scores are not calibrated event probabilities."""
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.svm import OneClassSVM
from sklearn.neural_network import MLPRegressor

METHODS=['zscore','isolation_forest','lof','one_class_svm','rolling','ewma','cusum','autoencoder']
def analyze(series,parameters,method='ensemble'):
 results=[]
 for p in parameters:
  samples=[r for r in series if r['parameter']==p['name']];values=np.array([r['value'] for r in samples],dtype=float)
  if len(values)<8:continue
  # Reference consists exclusively of the earlier portion; test window never fits models.
  split=max(6,int(len(values)*0.65)); train=values[:split]; test=values[split:]
  if not len(test):continue
  center=(p['low']+p['high'])/2; scale=max((p['high']-p['low'])/6,1e-6)
  x=((train-center)/scale).reshape(-1,1); y=((test-center)/scale).reshape(-1,1)
  scores={}; scores['zscore']=float(min(abs(y[-1,0])/6,1))
  prior=values[max(0,len(values)-21):-1];scores['rolling']=float(min(abs(values[-1]-prior.mean())/max(prior.std(),scale/2)/6,1))
  ewma=0.; cusum=0.
  for v in y[:,0]:ewma=.3*v+.7*ewma; cusum=max(0,cusum+abs(v)-.5)
  scores['ewma']=float(min(abs(ewma)/4,1));scores['cusum']=float(min(cusum/20,1))
  requested=METHODS if method=='ensemble' else [method]
  for name in requested:
   if name in scores:continue
   if name=='isolation_forest':
    model=IsolationForest(n_estimators=40,random_state=42,contamination=.05).fit(x)
   elif name=='lof':model=LocalOutlierFactor(n_neighbors=min(20,len(x)-1),novelty=True,contamination=.05).fit(x)
   elif name=='one_class_svm':model=OneClassSVM(nu=.05,gamma='scale').fit(x)
   else:
    model=MLPRegressor(hidden_layer_sizes=(3,1,3),max_iter=120,random_state=42,solver='lbfgs').fit(x,x.ravel())
    error=np.abs(model.predict(x)-x.ravel()); current=abs(float(model.predict(y[-1:])[0])-y[-1,0])
    scores[name]=float(min(current/max(float(np.quantile(error,.95)),.5)/4,1));continue
   scores[name]=float(np.clip(.5-model.decision_function(y[-1:])[0],0,1))
  selected=float(np.mean([scores[k] for k in requested]))
  outside=bool(test[-1]<p['low'] or test[-1]>p['high'])
  slope=float(np.polyfit(np.arange(min(12,len(test))),test[-12:],1)[0]) if len(test)>1 else 0
  results.append({'parameter':p['name'],'timestamp':next(r['timestamp'] for r in reversed(series) if r['parameter']==p['name']),'detection_method':method,'uncertainty':'Uncalibrated screening indicator; not a probability of a deviation.','value':float(test[-1]),'low':p['low'],'high':p['high'],'score':round(selected,4),'methods':scores,'outside_range':outside,'flag':outside or selected>=p.get('alert_threshold',.65),'baseline':float(train.mean()),'slope_per_sample':slope,'attribution':float(abs(test[-1]-train.mean())/scale),'explanation':f"Latest value {test[-1]:.3f}; reference mean {train.mean():.3f}; engineering range {p['low']}–{p['high']}.",'reference_count':len(train),'test_count':len(test),'forecast_reference':train.tolist(),'forecast_reference_timestamps':[r['timestamp'] for r in samples[:split]],'slope_per_minute':__import__('backend.app.forecasting',fromlist=['slope_per_minute']).slope_per_minute(values[-12:].tolist(),[r['timestamp'] for r in samples[-12:]])})
 return results

def predict(findings,horizon,interval_minutes=1,coverage=.9):
 from .forecasting import residual_envelope
 outputs=[]
 for f in findings:
  slope=f.get('slope_per_minute')
  if slope is None:slope=f['slope_per_sample']/max(interval_minutes,.001)
  forecast=f['value']+slope*horizon;distance=max(f['high']-f['low'],1e-6);crossing=forecast<f['low'] or forecast>f['high']
  calibrated=residual_envelope(f.get('forecast_reference',[]),f.get('forecast_reference_timestamps',[]),horizon,coverage)
  interval={'lower':forecast-calibrated['radius'],'upper':forecast+calibrated['radius'],**{k:v for k,v in calibrated.items() if k!='radius'}} if calibrated else None
  trajectory=[]
  for step in range(1,7):
   minutes=horizon*step/6;point=f['value']+slope*minutes;bounds=residual_envelope(f.get('forecast_reference',[]),f.get('forecast_reference_timestamps',[]),minutes,coverage)
   trajectory.append({'minutes':minutes,'forecast':point,'interval':[point-bounds['radius'],point+bounds['radius']] if bounds else None})
  outputs.append({'trajectory':trajectory,'parameter':f['parameter'],'observed_value':f['value'],'low':f['low'],'high':f['high'],'forecast':forecast,'horizon_minutes':horizon,'early_warning':crossing and not f['outside_range'],'already_outside_range':f['outside_range'],'category':'potential_range_excursion' if crossing else 'stable_projection','risk_score':float(min(abs(forecast-(f['low']+f['high'])/2)/distance,1)),'uncertainty':f'Empirical {coverage:.0%} within-batch time-horizon residual envelope; dependence and drift can invalidate coverage.' if interval else 'Insufficient within-batch horizon residuals for an interval; score is not a probability.','interval':interval,'method':'time_aware_linear_trend','prediction':True})
 return outputs

def assess(severity,occurrence,detectability,patient_safety=False,critical_parameter=False,thresholds=None):
 t=thresholds or {'medium':20,'high':50,'critical':90}
 rpn=severity*occurrence*detectability
 critical=patient_safety or (critical_parameter and severity>=t.get('critical_parameter_severity',4))
 level='Critical' if critical or rpn>=t['critical'] else 'High' if rpn>=t['high'] else 'Medium' if rpn>=t['medium'] else 'Low'
 return {'severity':severity,'occurrence':occurrence,'detectability':detectability,'rpn':rpn,'classification':level,'critical_override':critical,'contributing_factors':{'patient_safety_flag':patient_safety,'critical_parameter_flag':critical_parameter,'critical_severity_trigger':t.get('critical_parameter_severity',4)},'configuration_snapshot':t,'explanation':'FMEA-inspired screening using configurable thresholds; patient-safety or critical-parameter rule overrides RPN. Scores require quality review.','escalation':'Authorized quality investigation' if level in ['High','Critical'] else 'Process reviewer assessment'}

def multivariate_analyze(readings,parameters):
 import pandas as pd
 from sklearn.covariance import LedoitWolf
 wide=pd.DataFrame(readings).pivot_table(index='timestamp',columns='parameter',values='value').sort_index().dropna()
 if wide.shape[0]<16 or wide.shape[1]<2:return {'status':'insufficient_data','flag':False,'explanation':'At least 16 complete aligned samples and two parameters required.'}
 split=max(10,int(len(wide)*.65));train=wide.iloc[:split];test=wide.iloc[split:]
 if test.empty:return {'status':'insufficient_data','flag':False}
 means=train.mean();scale=train.std().clip(lower=1e-6);x=(train-means)/scale;y=(test-means)/scale
 covariance=LedoitWolf().fit(x);baseline=covariance.mahalanobis(x);distances=covariance.mahalanobis(y)
 threshold=max(float(np.quantile(baseline,.99))*1.5,wide.shape[1]*2.5)
 forest=IsolationForest(n_estimators=60,random_state=42,contamination=.05).fit(x)
 current=float(distances[-1]);score=float(min(current/threshold,2)/2)
 return {'status':'complete','method':'shrinkage_mahalanobis_and_isolation_forest','parameters':wide.columns.tolist(),'score':score,'mahalanobis_squared':current,'reference_threshold':threshold,'forest_indicator':int(forest.predict(y.iloc[-1:])[0]),'flag':bool(current>threshold),'reference_samples':len(train),'test_samples':len(test),'explanation':f'Joint standardized covariance distance {current:.3f} versus reference threshold {threshold:.3f}. Changed parameter relationships are screening evidence, not a probability.','timeline':[{'timestamp':t,'distance':float(d),'flag':bool(d>threshold)} for t,d in zip(test.index,distances)]}
