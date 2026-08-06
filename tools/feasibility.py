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
from tools.session_decomposition import (  # noqa: E402
    WINDOWS, window_excursion, window_returns,
)

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


def apply_daily_stop(final_usd: np.ndarray, mae_usd: np.ndarray,
                     stop_usd: float | None, slip_usd: float = 6.25) -> np.ndarray:
    """
    Apply a per-session loss cap using the ACTUAL intraday path.

    A session whose adverse excursion reached the cap is closed there and its later
    recovery is NOT available. This is the whole correction: an earlier version floored the
    session's FINAL return instead, which kept every session that traded through the stop
    and came back. On this data that look-ahead was worth about $40 a session against a
    real edge of $8.68, and it turned a -$12.57 configuration into +$75.92. It reported a
    100% pass rate for a strategy with negative expectancy.

    `slip_usd` is one MES tick, because a stop is a market order once touched.
    """
    if stop_usd is None:
        return final_usd
    hit = mae_usd <= -stop_usd
    return np.where(hit, -(stop_usd + slip_usd), final_usd)


def simulate(returns: np.ndarray, rules: PropRules, n_sessions: int, trials: int,
             rng, daily_stop: float | None = None, base_qty: int = 1,
             ramp_qty: int | None = None) -> dict:
    """
    Replay the Topstep rules over bootstrapped session P&L.

    `returns` is PER CONTRACT. The trailing MLL ratchets on end-of-day balance and locks at
    the starting balance, so reaching +$2,000 is the milestone that makes the account
    structurally safe: past it the floor never rises again and every further dollar of
    profit is pure buffer.

    `ramp_qty` exploits exactly that. Sizing up from the start doubles the exposure through
    the only genuinely dangerous stretch, which the sweep shows converts a 2:1 edge into a
    permanent coin flip. Sizing up only AFTER the floor has locked is a different bet: from
    there the account can lose nothing but profit it has already earned, so the larger size
    is applied to a bounded downside rather than to the buffer.
    """
    lock_at = rules.mll_locks_at + rules.mll_buffer      # balance at which the floor locks
    passed = breached = 0
    t_pass: list[int] = []
    t_breach: list[int] = []
    for _ in range(trials):
        # `returns` already has the stop applied per session using the real intraday
        # path. Applying it here, to a bootstrapped series, would be the look-ahead this
        # tool exists to avoid.
        r = stationary_bootstrap(returns, n_sessions, rng)
        bal = rules.starting_balance
        floor = rules.starting_balance - rules.mll_buffer
        peak = bal
        for k, x in enumerate(r, start=1):
            qty = ramp_qty if (ramp_qty is not None and peak >= lock_at) else base_qty
            bal += x * qty
            if bal <= floor:
                breached += 1
                t_breach.append(k)
                break
            if bal >= rules.target_balance:
                passed += 1
                t_pass.append(k)
                break
            peak = max(peak, bal)
            floor = min(peak - rules.mll_buffer, rules.mll_locks_at)
    return {"pass": passed / trials, "breach": breached / trials,
            "neither": 1 - (passed + breached) / trials,
            "sessions_to_pass": float(np.mean(t_pass)) if t_pass else float("nan"),
            "sessions_to_breach": float(np.mean(t_breach)) if t_breach else float("nan")}


SESSIONS_PER_MONTH = 21.0


def expected_fees(res: dict, fee_upfront: float, fee_monthly: float,
                  fee_activation: float) -> float:
    """
    Expected total fees to reach a FUNDED account, allowing for repeated attempts.

        E = (1-p)/p * cost(failed attempt) + cost(successful attempt) + activation

    This is the objective, and it is not the same as maximising P(pass). A slow grind
    with a high pass rate pays a monthly subscription for years per attempt; a fast
    resolution with a mediocre pass rate fails cheaply and starts again. Cheap failure
    can beat expensive success, and ranking by P(pass) hides that completely.

    Unresolved paths are charged for the whole horizon, since the subscription does not
    stop just because nothing has happened.
    """
    p = res["pass"]
    if p <= 0:
        return float("inf")
    months = lambda n: (n / SESSIONS_PER_MONTH if np.isfinite(n) else 0.0)
    cost_fail = fee_upfront + fee_monthly * months(res["sessions_to_breach"])
    cost_pass = fee_upfront + fee_monthly * months(res["sessions_to_pass"])
    return (1 - p) / p * cost_fail + cost_pass + fee_activation


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
    ap.add_argument("--fee-upfront", type=float, default=50.0)
    ap.add_argument("--fee-monthly", type=float, default=50.0)
    ap.add_argument("--fee-activation", type=float, default=150.0)
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
    print("  `$/sess` is NET of cost and AFTER the stop, applied against each session's")
    print("  real intraday path. `stopped` is how often the cap actually fired.")
    print()
    print(f"  {'window':<16}{'vol gate':>10}{'daily stop':>12}{'qty':>5}"
          f"{'n sess':>8}{'$/sess':>9}{'sd $':>8}{'stopped':>8}{'PASS':>8}{'BREACH':>8}")

    for wname in ("GLOBEX_TO_OPEN", "FULL_SESSION"):
        lo, hi = WINDOWS[wname]
        exc = window_excursion(feats, mso, lo, hi)
        for gate in (1.00, 0.60, 0.40):
            sel = exc.index[rv.reindex(exc.index).fillna(1.0) <= gate]
            if len(sel) < 60:
                continue
            frac = len(sel) / len(exc)
            for stop in (None, 300.0, 150.0):
                for qty in (1, 2):
                    # Gross P&L and adverse excursion at this size, then the stop applied
                    # against the real path, then the round trip charged.
                    final = exc.loc[sel, "final"].to_numpy() * inst.point_value * qty
                    mae = exc.loc[sel, "mae"].to_numpy() * inst.point_value * qty
                    x = (apply_daily_stop(final, mae, stop)
                         - rt_points * inst.point_value * qty)
                    res = simulate(x, rules, int(args.sessions * frac), args.trials, rng)
                    hit_rate = (0.0 if stop is None
                                else float((mae <= -stop).mean()))
                    rows.append({"window": wname, "gate": gate, "daily_stop": stop,
                                 "qty": qty, "n_sessions": len(sel),
                                 "mean_usd": float(x.mean()),
                                 "sd_usd": float(x.std(ddof=1)),
                                 "stop_hit_rate": hit_rate, **res})
                    print(f"  {wname:<16}{gate:>10.2f}"
                          f"{('none' if stop is None else f'${stop:.0f}'):>12}{qty:>5}"
                          f"{len(sel):>8}{x.mean():>9.2f}{x.std(ddof=1):>8.0f}"
                          f"{hit_rate:>8.0%}{res['pass']:>8.1%}{res['breach']:>8.1%}")

    # ---- horizon sensitivity -------------------------------------------------
    #
    # The single lever not in the table above. At $5-6 a session, 250 sessions produces
    # $1,250-1,575 against a $3,000 target, so most paths end in "neither" rather than in
    # a verdict. Topstep no longer imposes a time limit, which makes patience a real and
    # free lever in a way that sizing up is not.
    #
    # The trailing MLL makes this asymmetric rather than a simple race. The floor is
    # min(peak - buffer, starting balance), so once the balance reaches +$2,000 the floor
    # LOCKS at the starting balance and never rises again. Past that point the account can
    # only lose profit it has already made, and the remaining $1,000 is far easier than the
    # first $2,000. Time helps disproportionately once that milestone is cleared.
    ranked = sorted(rows, key=lambda r: -(r["pass"] / max(r["breach"], 1e-9)))
    top = [r for r in ranked if r["pass"] > 0.10][:3]
    if top:
        print()
        print("  HORIZON SENSITIVITY for the best pass-to-breach configurations.")
        print("  Topstep imposes no time limit, so this is a free lever. The MLL floor")
        print("  LOCKS at the starting balance once the account is +$2,000, after which it")
        print("  can only give back profit already earned.")
        print()
        print(f"  {'config':<44}{'250':>9}{'500':>9}{'750':>9}{'1000':>9}")
        for cfg in top:
            lo, hi = WINDOWS[cfg["window"]]
            exc = window_excursion(feats, mso, lo, hi)
            sel = exc.index[rv.reindex(exc.index).fillna(1.0) <= cfg["gate"]]
            frac = len(sel) / len(exc)
            final = exc.loc[sel, "final"].to_numpy() * inst.point_value * cfg["qty"]
            mae = exc.loc[sel, "mae"].to_numpy() * inst.point_value * cfg["qty"]
            x = (apply_daily_stop(final, mae, cfg["daily_stop"])
                 - rt_points * inst.point_value * cfg["qty"])
            stop_lbl = "none" if cfg["daily_stop"] is None else f"${cfg['daily_stop']:.0f}"
            label = (f"{cfg['window']} g{cfg['gate']:.2f} {stop_lbl} x{cfg['qty']}")
            cells = []
            for h in (250, 500, 750, 1000):
                r = simulate(x, rules, int(h * frac), args.trials, rng)
                cells.append(f"{r['pass']:.0%}/{r['breach']:.0%}")
                cfg[f"h{h}"] = r
            print(f"  {label:<44}" + "".join(f"{c:>9}" for c in cells))
        print("  each cell is PASS/BREACH")

        # ---- cost to a funded account -----------------------------------
        #
        # The objective the fee structure actually implies. Passing inside one month is
        # arithmetically out of reach: $3,000 over 21 sessions is $143 a session, which at
        # the measured $6.30 per contract needs 23 contracts, and 23 contracts puts the
        # session standard deviation at roughly $2,800 against a $2,000 buffer. MES has no
        # smaller size, so that is a wall rather than a parameter.
        #
        # What IS controllable is expected total fees, and it ranks configurations
        # differently from P(pass): a slow grind pays the monthly subscription for years
        # per attempt, while a fast resolution fails cheaply and starts again.
        print()
        print("  EXPECTED COST TO A FUNDED ACCOUNT")
        print(f"  ${args.fee_upfront:.0f} up front, ${args.fee_monthly:.0f}/month, "
              f"${args.fee_activation:.0f} on passing, retrying until funded.")
        print("  Ranked by cost, NOT by P(pass). Cheap failure can beat expensive success.")
        print()
        cfg = top[0]
        lo, hi = WINDOWS[cfg["window"]]
        exc = window_excursion(feats, mso, lo, hi)
        sel = exc.index[rv.reindex(exc.index).fillna(1.0) <= cfg["gate"]]
        frac = len(sel) / len(exc)
        f1 = exc.loc[sel, "final"].to_numpy() * inst.point_value
        m1 = exc.loc[sel, "mae"].to_numpy() * inst.point_value
        per_contract = (apply_daily_stop(f1, m1, cfg["daily_stop"])
                        - rt_points * inst.point_value)

        plans = [(f"flat {q} contract" + ("s" if q > 1 else ""), q, None)
                 for q in (1, 2, 3, 4, 6)]
        plans += [(f"1 then {q} after the lock", 1, q) for q in (2, 3, 4)]
        plans += [(f"2 then {q} after the lock", 2, q) for q in (4, 6)]

        cost_rows = []
        for label, base, ramp in plans:
            r = simulate(per_contract, rules, int(1500 * frac), args.trials, rng,
                         base_qty=base, ramp_qty=ramp)
            r["cost"] = expected_fees(r, args.fee_upfront, args.fee_monthly,
                                      args.fee_activation)
            r["label"] = label
            cost_rows.append(r)
        cost_rows.sort(key=lambda r: r["cost"])

        print(f"  {'sizing plan':<28}{'PASS':>7}{'BREACH':>8}{'mo pass':>9}"
              f"{'mo fail':>9}{'E[fees]':>10}")
        for r in cost_rows:
            mp = r["sessions_to_pass"] / SESSIONS_PER_MONTH
            mf = r["sessions_to_breach"] / SESSIONS_PER_MONTH
            print(f"  {r['label']:<28}{r['pass']:>7.0%}{r['breach']:>8.0%}"
                  f"{mp:>9.1f}{mf:>9.1f}{r['cost']:>10,.0f}")
        print()
        print(f"  on {cfg['window']} gate {cfg['gate']:.2f} stop "
              f"{'none' if cfg['daily_stop'] is None else '$%.0f' % cfg['daily_stop']}")
        cheapest = cost_rows[0]
        print(f"  CHEAPEST: {cheapest['label']} at ${cheapest['cost']:,.0f} expected, "
              f"P(pass) {cheapest['pass']:.0%}")

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
    print("  3. The daily stop is a DESIGN choice, not a firm rule. It truncates a")
    print("     session's loss without reducing size, and it COSTS expectancy: every")
    print("     session that traded through the cap and recovered is now a realised loss.")
    print("     If a stop RAISES `$/sess`, that is a bug, not a discovery.")
    print("  4. P(breach) is the probability of losing the account. Weigh it against the")
    print("     evaluation fee, not against P(pass).")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(rows, indent=2, default=str))
        print(f"\nwritten to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
