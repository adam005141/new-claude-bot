#!/usr/bin/env python3
"""
Does ANY feature we already compute predict forward price movement by more than the
round trip costs?

This is a MEASUREMENT, not a strategy. It has no entry rule, no stop, no target, no
position sizing, and books no P&L. It exists because two structurally opposite legs have
now failed before costs, and building a third entry rule before checking whether the
underlying data contains anything to trade would be a third draw from the same urn.

WHY POINTS, NOT R
-----------------
A signal is tradable when the move it predicts is bigger than the round trip. Both are
measured in index points, and the stop distance cancels out of the comparison:

    edge_in_R / hurdle_in_R = (edge_pts / stop_pts) / (cost_pts / stop_pts)
                            = edge_pts / cost_pts

So the arbitrary choice of stop multiple, which dominated the cost-hurdle analysis, is
irrelevant here. The question reduces to: is the conditional mean forward move larger than
the round trip, in points?

WHY THIS IS AN UPPER BOUND
--------------------------
The mean forward move over the next h bars is what a position captures with NO stop, NO
target, and perfect exit timing at exactly bar t+h. Every real mechanism, a protective
stop, a fixed target, a time stop, a one-bar entry delay, takes a bite out of it. So:

    **If the unconditional-of-mechanism upper bound does not clear cost, nothing built
    on that feature can clear cost either.**

That makes a negative result here genuinely conclusive in a way a strategy backtest is
not, because a strategy backtest confounds the signal with the machinery around it.
A POSITIVE result here concludes nothing except "not yet excluded".

MULTIPLE TESTING
----------------
This screens many features across many horizons and many bins. Searching a few hundred
cells and reporting the best one is how noise gets published, so the family-wise null is
computed rather than assumed, by ROTATION: the forward-return series is circularly shifted
by whole sessions and the whole screen is re-run. Rotation preserves the autocorrelation
of both series exactly, including the heavy overlap between forward returns at adjacent
bars, and destroys only the link between them. The observed best cell is then compared
against the distribution of the best cell under the null.

A naive t-statistic on overlapping forward returns is badly overstated. The rotation null
is calibrated with the same overlap, so it corrects for that and for the search at once.

How badly overstated: run this screen on a SYNTHETIC RANDOM WALK, where the true edge is
exactly zero by construction, and the best of its 260 cells comes back at |t| = 7.43. Read
naively that is a p-value around 1e-13. The rotation null puts the median best-of-260 at
9.18 and returns a family-wise p of 0.92, which is the correct answer. Any version of this
tool without the null would have "discovered" a tradable signal in noise on its first run.

Usage:

    python tools/forward_returns.py --data data --symbols MES --price-source ES \
        --measured-costs config/measured_costs.json
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
    COST_SCENARIOS, INSTRUMENTS, Instrument, CostModel, measured_cost_models,
)
from engine.data import build_continuous, resample  # noqa: E402
from engine.features import compute  # noqa: E402
from engine.sessions import ET, classify_index, DEFAULT_ENABLED  # noqa: E402

# Forward horizons in decision bars. At 5 minutes each: 5, 15, 30, 60, 120 minutes.
HORIZONS = (1, 3, 6, 12, 24)

# Every feature the engine already computes that could plausibly carry information.
# Fixed here, in the source, so the list cannot be quietly extended after seeing results.
FEATURES = (
    "vwap_dev",          # deviation from VWAP in sigma units      (Leg A's signal)
    "prev_vwap_dev",
    "vwap_slope",        # ATR-normalised VWAP slope               (regime input)
    "rvol",              # session-to-date relative volume         (both legs' filter)
    "rv_pct",            # volatility percentile vs prior sessions (regime input)
    "or_width_norm",     # opening range width vs random walk      (Leg B's filter)
    "atr",               # raw volatility level
    "realized_vol",
    "minutes_since_open",
    "bar_of_session",
    # Overnight, gap and prior-session structure. Added 2026-08-06 because the first
    # screen's real limitation was not its method but its inputs: every feature above is
    # computed from RTH bars of the session being traded, which ignored roughly fifteen
    # hours per session that the engine already had bars for.
    "gap_atr",             # RTH open vs prior cash close, in ATR
    "gap_vs_on_range",     # the same gap as a fraction of the overnight range
    "on_range_atr",        # was the night wide or quiet
    "on_range_norm",       # ... relative to recent nights. The volatility-clustering control.
    "on_pos",              # where price sits in the overnight range; outside [0,1] is a break
    "dist_on_high_atr",
    "dist_on_low_atr",
    "prior_close_pos",     # where the prior cash close sat in the prior day's range
)
CATEGORICAL = ("regime",)

N_BINS = 5


def forward_move_points(df: pd.DataFrame, horizon: int) -> pd.Series:
    """
    Signed change in close over the next `horizon` bars, in index points.

    Confined to the session. A forward return spanning the session boundary would be
    measuring the overnight gap, which no intraday strategy holds through, and would
    dominate every statistic on this page.
    """
    fwd = df.groupby("session_date", sort=False)["close"].shift(-horizon)
    return fwd - df["close"]


def forward_move_normalised(df: pd.DataFrame, horizon: int) -> pd.Series:
    """
    The same forward move divided by ATR at the decision bar.

    A second view of the same question, reported alongside raw points rather than
    replacing them.

    Most of the screened features are volatility measures, so a raw-points bin sorted on
    volatility is heteroskedastic by construction: high-volatility bins hold larger moves
    in both directions. Dividing by ATR at the decision bar makes the target roughly
    homoskedastic across regimes, which is a cleaner basis for a t-statistic.

    It was originally added on the theory that heteroskedasticity was biasing the null.
    It was not: see `signflip_null`. Both targets are now reported because they answer
    slightly different questions and it costs almost nothing to show both.

    Tradability is always read from raw points, never from this, because the round trip is
    denominated in index points and not in ATR.
    """
    return forward_move_points(df, horizon) / df["atr"].replace(0.0, np.nan)


def cell_stats(x: pd.Series, y: pd.Series, n_bins: int) -> list[dict]:
    """Mean forward move within each quantile bin of a feature."""
    ok = x.notna() & y.notna()
    if ok.sum() < n_bins * 30:
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
        if n < 30:
            continue
        mean = float(vals.mean())
        sd = float(vals.std(ddof=1))
        # Naive t. It is NOT trustworthy on its own, because forward returns at adjacent
        # bars overlap heavily. It is used only as a scale-fair statistic whose null
        # distribution the rotation test supplies.
        t = mean / (sd / np.sqrt(n)) if sd > 0 else 0.0
        out.append({"bin": int(b), "n": n, "mean_points": mean, "t": float(t),
                    "lo": float(x[bins == b].min()), "hi": float(x[bins == b].max())})
    return out


def categorical_stats(x: pd.Series, y: pd.Series) -> list[dict]:
    ok = x.notna() & y.notna()
    x, y = x[ok], y[ok]
    out = []
    for level in sorted(pd.unique(x), key=str):
        vals = y[x == level]
        n = len(vals)
        if n < 30:
            continue
        mean, sd = float(vals.mean()), float(vals.std(ddof=1))
        t = mean / (sd / np.sqrt(n)) if sd > 0 else 0.0
        out.append({"bin": str(level), "n": n, "mean_points": mean, "t": float(t)})
    return out


def targets(df: pd.DataFrame, horizons, normalise: bool) -> dict[int, pd.Series]:
    fn = forward_move_normalised if normalise else forward_move_points
    return {h: fn(df, h) for h in horizons}


def screen(df: pd.DataFrame, horizons=HORIZONS, n_bins: int = N_BINS,
           precomputed: dict[int, pd.Series] | None = None,
           normalise: bool = False) -> list[dict]:
    """Run the full feature x horizon x bin screen once."""
    ys = precomputed if precomputed is not None else targets(df, horizons, normalise)
    cells = []
    for h in horizons:
        y = ys[h]
        for feat in FEATURES:
            if feat not in df.columns:
                continue
            for c in cell_stats(df[feat], y, n_bins):
                cells.append({"feature": feat, "horizon": h, **c})
        for feat in CATEGORICAL:
            if feat not in df.columns:
                continue
            for c in categorical_stats(df[feat].astype(str), y):
                cells.append({"feature": feat, "horizon": h, **c})
    return cells


def signflip_null(df: pd.DataFrame, n_draws: int, seed: int,
                  horizons=HORIZONS, n_bins: int = N_BINS,
                  normalise: bool = False) -> np.ndarray:
    """
    Family-wise null by flipping the SIGN of whole sessions of forward returns.

    A SECOND, independent null, not a replacement for rotation.

    It exists because rotation looked conservative and turned out not to be. On the first
    dataset checked, the observed statistic sat at the 8th percentile of its own rotation
    null when the true edge was exactly zero, which suggested the null was running too
    high and reporting p-values too kind to the no-signal conclusion. Measured properly
    across 12 independent zero-edge datasets, the observed statistic lands at a mean
    percentile of 40% against the 50% a calibrated null gives, z = -1.24. **That is not a
    detectable bias.** The single-dataset reading was sampling noise, and a family-wise
    maximum lands anywhere in its null.

    Sign-flipping is kept because it is the better-motivated null for this specific
    hypothesis and because two nulls built on different principles agreeing is worth more
    than one. The hypothesis is that a feature does not predict the DIRECTION of the next
    move, so negating whole sessions leaves the magnitude of every forward return, every
    volatility cluster, every within-session autocorrelation, and the entire relationship
    between the features and |target| exactly as observed. Only the sign relationship
    dies. Sessions flip as blocks so overlapping forward returns keep their joint
    structure.
    """
    rng = np.random.default_rng(seed)
    base = targets(df, horizons, normalise)
    sessions = df["session_date"].to_numpy()
    codes = pd.factorize(sessions)[0]
    n_sessions = codes.max() + 1

    out = []
    for _ in range(n_draws):
        flip = rng.choice((-1.0, 1.0), size=n_sessions)[codes]
        flipped = {h: y * flip for h, y in base.items()}
        cells = screen(df, horizons, n_bins, precomputed=flipped)
        out.append(max((abs(c["t"]) for c in cells), default=0.0))
    return np.array(out)


def rotation_null(df: pd.DataFrame, n_rotations: int, seed: int,
                  horizons=HORIZONS, n_bins: int = N_BINS,
                  normalise: bool = False) -> np.ndarray:
    """
    Distribution of the BEST |t| across the whole screen when there is nothing to find.

    The features stay exactly where they are; the TARGET SERIES is rotated by a whole
    number of sessions. Every autocorrelation, volatility cluster, and overlap between
    adjacent forward returns survives intact. Only the alignment between feature and
    future is destroyed.

    Rotating the target rather than the price is deliberate. Rolling `close` and then
    recomputing forward moves leaves ATR, and every other price-derived feature, sitting
    at its ORIGINAL position, so a rotated run pairs one period's volatility with another
    period's moves. That mismatch inflated the null. Rotating the finished target keeps
    the normalisation attached to the thing it normalises.
    """
    rng = np.random.default_rng(seed)
    sessions = df["session_date"].to_numpy()
    boundaries = np.flatnonzero(np.r_[True, sessions[1:] != sessions[:-1]])
    n = len(df)

    base = targets(df, horizons, normalise)
    out = []
    # Skip rotations near zero in either direction; those leave the series almost aligned.
    usable = boundaries[(boundaries > 0.02 * n) & (boundaries < 0.98 * n)]
    if len(usable) == 0:
        return np.array([])

    for shift in rng.choice(usable, size=min(n_rotations, len(usable)), replace=False):
        rolled = {h: pd.Series(np.roll(y.to_numpy(), int(shift)), index=y.index)
                  for h, y in base.items()}
        cells = screen(df, horizons, n_bins, precomputed=rolled)
        out.append(max((abs(c["t"]) for c in cells), default=0.0))
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
    ap.add_argument("--rotations", type=int, default=200,
                    help="Rotations used to build the family-wise null.")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    print("FORWARD RETURN SCREEN")
    print("=" * 78)
    print("Upper bound on any strategy: the mean forward move with no stop, no target,")
    print("and a perfect exit. Real machinery only subtracts from it.")
    print()

    summary = {}
    for symbol in args.symbols:
        inst = INSTRUMENTS[symbol]
        costs = (measured_cost_models(args.measured_costs, symbol)[args.cost_scenario]
                 if args.measured_costs else COST_SCENARIOS[args.cost_scenario])
        rt_points = costs.round_trip_points(inst)

        data_symbol = args.price_source or symbol
        cont = build_continuous(args.data, data_symbol)
        bars = resample(cont, args.decision_minutes)
        feats = compute(bars, or_minutes=30, atr_window=14, rvol_lookback=20,
                        bar_minutes=args.decision_minutes)

        sessions = sorted(feats["session_date"].unique())
        keep = set(sessions[:int(len(sessions) * args.dev_fraction)])
        feats = feats[feats["session_date"].isin(keep)].reset_index(drop=True)

        # Tradable RTH bars only. Screening bars the engine would never act on would
        # measure a market we have already decided not to trade.
        named = classify_index(pd.DatetimeIndex(feats["timestamp_utc"]))
        feats = feats[named.isin({s.value for s in DEFAULT_ENABLED}).to_numpy()]
        feats = feats.reset_index(drop=True)

        print(f"--- {symbol}" + (f" (bars from {data_symbol})" if args.price_source else "")
              + " ---")
        print(f"  {len(feats):,} tradable bars over {len(keep)} development sessions")
        print(f"  round trip            {costs.round_trip_usd(inst):.2f} USD = "
              f"{rt_points:.3f} index points")
        print()

        # ---- the unconditional baseline ------------------------------------
        print("  UNCONDITIONAL forward move (the drift, before any signal):")
        print(f"    {'horizon':>10} {'mean pts':>10} {'vs cost':>9} {'sd pts':>9}")
        for h in HORIZONS:
            y = forward_move_points(feats, h).dropna()
            print(f"    {h * args.decision_minutes:>7} min {y.mean():>10.4f} "
                  f"{y.mean() / rt_points:>9.2f}x {y.std():>9.3f}")
        print()

        # ---- the screen ----------------------------------------------------
        cells = screen(feats)
        for c in cells:
            c["vs_cost"] = abs(c["mean_points"]) / rt_points
        cells.sort(key=lambda c: -abs(c["t"]))
        n_cells = len(cells)

        print(f"  SCREEN: {n_cells} cells "
              f"({len(FEATURES) + len(CATEGORICAL)} features x {len(HORIZONS)} horizons "
              f"x up to {N_BINS} bins)")
        print(f"  Tradability bar: |mean move| must exceed {rt_points:.3f} points, "
              f"which is 1.00x cost.")
        print()
        print(f"    {'feature':<19}{'horizon':>8}{'bin':>5}{'n':>8}"
              f"{'mean pts':>10}{'vs cost':>9}{'t':>8}")
        for c in cells[:12]:
            print(f"    {c['feature']:<19}{c['horizon'] * args.decision_minutes:>6} min"
                  f"{str(c['bin']):>5}{c['n']:>8,}{c['mean_points']:>10.4f}"
                  f"{c['vs_cost']:>8.2f}x{c['t']:>8.2f}")
        print()

        # ---- family-wise null ----------------------------------------------
        print(f"  Building the family-wise null, {args.rotations} draws per method.")
        print("  Two null constructions on different principles, so a verdict does not")
        print("  rest on one. ROTATION shifts the target by whole sessions. SIGN-FLIP")
        print("  negates whole sessions, preserving every magnitude and destroying only")
        print("  the direction, which is exactly the hypothesis under test.")
        print()
        print(f"    {'target':<18}{'null':<12}{'observed':>10}{'null med':>10}"
              f"{'null p95':>10}{'FW p':>8}")

        combos = (("raw points", False, "rotation", rotation_null),
                  ("ATR-normalised", True, "rotation", rotation_null),
                  ("ATR-normalised", True, "sign-flip", signflip_null))
        results = {}
        for label, norm, null_name, null_fn in combos:
            obs = max((abs(c["t"]) for c in screen(feats, normalise=norm)), default=0.0)
            null = null_fn(feats, args.rotations, args.seed, normalise=norm)
            if not len(null):
                continue
            p = float((null >= obs).mean())
            results[f"{label} / {null_name}"] = {
                "observed": obs, "median": float(np.median(null)),
                "p95": float(np.percentile(null, 95)), "p": p}
            print(f"    {label:<18}{null_name:<12}{obs:>10.2f}{np.median(null):>10.2f}"
                  f"{np.percentile(null, 95):>10.2f}{p:>8.3f}")

        print()
        # The verdict is the WORST case across constructions. If any credible null says
        # significant, that has to be confronted rather than averaged away.
        p = max(r["p"] for r in results.values()) if results else None
        min_p = min(r["p"] for r in results.values()) if results else None
        observed_max_t = (results["raw points / rotation"]["observed"]
                          if "raw points / rotation" in results else 0.0)
        if min_p is not None and min_p <= 0.05 < p:
            print(f"    ** NULLS DISAGREE: p ranges {min_p:.3f} to {p:.3f} across")
            print("       constructions. Treat as unresolved, not as a finding. **")
            p = min_p
        if p is None:
            print("    null could not be built (too few sessions)")
        elif p > 0.05:
            print("    ** NOT SIGNIFICANT under every null construction. The best cell in")
            print("       this search is no better than what permuting the target")
            print("       produces by chance. No evidence of predictability here. **")
        else:
            print("    Best cell survives the family-wise null. That means it is not")
            print("    obviously noise. It does NOT mean it is tradable: check the")
            print("    vs-cost column, and note the bin boundaries were fitted here.")

        # ---- the tradability question ---------------------------------------
        clears = [c for c in cells if c["vs_cost"] >= 1.0]
        print()
        print(f"  Cells whose upper bound clears the round trip: {len(clears)} of {n_cells}")
        if clears:
            for c in clears[:8]:
                print(f"    {c['feature']:<19}{c['horizon'] * args.decision_minutes:>6} min"
                      f"  bin {c['bin']}  {c['mean_points']:>8.4f} pts  "
                      f"{c['vs_cost']:.2f}x cost  t={c['t']:.2f}")
        print()

        summary[symbol] = {
            "bars": len(feats), "sessions": len(keep),
            "round_trip_points": rt_points,
            "n_cells": n_cells,
            "observed_max_abs_t": observed_max_t,
            "family_wise_p": p,
            "nulls": results,
            "cells_clearing_cost": len(clears),
            "top_cells": cells[:20],
        }

    print("=" * 78)
    print("HOW TO READ THIS, stated so the table is not over-read:")
    print("  1. Every mean here is an UPPER BOUND. It assumes no stop, no target, no")
    print("     entry delay, and an exit at exactly the horizon. A real strategy gets")
    print("     less. A cell that fails here cannot be rescued by a better entry rule.")
    print("  2. Bin boundaries were fitted on this same data, which flatters the best")
    print("     cell. The rotation null is computed the same way, so the family-wise p")
    print("     accounts for it; the individual t-statistics do not.")
    print("  3. A surviving cell is a HYPOTHESIS, not a result. It has to be registered")
    print("     in the ledger and tested on the validation split like anything else.")
    print("  4. This screen consumed the development split only.")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, indent=2, default=str))
        print(f"\nwritten to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
