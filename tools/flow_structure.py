#!/usr/bin/env python3
"""
Does volume discriminate informative price moves from noise? DIAGNOSTIC, not a strategy.

All 84 closed cells are transformations of OHLC. None ever conditioned on volume. This asks
one question the bounce work makes sharp:

  bid-ask bounce should concentrate in THIN bars, where the spread is a larger fraction of
  the move and prints are sparse. Genuine information should sit in HEAVY bars.

If that is right, the negative autocorrelation measured everywhere should be a thin-bar
phenomenon, and heavy bars should be flat or positive. A positive autocorrelation in heavy
bars would be the first trending structure found in this project.

Volume is normalised BY TIME OF DAY before ranking. Raw volume terciles would just separate
New York from Asia, which is the collinearity that voided four earlier filters.

Also computes Bulk Volume Classification order-flow imbalance (Easley, Lopez de Prado,
O'Hara 2012), the standard way to sign bar volume without tick data:

    OFI(t) = V(t) * (2 * Phi(dP(t) / sigma_dP) - 1)

and its forward information coefficient at a one-bar delay. Note honestly what this is:
BVC-OFI is a monotone function of the same bar's price change scaled by its volume, so it
is a volume-weighted transformation of OHLCV, NOT a substitute for true signed order flow.
A null here does not close true order flow. It does close this proxy.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.data import build_continuous  # noqa: E402
from engine.overnight import minutes_since_open  # noqa: E402
from tools.return_structure import variance_ratio  # noqa: E402

def _ncdf(x):
    """Standard normal CDF via erf. scipy is not installed in this environment."""
    return 0.5 * (1.0 + np.vectorize(math.erf)(np.asarray(x, dtype=float) / math.sqrt(2.0)))


VOL_WIN = 60          # sessions of trailing history for the time-of-day volume norm
BVC_WIN = 60          # bars of trailing history for the BVC sigma


def prepare(sym: str, data: str, bar: str, start: str, end: str) -> pd.DataFrame:
    c = build_continuous(data, sym, bar_size=bar)
    c = c[~c["thin_session"]].copy()
    c["mso"] = minutes_since_open(c)
    sd = c["session_date"].astype(str)
    c = c[(sd >= start) & (sd <= end)].sort_values("timestamp_utc").reset_index(drop=True)

    c["ret"] = np.log(c["close"]).diff()
    # break returns at session/contract boundaries and at any gap in mso
    newblk = ((c["session_date"] != c["session_date"].shift())
              | (c["contract_month"] != c["contract_month"].shift()))
    step = c.groupby("session_date")["mso"].diff().median()
    newblk |= (c.groupby("session_date")["mso"].diff() != step)
    c.loc[newblk, "ret"] = np.nan
    c["blk"] = newblk.cumsum()

    # volume normalised by its own time-of-day, using only PAST sessions
    c["vol"] = pd.to_numeric(c["volume"], errors="coerce").fillna(0.0)
    med = (c.groupby("mso")["vol"]
             .transform(lambda s: s.shift(1).rolling(VOL_WIN, min_periods=10).median()))
    c["relvol"] = c["vol"] / med.replace(0, np.nan)

    # BVC order-flow imbalance, causal sigma
    dp = c["close"].diff().where(~newblk)
    sig = dp.shift(1).rolling(BVC_WIN, min_periods=20).std()
    c["ofi"] = c["vol"] * (2 * _ncdf((dp / sig).clip(-6, 6).fillna(0.0)) - 1)
    return c


def pooled_ac(df: pd.DataFrame, mask: pd.Series, max_lag: int):
    """Autocorrelation of returns where the PRIOR bar satisfies `mask`, within blocks."""
    num = np.zeros(max_lag)
    den = 0.0
    n = 0
    r = df["ret"]
    mu = r[mask.shift(1).fillna(False) & r.notna()].mean()
    for _, g in df.groupby("blk", sort=False):
        v = g["ret"].to_numpy()
        m = mask.loc[g.index].to_numpy()
        ok = np.isfinite(v)
        if ok.sum() < max_lag + 2:
            continue
        e = np.where(ok, v - mu, np.nan)
        for k in range(1, max_lag + 1):
            a, b = e[k:], e[:-k]
            sel = np.isfinite(a) & np.isfinite(b) & m[:-k]
            if sel.any():
                num[k - 1] += float((a[sel] * b[sel]).sum())
        sel0 = np.isfinite(e) & m
        den += float((e[sel0] ** 2).sum())
        n += int(sel0.sum())
    return (num / den if den > 0 else num * np.nan), (1 / np.sqrt(n) if n else np.nan), n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="ES")
    ap.add_argument("--data", default="data_5min")
    ap.add_argument("--bar", default="5min")
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    c = prepare(args.symbol, args.data, args.bar, args.start, args.end)
    valid = c["relvol"].notna() & c["ret"].notna()
    q = c.loc[valid, "relvol"].quantile([1 / 3, 2 / 3]).to_numpy()

    print(f"VOLUME-CONDITIONED RETURN STRUCTURE, {args.symbol} {args.bar} "
          "-- DIAGNOSTIC, NOT A STRATEGY")
    print("=" * 96)
    print(f"{c['session_date'].nunique():,} sessions {args.start[:4]}-{args.end[:4]}. "
          "Volume ranked WITHIN time-of-day, causally.")
    print(f"relative-volume tercile cuts: {q[0]:.2f}, {q[1]:.2f}  "
          "(1.00 = typical for that time of day)")
    print("\nAutocorrelation of the return FOLLOWING a bar in each volume tercile:")
    print(f"\n  {'tercile':<10}{'bars':>10}{'2se':>8}{'ac1':>9}{'ac2':>9}{'ac3':>9}"
          + "".join(f"{'VR' + str(x):>14}" for x in (2, 4, 8)))

    res = {}
    bands = {"THIN": (0, q[0]), "MID": (q[0], q[1]), "HEAVY": (q[1], np.inf)}
    for name, (lo, hi) in bands.items():
        mask = valid & (c["relvol"] >= lo) & (c["relvol"] < hi)
        ac, se, n = pooled_ac(c, mask, 3)
        sub = c.loc[mask.shift(1).fillna(False) & c["ret"].notna(), "ret"].to_numpy()
        vrs = {x: variance_ratio(sub, x) for x in (2, 4, 8)}
        res[name] = {"bars": n, "ac": ac.tolist(), "se": se,
                     "vr": {k: {"vr": v, "z": z} for k, (v, z) in vrs.items()}}
        print(f"  {name:<10}{n:>10,}{2 * se:>8.4f}" + "".join(f"{a:>9.4f}" for a in ac)
              + "".join(f"{v:>8.3f}/{z:>+5.1f}" for v, z in vrs.values()))

    # BVC order-flow imbalance: forward IC, immediate and one bar delayed
    print("\nBVC order-flow imbalance -> forward return, information coefficient:")
    print(f"  {'horizon':<10}{'IC (next bar)':>16}{'IC (1-bar delay)':>19}{'n':>10}")
    d = c[c["ofi"].notna() & c["ret"].notna()].copy()
    d["z"] = d["ofi"] / d["ofi"].abs().rolling(BVC_WIN, min_periods=20).mean()
    for h in (1, 2, 4):
        fwd = (np.log(d["close"]).shift(-h) - np.log(d["close"]))
        fwd = fwd.where(d["blk"] == d["blk"].shift(-h))
        dly = (np.log(d["close"]).shift(-h - 1) - np.log(d["close"]).shift(-1))
        dly = dly.where(d["blk"] == d["blk"].shift(-h - 1))
        m = d["z"].notna() & fwd.notna() & dly.notna()
        ic0 = float(d.loc[m, "z"].corr(fwd[m]))
        ic1 = float(d.loc[m, "z"].corr(dly[m]))
        res[f"ofi_h{h}"] = {"ic_immediate": ic0, "ic_delayed": ic1, "n": int(m.sum())}
        print(f"  {h:<10}{ic0:>16.4f}{ic1:>19.4f}{int(m.sum()):>10,}")
    print(f"\n  2-sigma band on an IC at n~{int(m.sum()):,} is about "
          f"{2 / np.sqrt(int(m.sum())):.4f}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(res, indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
