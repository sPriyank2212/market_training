"""Do signals carry forward information? Signed forward spot move after the signal minute vs matched random minutes."""
import pandas as pd, numpy as np
from common import *
rng=np.random.default_rng(7)
s=load_sigs(); s["i"]=(s.ts.dt.hour*60+s.ts.dt.minute)-555
def fwd(c,i,sgn,k): 
    j=min(i+k,len(c)-1); return sgn*(c.close.iloc[j]-c.open.iloc[i])
rows=[]
for (d,idx),x in s.groupby(["date","index"]):
    c=load_c(idx,d); sig_i=set(x.i)
    for _,r in x.iterrows():
        i=int(r.i); sgn=1 if r.opt=="CE" else -1
        if i<10 or i>340: continue
        rows.append(dict(kind="signal",idx=idx,f5=fwd(c,i,sgn,5),f15=fwd(c,i,sgn,15),f30=fwd(c,i,sgn,30),p10=sgn*(c.close.iloc[i-1]-c.close.iloc[i-11])))
        cand=[j for j in range(max(10,i-45),min(341,i+46)) if all(abs(j-q)>=3 for q in sig_i)]
        for j in rng.choice(cand,size=min(20,len(cand)),replace=False):
            pm=np.sign(c.close.iloc[j-1]-c.close.iloc[j-11]) or 1
            # control A: same direction as the signal; control B: direction = sign of prior 10-min move (pure momentum rule)
            rows.append(dict(kind="ctrl_same_dir",idx=idx,f5=fwd(c,j,sgn,5),f15=fwd(c,j,sgn,15),f30=fwd(c,j,sgn,30),p10=sgn*(c.close.iloc[j-1]-c.close.iloc[j-11])))
            rows.append(dict(kind="ctrl_momentum_dir",idx=idx,f5=fwd(c,j,pm,5),f15=fwd(c,j,pm,15),f30=fwd(c,j,pm,30),p10=pm*(c.close.iloc[j-1]-c.close.iloc[j-11])))
D=pd.DataFrame(rows)
print(D.groupby(["idx","kind"])[["p10","f5","f15","f30"]].mean().round(2).to_string())
# bootstrap by signal not available -> simple t on signal vs ctrl_same_dir
from scipy import stats
for idx in ("NIFTY","SENSEX"):
    a=D[(D.idx==idx)&(D.kind=="signal")]; b=D[(D.idx==idx)&(D.kind=="ctrl_same_dir")]; m=D[(D.idx==idx)&(D.kind=="ctrl_momentum_dir")]
    for k in ("f5","f15","f30"):
        print(idx,k,"signal %.2f | same-dir ctrl %.2f (p=%.2f) | momentum-dir ctrl %.2f (p=%.2f)"%(a[k].mean(),b[k].mean(),stats.ttest_ind(a[k],b[k],equal_var=False).pvalue,m[k].mean(),stats.ttest_ind(a[k],m[k],equal_var=False).pvalue))
