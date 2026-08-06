#!/usr/bin/env python3
"""
Can ANY configuration of this account pass reliably? Asked before building a fifth leg.

WHY THIS COMES BEFORE ANOTHER STRATEGY
--------------------------------------
Leg D passed the Combine on development and was HALTED_PERMANENT after 25 validation
sessions. Before designing a fifth variant it is worth establishing whether the account
structure can support the measured edge at all, because if it cannot then no entry rule
fixes it and the next four legs fail for the same reason as the last four.

The structural ratio, measured:

    window                    session sd    buffer / sd
    GLOBEX_TO_OPEN, dev+val         $141           14.2
    FULL_SESSION,   dev+val         $257            7.8

A fixed drawdown limit wants twenty or more standard deviations of room. The best
available here is fourteen, and one MES contract is the SMALLEST position that exists, so
the exposure cannot be reduced by sizing down. That is a property of the account and the
contract, not of any signal.

WHAT THIS SWEEPS
----------------
Every lever that is genuinely available, under the real Topstep rules:

    window          which slice of the session is held
    volatility gate trade only when the causal volatility percentile is below a threshold
    daily stop      the SELF-IMPOSED per-session loss cap, a DESIGN choice not a firm rule
    contracts       1 or 2

WHY THE BOOTSTRAP IS BLOCKED, NOT NORMAL
----------------------------------------
An earlier Monte Carlo on these moments assumed normal returns and put P(breach) at 23%
over 387 sessions. The real account breached in 25. The error was not the drift estimate,
it was the tail and the clustering: losing sessions arrive together, and a normal draw
cannot produce that.

This resamples CONTIGUOUS BLOCKS of actual observed sessions, mean length ten, so the fat
left tail and the volatility clustering both survive into the simulation. Every number
here inherits the sample's own worst stretches rather than a tidy assumption about them.
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
from tools.session_decomposition import WINDOWS, window_returns  # noqa: E402

MEAN_BLOCK = 10          # sessions; long enough to carry a losing cluster intact


def stationary_bootstrap(x: np.ndarray, n_out: int, rng, mean_block: int = MEAN_BLOCK):
    """
    Politis-Romano stationary bootstrap. Blocks of geometric length, wrapped circularly,
    so volatility clustering and the joint behaviour of consecutive sessions survive.
    """
    n = len(x)
    out = np.empty(n_out)
    i, p = rng.integers(n), 1.0 / mean_block
    for k in range(n_out):
        out[k] = x[i % n]
        i = rng.integers(n) if rng.random() < p else i + 1
    return out


def simulate(returns: np.ndarray, rules: PropRules, n_sessions: int, trials: int,
             rng, daily_stop: float | None) -> dict:
    """
    Replay the Topstep rules over bootstrapped session P&L.

    The trailing MLL ratchets on end-of-day balance and locks at the starting balance, so
    reaching +$2,000 is the milestone that makes the account structurally safe: past it the
    floor never rises again and every further dollar of profit is pure buffer.
    """
    passed = breached = 0
    for _ in range(trials):
        r = stationary_bootstrap(returns, n_sessions, rng)
        if daily_stop is not None:
            # The self-imposed stop flattens the position once the session loss reaches it.
            # Modelled as a floor with a tick of slippage, since the exit is a market order.
            r = np.maximum(r, -daily_stop * 1.05)
        bal = rules.starting_balance
        floor = rules.starting_balance - rules.mll_buffer
        peak = bal
        for x in r:
            bal += x
            if bal <= floor:
                breached += 1
                break
            if bal >= rules.target_balance:
                passed += 1
                break
            peak = max(peak, bal)
            floor = min(peak - rules.mll_buffer, rules.mll_locks_at)
    return {"pass": passed / trials, "breach": breached / trials,
            "neither": 1 - (passed + breached) / trials}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--symbol", default="MES")
    ap.add_argument("--price-source")
    ap.add_argument("--measured-costs", type=Path)
    ap.add_argument("--cost-scenario", choices=sorted(COST_SCENARIOS), default="adverse")
    ap.add_argument("--decision-minutes", type=int, default=5)
    ap.add_argument("--through", type=float, default=0.80,
                    help="Fraction of the sample to use. 0.80 is development plus "
                         "validation, both of which have been seen. The lockbox is the "
                         "remaining 0.20 and is NOT touched by this tool.")
    ap.add_argument("--sessions", type=int, default=250,
                    help="Horizon in sessions, roughly one year.")
    ap.add_argument("--trials", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    inst = INSTRUMENTS[args.symbol]
    costs = (measured_cost_models(args.measured_costs, args.symbol)[args.cost_scenario]
             if args.measured_costs else COST_SCENARIOS[args.cost_scenario])
    rt_points = costs.round_trip_points(inst)
    rules = PropRules()

    data_symbol = args.price_source or args.symbol
    bars = resample(build_continuous(args.data, data_symbol), args.decision_minutes)
    feats = compute(bars, or_minutes=30, atr_window=14, rvol_lookback=20,
                    bar_minutes=args.decision_minutes)
    sessions = sorted(feats["session_date"].unique())
    keep = set(sessions[:int(len(sessions) * args.through)])
    feats = feats[feats["session_date"].isin(keep)].reset_index(drop=True)
    mso = minutes_since_open(feats)

    # Causal volatility percentile, one value per session, built from PRIOR sessions only.
    rv = feats.groupby("session_date")["rv_pct"].first()

    print("FEASIBILITY SWEEP")
    print("=" * 84)
    print(f"{args.symbol} via {data_symbol} | {len(keep)} sessions "
          f"| horizon {args.sessions} | {args.trials:,} trials")
    print(f"round trip {rt_points:.3f} pts = ${costs.round_trip_usd(inst):.2f} | "
          f"buffer ${rules.mll_buffer:,.0f} | target ${rules.profit_target:,.0f}")
    print("Stationary block bootstrap of ACTUAL sessions, mean block "
          f"{MEAN_BLOCK}, so fat tails and clustering survive.")
    print()

    rng = np.random.default_rng(args.seed)
    rows = []
    print(f"  {'window':<16}{'vol gate':>10}{'daily stop':>12}{'qty':>5}"
          f"{'n sess':>8}{'$/sess':>9}{'sd $':>8}{'PASS':>8}{'BREACH':>8}")

    for wname in ("GLOBEX_TO_OPEN", "FULL_SESSION"):
        lo, hi = WINDOWS[wname]
        r_pts = window_returns(feats, mso, lo, hi)
        for gate in (1.00, 0.60, 0.40):
            sel = r_pts.index[rv.reindex(r_pts.index).fillna(1.0) <= gate]
            if len(sel) < 60:
                continue
            base = (r_pts.loc[sel] - rt_points).to_numpy() * inst.point_value
            frac = len(sel) / len(r_pts)
            for stop in (None, 300.0, 150.0):
                for qty in (1, 2):
                    x = base * qty
                    res = simulate(x, rules, int(args.sessions * frac), args.trials,
                                   rng, stop)
                    rows.append({"window": wname, "gate": gate, "daily_stop": stop,
                                 "qty": qty, "n_sessions": len(sel),
                                 "mean_usd": float(x.mean()), "sd_usd": float(x.std(ddof=1)),
                                 **res})
                    print(f"  {wname:<16}{gate:>10.2f}"
                          f"{('none' if stop is None else f'${stop:.0f}'):>12}{qty:>5}"
                          f"{len(sel):>8}{x.mean():>9.2f}{x.std(ddof=1):>8.0f}"
                          f"{res['pass']:>8.1%}{res['breach']:>8.1%}")

    best = max(rows, key=lambda r: r["pass"])
    print()
    print(f"  BEST P(pass): {best['pass']:.1%} at {best['window']}, gate "
          f"{best['gate']:.2f}, daily stop "
          f"{'none' if best['daily_stop'] is None else '$%.0f' % best['daily_stop']}, "
          f"{best['qty']} contract(s), P(breach) {best['breach']:.1%}")
    print()
    print("=" * 84)
    print("HOW TO READ THIS:")
    print("  1. Every configuration is measured on data ALREADY SEEN (development plus")
    print("     validation). These are in-sample odds and are the OPTIMISTIC case.")
    print("  2. A gate of 1.00 means no volatility filter. Gating raises survival by")
    print("     trading less, which also lengthens the time to the target.")
    print("  3. The daily stop is a DESIGN choice, not a firm rule. It is the only lever")
    print("     that truncates a session's loss without reducing position size.")
    print("  4. P(breach) is the probability of losing the account. Weigh it against the")
    print("     evaluation fee, not against P(pass).")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(rows, indent=2, default=str))
        print(f"\nwritten to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
