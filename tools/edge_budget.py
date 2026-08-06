#!/usr/bin/env python3
"""
How much edge does this account actually require, and where could it come from?

THE POINT
---------
Three ideas keep coming up: size up to finish faster, take fewer larger trades, take more
smaller ones. They are all the same move, and none of them can work, for a reason that is
one line of algebra:

    position size multiplies BOTH the edge and the noise by the same number,
    so the per-session ratio mu/sigma is INVARIANT to size.

Size trades speed against P(pass) and touches nothing else. Measured on one MES contract
holding the overnight window with a $150 cap, that ratio is about 0.051 a session, an
annual Sharpe near 0.8, and it is the same number at one contract and at twelve.

What the account demands is set by the same ratio:

    target  $3,000 / sigma  =  24 sigma of gain
    buffer  $2,000 / sigma  =  16 sigma of TRAILING drawdown that must never happen

Only three things move that ratio: COST, VARIANCE, and INSTRUMENT. This tool prices them.

WHAT IT COMPUTES
----------------
1. P(pass) as a function of per-session Sharpe and horizon, simulated under the real
   Topstep rules using the ACTUAL return distribution rescaled to each Sharpe, so the fat
   left tail and the clustering are preserved rather than assumed away.
2. The Sharpe REQUIRED to reach a given P(pass) inside a given number of months.
3. What each available lever is worth, in the same units, so improvements can be compared
   against the requirement instead of against each other.

The largest unexamined lever is cost. The round trip is $4.95 against a gross overnight
edge of $13.42, which is 37% of the edge spent on crossing the spread twice a day for a
position held fifteen hours. A scheduled exposure has no signal urgency, so a resting
limit order is available in a way it is not for a breakout.
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
    COST_SCENARIOS, INSTRUMENTS, PropRules, measured_cost_models,
)
from engine.data import build_continuous, resample  # noqa: E402
from engine.features import compute  # noqa: E402
from engine.overnight import minutes_since_open  # noqa: E402
from tools.feasibility import (  # noqa: E402
    SESSIONS_PER_MONTH, apply_daily_stop, simulate,
)
from tools.session_decomposition import WINDOWS, window_excursion  # noqa: E402

SHARPES = (0.00, 0.025, 0.05, 0.075, 0.10, 0.15, 0.20, 0.30)
HORIZON_MONTHS = (1, 3, 6, 12, 24)


def at_sharpe(returns: np.ndarray, target: float) -> np.ndarray:
    """
    Rescale a real return series to a target per-session Sharpe.

    The mean is replaced; the standard deviation, the skew, the fat left tail and the
    ordering are all left exactly as observed. This is deliberately NOT a normal draw:
    the whole point of the earlier bootstrap correction was that the tail is what ends
    accounts, and a Sharpe sweep on Gaussian returns would flatter every row.
    """
    sd = returns.std(ddof=1)
    return (returns - returns.mean()) + target * sd


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--symbol", default="MES")
    ap.add_argument("--price-source")
    ap.add_argument("--measured-costs", type=Path)
    ap.add_argument("--cost-scenario", choices=sorted(COST_SCENARIOS), default="adverse")
    ap.add_argument("--window", default="GLOBEX_TO_OPEN", choices=sorted(WINDOWS))
    ap.add_argument("--daily-stop", type=float, default=150.0)
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument("--decision-minutes", type=int, default=5)
    ap.add_argument("--through", type=float, default=0.80)
    ap.add_argument("--trials", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    inst = INSTRUMENTS[args.symbol]
    costs = (measured_cost_models(args.measured_costs, args.symbol)[args.cost_scenario]
             if args.measured_costs else COST_SCENARIOS[args.cost_scenario])
    rt_usd = costs.round_trip_usd(inst)
    rules = PropRules()

    data_symbol = args.price_source or args.symbol
    bars = resample(build_continuous(args.data, data_symbol), args.decision_minutes)
    feats = compute(bars, or_minutes=30, atr_window=14, rvol_lookback=20,
                    bar_minutes=args.decision_minutes)
    sessions = sorted(feats["session_date"].unique())
    keep = set(sessions[:int(len(sessions) * args.through)])
    feats = feats[feats["session_date"].isin(keep)].reset_index(drop=True)
    mso = minutes_since_open(feats)

    lo, hi = WINDOWS[args.window]
    exc = window_excursion(feats, mso, lo, hi)
    final = exc["final"].to_numpy() * inst.point_value * args.qty
    mae = exc["mae"].to_numpy() * inst.point_value * args.qty
    gross = apply_daily_stop(final, mae, args.daily_stop)
    net = gross - rt_usd * args.qty

    mu, sd = float(net.mean()), float(net.std(ddof=1))
    sharpe_now = mu / sd

    print("EDGE BUDGET")
    print("=" * 78)
    print(f"{args.symbol} via {data_symbol} | {args.window} | {len(keep)} sessions "
          f"| {args.qty} contract(s) | ${args.daily_stop:.0f} cap")
    print()
    print("  Position size multiplies edge and noise identically, so the ratio below is")
    print("  the same at any size. Sizing up buys speed and nothing else.")
    print()
    print(f"  gross edge            ${gross.mean():>8.2f}/session")
    print(f"  round trip            ${rt_usd * args.qty:>8.2f}   "
          f"({rt_usd * args.qty / max(gross.mean(), 1e-9):.0%} of gross)")
    print(f"  net edge              ${mu:>8.2f}/session")
    print(f"  session sd            ${sd:>8.2f}")
    print(f"  PER-SESSION SHARPE     {sharpe_now:>8.4f}   "
          f"(annualised {sharpe_now * np.sqrt(250):.2f})")
    print(f"  target in sd           {rules.profit_target / sd:>8.1f}")
    print(f"  buffer in sd           {rules.mll_buffer / sd:>8.1f}   and it TRAILS")
    print()

    # ---- P(pass) as a function of Sharpe and horizon ----------------------
    rng = np.random.default_rng(args.seed)
    print("  P(PASS) BY PER-SESSION SHARPE AND HORIZON")
    print("  Real return distribution rescaled to each Sharpe: same sd, same fat tail,")
    print("  same clustering. Only the mean moves.")
    print()
    header = "".join(f"{m:>3}mo" + " " * 4 for m in HORIZON_MONTHS)
    print(f"  {'Sharpe':>8}{'annual':>9}   {header}")
    grid = {}
    for s in SHARPES:
        r = at_sharpe(net, s)
        cells = []
        for m in HORIZON_MONTHS:
            res = simulate(r, rules, int(m * SESSIONS_PER_MONTH), args.trials, rng)
            cells.append(res["pass"])
            grid[(s, m)] = res
        mark = "  <-- measured" if abs(s - sharpe_now) < 0.0126 else ""
        print(f"  {s:>8.3f}{s * np.sqrt(250):>9.2f}   "
              + "".join(f"{c:>6.0%} " for c in cells) + mark)
    print()

    # ---- what is required ------------------------------------------------
    print("  SHARPE REQUIRED for a given P(pass) inside a given horizon")
    print(f"  {'P(pass)':>9}" + "".join(f"{m:>8}mo" for m in HORIZON_MONTHS))
    for want in (0.60, 0.75, 0.90):
        cells = []
        for m in HORIZON_MONTHS:
            hit = [s for s in SHARPES if grid[(s, m)]["pass"] >= want]
            cells.append(f"{min(hit):.3f}" if hit else ">0.30")
        print(f"  {want:>9.0%}" + "".join(f"{c:>10}" for c in cells))
    print()

    # ---- what the levers are worth --------------------------------------
    print("  WHAT EACH LEVER IS WORTH, in per-session Sharpe")
    print()
    levers = [
        ("resting limit entry, save 1 tick/side",
         (mu + 2 * inst.tick_value * args.qty) / sd),
        ("resting limit entry, save 2 ticks/side",
         (mu + 4 * inst.tick_value * args.qty) / sd),
        ("zero commission (not available, bound)",
         (mu + rt_usd * args.qty) / sd),
        ("cut session sd by 20% at the same edge", mu / (sd * 0.8)),
        ("double the gross edge", (2 * gross.mean() - rt_usd * args.qty) / sd),
    ]
    print(f"  {'lever':<44}{'Sharpe':>9}{'annual':>9}{'change':>9}")
    print(f"  {'measured now':<44}{sharpe_now:>9.4f}"
          f"{sharpe_now * np.sqrt(250):>9.2f}{'':>9}")
    for name, s in levers:
        print(f"  {name:<44}{s:>9.4f}{s * np.sqrt(250):>9.2f}"
              f"{s / sharpe_now - 1:>+9.0%}")
    print()
    print("=" * 78)
    print("HOW TO READ THIS:")
    print("  1. Compare the LEVER table against the REQUIRED table. If no lever reaches")
    print("     the Sharpe needed for an acceptable P(pass), the answer is not a better")
    print("     entry rule; it is a different account or a different instrument.")
    print("  2. Cost is the largest lever here because the round trip is a large share of")
    print("     a small edge. It is also the only one that is pure execution, requiring")
    print("     no new signal and no new data.")
    print("  3. Everything is measured on data already seen. Optimistic by construction.")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(
            {"sharpe_now": sharpe_now, "mu": mu, "sd": sd,
             "grid": {f"{s}|{m}": v for (s, m), v in grid.items()},
             "levers": dict(levers)}, indent=2, default=str))
        print(f"\nwritten to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
