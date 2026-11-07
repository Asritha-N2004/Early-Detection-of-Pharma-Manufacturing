"""Seed synthetic data and verify this deployment; no secrets in output."""
import csv,json,sys,uuid
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
base=sys.argv[1] if len(sys.argv)>1 else 'https://pharmasignal-manufacturing.vercel.app'
secret=json.loads((ROOT/'.env.vercel.secrets').read_text())
with httpx.Client(base_url=base,timeout=300,follow_redirects=True) as client:
    response=client.get('/health');response.raise_for_status();assert response.json()['status']=='ok'
    print('Public health: passed',flush=True)
    response=client.post('/api/v1/auth/login',json={'username':'admin','password':secret['BOOTSTRAP_PASSWORD']});response.raise_for_status()
    client.headers['Authorization']='Bearer '+response.json()['access_token']
    try:
        if '--seed' in sys.argv:
            for path in sorted((ROOT/'data/synthetic').glob('*.csv')):
                with path.open('rb') as source:response=client.post('/api/v1/data/upload',files={'file':(path.name,source,'text/csv')})
                response.raise_for_status();print(path.stem,response.json(),flush=True)
                with path.open(encoding='utf-8') as source:rows=list(csv.DictReader(source))
                response=client.post('/api/v1/agents/workflow/run',json={'process':path.stem,'batch':rows[-1]['batch'],'event_id':'vercel-bootstrap-'+path.stem})
                response.raise_for_status();print('Investigation:',path.stem,response.json()['status'],flush=True)
        for route in ['processes','dashboard','agents/graph','models','audit/logs','simulation']:
            response=client.get('/api/v1/'+route);response.raise_for_status()
            if route=='audit/logs':assert response.json()['integrity_verified']
            if route=='dashboard':
                dashboard=response.json()
                print('Dashboard totals:',{key:dashboard[key] for key in ['processes','batches','readings','anomalies','investigations']},flush=True)
            print(route+': passed',flush=True)
    finally:
        client.post('/api/v1/auth/logout').raise_for_status()
print('Production verification passed',flush=True)
