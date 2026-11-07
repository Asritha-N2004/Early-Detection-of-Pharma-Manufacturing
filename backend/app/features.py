"""Reusable time-aligned features with strictly historical window semantics."""
import numpy as np
import pandas as pd
from pydantic import BaseModel,Field

class FeatureWindow(BaseModel):
    parameter:str
    sample_count:int
    mean:float
    std:float
    slope_per_sample:float
    ewma:float

def aligned_frame(readings):
    if not readings:return pd.DataFrame()
    return pd.DataFrame(readings).pivot_table(index='timestamp',columns='parameter',values='value',aggfunc='mean').sort_index()

def historical_features(readings,window=12):
    if window<3:raise ValueError('A feature window needs at least three historical observations')
    frame=aligned_frame(readings);result=[]
    for parameter in frame:
        values=frame[parameter].dropna().tail(window)
        if len(values)<3:continue
        result.append(FeatureWindow(parameter=parameter,sample_count=len(values),mean=float(values.mean()),std=float(values.std(ddof=0)),slope_per_sample=float(np.polyfit(np.arange(len(values)),values,1)[0]),ewma=float(values.ewm(alpha=.3,adjust=False).mean().iloc[-1])).model_dump())
    return result
