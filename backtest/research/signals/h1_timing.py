"""H1 side-analysis: structure of the signal stream itself (no market data): gaps, cooldowns, time of day, direction flips."""
import numpy as np
from load import *
S = signals(); S = S[S.t.notna()].sort_values(["idx", "t"]).copy()
S["mins"] = S.t.dt.hour * 60 + S.t.dt.minute
print("Earliest/latest signal HH:MM:", S.hhmm.min(), S.hhmm.max())
print("\nSignals by hour (NIFTY / SENSEX):"); print(pd.crosstab(S.t.dt.hour, S.idx).T.to_string())
S["gap"] = S.groupby(["idx", "day"]).mins.diff()
print("\nGap to previous same-index signal (min):"); print(S.groupby("idx").gap.describe().round(1).to_string())
print("gap==0:", int((S.gap == 0).sum()), " gap<=1:", int((S.gap <= 1).sum()), " gap<=3:", int((S.gap <= 3).sum()), " of", int(S.gap.notna().sum()))
print("\nGap histogram (NIFTY):", np.histogram(S[S.idx == "NIFTY"].gap.dropna(), bins=[0, 1, 2, 3, 5, 8, 12, 20, 30, 60, 400])[0])
# direction flips
S["prev_opt"] = S.groupby(["idx", "day"]).opt.shift(); S["same_dir"] = (S.opt == S.prev_opt)
print("\nSame direction as previous signal (same idx/day):", S.groupby("idx").same_dir.mean().round(3).to_dict(),
      " CE share:", S.groupby("idx").opt.apply(lambda s: (s == "CE").mean()).round(3).to_dict())
# per-day counts
print("\nSignals per day:"); print(pd.crosstab(S.day, S.idx).to_string())
# cooldown after SL / T1 on same index
S["prev_status"] = S.groupby(["idx", "day"]).status.shift()
print("\nMedian gap by previous signal's status:"); print(S.groupby(["idx", "prev_status"]).gap.agg(["median", "min", "count"]).round(1).to_string())
# same-minute cross-index
n = S.groupby("t").idx.nunique(); print("\nMinutes with both NIFTY and SENSEX signals:", int((n == 2).sum()), "of", len(n))
# repeated strike
print("Repeated exact (idx, day, trade) rows:", int(S.duplicated(["idx", "day", "Trade"]).sum()))
# time-of-day uniformity of minute-of-hour
print("\nMinute-of-5 :", np.bincount((S.mins % 5).astype(int)), " second-of-minute n/a")
