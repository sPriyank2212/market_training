"""What moves NIFTY/SENSEX option premiums? (1) Black-Scholes sensitivities for a typical ATM option, (2) empirical check on our cached
1-min Dhan option data: delta/gamma by moneyness, theta by days-to-expiry, IV level by days-to-expiry."""
import numpy as np
from scipy.stats import norm
from opt import *
r = 0.065
def bs(S, K, T, sg, call=True):
    d1 = (np.log(S / K) + (r + .5 * sg**2) * T) / (sg * np.sqrt(T)); d2 = d1 - sg * np.sqrt(T)
    return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2) if call else K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
print("=== (1) Black-Scholes, NIFTY 25,000 ATM call, IV 13%, lot 65: premium change (Rs per unit) for each shock")
print(f"{'DTE':>4} {'premium':>8} {'+100pt spot':>12} {'-100pt spot':>12} {'+1 vol pt':>10} {'-1 day':>8} {'-1 day, % of prem':>18} {'+1% rate':>9}")
for dte in (0.25, 1, 2, 5, 10, 30):
    T = dte / 365; p = bs(25000, 25000, T, .13)
    print(f"{dte:>4} {p:8.1f} {bs(25100,25000,T,.13)-p:+12.1f} {bs(24900,25000,T,.13)-p:+12.1f} {bs(25000,25000,T,.14)-p:+10.1f} "
          f"{(bs(25000,25000,max(T-1/365,1e-6),.13)-p) if dte>1 else float('nan'):+8.1f} {((bs(25000,25000,T-1/365,.13)/p-1)*100) if dte>1 else float('nan'):+17.1f}% {bs(25000,25000,T,.13)-p:+9.1f}")
print("\n=== (2) Empirical, from our Dhan 1-min option data (11 signal days + others), strike unchanged between bars")
rows = []
for sym in ("NIFTY",):
    for p_ in sorted(CACHE.glob(f"opt_{sym}_*_c1_CE_k+0.csv")):
        day = p_.name.split("_")[2]
        for k in (-4, -2, 0, 2, 4):
            d = option(sym, day, 1, "CE", k)
            if d.empty or len(d) < 100: continue
            d = d.sort_index(); same = d.strike.eq(d.strike.shift(1))
            ds, dp = d.spot.diff()[same], d.close.diff()[same]
            m = ds.notna() & dp.notna() & (ds.abs() > 0)
            rows.append(pd.DataFrame({"day": day, "k": k, "ds": ds[m], "dp": dp[m], "iv": d.iv[same][m], "px": d.close[same][m]}))
D = pd.concat(rows); D["exp"] = D.day.map(lambda x: x)
# DTE per day from the sheet's expiry for code 1 = nearest weekly: NIFTY expiries Tue (shifted by holidays)
exp = {"2026-10-19": "2026-10-19", "2026-10-21": "2026-10-27", "2026-10-22": "2026-10-27", "2026-10-23": "2026-10-27", "2026-10-26": "2026-10-27", "2026-10-27": "2026-10-27",
       "2026-10-28": "2026-11-03", "2026-10-29": "2026-11-03", "2026-10-30": "2026-11-03", "2026-11-02": "2026-11-03", "2026-11-03": "2026-11-03",
       "2026-11-04": "2026-11-09", "2026-11-05": "2026-11-09", "2026-11-06": "2026-11-09", "2026-11-09": "2026-11-09",
       "2026-11-11": "2026-11-17", "2026-11-12": "2026-11-17", "2026-11-13": "2026-11-17"}
D["dte"] = (pd.to_datetime(D.day.map(exp)) - pd.to_datetime(D.day)).dt.days
D["bucket"] = pd.cut(D.dte, [-1, 0, 2, 7], labels=["0 DTE", "1-2 DTE", "3-7 DTE"])
print("Empirical delta (slope of 1-min premium change on 1-min spot change), ATM call (k=0) and neighbours (k = strike steps from ATM; negative = ITM call):")
tab = D.groupby(["bucket", "k"], observed=True).apply(lambda g: pd.Series({"delta": np.polyfit(g.ds, g.dp, 1)[0], "n": len(g), "median_premium": g.px.median()})).round(2)
print(tab.unstack("k")["delta"].to_string())
print("\nMedian ATM implied vol (%) and ATM premium by days to expiry:")
a = D[D.k == 0].groupby("dte").agg(iv=("iv", "median"), prem=("px", "median")).round(1); print(a.T.to_string())
# theta: ATM straddle decay through the day (CE+PE at k=0), average across days by bucket
th = []
for day in sorted({x.split("_")[2] for x in map(lambda p: p.name, CACHE.glob("opt_NIFTY_*_c1_CE_k+0.csv"))}):
    ce, pe = option("NIFTY", day, 1, "CE", 0), option("NIFTY", day, 1, "PE", 0)
    if ce.empty or pe.empty: continue
    st = (ce.close + pe.close.reindex(ce.index)).dropna()
    for hhmm in ("09:30", "11:30", "13:30", "15:00"):
        t = pd.Timestamp(f"{day} {hhmm}")
        if t in st.index: th.append(dict(day=day, dte=(pd.Timestamp(exp[day]) - pd.Timestamp(day)).days, t=hhmm, straddle=st[t]))
T_ = pd.DataFrame(th); T_["b"] = pd.cut(T_.dte, [-1, 0, 2, 7], labels=["0 DTE", "1-2 DTE", "3-7 DTE"])
print("\nATM straddle (CE+PE) premium through the day, median Rs (time decay + whatever spot did):")
print(T_.pivot_table(index="b", columns="t", values="straddle", aggfunc="median", observed=True).round(0).to_string())
