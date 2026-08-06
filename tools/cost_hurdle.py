#!/usr/bin/env python3
"""
Measure the cost hurdle, in R, as a function of stop distance and instrument.

This is a MEASUREMENT, not a strategy. It evaluates no signal, books no P&L, and consumes
no split. It exists because two structurally opposite legs have now failed, and the
binding constraint was shown to be the ratio between what a trade costs and what it risks,
not either entry rule.

The central identity, which is exact rather than simulated:

    cost_usd = qty * round_trip_usd
    risk_usd = qty * stop_points * point_value

    cost_in_R = cost_usd / risk_usd = round_trip_points / stop_points

**Quantity cancels completely.** Integer rounding, the contract cap, and portfolio heat all
drop out. The cost hurdle depends on exactly two things: how many index points the round
trip costs, and how many index points the stop is. Nothing else.

Three consequences follow, and they are arithmetic, not opinion:

1. Widening the stop lowers the hurdle proportionally. Doubling the stop halves it. The
   position shrinks to keep dollar risk constant, so this is not a risk increase.
2. It stops working at the point where one contract already exceeds the R budget, because
   the engine correctly refuses to trade there (sizing.SIZE_ZERO_STOP_TOO_WIDE). Going
   past it requires raising r_target_usd, which spends the prop buffer.
3. The right instrument is the one whose round trip is small RELATIVE TO ITS OWN point
   moves. That is not the same as the one that is cheap in dollars, and the two answers
   can disagree.

Usage:

    python tools/cost_hurdle.py --data data --measured-costs config/measured_costs.json
    python tools/cost_hurdle.py --data data --price-source ES --symbols MES
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
    COST_SCENARIOS, INSTRUMENTS, Instrument, CostModel, PropRules, RiskParams,
    measured_cost_models,
)
from engine.data import build_continuous, resample  # noqa: E402
from engine.features import atr  # noqa: E402

# Stop distances to evaluate, as multiples of the decision-timeframe ATR. 1.5 is the
# current setting for both legs; the rest bracket it in both directions.
ATR_MULTIPLES = (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0)


def cost_in_r(round_trip_points: float, stop_points: float) -> float:
    """The identity above. Independent of position size."""
    if stop_points <= 0:
        return float("inf")
    return round_trip_points / stop_points


def redenominate_slippage(costs: CostModel, inst: Instrument,
                          usd_per_side: float) -> CostModel:
    """
    Rebuild a cost model with slippage charged in DOLLARS rather than ticks.

    This exists because the choice of denomination is not neutral and was never measured.
    The spread in these models is measured; the slippage allowance is a prior, and it is
    expressed in ticks. A tick is worth $1.25 on MES and $0.50 on MNQ, so an identical
    "0.5 ticks" allowance charges MES two and a half times more in dollars for no reason
    grounded in observation.

    That assumption is load-bearing: it decides which instrument looks cheaper per
    contract. Any conclusion that survives only one denomination is an artefact of the
    denomination, and this function is how that gets caught rather than published.
    """
    return CostModel(
        name=f"{costs.name}[slip=${usd_per_side:.3f}/side]",
        commission_per_side=costs.commission_per_side,
        spread_ticks_per_side=costs.spread_ticks_per_side,
        slippage_ticks_per_side=usd_per_side / inst.tick_value,
        measured=costs.measured,
    )


def measure_atr(data_dir: str, symbol: str, bar_minutes: int, atr_window: int,
                split_hi: float) -> pd.Series:
    """
    ATR distribution on the decision timeframe, restricted to the development split.

    Restricted deliberately. This tool does not evaluate a signal, so it cannot overfit
    one, but reading the shape of validation or lockbox data is still a look at data that
    is supposed to be unseen. Cheap to avoid, so it is avoided.
    """
    cont = build_continuous(data_dir, symbol)
    bars = resample(cont, bar_minutes)
    sessions = sorted(bars["session_date"].unique())
    keep = set(sessions[:int(len(sessions) * split_hi)])
    bars = bars[bars["session_date"].isin(keep)]
    return atr(bars.reset_index(drop=True), atr_window).dropna()


def report(inst: Instrument, costs: CostModel, atr_points: pd.Series,
           risk: RiskParams) -> list[dict]:
    rt_points = costs.round_trip_points(inst)
    med_atr = float(atr_points.median())

    rows = []
    for mult in ATR_MULTIPLES:
        stop_pts = mult * med_atr
        # The engine's own floor, applied here so the table cannot recommend a geometry
        # that size_position would refuse.
        risk_per_contract = stop_pts * inst.point_value
        qty = int(risk.r_target_usd // risk_per_contract) if risk_per_contract > 0 else 0
        qty = min(qty, risk.max_contracts_per_instrument)
        tradable = qty >= 1
        realised_risk = qty * risk_per_contract
        rows.append({
            "atr_mult": mult,
            "stop_points": stop_pts,
            "risk_per_contract_usd": risk_per_contract,
            "contracts": qty,
            "realised_risk_usd": realised_risk,
            "cost_usd": qty * costs.round_trip_usd(inst),
            "cost_in_R": cost_in_r(rt_points, stop_pts),
            "tradable": tradable,
        })
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--symbols", nargs="+", default=["MES", "MNQ"])
    ap.add_argument("--price-source",
                    help="Read bars from this symbol while costing the traded one. "
                         "ES and MES track the same index, so ES ATR in points is MES "
                         "ATR in points; only the dollar economics differ.")
    ap.add_argument("--measured-costs", type=Path)
    ap.add_argument("--cost-scenario", default="adverse",
                    choices=sorted(COST_SCENARIOS))
    ap.add_argument("--cost-session", default="ALL")
    ap.add_argument("--decision-minutes", type=int, default=5)
    ap.add_argument("--atr-window", type=int, default=14)
    ap.add_argument("--dev-fraction", type=float, default=0.50)
    ap.add_argument("--slippage-usd", type=float, default=0.625,
                    help="Sensitivity: re-charge slippage at this many USD per side on "
                         "every instrument, instead of the tick-denominated prior. "
                         "Default 0.625 is what 0.5 ticks currently costs on MES.")
    args = ap.parse_args(argv)

    risk, prop = RiskParams(), PropRules()

    print("COST HURDLE ANALYSIS")
    print("=" * 78)
    print("cost_in_R = round_trip_points / stop_points.  Position size cancels exactly.")
    print(f"R target ${risk.r_target_usd:,.0f} | contract cap {risk.max_contracts_per_instrument}"
          f" | usable MLL buffer ${prop.usable_mll:,.0f}"
          f" = {prop.usable_mll / risk.r_target_usd:.0f}R")
    print()

    summary = {}
    for symbol in args.symbols:
        inst = INSTRUMENTS[symbol]
        if args.measured_costs:
            costs = measured_cost_models(
                args.measured_costs, symbol,
                session=None if args.cost_session.upper() == "ALL" else args.cost_session,
            )[args.cost_scenario]
        else:
            costs = COST_SCENARIOS[args.cost_scenario]

        data_symbol = args.price_source or symbol
        try:
            atr_pts = measure_atr(args.data, data_symbol, args.decision_minutes,
                                  args.atr_window, args.dev_fraction)
        except FileNotFoundError as exc:
            print(f"{symbol}: {exc}")
            continue
        if atr_pts.empty:
            print(f"{symbol}: no ATR observations")
            continue

        rt_usd = costs.round_trip_usd(inst)
        rt_points = costs.round_trip_points(inst)
        med_atr = float(atr_pts.median())

        print(f"--- {symbol} "
              f"{'(bars from ' + data_symbol + ')' if data_symbol != symbol else ''} ---")
        print(f"  cost model            {costs.name}"
              f"{'  MEASURED' if costs.measured else '  ASSUMED'}")
        print(f"  round trip            ${rt_usd:.2f}/contract = "
              f"{rt_points:.3f} index points")
        print(f"  {args.decision_minutes}-min ATR (dev)      "
              f"median {med_atr:.2f} pts, "
              f"p25 {atr_pts.quantile(.25):.2f}, p75 {atr_pts.quantile(.75):.2f}")
        print()
        print(f"  {'stop':>10} {'stop':>8} {'risk/ctr':>9} {'qty':>4} "
              f"{'risk':>8} {'cost':>7} {'HURDLE':>8}")
        print(f"  {'(xATR)':>10} {'(pts)':>8} {'(USD)':>9} {'':>4} "
              f"{'(USD)':>8} {'(USD)':>7} {'(R)':>8}")
        rows = report(inst, costs, atr_pts, risk)
        for r in rows:
            flag = "" if r["tradable"] else "   REFUSED: 1 contract exceeds R budget"
            print(f"  {r['atr_mult']:>10.1f} {r['stop_points']:>8.2f} "
                  f"{r['risk_per_contract_usd']:>9.2f} {r['contracts']:>4d} "
                  f"{r['realised_risk_usd']:>8.2f} {r['cost_usd']:>7.2f} "
                  f"{r['cost_in_R']:>8.3f}{flag}")

        tradable = [r for r in rows if r["tradable"]]
        if tradable:
            best = min(tradable, key=lambda r: r["cost_in_R"])
            worst = max(tradable, key=lambda r: r["cost_in_R"])
            print()
            print(f"  Best tradable hurdle  {best['cost_in_R']:.3f}R at "
                  f"{best['atr_mult']:.1f}xATR ({best['stop_points']:.1f} pts, "
                  f"{best['contracts']} contract{'s' if best['contracts'] > 1 else ''})")
            print(f"  vs current 1.5xATR    {[r for r in rows if r['atr_mult'] == 1.5][0]['cost_in_R']:.3f}R")
            alt = redenominate_slippage(costs, inst, args.slippage_usd)
            summary[symbol] = {
                "round_trip_usd": rt_usd,
                "round_trip_points": rt_points,
                "median_atr_points": med_atr,
                "hurdle_at_1_5_atr": [r for r in rows if r["atr_mult"] == 1.5][0]["cost_in_R"],
                "best_tradable_hurdle": best["cost_in_R"],
                "best_atr_multiple": best["atr_mult"],
                "alt_round_trip_usd": alt.round_trip_usd(inst),
                "alt_hurdle_at_1_5_atr": cost_in_r(alt.round_trip_points(inst),
                                                   1.5 * med_atr),
                "rows": rows,
            }
        print()

    if len(summary) > 1:
        print("=" * 78)
        print("INSTRUMENT COMPARISON")
        print("The cheap instrument in DOLLARS is not necessarily the cheap one in R.")
        print()
        print(f"  {'symbol':>8} {'$/RT':>8} {'pts/RT':>8} {'med ATR':>9} "
              f"{'hurdle@1.5x':>12} {'best':>8}")
        for sym, s in summary.items():
            print(f"  {sym:>8} {s['round_trip_usd']:>8.2f} {s['round_trip_points']:>8.3f} "
                  f"{s['median_atr_points']:>9.2f} {s['hurdle_at_1_5_atr']:>12.3f} "
                  f"{s['best_tradable_hurdle']:>8.3f}")
        print()
        cheap_usd = min(summary, key=lambda s: summary[s]["round_trip_usd"])
        cheap_r = min(summary, key=lambda s: summary[s]["hurdle_at_1_5_atr"])
        if cheap_usd == cheap_r:
            print(f"  {cheap_r} is cheaper on both measures.")
        else:
            print(f"  {cheap_usd} is cheaper in DOLLARS, but {cheap_r} is cheaper in R. "
                  f"R is what matters:\n  it is the ratio the strategy actually has to "
                  f"overcome.")

        # ---- sensitivity: is that verdict an artefact of an unmeasured assumption? ----
        print()
        print(f"  SENSITIVITY. The spread above is measured; the slippage allowance is a")
        print(f"  PRIOR denominated in TICKS, which charges each instrument a different")
        print(f"  number of dollars for the same nominal allowance. Re-charging slippage")
        print(f"  at a flat ${args.slippage_usd:.3f}/side on every instrument instead:")
        print()
        print(f"  {'symbol':>8} {'$/RT':>8} {'$/RT alt':>10} {'hurdle@1.5x':>12} {'alt':>8}")
        for sym, s in summary.items():
            print(f"  {sym:>8} {s['round_trip_usd']:>8.2f} {s['alt_round_trip_usd']:>10.2f} "
                  f"{s['hurdle_at_1_5_atr']:>12.3f} {s['alt_hurdle_at_1_5_atr']:>8.3f}")
        print()
        alt_cheap_usd = min(summary, key=lambda s: summary[s]["alt_round_trip_usd"])
        alt_cheap_r = min(summary, key=lambda s: summary[s]["alt_hurdle_at_1_5_atr"])
        if alt_cheap_usd != cheap_usd:
            print(f"  ** THE DOLLAR RANKING FLIPS: {cheap_usd} under tick-denominated "
                  f"slippage,\n     {alt_cheap_usd} under dollar-denominated. That "
                  f"comparison is an ARTEFACT of an\n     assumption, not a measurement. "
                  f"Do not choose an instrument on it. **")
        else:
            print(f"  Dollar ranking is unchanged ({alt_cheap_usd} cheaper either way).")
        if alt_cheap_r != cheap_r:
            print(f"  ** THE R RANKING ALSO FLIPS. No instrument conclusion is safe. **")
        else:
            print(f"  R ranking SURVIVES: {cheap_r} is cheaper under both denominations,")
            print(f"  so its advantage comes from the contract spec rather than the prior.")

    print()
    print("LIMITS OF THIS ANALYSIS, stated so the table is not over-read:")
    print("  1. A lower hurdle does not create an edge. It widens the window in which a")
    print("     real edge survives. Legs A and B were negative BEFORE costs, so nothing")
    print("     in this table would have rescued either of them.")
    print("  2. Wider stops mean fewer contracts and eventually one contract, at which")
    print("     point the lever is exhausted without raising r_target_usd and spending")
    print("     the MLL buffer.")
    print("  3. Wider stops change the strategy's holding time and hit rate. Those are")
    print("     signal properties and are NOT predicted here.")
    print("  4. Spread is measured but is a LOWER BOUND. Queue position and widening on")
    print("     order arrival are invisible in bar data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
