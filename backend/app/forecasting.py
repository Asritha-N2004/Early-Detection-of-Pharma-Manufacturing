"""Time-aware linear projection and historical, within-window residual envelopes."""
from datetime import datetime
import numpy as np

def minute_axis(timestamps):
    parsed=[datetime.fromisoformat(str(t)) for t in timestamps]
    return np.asarray([(t-parsed[0]).total_seconds()/60 for t in parsed])

def slope_per_minute(values,timestamps):
    if len(values)<2 or len(values)!=len(timestamps):return None
    times=minute_axis(timestamps)
    if np.ptp(times)<=0:return None
    return float(np.polyfit(times,values,1)[0])

def residual_envelope(values,timestamps,horizon,coverage=.9):
    if len(values)<10 or len(values)!=len(timestamps):return None
    values=np.asarray(values,dtype=float);times=minute_axis(timestamps);spacing=np.diff(times)
    positive=spacing[spacing>0]
    if not len(positive):return None
    tolerance=float(np.median(positive))*.5;errors=[]
    for index in range(6,len(values)):
        target=times[index]+horizon;future=int(np.searchsorted(times,target))
        candidates=[j for j in [future-1,future] if index<j<len(values) and abs(times[j]-target)<=tolerance]
        if not candidates:continue
        j=min(candidates,key=lambda j:abs(times[j]-target));start=max(0,index-11);x=times[start:index+1]
        if np.ptp(x)<=0:continue
        slope=float(np.polyfit(x-x[0],values[start:index+1],1)[0]);estimate=values[index]+slope*(times[j]-times[index]);errors.append(abs(values[j]-estimate))
    if len(errors)<8:return None
    return {'radius':float(np.quantile(errors,min(1,coverage*(1+1/len(errors))),method='higher')),'calibration_samples':len(errors),'nominal_coverage':coverage,'matching_tolerance_minutes':tolerance,'method':'within-batch chronological rolling-origin time-horizon residual quantile'}
