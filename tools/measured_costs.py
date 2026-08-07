#!/usr/bin/env python3
"""
Replace the commodity ORB's ASSUMED costs with MEASURED bid/ask, and add the depth
constraint the assumed model never had.

WHY THIS EXISTS
---------------
Every MES and MNQ result in this project used spreads measured from BID/ASK bars. The
imported commodity data has no quote series, so `tools/orb_commodity.py` fell back to a flat
1.5 ticks per side. That number was carried over from the MES adverse model and applied to
gold, silver, copper, crude and gas without anyone checking whether it fit. A headline PF of
1.39 resting on an unchecked cost constant is not a result.

This tool checks it against live quotes, and then asks the question the flat model cannot:
the strategy sizes up to 20 contracts, so is there anything on the other side?

WHAT WAS MEASURED, AND WHAT THAT IS WORTH
-----------------------------------------
Three rounds of top-of-book snapshots, 2026-08-06 22:08-22:12 America/New_York, pulled from
the IBKR quote feed. That is the Globex evening session.

State the limits before the numbers:

  * N=3 per symbol, over four minutes, on one evening. This is a spot check, not a spread
    distribution. It can catch a constant that is wrong by a factor of two. It cannot
    estimate a mean.
  * The sample is EVENING. The ORB enters within 180 minutes of the 09:30 open, which is the
    most liquid part of the day. Evening spreads are the wider end, so using them is
    conservative in the direction that matters.
  * These are TODAY's spreads on a strategy backtested over 2024-26. Spreads are not
    constant across two years. Nothing here reconstructs what the spread was at the moment
    of any historical trade, and no amount of live sampling can.
  * Micro Henry Hub gas could not be resolved through this interface at all; the NG expiry
    ladder returned only full-size contracts. NG is quoted below from the FULL-SIZE contract.
    Both trade the same price grid at the same 0.001 tick, so the tick COUNT carries over,
    but a micro is normally wider than its full-size parent. The NG figure is therefore a
    LOWER bound on the micro spread and is labelled as such everywhere it appears.
  * Silver is ambiguous. COMEX lists several silver futures against one underlying and the
    feed's symbol field is identical across every expiry, so the 1,000 oz micro cannot be
    told apart from the 5,000 oz parent by symbol. Both candidates at the September expiry
    quoted 2-4 ticks wide, so the number below is right either way; which contract produced
    it is not established.

THE DEPTH MODEL, WHICH IS THE POINT
------------------------------------
A flat per-side cost assumes the whole order fills at the touch. Observed top-of-book sizes
in this basket run 1 to 6 contracts. The strategy is permitted 20. An order larger than the
touch walks the book.

Modelled as a uniform book: `depth` contracts resting at every price level, levels one tick
apart. Filling `qty` consumes `ceil(qty / depth)` levels, and the contracts at level k pay k
extra ticks, so the average extra cost per contract is

    extra_ticks = sum_k (contracts at level k) * k / qty  ~=  (qty / depth - 1) / 2

A real book is not uniform and usually thickens away from the touch, so this OVERSTATES the
penalty for large orders. It is used as an upper bound, reported alongside the no-depth case
rather than instead of it.

WHAT THIS TOOL DOES NOT DO
--------------------------
It does not re-fit anything. `run_orb` is called once at zero slippage and the cost is
applied afterwards, which is exact: in that engine slippage is a pure deduction and never
moves a fill or triggers a stop. The trade list is identical under every cost model here.
Only the arithmetic on top of it changes.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.data import build_continuous, resample  # noqa: E402
from engine.overnight import minutes_since_open  # noqa: E402
from tools.feasibility import (  # noqa: E402
    SESSIONS_PER_MONTH, account_rules, expected_fees, simulate, stationary_bootstrap,
)
from tools.import_stitched import SPECS  # noqa: E402
from tools.orb_commodity import BASKET, OrbConfig, run_orb, summarise  # noqa: E402

# Observed top of book. (bid, ask, bid_size, ask_size) per snapshot.
# Source: IBKR quote feed, 2026-08-06 22:08-22:12 America/New_York, Globex evening session.
# Contract ids are recorded so the reading is reproducible and auditable.
QUOTES: dict[str, dict] = {
    "MGC": {
        "contract": "MGC Dec-2026 (COMEX id 751494403)",
        "note": "front by volume: 34,202 lots vs 22 in the Aug expiry, which quoted 16 ticks",
        "obs": [(4315.5, 4315.7, 4, 1), (4319.1, 4319.4, 3, 2), (4318.3, 4318.5, 4, 2)],
    },
    "SI": {
        "contract": "silver Sep-2026 (COMEX id 738529133)",
        "note": "micro vs 5,000 oz parent NOT established; the other Sep candidate quoted 2 ticks",
        "obs": [(62.385, 62.400, 2, 1), (62.425, 62.445, 2, 1), (62.410, 62.425, 1, 1)],
    },
    "HG": {
        "contract": "MHG Sep-2026 (COMEX id 559306209)",
        "note": "confirmed micro copper, 2,500 lb",
        "obs": [(6.7505, 6.7520, 4, 5), (6.7580, 6.7590, 1, 3), (6.7560, 6.7575, 3, 3)],
    },
    "MCL": {
        "contract": "MCL Sep-2026 (NYMEX id 661016525)",
        "note": "confirmed micro WTI, 100 bbl",
        "obs": [(78.06, 78.07, 6, 1), (78.03, 78.04, 2, 5), (78.06, 78.07, 1, 5)],
    },
    "NG": {
        "contract": "NG Sep-2026 FULL SIZE (NYMEX id 269460131)",
        "note": "LOWER BOUND: micro not listed in the ladder, full-size stands in",
        "obs": [(2.625, 2.626, 6, 6), (2.625, 2.626, 5, 4)],
    },
}

# Carried from the MES adverse model: beyond the spread itself, an allowance for latency
# between signal and fill and for the stop-order case where price is already moving.
BASE_SLIP_TICKS = 0.5

ASSUMED_SLIP_TICKS = 1.5   # what orb_commodity.py used for every symbol


def spread_stats(symbol: str) -> dict:
    """Half-spread in ticks, and the depth resting at the touch."""
    _pv, tick, tick_value = SPECS[symbol]
    obs = QUOTES[symbol]["obs"]
    spreads = np.array([(a - b) / tick for b, a, _bs, _as_ in obs])
    depths = np.array([min(bs, as_) for _b, _a, bs, as_ in obs], dtype=float)
    return {
        "n": len(obs),
        "spread_ticks_med": float(np.median(spreads)),
        "spread_ticks_min": float(spreads.min()),
        "spread_ticks_max": float(spreads.max()),
        "half_spread_ticks": float(np.median(spreads)) / 2.0,
        "depth_med": float(np.median(depths)),
        "depth_min": float(depths.min()),
        "tick_value": tick_value,
        "measured_side_usd": (float(np.median(spreads)) / 2.0 + BASE_SLIP_TICKS) * tick_value,
        "assumed_side_usd": ASSUMED_SLIP_TICKS * tick_value,
    }


def book_walk_ticks(qty: np.ndarray | float, depth: float) -> np.ndarray | float:
    """
    Average extra ticks per contract from consuming more than the touch.

    Uniform book: `depth` contracts at every level, one tick apart. Exact for the general
    case, not just for whole multiples of depth, so a 1-lot never pays a penalty.
    """
    q = np.asarray(qty, dtype=float)
    if depth <= 0:
        return np.zeros_like(q)
    levels = np.ceil(q / depth).astype(int)
    total = np.zeros_like(q)
    for k in range(1, int(levels.max()) + 1 if levels.size else 1):
        # contracts that land on level k (0-indexed levels; level 0 is free)
        on_k = np.clip(q - k * depth, 0.0, depth)
        total += on_k * k
    return np.divide(total, q, out=np.zeros_like(q), where=q > 0)


def apply_cost(trades: pd.DataFrame, symbol: str, side_ticks, commission: float
               ) -> pd.DataFrame:
    """Recompute net from a zero-slippage trade list. Exact: slippage never moves a fill."""
    pv, tick, _tv = SPECS[symbol]
    t = trades.copy()
    t["cost"] = (2.0 * np.asarray(side_ticks) * tick * pv + commission) * t["qty"]
    t["net"] = t["gross"] - t["cost"]
    t["r"] = np.where(t["risk"] > 0, t["net"] / t["risk"], 0.0)
    return t


def cap_qty(trades: pd.DataFrame, depth: float) -> pd.DataFrame:
    """
    Refuse to order more than is resting at the touch.

    Exact rescale, not a re-fit: quantity enters the engine only through `gross`, `risk`
    and `cost`, never through a fill price or a stop trigger. The trade list, its entries,
    its exits and its win rate are all unchanged. Only the size is.
    """
    t = trades.copy()
    old = t["qty"].to_numpy(dtype=float)
    new = np.minimum(old, max(1.0, np.floor(depth)))
    scale = new / old
    t["qty"] = new
    t["gross"] = t["gross"] * scale
    t["risk"] = t["risk"] * scale
    return t


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data_commodity")
    ap.add_argument("--symbols", nargs="+", default=list(BASKET))
    ap.add_argument("--bar-minutes", type=int, default=30)
    ap.add_argument("--or-minutes", type=int, default=60)
    ap.add_argument("--risk", type=float, default=250.0)
    ap.add_argument("--trials", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--account-model", default="MEAS+DEPTH",
                    choices=["ASSUMED", "MEASURED", "MEAS+DEPTH", "CAPPED"],
                    help="which cost model feeds the account simulation")
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    print("MEASURED COSTS vs THE ASSUMED CONSTANT")
    print("=" * 84)
    print("Quotes: IBKR top of book, 2026-08-06 22:08-22:12 ET, Globex evening.")
    print("N=3 per symbol. A spot check that can catch a bad constant, not a distribution.")
    print("Evening is the wide end of the day and the ORB trades the open, so this errs")
    print("toward overstating cost. NG is full-size standing in for the micro: LOWER BOUND.")
    print()

    stats = {s: spread_stats(s) for s in args.symbols if s in QUOTES}
    print(f"  {'sym':<5}{'spread ticks':>16}{'half':>7}{'depth':>8}{'tick $':>9}"
          f"{'assumed/side':>14}{'measured/side':>15}{'verdict':>12}")
    for s in args.symbols:
        if s not in stats:
            continue
        d = stats[s]
        rng_txt = (f"{d['spread_ticks_min']:.0f}-{d['spread_ticks_max']:.0f}"
                   f" (med {d['spread_ticks_med']:.1f})")
        ratio = d["measured_side_usd"] / d["assumed_side_usd"]
        verdict = ("assumed OK" if ratio <= 1.0 else
                   "assumed LOW" if ratio > 1.05 else "matched")
        print(f"  {s:<5}{rng_txt:>16}{d['half_spread_ticks']:>7.1f}"
              f"{d['depth_med']:>8.0f}{d['tick_value']:>9.2f}"
              f"{d['assumed_side_usd']:>14.2f}{d['measured_side_usd']:>15.2f}"
              f"{verdict:>12}")
    for s in args.symbols:
        if s in QUOTES:
            print(f"      {s:<4} {QUOTES[s]['contract']}: {QUOTES[s]['note']}")
    print()

    # ---- the trade list, once, at zero slippage ----------------------------
    base = OrbConfig(or_minutes=args.or_minutes, bar_minutes=args.bar_minutes,
                     per_trade_risk_dollars=args.risk)
    zero = replace(base, slip_ticks_per_side=0.0, commission_round_turn=0.0)

    raw: dict[str, pd.DataFrame] = {}
    for sym in args.symbols:
        bars = resample(build_continuous(args.data, sym), args.bar_minutes)
        bars = bars.assign(mso=minutes_since_open(bars))
        t = run_orb(bars, SPECS[sym], zero)
        if not t.empty:
            raw[sym] = t

    if not raw:
        print("  no trades; nothing to cost")
        return 1

    # ---- how big are the orders, against how much is resting? --------------
    print("  ORDER SIZE vs RESTING DEPTH. The flat model assumed the whole order fills")
    print("  at the touch. This is what it was actually asking for.")
    print(f"  {'sym':<5}{'trades':>8}{'qty med':>9}{'qty p90':>9}{'qty max':>9}"
          f"{'depth med':>11}{'over depth':>12}{'walk ticks':>12}")
    for sym, t in raw.items():
        d = stats.get(sym)
        if d is None:
            continue
        q = t["qty"].to_numpy(dtype=float)
        walk = book_walk_ticks(q, d["depth_med"])
        print(f"  {sym:<5}{len(t):>8}{np.median(q):>9.0f}"
              f"{np.percentile(q, 90):>9.0f}{q.max():>9.0f}"
              f"{d['depth_med']:>11.0f}{(q > d['depth_med']).mean():>12.0%}"
              f"{np.median(walk):>12.2f}")
    print()

    # ---- three cost models on the same trades ------------------------------
    models = {
        "ASSUMED": "flat 1.5 ticks/side, what the headline used",
        "MEASURED": "half-spread + 0.5 tick, no depth penalty",
        "MEAS+DEPTH": "adds the book walk; upper bound, uniform book",
        "CAPPED": "never order more than rests at the touch; no walk to pay",
    }
    per_model: dict[str, dict] = {}
    print("  THE SAME TRADE LIST UNDER FOUR COST MODELS")
    for name, blurb in models.items():
        print(f"\n  {name} -- {blurb}")
        print(f"  {'sym':<5}{'net $':>11}{'PF':>7}{'drag':>7}{'$/side':>9}")
        combined = []
        rows = {}
        for sym, t in raw.items():
            d = stats.get(sym)
            _pv, _tick, tv = SPECS[sym]
            if name == "ASSUMED" or d is None:
                side = np.full(len(t), ASSUMED_SLIP_TICKS)
            elif name == "MEASURED":
                side = np.full(len(t), d["half_spread_ticks"] + BASE_SLIP_TICKS)
            elif name == "CAPPED":
                t = cap_qty(t, d["depth_med"])
                side = np.full(len(t), d["half_spread_ticks"] + BASE_SLIP_TICKS)
            else:
                side = (d["half_spread_ticks"] + BASE_SLIP_TICKS
                        + book_walk_ticks(t["qty"].to_numpy(dtype=float), d["depth_med"]))
            ct = apply_cost(t, sym, side, base.commission_round_turn)
            s = summarise(ct)
            rows[sym] = s
            combined.append(ct)
            print(f"  {sym:<5}{s['net']:>11,.0f}{s['pf']:>7.2f}{s['drag']:>7.0%}"
                  f"{float(np.median(side)) * tv:>9.2f}")
        allt = pd.concat(combined, ignore_index=True)
        tot = summarise(allt)
        rows["ALL"] = tot
        per_model[name] = {"per_symbol": rows,
                           "daily": allt.groupby("session_date")["net"].sum()}
        print(f"  {'ALL':<5}{tot['net']:>11,.0f}{tot['pf']:>7.2f}{tot['drag']:>7.0%}")
    print()

    # ---- does the account still pass under the strictest model? ------------
    print("=" * 84)
    print(f"  ACCOUNT SIMULATION under {args.account_model}.")
    print("  Block bootstrap, mean block 10. `luck` is the same series with the mean")
    print("  removed, so LIFT is what the strategy adds over a matched coin flip.")
    print()
    rng = np.random.default_rng(args.seed)
    daily = per_model[args.account_model]["daily"].sort_index()
    series = daily.to_numpy()
    edge_free = series - series.mean()
    print(f"  {len(daily)} sessions, ${series.mean():.2f}/session, "
          f"sd ${series.std(ddof=1):.0f}")
    print(f"  {'account':<8}{'mult':>6}{'B/sd':>7}{'PASS':>7}{'luck':>7}{'LIFT':>7}"
          f"{'BREACH':>8}{'mo':>6}{'E[fees]':>10}")
    acct_rows = []
    for acct in ("50k", "100k", "150k"):
        ar = account_rules(acct)
        for mult in (0.5, 0.75, 1.0):
            x = series * mult
            res = simulate(x, ar, 1500, args.trials, rng)
            null = simulate(edge_free * mult, ar, 1500, args.trials, rng)
            res["cost"] = expected_fees(res, 50, 50, 150)
            row = {"account": acct, "mult": mult,
                   "b_over_sd": ar.mll_buffer / (series.std(ddof=1) * mult),
                   "pass_no_edge": null["pass"], "lift": res["pass"] - null["pass"], **res}
            acct_rows.append(row)
            print(f"  {acct:<8}{mult:>6.2f}{row['b_over_sd']:>7.1f}{res['pass']:>7.0%}"
                  f"{null['pass']:>7.0%}{row['lift']:>+7.0%}{res['breach']:>8.0%}"
                  f"{res['sessions_to_pass'] / SESSIONS_PER_MONTH:>6.1f}"
                  f"{res['cost']:>10,.0f}")
        print()

    obs_t = float(series.mean() / (series.std(ddof=1) / np.sqrt(len(series))))
    null_t = []
    for _ in range(2000):
        b = stationary_bootstrap(edge_free, len(series), rng)
        null_t.append(b.mean() / (b.std(ddof=1) / np.sqrt(len(b))))
    null_t = np.array(null_t)
    p = float((null_t >= obs_t).mean())
    print(f"  ROTATION NULL under {args.account_model}: observed t {obs_t:+.2f}, "
          f"null 95th {np.percentile(null_t, 95):+.2f}, one-sided p {p:.4f}")
    print()
    print("=" * 84)
    print("READ THIS BEFORE THE NUMBERS ABOVE:")
    print("  1. N=3 quotes on one evening. It rules out a badly wrong constant. It is not")
    print("     a spread estimate and it says nothing about 2024-26 spreads.")
    print("  2. NG's spread is the FULL-SIZE contract. The micro is wider. That column is")
    print("     a lower bound and NG's net under every model here is optimistic.")
    print("  3. The depth penalty assumes a uniform book, which is pessimistic for large")
    print("     orders. Truth sits between MEASURED and MEAS+DEPTH, nearer MEAS+DEPTH")
    print("     for the symbols showing 1-lot touches.")
    print("  4. The trade list is identical in all three columns. Nothing was re-fit.")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({
            "quotes": {k: {"contract": v["contract"], "note": v["note"],
                           "obs": v["obs"]} for k, v in QUOTES.items()},
            "spread_stats": stats,
            "models": {k: v["per_symbol"] for k, v in per_model.items()},
            "accounts": acct_rows, "rotation_p": p, "observed_t": obs_t,
        }, indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
