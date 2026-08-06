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

# Barrier geometries as (stop, target) multiples of ATR.
#
# The SYMMETRIC ones carry the headline statistic, and the asymmetric ones are reported
# but excluded from it. The reason is a flaw found in calibration: the path/drift split is
# only exact when stop equals target. With a payoff of 2, a winning long pays +2R while a
# losing short pays only -1R, so a purely directional drift does not cancel and leaks into
# PATH. Measured on a synthetic pure uptrend that leak was +0.05R, which is the same order
# as anything this project could plausibly find.
#
# Three symmetric widths bracket the 1.5x stop both legs used, so a headline result cannot
# be an artefact of one arrangement.
SYMMETRIC = ((1.0, 1.0), (1.5, 1.5), (3.0, 3.0))
ASYMMETRIC = ((1.5, 3.0), (3.0, 1.5))
GEOMETRIES = SYMMETRIC + ASYMMETRIC

MAX_BARS = 24        # the same 24-bar time cap the legs use
N_BINS = 5


def barrier_outcome_r(df: pd.DataFrame, stop_mult: float, target_mult: float,
                      max_bars: int = MAX_BARS, side: str = "long") -> pd.Series:
    """
    Outcome of one trade opened at each bar's close, in R, gross of cost.

    Every bar resolves. Target first pays `+target/stop` R, stop first pays `-1` R, and a
    trade that reaches neither is marked to market at the cap or at the session end, which
    is exactly what the engine's time stop does.

    THIS REPLACED A BINARY TOUCH RATE, and the reason is worth keeping. Measuring
    "did the target come first" discards every unresolved path, and the resolution rate is
    not constant across bins: barriers are scaled by ATR, so a high-ATR bar gets wider
    barriers, resolves less often, and its surviving outcomes are drawn disproportionately
    from whichever barrier sits nearer. That is a bin-dependent bias, and no baseline
    subtraction removes it because it travels WITH the feature. Nor can rotation absorb it:
    rotation hands a high-ATR bin outcomes drawn from ordinary bars, so the null does not
    reproduce the censoring the real data has.

    The symptom was unmistakable. On a synthetic random walk with a true edge of exactly
    zero the binary version returned a family-wise p of 0.000. Marking unresolved trades to
    market removes the censoring entirely rather than trying to correct for it.

    Adverse tie-breaking, matching `engine.execution`: a bar spanning both barriers
    resolves to the STOP.
    """
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    atr = df["atr"].to_numpy(dtype=float)
    sess = pd.factorize(df["session_date"].to_numpy())[0]
    n = len(df)
    sign = 1.0 if side == "long" else -1.0
    payoff = target_mult / stop_mult

    out = np.full(n, np.nan)
    for i in range(n):
        a = atr[i]
        if not np.isfinite(a) or a <= 0 or i + 1 >= n or sess[i + 1] != sess[i]:
            continue
        entry = close[i]
        tgt = entry + sign * target_mult * a
        stp = entry - sign * stop_mult * a
        end = min(i + max_bars, n - 1)
        last = i
        resolved = None
        for j in range(i + 1, end + 1):
            if sess[j] != sess[i]:
                break
            last = j
            if (low[j] <= stp) if sign > 0 else (high[j] >= stp):
                resolved = -1.0            # stop wins ties, always
                break
            if (high[j] >= tgt) if sign > 0 else (low[j] <= tgt):
                resolved = payoff
                break
        # Neither barrier: mark to market, exactly as the engine's time stop does.
        out[i] = resolved if resolved is not None else \
            sign * (close[last] - entry) / (stop_mult * a)
    return pd.Series(out, index=df.index)


def decompose(excess_long: float, excess_short: float) -> tuple[float, float]:
    """
    Split a two-sided result into the part that is a PATH property and the part that is
    just DRIFT.

        path  = (excess_long + excess_short) / 2
        drift = (excess_long - excess_short) / 2

    A market that simply goes up makes longs earn more and shorts lose the same, so `path`
    cancels to zero and `drift` carries everything. A market that genuinely trends or
    genuinely reverts moves BOTH sides the same way, so `path` carries it.

    Only `path` is worth anything here. The development split runs 2023-08 to 2025-01,
    which was a strong equity bull market, so a positive drift term is exactly what that
    sample produces whether or not anything is predictable. It would not survive a bear
    regime, and the lockbox cannot be spent finding that out.
    """
    return ((excess_long + excess_short) / 2.0,
            (excess_long - excess_short) / 2.0)


def cell_stats(x: pd.Series, y: pd.Series, baseline: float, n_bins: int) -> list[dict]:
    """Mean outcome in R per quantile bin, against the unconditional mean at the same
    geometry. The baseline absorbs tie-break drag and anything else common to all bars."""
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
        out.append({"bin": int(b), "n": n, "mean_r": float(vals.mean()),
                    "sd": float(vals.std(ddof=1)),
                    "excess": float(vals.mean()) - baseline})
    return out


def screen(df: pd.DataFrame, touches: dict, n_bins: int = N_BINS,
           symmetric_only: bool = True) -> list[dict]:
    """
    Every cell is compared to the observed unconditional rate for its own geometry and
    side, which is recomputed inside each null draw so the comparison stays internally
    consistent under permutation.

    `touches` maps (stop, target) to {"long": series, "short": series, "theory": float}.
    Each cell reports both sides and their path/drift decomposition; the headline
    statistic is the PATH component, because drift in a bull sample proves nothing.
    """
    cells = []
    for (gs, gt), sides in touches.items():
        if symmetric_only and gs != gt:
            continue                    # drift does not cancel when the payoff is not 1
        base = {k: float(sides[k].mean()) for k in ("long", "short")}
        if not all(np.isfinite(v) for v in base.values()):
            continue
        for feat in FEATURES:
            if feat not in df.columns:
                continue
            per_side = {k: {c["bin"]: c for c in cell_stats(df[feat], sides[k],
                                                            base[k], n_bins)}
                        for k in ("long", "short")}
            for b, cl in per_side["long"].items():
                cs = per_side["short"].get(b)
                if cs is None:
                    continue
                path, drift = decompose(cl["excess"], cs["excess"])
                # The two sides are measured on the same bars and are strongly
                # anticorrelated, so their average has less variance than either. Using the
                # long-side sd is conservative, and the null is what actually settles it.
                se = cl["sd"] / np.sqrt(cl["n"])
                cells.append({
                    "feature": feat, "stop": gs, "target": gt, "bin": b, "n": cl["n"],
                    "symmetric": gs == gt,
                    "base_long": base["long"], "base_short": base["short"],
                    "excess_long": cl["excess"], "excess_short": cs["excess"],
                    "path": path, "drift": drift, "excess": path,
                    "z": float(path / se) if se > 0 else 0.0,
                })
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
        rolled = {k: {"theory": v["theory"],
                      **{sd: pd.Series(np.roll(v[sd].to_numpy(), int(shift)),
                                       index=v[sd].index)
                         for sd in ("long", "short")}}
                  for k, v in touches.items()}
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
    print("Expectancy in R, gross of cost, under fixed barriers. A driftless random")
    print("walk scores zero at EVERY geometry, so anything non-zero is a real path")
    print("property. Long and short are split into PATH and DRIFT, because a bull")
    print("sample produces drift whether or not anything is predictable.")
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
        print("  UNCONDITIONAL outcome: what an average bar earns, no signal at all.")
        print("  Every cell below is measured as an EXCESS over this row, so tie-break")
        print("  drag and any whole-sample tilt are subtracted rather than credited.")
        print()
        print(f"  {'geometry':<22}{'trades':>8}{'long R':>10}{'short R':>10}"
              f"{'PATH':>9}{'drift':>9}")
        for gs, gt in GEOMETRIES:
            yl = barrier_outcome_r(feats, gs, gt, side="long")
            ys = barrier_outcome_r(feats, gs, gt, side="short")
            touches[(gs, gt)] = {"long": yl, "short": ys, "theory": gs / (gs + gt)}
            ol, os_ = float(yl.mean()), float(ys.mean())
            label = "%.1fx / %.1fx" % (gs, gt) + ("" if gs == gt else "  (excl)")
            print(f"  {label:<22}{yl.notna().sum():>8,}{ol:>+10.4f}{os_:>+10.4f}"
                  f"{(ol + os_) / 2:>+9.4f}{(ol - os_) / 2:>+9.4f}")
        print()
        print("  Every figure is R per trade, GROSS of cost. A driftless random walk")
        print("  scores ~0 at every geometry, which is the whole point: geometry cannot")
        print("  create an edge. `drift` is the whole-sample directional tilt.")
        print()
        print("  Only the SYMMETRIC geometries (stop = target) feed the screen below.")
        print("  When the payoff is not 1 a winning long pays more R than a losing short")
        print("  loses, so drift does not cancel and leaks into PATH. Calibration put")
        print("  that leak at +0.05R on a synthetic pure uptrend, which is the same size")
        print("  as anything worth finding. The asymmetric rows are shown for context")
        print("  only and are excluded from the statistic.")
        print("  The development split is a 2023-2025 equity bull market, so a positive")
        print("  drift is what this sample produces whether or not anything is")
        print("  predictable. Every cell below reports the PATH component, which is the")
        print("  part that survives cancelling drift out.")
        print()

        cells = screen(feats, touches)
        for c in cells:
            # Excess needed just to pay the round trip at this geometry, in the same units.
            # Cost in R is the round trip over the stop distance, which IS the R unit.
            c["excess_needed_for_cost"] = rt_points / (c["stop"] * float(feats["atr"].median()))
            c["clears_cost"] = c["path"] > c["excess_needed_for_cost"]
        cells.sort(key=lambda c: -c["path"])
        # bar_of_session and minutes_since_open are the same quantity inside RTH, so a
        # result appearing in both is ONE finding, not two. Flagged rather than dropped.
        dupes = {"minutes_since_open", "bar_of_session"}
        seen_dupe = [c for c in cells[:12] if c["feature"] in dupes]
        if len({c["feature"] for c in seen_dupe}) > 1:
            print("  NOTE: minutes_since_open and bar_of_session are the same quantity")
            print("  inside RTH. Where both appear below they are ONE finding.")
            print()

        print(f"  SCREEN: {len(cells)} cells "
              f"({len(FEATURES)} features x {len(SYMMETRIC)} symmetric geometries "
              f"x {N_BINS} bins)")
        print()
        print(f"    {'feature':<19}{'geom':>10}{'bin':>5}{'n':>8}{'exc L':>9}"
              f"{'exc S':>9}{'PATH':>9}{'drift':>9}{'z':>7}  cost?")
        for c in cells[:12]:
            geom = "%.1fx/%.1fx" % (c["stop"], c["target"])
            flag = "YES" if c["clears_cost"] else "no"
            print(f"    {c['feature']:<19}{geom:>10}{c['bin']:>5}{c['n']:>8,}"
                  f"{c['excess_long']:>+9.4f}{c['excess_short']:>+9.4f}"
                  f"{c['path']:>+9.4f}{c['drift']:>+9.4f}{c['z']:>7.2f}  {flag}")
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
            "unconditional": {"%.1fx/%.1fx" % (gs, gt): {
                "long_r": float(v["long"].mean()), "short_r": float(v["short"].mean()),
                "path_r": float((v["long"].mean() + v["short"].mean()) / 2),
                "drift_r": float((v["long"].mean() - v["short"].mean()) / 2),
                "trades": int(v["long"].notna().sum())}
                for (gs, gt), v in touches.items()},
            "n_cells": len(cells), "family_wise_p": p,
            "cells_clearing_cost": len(positive),
            "top_cells": cells[:20],
        }

    print("=" * 78)
    print("HOW TO READ THIS:")
    print("  1. PATH decides the SIGN of an edge. Nothing else does. A negative path")
    print("     cannot be rescued by geometry, instrument, or sizing.")
    print("  1b. `drift` is NOT tradeable evidence from this sample. It is the bull")
    print("     market. Long and short excesses that mirror each other are drift;")
    print("     ones that move together are a real path property.")
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
