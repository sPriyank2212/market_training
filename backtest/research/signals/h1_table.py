"""H1: build feature table for signal minutes and matched random control minutes (same day/index,
time-of-day within +-45 min, >=3 min away from any signal). Fixed seed."""
from __future__ import annotations
import numpy as np
from features import *

SEED, NCTRL, WIN, EXCL = 20261116, 20, 45, 2

def decision_row(F: pd.DataFrame, T: pd.Timestamp, off: int):
    ts = T + pd.Timedelta(minutes=off - 1)       # last CLOSED bar when the engine shows minute T (+offset)
    return F.loc[ts] if ts in F.index else None

def add_signed(df: pd.DataFrame) -> pd.DataFrame:
    d = df["dirn"]
    for n in (1, 3, 5, 10):
        df[f"s_ret{n}"] = d * df[f"ret{n}"]; df[f"s_retz{n}"] = d * df[f"retz{n}"]
        df[f"a_ret{n}"] = df[f"ret{n}"].abs(); df[f"a_retz{n}"] = df[f"retz{n}"].abs()
    for n in (15, 30, 60): df[f"s_ret{n}"] = d * df[f"ret{n}"]
    df["s_ema"] = d * df["ema_d"]; df["s_rsi"] = d * (df["rsi14"] - 50); df["s_f5"] = d * df["f5_ret"]
    df["s_f5brk"] = np.where(d > 0, df["f5_brkup"], df["f5_brkdn"])
    df["s_vwap"] = d * df["vwap_d"]; df["s_open"] = d * df["open_d"]
    if "pc_d" in df: df["s_pc"] = d * df["pc_d"]
    df["s_ext"] = np.where(d > 0, df["dh_d"], -df["dl_d"])      # 0 = at day extreme in signal direction
    for n in (5, 10, 15, 30):
        df[f"s_brk{n}"] = np.where(d > 0, df[f"brkup{n}"], df[f"brkdn{n}"])
    return df

def build(off: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    S = signals(); S = S[S.t.notna()]
    rows = []
    for sym in ("NIFTY", "SENSEX"):
        F = feats(sym)
        for day, g in S[S.idx == sym].groupby("day"):
            Fd = F[day]; sig_t = list(g.t)
            blocked = set()
            for t in sig_t:
                for k in range(-EXCL, EXCL + 1): blocked.add(t + pd.Timedelta(minutes=k))
            for _, r in g.iterrows():
                fr = decision_row(Fd, r.t, off)
                if fr is None: continue
                base = dict(idx=sym, day=day, split=r.split, T=r.t, dirn=1 if r.opt == "CE" else -1,
                            row=r.row, excl=r.excl, status=r.status)
                rows.append({**base, "kind": "signal", **fr.to_dict()})
                lo, hi = r.t - pd.Timedelta(minutes=WIN), r.t + pd.Timedelta(minutes=WIN)
                cand = [t for t in Fd.index if lo <= t <= hi and t not in blocked and t.hour * 60 + t.minute >= 9 * 60 + 20
                        and t.hour * 60 + t.minute <= 15 * 60 + 15]
                if not cand: continue
                for t in rng.choice(len(cand), size=min(NCTRL, len(cand)), replace=False):
                    ct = cand[t]; fr2 = decision_row(Fd, ct, off)   # label minute ct == "signal minute"
                    if fr2 is None: continue
                    rows.append({**{**base, "T": ct}, "kind": "control", **fr2.to_dict()})
    return add_signed(pd.DataFrame(rows))

if __name__ == "__main__":
    t = build(0); t.to_csv(OUT / "h1_table_off0.csv", index=False)
    print(t.groupby(["idx", "kind"]).size())
