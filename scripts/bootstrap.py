"""Load generated synthetic data and execute one investigation per process."""
import sys,csv
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.main import init,ingest,workflow,Ingest,Run
init()
for path in (Path(__file__).resolve().parents[1]/'data/synthetic').glob('*.csv'):
 with path.open(encoding='utf-8') as f:rows=list(csv.DictReader(f))
 for r in rows:
  if r['value']=='':r['value']=None
 print(path.stem,ingest(Ingest(records=rows),{'id':'bootstrap','role':'admin'}))
 print(workflow(Run(process=path.stem,batch=rows[-1]['batch'],event_id='bootstrap-'+path.stem),{'id':'bootstrap','role':'admin'})['status'])
