#!/usr/bin/env python3
"""
Test whether ES data is an acceptable proxy for MES signal research.

Why this exists
---------------
SPECIFICATION.md section 3 forbids transferring parent-contract levels to micro
execution, and requires an ablation before any parent feed is trusted. That rule was
written as a precaution, not as a measurement. This tool replaces the precaution with
evidence, using the period where BOTH datasets exist.

ES and MES track the same index and share a 0.25-point tick, so in principle their
opening ranges are the same levels. In practice they are separate order books with their
own basis, and Leg B's edge lives in a few ticks. Whether "in principle" survives contact
with the data is exactly what a few ticks of basis decides.

What it measures
----------------
1. Price basis, ES minus MES, in ticks.
2. Opening-range levels computed independently on each, in ticks of difference.
3. THE DECISIVE TEST: whether Leg B's entry trigger fires identically on both. Feature
   levels agreeing on average is not enough; what matters is whether the strategy would
   have taken the same trades.

Usage
-----
    python tools/compare_es_mes.py --data data
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.config import INSTRUMENTS, StrategyParams          # noqa: E402
from engine.data import build_continuous, resample             # noqa: E402
from engine.features import compute                            # noqa: E402

log = logging.getLogger("compare_es_mes")


def prepare(data_dir: str, symbol: str, decision_minutes: int,
            params: StrategyParams) -> pd.DataFrame:
    cont = build_continuous(data_dir, symbol)
    bars = resample(cont, decision_minutes)
    return compute(bars, or_minutes=params.or_minutes, atr_window=params.atr_window,
                   rvol_lookback=params.rvol_lookback, bar_minutes=decision_minutes)


def entry_trigger(df: pd.DataFrame, params: StrategyParams) -> pd.Series:
    """
    Leg B's directional trigger, as a signed series: +1 long, -1 short, 0 none.

    Deliberately only the breakout condition, not the full filter chain. Filters depend on
    volume, which legitimately differs between a mini and a micro; the question here is
    whether the PRICE-based trigger agrees.
    """
    buf = params.b_buffer_atr * df["atr"]
    long_ = df["or_ready"] & (df["close"] > df["or_high"] + buf)
    short = df["or_ready"] & (df["close"] < df["or_low"] - buf)
    return long_.astype(int) - short.astype(int)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--parent", default="ES")
    ap.add_argument("--micro", default="MES")
    ap.add_argument("--decision-minutes", type=int, default=5)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(message)s")
    params = StrategyParams()
    tick = INSTRUMENTS[args.micro].tick_size

    try:
        parent = prepare(args.data, args.parent, args.decision_minutes, params)
        micro = prepare(args.data, args.micro, args.decision_minutes, params)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 1

    merged = parent.merge(micro, on="timestamp_utc", suffixes=("_p", "_m"), how="inner")
    if merged.empty:
        print(f"No overlapping timestamps between {args.parent} and {args.micro}.")
        print(f"  {args.parent}: {parent['session_date'].min()} to {parent['session_date'].max()}")
        print(f"  {args.micro}: {micro['session_date'].min()} to {micro['session_date'].max()}")
        print("\nWithout an overlap the proxy assumption cannot be tested, only asserted.")
        return 1

    sessions = merged["session_date_p"].nunique()
    print(f"\nOverlap: {len(merged):,} bars across {sessions} sessions "
          f"({merged['session_date_p'].min()} to {merged['session_date_p'].max()})\n")

    # --- 1. price basis ---------------------------------------------------
    basis = (merged["close_p"] - merged["close_m"]) / tick
    print("=== price basis, ES minus MES, in ticks ===")
    for label, value in (("median", basis.median()), ("mean", basis.mean()),
                         ("p05", basis.quantile(0.05)), ("p95", basis.quantile(0.95)),
                         ("max |basis|", basis.abs().max())):
        print(f"  {label:<14}{value:>10.3f}")
    print(f"  within 1 tick {(basis.abs() <= 1).mean():>9.1%}")

    # --- 2. opening-range levels -----------------------------------------
    ready = merged["or_ready_p"] & merged["or_ready_m"]
    if ready.any():
        hi = ((merged.loc[ready, "or_high_p"] - merged.loc[ready, "or_high_m"]) / tick).abs()
        lo = ((merged.loc[ready, "or_low_p"] - merged.loc[ready, "or_low_m"]) / tick).abs()
        print("\n=== opening-range level difference, in ticks ===")
        print(f"  {'':<14}{'median':>10}{'p95':>10}{'max':>10}")
        print(f"  {'OR high':<14}{hi.median():>10.3f}{hi.quantile(.95):>10.3f}{hi.max():>10.3f}")
        print(f"  {'OR low':<14}{lo.median():>10.3f}{lo.quantile(.95):>10.3f}{lo.max():>10.3f}")

    # --- 3. the decisive test --------------------------------------------
    tp = entry_trigger(merged.rename(columns=lambda c: c[:-2] if c.endswith("_p") else c),
                       params)
    tm = entry_trigger(merged.rename(columns=lambda c: c[:-2] if c.endswith("_m") else c),
                       params)
    evaluated = merged["or_ready_p"] & merged["or_ready_m"]
    tp, tm = tp[evaluated], tm[evaluated]

    agree = (tp == tm)
    fires = (tp != 0) | (tm != 0)
    print("\n=== DECISIVE TEST: would Leg B have taken the same trades? ===")
    print(f"  bars evaluated            {len(tp):>10,}")
    print(f"  bars where either fires   {int(fires.sum()):>10,}")
    print(f"  overall agreement         {agree.mean():>10.2%}")
    if fires.any():
        print(f"  agreement when either fires {agree[fires].mean():>8.2%}")
        print(f"  fires on {args.parent} only        {int(((tp != 0) & (tm == 0)).sum()):>10,}")
        print(f"  fires on {args.micro} only       {int(((tm != 0) & (tp == 0)).sum()):>10,}")
        print(f"  opposite directions       "
              f"{int(((tp != 0) & (tm != 0) & (tp != tm)).sum()):>10,}")

    # --- verdict ----------------------------------------------------------
    disagree_rate = 1 - agree[fires].mean() if fires.any() else 0.0
    print("\n=== verdict ===")
    if fires.sum() < 50:
        print("  INCONCLUSIVE. Too few triggering bars in the overlap to judge.")
        return 0
    if disagree_rate <= 0.02:
        print(f"  ES is an ACCEPTABLE PROXY for Leg B signal research.")
        print(f"  Triggers disagree on {disagree_rate:.2%} of firing bars.")
        print("  Execution prices, costs, and sizing must still come from MES.")
    elif disagree_rate <= 0.10:
        print(f"  MARGINAL. Triggers disagree on {disagree_rate:.2%} of firing bars.")
        print("  Usable for exploratory work, but any result carries this as a known")
        print("  source of error, and a final verdict should be re-run on MES.")
    else:
        print(f"  ES is NOT an acceptable proxy. Triggers disagree on "
              f"{disagree_rate:.2%} of firing bars.")
        print("  Leg B's edge is a few ticks wide, and a disagreement rate this high")
        print("  means the ES backtest would be testing a materially different strategy.")
        print("  Re-download as MES.")
    print("\n  Note: this tests SIGNAL equivalence only. Costs and fills must come from")
    print("  MES regardless of the outcome, per SPECIFICATION.md section 3.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
