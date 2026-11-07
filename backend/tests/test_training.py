"""Exercise real chronological supervised evaluation and model serialization."""
from backend.tests.test_system import client,auth
from datetime import datetime,timedelta,timezone
import uuid

def test_research_model_evaluation(client,auth):
 prefix='ML-'+uuid.uuid4().hex[:5];rows=[]
 for b in range(6):
  for t in range(30):
   for parameter,unit,center in [('temperature','°C',37),('pH','pH',7.1)]:
    abnormal=t>=20
    rows.append({'process':'fermentation','batch':f'{prefix}-{b}','equipment':'ML-EQ','timestamp':(datetime(2026,2,1,tzinfo=timezone.utc)+timedelta(days=b,minutes=t)).isoformat(),'parameter':parameter,'unit':unit,'value':center+(.03*(t%4) if not abnormal else 2),'source':'synthetic','label':int(abnormal)})
 response=client.post('/api/v1/data/ingest',headers=auth,json={'records':rows});assert response.status_code==200,response.text
 result=client.post('/api/v1/models/train',headers=auth,json={});assert result.status_code==200,result.text
 models=result.json();assert {'random_forest','gradient_boosting'}.issubset({m['name'] for m in models})
 for m in models:
  assert m['approval_status']=='unapproved'
  assert m['test_batch'] not in m['train_batches']
  assert m['validation_batch'] not in m['train_batches']
  assert 0<=m['metrics']['f1']<=1
  assert m['test_samples']>0
  assert m['distribution_shift']['method']
