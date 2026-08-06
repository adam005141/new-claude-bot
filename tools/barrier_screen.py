#!/usr/bin/env python3
"""
Does anything make the PATH favourable? The only screen whose answer decides a sign.

WHY THE PREVIOUS SCREEN WAS THE WRONG STATISTIC
-----------------------------------------------
`forward_returns.py` measures the mean forward move. That turned out to be the wrong
quantity, and the project has a concrete demonstration of why: `gap_vs_on_range` produced
the largest mean effect of any of 460 cells, at 2.41x the round trip and in the direction
Leg C bets, while Leg C itself lost 0.432R with a profit factor of 0.57. A favourable mean
with an adverse path is not an edge. It is a way to lose money slowly while being right on
average.

THE ARITHMETIC THIS TOOL MEASURES
---------------------------------
For a driftless random walk with stop distance S and target distance T:

    P(target first)     = S / (S + T)
    break-even win rate = 1 / (1 + T/S) = S / (S + T)

They are the same expression, so a random walk breaks even at EVERY geometry. Widening a
stop raises the win rate and lowers the payoff by exactly offsetting amounts.

Therefore the sign of any edge before costs depends on exactly one number:

    edge_sign = sign( observed P(target first) - S/(S+T) )

Stop width, target distance, reward-to-risk and position size cannot change that sign.
Measured on this project's two fade legs the shortfall was -14.3 and -14.8 percentage
points, replicated across different anchors, triggers and sample sizes.

So this tool asks the only question that matters: conditional on a feature, does price
touch the favourable barrier before the adverse one MORE often than S/(S+T)?

It has no entry rule, no position sizing, no P&L, and no free parameters beyond the
barrier geometry it sweeps. It cannot be overfitted by a better strategy design because it
contains no strategy.

READING THE OUTPUT
------------------
`excess` is the whole answer. Positive means the path is favourable more often than chance
and an edge exists before costs. Negative means no arrangement of stops and targets can
make that cell profitable. The cost column then says how much positive excess is needed to
survive the round trip, which is a separate and stricter bar.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.config import (  # noqa: E402
    COST_SCENARIOS, INSTRUMENTS, measured_cost_models,
)
from engine.data import build_continuous, resample  # noqa: E402
from engine.features import compute  # noqa: E402
from engine.sessions import classify_index, DEFAULT_ENABLED  # noqa: E402
from tools.forward_returns import CATEGORICAL, FEATURES  # noqa: E402

# Barrier geometries as (stop, target) multiples of ATR. Chosen to bracket what the legs
# used (1.5x stop) and to include asymmetric shapes in both directions, so the result
# cannot be an artefact of one arrangement.
GEOMETRIES = ((1.5, 1.5), (1.5, 3.0), (3.0, 1.5), (2.0, 4.0), (4.0, 2.0))

MAX_BARS = 24        # the same 24-bar time cap the legs use
N_BINS = 5


def first_touch(df: pd.DataFrame, stop_mult: float, target_mult: float,
                max_bars: int = MAX_BARS) -> pd.Series:
    """
    For a LONG opened at each bar's close: +1 if the target is touched before the stop,
    0 if the stop comes first, NaN if neither resolves inside the session or the cap.

    Symmetric by construction. A short's outcome is the mirror of a long's on the same
    path, so measuring longs and letting the feature carry the sign is equivalent to
    measuring both and avoids double counting the same bar.

    Adverse tie-breaking, matching `engine.execution`: when a single bar spans both
    barriers the STOP is taken. That is a real bias against the result, and it is kept
    here so this screen cannot look better than the backtest it is meant to inform.
    """
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    atr = df["atr"].to_numpy(dtype=float)
    sess = pd.factorize(df["session_date"].to_numpy())[0]
    n = len(df)

    out = np.full(n, np.nan)
    for i in range(n):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        up = close[i] + target_mult * a
        dn = close[i] - stop_mult * a
        end = min(i + max_bars, n - 1)
        for j in range(i + 1, end + 1):
            if sess[j] != sess[i]:
                break                      # never resolve across a session boundary
            hit_dn = low[j] <= dn
            hit_up = high[j] >= up
            if hit_dn:                     # stop wins ties, always
                out[i] = 0.0
                break
            if hit_up:
                out[i] = 1.0
                break
    return pd.Series(out, index=df.index)


def cell_stats(x: pd.Series, y: pd.Series, baseline: float,
               n_bins: int) -> list[dict]:
    """
    Target-first rate per quantile bin, against the OBSERVED unconditional rate.

    Not against the theoretical S/(S+T). That distinction is the difference between a
    working tool and one that manufactures edges, and the calibration run proved it: on a
    pure random walk the unconditional rate came out at 76.1% against a theoretical 66.7%
    for a 4.0x stop and 2.0x target, and at 29.2% against 33.3% for the mirror geometry.

    The cause is the 24-bar cap. A trade that resolves at neither barrier is censored, and
    the FARTHER barrier is the one more often censored, so whichever barrier sits nearer is
    systematically over-represented among resolved outcomes. The bias is large, it is
    signed by geometry, and it has nothing to do with any signal.

    Comparing each bin to the unconditional rate at the SAME geometry absorbs it exactly,
    along with tie-breaking drag, sample drift, and anything else common to every bar. What
    survives is the only thing asked about: does this feature do better than an average bar
    faced with the same barriers?
    """
    ok = x.notna() & y.notna()
    if ok.sum() < n_bins * 50:
        return []
    x, y = x[ok], y[ok]
    try:
        bins = pd.qcut(x, n_bins, labels=False, duplicates="drop")
    except ValueError:
        return []

    out = []
    for b in sorted(pd.unique(bins.dropna())):
        vals = y[bins == b]
        n = len(vals)
        if n < 50:
            continue
        rate = float(vals.mean())
        excess = rate - baseline
        # Binomial standard error. Overlapping windows make this optimistic, which is why
        # the family-wise null is computed rather than trusted from this number.
        se = np.sqrt(baseline * (1 - baseline) / n) if 0 < baseline < 1 else 0.0
        out.append({"bin": int(b), "n": n, "rate": rate, "excess": excess,
                    "z": float(excess / se) if se > 0 else 0.0})
    return out


def screen(df: pd.DataFrame, touches: dict, n_bins: int = N_BINS) -> list[dict]:
    """
    Every cell is compared to the observed unconditional rate for its own geometry, which
    is recomputed inside each null draw as well so the comparison stays internally
    consistent under permutation.
    """
    cells = []
    for (s, t), (y, theory) in touches.items():
        observed = float(y.mean()) if y.notna().any() else float("nan")
        if not np.isfinite(observed):
            continue
        for feat in FEATURES:
            if feat not in df.columns:
                continue
            for c in cell_stats(df[feat], y, observed, n_bins):
                cells.append({"feature": feat, "stop": s, "target": t,
                              "baseline": observed, "theory": theory,
                              "censoring_bias": observed - theory, **c})
    return cells


def rotation_null(df: pd.DataFrame, touches: dict, n_draws: int, seed: int,
                  n_bins: int = N_BINS) -> np.ndarray:
    """
    Family-wise null by rotating the OUTCOME series by a whole number of sessions.

    Sign-flipping is meaningless for a 0/1 outcome, so this uses the rotation construction
    that was calibrated in `forward_returns.py`: shift the finished outcome series,
    leaving every feature exactly where it is. Rotation preserves the within-session
    dependence of overlapping windows, the volatility clustering that drives it, and the
    overall target-first rate, and destroys only the alignment between feature and
    outcome.
    """
    rng = np.random.default_rng(seed)
    sessions = df["session_date"].to_numpy()
    boundaries = np.flatnonzero(np.r_[True, sessions[1:] != sessions[:-1]])
    n = len(df)
    usable = boundaries[(boundaries > 0.02 * n) & (boundaries < 0.98 * n)]
    if len(usable) == 0:
        return np.array([])

    out = []
    for shift in rng.choice(usable, size=min(n_draws, len(usable)), replace=False):
        rolled = {k: (pd.Series(np.roll(y.to_numpy(), int(shift)), index=y.index), b)
                  for k, (y, b) in touches.items()}
        out.append(max((abs(c["z"]) for c in screen(df, rolled, n_bins)), default=0.0))
    return np.array(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--symbols", nargs="+", default=["MES"])
    ap.add_argument("--price-source")
    ap.add_argument("--measured-costs", type=Path)
    ap.add_argument("--cost-scenario", choices=sorted(COST_SCENARIOS), default="adverse")
    ap.add_argument("--decision-minutes", type=int, default=5)
    ap.add_argument("--dev-fraction", type=float, default=0.50)
    ap.add_argument("--draws", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    print("BARRIER TOUCH SCREEN")
    print("=" * 78)
    print("A random walk breaks even at EVERY stop/target geometry, because")
    print("P(target first) = S/(S+T) is identical to the break-even win rate.")
    print("The sign of any edge is therefore decided by one number: excess.")
    print()

    summary = {}
    for symbol in args.symbols:
        inst = INSTRUMENTS[symbol]
        costs = (measured_cost_models(args.measured_costs, symbol)[args.cost_scenario]
                 if args.measured_costs else COST_SCENARIOS[args.cost_scenario])
        rt_points = costs.round_trip_points(inst)

        data_symbol = args.price_source or symbol
        bars = resample(build_continuous(args.data, data_symbol), args.decision_minutes)
        feats = compute(bars, or_minutes=30, atr_window=14, rvol_lookback=20,
                        bar_minutes=args.decision_minutes)
        sessions = sorted(feats["session_date"].unique())
        keep = set(sessions[:int(len(sessions) * args.dev_fraction)])
        feats = feats[feats["session_date"].isin(keep)].reset_index(drop=True)
        named = classify_index(pd.DatetimeIndex(feats["timestamp_utc"]))
        feats = feats[named.isin({s.value for s in DEFAULT_ENABLED}).to_numpy()]
        feats = feats.reset_index(drop=True)

        print(f"--- {symbol}" + (f" (bars from {data_symbol})" if args.price_source else "")
              + " ---")
        print(f"  {len(feats):,} tradable bars over {len(keep)} development sessions")
        print(f"  round trip {rt_points:.3f} index points, {MAX_BARS}-bar cap")
        print()

        touches = {}
        print("  UNCONDITIONAL path outcome: what an average bar does, no signal at all.")
        print("  The gap between theory and observed is MECHANICAL, not an edge: the")
        print("  24-bar cap censors the farther barrier, so the nearer one is")
        print("  over-represented. Every cell below is compared to `observed`, never to")
        print("  `theory`, which is what removes it.")
        print()
        print(f"  {'geometry':<14}{'resolved':>10}{'theory':>10}{'observed':>10}"
              f"{'censoring':>11}")
        for s, t in GEOMETRIES:
            y = first_touch(feats, s, t)
            baseline = s / (s + t)
            touches[(s, t)] = (y, baseline)
            res = y.notna().sum()
            obs = float(y.mean()) if res else float("nan")
            label = "%.1fx / %.1fx" % (s, t)
            print(f"  {label:<14}{res:>10,}{baseline:>10.1%}{obs:>10.1%}"
                  f"{obs - baseline:>+11.1%}")
        print()

        cells = screen(feats, touches)
        for c in cells:
            # Excess needed just to pay the round trip at this geometry, in the same units.
            stop_pts = c["stop"] * float(feats["atr"].median())
            target_pts = c["target"] * float(feats["atr"].median())
            c["excess_needed_for_cost"] = rt_points / (stop_pts + target_pts)
            c["clears_cost"] = c["excess"] > c["excess_needed_for_cost"]
        cells.sort(key=lambda c: -c["excess"])

        print(f"  SCREEN: {len(cells)} cells "
              f"({len(FEATURES)} features x {len(GEOMETRIES)} geometries x {N_BINS} bins)")
        print()
        print(f"    {'feature':<19}{'geom':>10}{'bin':>5}{'n':>8}{'base':>8}"
              f"{'rate':>8}{'excess':>9}{'z':>7}  cost?")
        for c in cells[:12]:
            geom = "%.1fx/%.1fx" % (c["stop"], c["target"])
            flag = "YES" if c["clears_cost"] else "no"
            print(f"    {c['feature']:<19}{geom:>10}"
                  f"{c['bin']:>5}{c['n']:>8,}{c['baseline']:>8.1%}{c['rate']:>8.1%}"
                  f"{c['excess']:>+9.1%}{c['z']:>7.2f}  {flag}")
        print()

        print(f"  Family-wise null from {args.draws} session shuffles.")
        null = rotation_null(feats, touches, args.draws, args.seed)
        obs = max((abs(c["z"]) for c in cells), default=0.0)
        best_pos = max((c["z"] for c in cells), default=0.0)
        p = float((null >= obs).mean()) if len(null) else None
        if p is not None:
            print(f"    observed best |z|      {obs:.2f}")
            print(f"    null median            {np.median(null):.2f}")
            print(f"    null 95th percentile   {np.percentile(null, 95):.2f}")
            print(f"    FAMILY-WISE p          {p:.3f}")
        print()

        positive = [c for c in cells if c["clears_cost"]]
        print(f"  Cells with excess large enough to clear the round trip: "
              f"{len(positive)} of {len(cells)}")
        print(f"  Best positive z across all cells: {best_pos:+.2f}")
        if p is not None and p > 0.05:
            print()
            print("    ** NOT SIGNIFICANT. Nothing in the feature set makes the path")
            print("       favourable beyond what shuffling produces. Since path is the")
            print("       ONLY thing that sets the sign of an edge, no stop, target or")
            print("       sizing choice applied to these features can be profitable. **")
        print()

        summary[symbol] = {
            "bars": len(feats), "sessions": len(keep),
            "round_trip_points": rt_points,
            "unconditional": {"%.1fx/%.1fx" % (s, t): {
                "baseline": b, "observed": float(y.mean()) if y.notna().any() else None,
                "resolved": int(y.notna().sum())}
                for (s, t), (y, b) in touches.items()},
            "n_cells": len(cells), "family_wise_p": p,
            "cells_clearing_cost": len(positive),
            "top_cells": cells[:20],
        }

    print("=" * 78)
    print("HOW TO READ THIS:")
    print("  1. `excess` decides the SIGN of an edge. Nothing else does. A negative")
    print("     excess cannot be rescued by geometry, instrument, or sizing.")
    print("  2. `cost?` is the stricter second bar: excess large enough to also pay the")
    print("     round trip. A cell can have a real positive excess and still not trade.")
    print("  3. Bin boundaries are fitted on this data. The family-wise p accounts for")
    print("     that and for the search; the per-cell z does not.")
    print("  4. Development split only.")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, indent=2, default=str))
        print(f"\nwritten to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
