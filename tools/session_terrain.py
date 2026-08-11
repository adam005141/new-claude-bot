#!/usr/bin/env python3
"""
Measure what each regional session can support, before any strategy is designed.

EXPLORATORY CHARACTERISATION, NOT A HYPOTHESIS TEST. Nothing here may be reported as a
finding without fresh confirmation on unopened data. It exists to answer one question:
which sessions can carry an intraday strategy at all, given what a round trip costs.

The number that matters is `cost/range`: one round trip as a fraction of the median
session range. It is the hurdle any strategy working inside that window must clear before
it earns a cent, and it varies by a factor of five across the four windows.

Windows are minutes-since-open, so they are DST-correct by construction:

    ASIA    -930..-390   18:00-03:00 ET
    LONDON  -390..0      03:00-09:30 ET
    NY         0..390    09:30-16:00 ET
    POST     390..450    16:00-17:00 ET

The account must be flat 17:00-18:00 ET, so these four tile the whole tradeable day.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.data import build_continuous  # noqa: E402
from engine.overnight import minutes_since_open  # noqa: E402

WINDOWS = {"ASIA": (-930, -390), "LONDON": (-390, 0), "NY": (0, 390), "POST": (390, 450)}
TICK = 0.25
ROUND_TRIP_PTS = 2 * (0.5 + 0.5) * TICK      # one tick per side, ES quotes one tick wide


def terrain(data: str, symbol: str, start: str, end: str) -> pd.DataFrame:
    c = build_continuous(data, symbol, bar_size="30min")
    c = c[~c["thin_session"] & ~c["entries_blocked"]].copy()
    c["mso"] = minutes_since_open(c)
    sd = c["session_date"].astype(str)
    c = c[(sd >= start) & (sd <= end)]

    total_vol = c["volume"].sum()
    rows = []
    for name, (a, b) in WINDOWS.items():
        w = c[(c["mso"] >= a) & (c["mso"] < b)]
        g = w.sort_values("timestamp_utc").groupby("session_date")
        rng = g["high"].max() - g["low"].min()
        ret = g["close"].last() - g["open"].first()
        rows.append({
            "window": name, "et": f"{a}..{b}", "sessions": len(ret),
            "vol_share": w["volume"].sum() / total_vol,
            "median_range": rng.median(),
            "median_abs_move": ret.abs().median(),
            "drift": ret.mean(),
            "t": ret.mean() / (ret.std(ddof=1) / np.sqrt(len(ret))),
            "cost_over_range": ROUND_TRIP_PTS / rng.median(),
            "drift_over_cost": ret.mean() / ROUND_TRIP_PTS,
        })
    return pd.DataFrame(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data_history")
    ap.add_argument("--symbol", default="ES")
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    args = ap.parse_args(argv)

    d = terrain(args.data, args.symbol, args.start, args.end)
    print(f"{args.symbol} {args.start[:4]}-{args.end[:4]}, {d['sessions'].max()} sessions")
    print("EXPLORATORY. Not a hypothesis test; no finding may be reported from it alone.\n")
    print(f"  {'window':<8}{'ET':<14}{'vol':>7}{'range':>8}{'|move|':>8}"
          f"{'drift':>9}{'t':>7}{'cost/rng':>10}{'drift/cost':>12}")
    for _, r in d.iterrows():
        print(f"  {r['window']:<8}{r['et']:<14}{r['vol_share']:>7.1%}"
              f"{r['median_range']:>8.2f}{r['median_abs_move']:>8.2f}"
              f"{r['drift']:>+9.3f}{r['t']:>7.2f}{r['cost_over_range']:>10.1%}"
              f"{r['drift_over_cost']:>12.2f}x")
    print(f"\n  round trip {ROUND_TRIP_PTS} pts. drift/cost below 1.0 means buy-and-hold in")
    print("  that window cannot pay for its own execution.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
