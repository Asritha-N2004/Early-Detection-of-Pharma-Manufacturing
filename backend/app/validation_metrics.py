from datetime import datetime
import numpy as np

def event_timing(timestamps,labels,alerts,lookback_minutes=15):
    """Event-onset measures on held-out observations, with missing events explicit."""
    times=[datetime.fromisoformat(t) for t in timestamps]
    labels=np.asarray(labels,dtype=bool);alerts=np.asarray(alerts,dtype=bool)
    events=[]
    for i,positive in enumerate(labels):
        if not positive or (i and labels[i-1]):continue
        end=i+1
        while end<len(labels) and labels[end]:end+=1
        before=[j for j in range(i) if alerts[j] and not labels[j] and 0<(times[i]-times[j]).total_seconds()<=lookback_minutes*60]
        during=[j for j in range(i,end) if alerts[j]]
        events.append({'onset':timestamps[i],'detected':bool(before or during),'detection_delay_seconds':0.0 if before else (times[during[0]]-times[i]).total_seconds() if during else None,'early_warning_lead_seconds':(times[i]-times[before[0]]).total_seconds() if before else 0.0})
    delays=[e['detection_delay_seconds'] for e in events if e['detection_delay_seconds'] is not None]
    return {'definition':'Contiguous held-out excursion events; warning search limited to prior 15 minutes of labeled normal observations.','events':events,'event_recall':sum(e['detected'] for e in events)/len(events) if events else None,'mean_detection_delay_seconds':float(np.mean(delays)) if delays else None,'mean_early_warning_lead_seconds':float(np.mean([e['early_warning_lead_seconds'] for e in events])) if events else None,'event_count':len(events)}
