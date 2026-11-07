import math
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict

class Measurement(BaseModel):
 model_config=ConfigDict(extra='forbid')
 process: str=Field(min_length=1,max_length=80)
 batch: str=Field(min_length=1,max_length=80)
 equipment: str=Field(min_length=1,max_length=80)
 timestamp: datetime
 parameter: str=Field(min_length=1,max_length=80)
 value: float|None
 unit: str=Field(min_length=1,max_length=30)
 source: Literal['synthetic','uploaded','rest']='rest'
 stage: str=Field(default='monitoring',min_length=1,max_length=80)
 label: int|None=Field(default=None,ge=0,le=1)
 low: float|None=Field(default=None,allow_inf_nan=False)
 high: float|None=Field(default=None,allow_inf_nan=False)
 quality: str|None=Field(default=None,max_length=80)
 @field_validator('timestamp')
 @classmethod
 def utc(cls,v):
  if v.tzinfo is None:raise ValueError('timezone required')
  if v > datetime.now(timezone.utc):raise ValueError('future timestamp')
  return v.astimezone(timezone.utc)
 @field_validator('value')
 @classmethod
 def finite(cls,v):
  if v is not None and not math.isfinite(v):raise ValueError('finite measurement required')
  return v
class Ingest(BaseModel):
 records: list[Measurement]=Field(min_length=1,max_length=20000)
class Run(BaseModel):
 process: str='fermentation'
 batch: str|None=None
 equipment:str|None=None
 event_id: str=Field(min_length=1,max_length=100)
 method: Literal['ensemble','zscore','isolation_forest','lof','one_class_svm','rolling','ewma','cusum','autoencoder']='ensemble'
 horizon: int=Field(default=15,ge=1,le=120)
class HumanReview(BaseModel):
 decision: Literal['accept','reject','more_evidence','escalate']
 notes: str=Field(min_length=10,max_length=10000)
class RiskInput(BaseModel):
 severity: int=Field(ge=1,le=10)
 occurrence: int=Field(ge=1,le=10)
 detectability: int=Field(ge=1,le=10)
 patient_safety: bool=False
 critical_parameter: bool=False
class SimulationInput(BaseModel):
 action: Literal['start','pause','stop','reset','step']
 process: str='fermentation'
 scenario: Literal['normal','drift','spike','sensor_failure','equipment_fault']='normal'
 interval: float=Field(default=3,ge=1,le=60)
