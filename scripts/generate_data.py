"""Reproducible synthetic records. No real manufacturing information."""
import sys,csv
from pathlib import Path
from datetime import datetime,timedelta,timezone
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.registry import PROCESSES

def generate(seed=42):
 rng=np.random.default_rng(seed);start=datetime(2026,1,1,tzinfo=timezone.utc)
 for process,params in PROCESSES.items():
  for batch in range(6):
   variation=rng.normal(0,.025)
   for t in range(70):
    if t in [32,33,34]:continue # deliberate communication interruption
    for i,(name,low,high,unit) in enumerate(params):
     drift=max(0,t-35)/40 if i<2 else 0
     spike=.8 if t in [25,26] and i==2 else 0
     v=(low+high)/2+(high-low)*(rng.normal(0,.055)+variation+drift+spike)
     missing=t==15 and i==0
     row={'process':process,'batch':f'{process[:3].upper()}-{batch+1:03}','equipment':f'EQ-{process[:3].upper()}-01','timestamp':(start+timedelta(days=batch,minutes=t)).isoformat(),'parameter':name,'value':None if missing else round(v,5),'unit':unit,'source':'synthetic','stage':'monitoring','label':int(v<low or v>high),'low':low,'high':high,'quality':'missing' if missing else 'synthetic'}
     yield row
     if t==8 and i==0:yield row.copy()
if __name__=='__main__':
 root=Path(__file__).resolve().parents[1]/'data/synthetic';root.mkdir(parents=True,exist_ok=True)
 rows=list(generate())
 for process in PROCESSES:
  selected=[r for r in rows if r['process']==process]
  with (root/f'{process}.csv').open('w',newline='',encoding='utf-8') as f:
   writer=csv.DictWriter(f,fieldnames=list(selected[0]));writer.writeheader();writer.writerows(selected)
 print(f'Generated {len(rows)} clearly synthetic observations, seed 42.')
