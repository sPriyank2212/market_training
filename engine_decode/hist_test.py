import pandas as pd, numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.ensemble import HistGradientBoostingClassifier
from common import R
F=pd.read_pickle(R/"data"/"minute_features.pkl").sort_values(["date","index","i"]).reset_index(drop=True)
parts=[]
for (d,idx),g in F.groupby(["date","index"]):
    y=g.n_sig.values; n=len(y); last=np.zeros(n); c10=np.zeros(n); c30=np.zeros(n); cd=np.zeros(n); cs=np.r_[0,np.cumsum(y)]; lt=None
    for i in range(n):
        last[i]=99 if lt is None else min(i-lt,99)
        if y[i]>0: lt=i
        c10[i]=cs[i]-cs[max(i-10,0)]; c30[i]=cs[i]-cs[max(i-30,0)]; cd[i]=cs[i]
    g=g.copy(); g["since_last"]=last; g["c10"]=c10; g["c30"]=c30; g["cday"]=cd; parts.append(g)
F=pd.concat(parts); F=F[(F.i>=1)&(F.i<=358)].reset_index(drop=True)
print("hazard by minutes-since-last signal (same index)")
for idx in ("NIFTY","SENSEX"):
    X=F[F["index"]==idx]; b=pd.cut(X.since_last,[0,1,2,3,5,8,12,20,30,60,100])
    print(idx); print(X.groupby(b,observed=True).y.agg(["mean","size"]).round(3).T.to_string())
base=[c for c in F.columns if c not in("date","n_sig","n_ce","n_pe","y","index","spot","since_last","c10","c30","cday")]
sets={"spot-only":base,"time+hist":["i","since_last","c10","c30","cday"],"spot+hist":base+["since_last","c10","c30","cday"]}
for idx in ("NIFTY","SENSEX"):
    X=F[F["index"]==idx].reset_index(drop=True)
    for nm,feats in sets.items():
        pred=np.zeros(len(X))
        for d in X.date.unique():
            tr=X.date!=d; m=HistGradientBoostingClassifier(max_depth=3,learning_rate=0.05,max_iter=150,min_samples_leaf=40)
            m.fit(X.loc[tr,feats],X.y[tr]); pred[~tr]=m.predict_proba(X.loc[~tr,feats])[:,1]
        print(idx,nm,"LODO AUC %.3f"%roc_auc_score(X.y,pred))
