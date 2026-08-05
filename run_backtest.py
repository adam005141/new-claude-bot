#!/usr/bin/env python3
"""
Run the MES/MNQ opening-range backtest.

Chronological splits are enforced here, not left to the caller. The lockbox is refused
unless explicitly unlocked, because a lockbox you can open by accident is not a lockbox.

    python run_backtest.py --data data --split dev
    python run_backtest.py --data data --split dev --cost-scenario severe
    python run_backtest.py --data data --split validation --report out/

The lockbox is used ONCE, ever, and only after the rules and code are frozen:

    python run_backtest.py --data data --split lockbox --i-understand-this-is-single-use
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from engine import __version__
from engine.backtest import Backtester
from engine.config import EngineConfig, StrategyParams
from engine.data import build_continuous, provenance, resample
from engine.features import compute
from engine.reporting import (
    block_bootstrap_ci, breakdown, compute_metrics, concentration_test, format_report,
)

log = logging.getLogger("run_backtest")

# Chronological split of the available sample. Fractions, applied to sorted session dates,
# so the boundaries move with the data rather than being hardcoded to specific dates.
SPLITS = {"dev": (0.0, 0.50), "validation": (0.50, 0.80), "lockbox": (0.80, 1.00),
          "all": (0.0, 1.00)}


def split_sessions(sessions: list[date], split: str) -> set[date]:
    lo, hi = SPLITS[split]
    n = len(sessions)
    return set(sessions[int(n * lo):int(n * hi)])


def prepare(data_dir: str, symbol: str, cfg: EngineConfig) -> pd.DataFrame:
    """
    Load and featurise price history for one traded instrument.

    When `price_source` is set the BARS come from that symbol while everything else,
    sizing, costs, P&L, and the orderable guard, stays on `symbol`. That split is the
    whole point: ES has years more history than the MES data on hand, and the proxy has
    been measured rather than assumed.
    """
    data_symbol = cfg.price_source or symbol
    cont = build_continuous(data_dir, data_symbol,
                            stop_entries_days_before_expiry=cfg.roll_stop_entries_days)
    bars = resample(cont, cfg.decision_bar_minutes)
    p = cfg.strategy_for(symbol)
    return compute(bars, or_minutes=p.or_minutes, atr_window=p.atr_window,
                   rvol_lookback=p.rvol_lookback, bar_minutes=cfg.decision_bar_minutes)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--symbols", nargs="+", default=["MES", "MNQ"])
    ap.add_argument("--split", choices=sorted(SPLITS), default="dev")
    ap.add_argument("--cost-scenario", choices=["base", "adverse", "severe"], default="adverse")
    ap.add_argument("--decision-minutes", type=int, default=5)
    ap.add_argument("--or-minutes", type=int, default=30)
    ap.add_argument("--measured-costs", type=Path,
                    help="JSON from tools/measure_costs.py. Replaces assumed spreads "
                         "with measured percentiles of the real quoted spread.")
    ap.add_argument("--price-source",
                    help="Take price history from this symbol while trading --symbols. "
                         "Validate the substitution with tools/compare_es_mes.py first. "
                         "Example: --symbols MES --price-source ES")
    ap.add_argument("--cost-session", default="RTH_OPEN",
                    help="Charge this session's measured spread rather than the all-day "
                         "figure. Leg B fires in the opening hour, which quotes wider "
                         "than midday. Pass ALL to use the blended number.")
    ap.add_argument("--no-prop", action="store_true",
                    help="Personal mode: no prop rule layer")
    ap.add_argument("--report", type=Path, help="Directory for CSV/JSON artefacts")
    ap.add_argument("--i-understand-this-is-single-use", action="store_true",
                    help="Required to touch the lockbox split")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)-7s %(message)s")

    if args.split == "lockbox" and not args.i_understand_this_is_single_use:
        log.error("The lockbox is single-use and must not be opened casually. "
                  "Re-run with --i-understand-this-is-single-use once, and only once, "
                  "after the rules and code are frozen. Every prior look invalidates it.")
        return 2

    cfg = EngineConfig(
        symbols=tuple(args.symbols),
        decision_bar_minutes=args.decision_minutes,
        strategy=StrategyParams(or_minutes=args.or_minutes),
        cost_scenario=args.cost_scenario,
        price_source=args.price_source,
        measured_costs_path=str(args.measured_costs) if args.measured_costs else None,
        measured_costs_session=(None if args.cost_session.upper() == "ALL"
                                else args.cost_session),
    )
    if args.no_prop:
        from dataclasses import replace
        cfg.prop = replace(cfg.prop, enabled=False)

    cost_source = "MEASURED" if args.measured_costs else "ASSUMED"
    print(f"engine {__version__} | split={args.split} | "
          f"costs={args.cost_scenario} ({cost_source}) | "
          f"prop={'off' if args.no_prop else 'on'}")
    if args.price_source:
        print(f"  PRICES from {args.price_source}, ECONOMICS from "
              f"{', '.join(args.symbols)}. This is a PROXY run: validate the "
              f"substitution with tools/compare_es_mes.py before trusting it.")
    if args.measured_costs:
        for sym in args.symbols:
            c = cfg.costs_for(sym)
            print(f"  {sym} [{args.cost_session}]: "
                  f"spread {c.spread_ticks_per_side:.2f} ticks/side "
                  f"+ {c.slippage_ticks_per_side:.2f} slippage, "
                  f"round trip ${c.round_trip_usd(cfg.instrument(sym)):.2f}/contract")
    print()

    all_trades, summaries = [], {}

    for symbol in args.symbols:
        try:
            feats = prepare(args.data, symbol, cfg)
        except FileNotFoundError as exc:
            log.error("%s", exc)
            return 1

        sessions = sorted(feats["session_date"].unique())
        keep = split_sessions(sessions, args.split)
        feats = feats[feats["session_date"].isin(keep)].reset_index(drop=True)
        if feats.empty:
            log.warning("%s: no bars in split %s", symbol, args.split)
            continue

        log.info("%s: %d bars, %d sessions (%s to %s)", symbol, len(feats), len(keep),
                 min(keep), max(keep))

        result = Backtester(cfg, symbol).run(feats)
        trades = result.trades_frame()
        # Rate metrics must divide by the sessions actually REPLAYED. A run that halts
        # permanently a third of the way through the split would otherwise report a
        # trade rate a third of the truth, and a no-trade-day share that never happened.
        observed = result.sessions_processed or len(keep)
        metrics = compute_metrics(trades, sessions_in_sample=observed)
        ci = block_bootstrap_ci(trades, seed=cfg.seed)

        print(format_report(metrics, f"{symbol} | {args.split} | {args.cost_scenario}", ci))
        if result.rejections:
            print("  rejected opportunities:")
            for reason, count in sorted(result.rejections.items(),
                                        key=lambda kv: -kv[1]):
                print(f"    {reason:<28}{count:>8,}")
        print(f"  final risk state    {result.final_state}")
        if result.terminated_early:
            print(f"\n  ** RUN TERMINATED EARLY: {result.final_state} after "
                  f"{result.sessions_processed} of {len(keep)} split sessions "
                  f"({result.sessions_processed / len(keep):.0%}). **")
            print("  The trades above stop at the moment the account died, so they are a")
            print("  PATH-TRUNCATED sample, not a sample of the split. Expectancy, win")
            print("  rate, and drawdown are all conditioned on surviving to that point.")
            print("  For the unconditioned research result, re-run with --no-prop.")
        print()

        if not trades.empty:
            for dim in ("side", "exit_reason", "contract_month"):
                b = breakdown(trades, dim)
                if not b.empty:
                    print(f"  by {dim}:")
                    print(b.to_string(index=False, float_format=lambda v: f"{v:,.2f}"))
                    print()

            conc = concentration_test(trades)
            print("  profit concentration:")
            for k, v in conc.items():
                print(f"    {k:<28}{v:>12,.2f}")
            print()

        all_trades.append(trades)
        summaries[symbol] = {
            "metrics": metrics.to_dict(),
            "ci": ci,
            "rejections": result.rejections,
            "sessions_in_split": len(keep),
            "sessions_processed": result.sessions_processed,
            "terminated_early": result.terminated_early,
            "final_state": result.final_state,
            "provenance": provenance(args.data, symbol),
        }

    if args.report and summaries:
        out = Path(args.report)
        out.mkdir(parents=True, exist_ok=True)
        combined = pd.concat([t for t in all_trades if not t.empty], ignore_index=True) \
            if any(not t.empty for t in all_trades) else pd.DataFrame()
        if not combined.empty:
            combined.to_csv(out / f"trades_{args.split}_{args.cost_scenario}.csv", index=False)
        (out / f"summary_{args.split}_{args.cost_scenario}.json").write_text(
            json.dumps({"engine_version": __version__,
                        "split": args.split,
                        "cost_scenario": args.cost_scenario,
                        "config": cfg.fingerprint(),
                        "results": summaries}, indent=2, default=str))
        print(f"artefacts written to {out}")

    if args.measured_costs:
        print("\nNOTE: spreads are MEASURED from real BID/ASK quotes, but quoted spread is "
              "a LOWER BOUND\non execution cost: queue position, partial fills, and "
              "widening on order arrival are\nnot observable in bar data. True cost is at "
              "least this, and usually worse.")
    else:
        print("\nNOTE: costs are ASSUMED, not measured. Run tools/measure_costs.py and pass "
              "--measured-costs\nto replace the priors. Every number above inherits that "
              "uncertainty.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
