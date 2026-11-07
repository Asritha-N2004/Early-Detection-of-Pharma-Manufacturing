"""Reproducible synthetic-data profile and engineering visualization."""
import json
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    root=Path(__file__).resolve().parents[1];report={};fig,axes=plt.subplots(2,2,figsize=(12,7));fig.suptitle('SYNTHETIC manufacturing data • seed 42 • not validated records')
    for axis,path in zip(axes.flat,sorted((root/'data/synthetic').glob('*.csv'))):
        frame=pd.read_csv(path);identity=['process','batch','equipment','timestamp','parameter']
        report[path.stem]={'observations':len(frame),'batches':int(frame.batch.nunique()),'missing_values':int(frame.value.isna().sum()),'duplicates':int(frame.duplicated(identity).sum()),'parameters':frame.groupby('parameter').value.agg(['count','min','max','mean','std']).round(5).to_dict(orient='index'),'label_counts':{str(k):int(v) for k,v in frame.label.value_counts().items()},'synthetic':bool((frame.source=='synthetic').all())}
        parameter=frame.parameter.iloc[0];sample=frame[(frame.batch==frame.batch.iloc[0])&(frame.parameter==parameter)].drop_duplicates(identity)
        axis.plot(pd.to_datetime(sample.timestamp),sample.value,color='#2d66dd',linewidth=1.5);axis.axhline(sample.low.iloc[0],color='#cb9353',linestyle='--');axis.axhline(sample.high.iloc[0],color='#cb9353',linestyle='--');axis.set_title(path.stem.title()+' · '+parameter);axis.tick_params(axis='x',labelrotation=20,labelsize=8);axis.set_ylabel(sample.unit.iloc[0]);axis.grid(alpha=.2)
    target=root/'data/processed';target.mkdir(parents=True,exist_ok=True);(target/'profile.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    fig.tight_layout();fig.savefig(target/'synthetic_process_profiles.png',dpi=160);plt.close(fig)
    print('Generated synthetic-data profile and four-process overview.')
if __name__=='__main__':main()
