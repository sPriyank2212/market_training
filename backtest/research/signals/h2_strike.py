"""H2: strike choice relative to spot at the signal (spot = open of the signal minute bar, and close of previous bar)."""
import numpy as np
from load import *
S = signals(); S = S[S.t.notna() & (S.excl == "")].copy()
rows = []
for i, r in S.iterrows():
    sp = spot(r.idx, r.day); T = r.t
    if T not in sp.index: continue
    st = STEP[r.idx]
    s_open = sp.loc[T, "open"]; s_prev = sp.loc[T - pd.Timedelta(minutes=1), "close"] if T - pd.Timedelta(minutes=1) in sp.index else s_open
    atm = round(s_open / st) * st
    itm = (atm - r.strike) / st if r.opt == "CE" else (r.strike - atm) / st      # +ve = in the money
    S.loc[i, ["spot_open", "spot_prev", "atm", "itm_steps"]] = [s_open, s_prev, atm, itm]
    S.loc[i, "itm_pts"] = (s_open - r.strike) if r.opt == "CE" else (r.strike - s_open)
S["dte"] = (pd.to_datetime(S.expiry) - pd.to_datetime(S.day)).dt.days
S["hr"] = S.t.dt.hour
S["half"] = np.where(S.t.dt.hour * 60 + S.t.dt.minute < 11 * 60, "09:15-11", "11-15:30")
pd.set_option("display.width", 200)
for sym in ("NIFTY", "SENSEX"):
    g = S[S.idx == sym]
    print(f"\n=== {sym}: ITM steps (+ve = in the money; step={STEP[sym]}), all days")
    print(g.itm_steps.value_counts().sort_index().to_string())
    print("by option type:\n", g.groupby("opt").itm_steps.describe().round(2).to_string())
    print("by DTE (days to expiry):\n", g.groupby("dte").itm_steps.agg(["count", "mean", "median", "std"]).round(2).to_string())
    print("by time:\n", g.groupby("half").itm_steps.agg(["count", "mean", "median", "std"]).round(2).to_string())
    print("fraction within +-1 step of ATM:", round((g.itm_steps.abs() <= 1).mean(), 3),
          " exactly ATM:", round((g.itm_steps == 0).mean(), 3))
    print("corr(itm_steps, entry premium):", round(g[["itm_steps", "entry"]].dropna().corr().iloc[0, 1], 3))
S.to_csv(OUT / "h2_strike_table.csv", index=False)
