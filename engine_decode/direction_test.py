"""Which simple, past-only rule predicts CE vs PE? Accuracy per rule, per index; then best 2-feature tree (leave-one-day-out)."""
import pandas as pd, numpy as np, itertools
from sklearn.tree import DecisionTreeClassifier
from common import *
s=load_sigs(); s["i"]=(s.ts.dt.hour*60+s.ts.dt.minute)-555
s=s[s.i>=1].copy()
def ema(a,n): return pd.Series(a).ewm(span=n,adjust=False).mean().values
rows=[]
cache={}
for (d,idx),x in s.groupby(["date","index"]):
    c=load_c(idx,d).reset_index(drop=True); cl=c.close.values
    typ=(c.high+c.low+c.close).values/3; vw=np.cumsum(typ*np.maximum(c.volume.values,1))/np.cumsum(np.maximum(c.volume.values,1)); mean_tp=np.cumsum(typ)/np.arange(1,len(c)+1)
    E={ (a,b):ema(cl,a)-ema(cl,b) for a,b in [(3,9),(5,20),(9,21),(20,50)]}
    dh=pd.Series(c.high).cummax().values; dl=pd.Series(c.low).cummin().values
    for _,r in x.iterrows():
        i=int(r.i); p=i-1; f=dict(date=d,idx=idx,y=1 if r.opt=="CE" else 0)
        for k,v in E.items(): f[f"ema{k[0]}_{k[1]}"]=v[p]
        f["vwap"]=cl[p]-vw[p]; f["meantp"]=cl[p]-mean_tp[p]; f["open"]=cl[p]-c.open.iloc[0]
        for k in (1,3,5,10,15,30,60): f[f"r{k}"]=cl[p]-cl[max(p-k,0)]
        f["pos"]=(cl[p]-dl[p])/(dh[p]-dl[p]+1e-9)-0.5
        rows.append(f)
D=pd.DataFrame(rows); feats=[c for c in D.columns if c not in("date","idx","y")]
for idx in ("NIFTY","SENSEX"):
    X=D[D.idx==idx]; print(f"\n{idx}: n={len(X)} CE share {X.y.mean():.2f}")
    acc={f:max(((X[f]>0)==(X.y==1)).mean(), 0) for f in feats}
    print(" sign-rule accuracy:", {k:round(v,2) for k,v in sorted(acc.items(),key=lambda t:-t[1])[:8]})
    best=[]
    for a,b in itertools.combinations(feats,2):
        ok=[]
        for d in X.date.unique():
            tr=X[X.date!=d]; te=X[X.date==d]
            m=DecisionTreeClassifier(max_depth=2,min_samples_leaf=8).fit(tr[[a,b]],tr.y); ok+=list(m.predict(te[[a,b]])==te.y)
        best.append((np.mean(ok),a,b))
    best.sort(reverse=True); print(" best 2-feature depth-2 tree, LODO acc:", [(round(x,3),a,b) for x,a,b in best[:5]])
