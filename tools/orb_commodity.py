#!/usr/bin/env python3
"""
Re-test the sibling project's commodity ORB basket with THIS project's gauntlet.

WHAT IS BEING CHECKED
---------------------
`adam005141/claude` reports a five-commodity opening-range-breakout basket at PF 1.47, 7%
blow rate on a $4,000 box, ~$12k captured. That is the strongest intraday result in either
project. It was produced by that project's engine and its own economics simulator.

This re-implements their entry logic faithfully from `es_bot/backtest/orb.py` and then runs
it through gates that engine does not have:

  1. drop-top-N fragility          is the edge a handful of trades?
  2. block-bootstrapped account    P(pass) and P(breach) on the REAL account geometries
     simulation                    the user has available, with fat tails and clustering
  3. rotation null                 could a random relabelling produce this?
  4. gap-through stops             their stop fills AT the stop price; this engine has
                                   always filled at the worse of stop and next open

WHERE THIS DELIBERATELY DIFFERS FROM THEIRS, AND WHY
-----------------------------------------------------
Their stop fills exactly at the stop level. A stop is a market order once touched, so on a
bar that gaps through it the real fill is worse. Every result in this project has used the
pessimistic convention and it is kept here, with their convention reported alongside so the
difference is visible rather than argued about.

Their slippage is one tick per side. This project's measured MES adverse model is one tick
of spread plus half a tick of slippage per side. The stricter one is the default here.

WHAT CANNOT BE FIXED
--------------------
The bars are pre-stitched, so the roll and near-expiry guards are off. There is no BID/ASK
for these instruments, so costs are ASSUMED. Neither is repairable from the data on hand,
and both bound what any result here can mean.

The contract specifications WERE verifiable and now are: checked against CME on 2026-08-07,
one error found and corrected (MNG was carried at 2.5x its real point value). See
`tools/import_stitched.py`.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.config import PropRules  # noqa: E402
from engine.data import build_continuous, resample  # noqa: E402
from engine.overnight import minutes_since_open  # noqa: E402
from tools.feasibility import (  # noqa: E402
    ACCOUNTS, SESSIONS_PER_MONTH, account_rules, expected_fees, simulate,
    stationary_bootstrap,
)
from tools.import_stitched import SPECS  # noqa: E402

BASKET = ("MGC", "SI", "HG", "MCL", "NG")
INDEX = ("MES", "MNQ", "M2K")


@dataclass
class OrbConfig:
    """Faithful to `es_bot/backtest/orb.py` ORBConfig, defaults included."""
    or_minutes: int = 60           # the commodity basket uses a 60-minute range
    bar_minutes: int = 30          # ... on 30-minute bars
    breakout_buffer_ticks: float = 1.0
    entry_cutoff_minutes: int = 180
    min_or_ticks: float = 2.0
    per_trade_risk_dollars: float = 250.0
    max_contracts: int = 20
    max_risk_mult: float = 2.0     # their post-forward-test guard; 0 disables
    slip_ticks_per_side: float = 1.5   # STRICTER than their 1.0; see the module docstring
    commission_round_turn: float = 1.20
    gap_through_stops: bool = True     # this project's convention; theirs is False


def run_orb(df: pd.DataFrame, spec: tuple[float, float, float],
            cfg: OrbConfig) -> pd.DataFrame:
    """
    One long-only trade per session: break the opening range, stop at its opposite side,
    ride to the close. Returns one row per trade.

    Exits are evaluated from the bar AFTER entry, matching their engine, so a single bar
    cannot both trigger and resolve a trade.
    """
    pv, tick, _ = spec
    buf = cfg.breakout_buffer_ticks * tick
    or_bars = max(1, cfg.or_minutes // cfg.bar_minutes)
    cutoff = max(or_bars + 1, cfg.entry_cutoff_minutes // cfg.bar_minutes)
    slip = cfg.slip_ticks_per_side * tick

    rows = []
    for sd, sess in df.groupby("session_date", sort=True):
        s = sess.reset_index(drop=True)
        if len(s) <= or_bars + 1:
            continue
        or_high = s["high"].iloc[:or_bars].max()
        or_low = s["low"].iloc[:or_bars].min()
        if (or_high - or_low) < cfg.min_or_ticks * tick:
            continue
        level = or_high + buf

        pos = None
        for i in range(or_bars, len(s)):
            b = s.iloc[i]
            last = i == len(s) - 1
            if pos is None and i <= cutoff:
                if b["high"] >= level:
                    entry = level if b["open"] <= level else b["open"]
                    stop_dist = entry - or_low
                    if stop_dist <= 0:
                        break
                    risk_ct = stop_dist * pv
                    if cfg.max_risk_mult > 0 and \
                            risk_ct > cfg.per_trade_risk_dollars * cfg.max_risk_mult:
                        break                       # wide-range day: their guard skips it
                    qty = min(max(1, int(cfg.per_trade_risk_dollars // risk_ct)),
                              cfg.max_contracts)
                    pos = {"entry": entry, "stop": or_low, "qty": qty, "i": i,
                           "risk": risk_ct * qty}
                    continue                        # exits start on the NEXT bar
            if pos is not None:
                px = reason = None
                if b["low"] <= pos["stop"]:
                    # A stop is a market order once touched. Filling AT the stop assumes a
                    # resting bid exactly there; on a bar that opens through it, the real
                    # fill is the open.
                    px = (min(pos["stop"], b["open"]) if cfg.gap_through_stops
                          else pos["stop"])
                    reason = "stop"
                elif last:
                    px, reason = b["close"], "eod"
                if px is not None:
                    gross = (px - pos["entry"]) * pv * pos["qty"]
                    cost = (2 * slip * pv + cfg.commission_round_turn) * pos["qty"]
                    rows.append({"session_date": sd, "qty": pos["qty"],
                                 "entry": pos["entry"], "exit": px, "reason": reason,
                                 "gross": gross, "cost": cost, "net": gross - cost,
                                 "risk": pos["risk"],
                                 "r": (gross - cost) / pos["risk"] if pos["risk"] else 0.0,
                                 "bars_held": i - pos["i"]})
                    pos = None
                    break                           # one trade per session
    return pd.DataFrame(rows)


def summarise(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"trades": 0}
    wins, losses = t[t["net"] > 0], t[t["net"] <= 0]
    gp, gl = wins["net"].sum(), -losses["net"].sum()
    return {
        "trades": len(t), "net": float(t["net"].sum()), "gross": float(t["gross"].sum()),
        "cost": float(t["cost"].sum()),
        "drag": float(t["cost"].sum() / abs(t["gross"].sum())) if t["gross"].sum() else 0.0,
        "pf": float(gp / gl) if gl > 0 else float("inf"),
        "wr": float(len(wins) / len(t)),
        "avg_win": float(wins["net"].mean()) if len(wins) else 0.0,
        "avg_loss": float(losses["net"].mean()) if len(losses) else 0.0,
    }


def drop_top_n(t: pd.DataFrame, n: int) -> dict:
    """Fragility. A high profit factor built on a handful of trades is not an edge."""
    if len(t) <= n:
        return {"trades": 0}
    return summarise(t.sort_values("net", ascending=False).iloc[n:])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data_commodity")
    ap.add_argument("--symbols", nargs="+", default=list(BASKET))
    ap.add_argument("--bar-minutes", type=int, default=30)
    ap.add_argument("--or-minutes", type=int, default=60)
    ap.add_argument("--risk", type=float, default=250.0)
    ap.add_argument("--no-guard", action="store_true", help="disable max_risk_mult")
    ap.add_argument("--their-stops", action="store_true",
                    help="fill stops AT the stop price, as their engine does")
    ap.add_argument("--trials", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    cfg = OrbConfig(or_minutes=args.or_minutes, bar_minutes=args.bar_minutes,
                    per_trade_risk_dollars=args.risk,
                    max_risk_mult=0.0 if args.no_guard else 2.0,
                    gap_through_stops=not args.their_stops)

    print("COMMODITY ORB, RE-TESTED")
    print("=" * 82)
    print(f"{args.or_minutes}-min opening range on {args.bar_minutes}-min bars, long only, "
          f"ride to close")
    print(f"stop = opposite side of the range | ${args.risk:.0f}/trade budget | "
          f"guard {'OFF' if args.no_guard else 'ON (2x)'}")
    print(f"stops fill at {'the stop price (THEIR convention)' if args.their_stops else 'the WORSE of stop and open (this project)'}"
          f" | slippage {cfg.slip_ticks_per_side} ticks/side")
    print("Costs ASSUMED and roll guard OFF: pre-stitched data. Specs verified 2026-08-07.")
    print()

    per_symbol, all_trades = {}, []
    print(f"  {'sym':<5}{'trades':>8}{'net $':>11}{'PF':>7}{'WR':>7}{'drag':>7}"
          f"{'avgW':>9}{'avgL':>9}")
    for sym in args.symbols:
        bars = resample(build_continuous(args.data, sym), args.bar_minutes)
        bars = bars.assign(mso=minutes_since_open(bars))
        t = run_orb(bars, SPECS[sym], cfg)
        if t.empty:
            print(f"  {sym:<5}{'no trades':>8}")
            continue
        s = summarise(t)
        per_symbol[sym] = s
        t = t.assign(symbol=sym)
        all_trades.append(t)
        print(f"  {sym:<5}{s['trades']:>8}{s['net']:>11,.0f}{s['pf']:>7.2f}"
              f"{s['wr']:>7.0%}{s['drag']:>7.0%}{s['avg_win']:>9,.0f}"
              f"{s['avg_loss']:>9,.0f}")

    if not all_trades:
        print("\nno trades at all")
        return 1
    T = pd.concat(all_trades, ignore_index=True)
    combined = summarise(T)
    print(f"  {'ALL':<5}{combined['trades']:>8}{combined['net']:>11,.0f}"
          f"{combined['pf']:>7.2f}{combined['wr']:>7.0%}{combined['drag']:>7.0%}"
          f"{combined['avg_win']:>9,.0f}{combined['avg_loss']:>9,.0f}")
    print()

    # ---- gate 1: fragility -------------------------------------------------
    print("  FRAGILITY. Their own graveyard killed `failed_breakout` on exactly this test:")
    print("  PF 1.32 collapsed to 0.97 after dropping five trades of 1,312.")
    print()
    print(f"  {'dropped':<12}{'trades':>8}{'net $':>11}{'PF':>7}")
    frag = {}
    for n in (0, 1, 5, 10, 20):
        d = drop_top_n(T, n) if n else combined
        frag[n] = d
        print(f"  {('none' if n == 0 else f'top {n}'):<12}{d['trades']:>8}"
              f"{d['net']:>11,.0f}{d['pf']:>7.2f}")
    print()

    # ---- gate 1b: out-of-sample split and by-year --------------------------
    #
    # Their own pre-registered bar required the second half to hold, and it is the gate
    # that killed `failed_breakout` (1st half PF 1.52, 2nd half 1.09) and exposed the
    # 30-minute RSI reversion as an eight-month mirage. Splitting on the trade MEDIAN
    # rather than by date keeps the two halves the same size.
    T = T.sort_values("session_date").reset_index(drop=True)
    mid = len(T) // 2
    first, second = summarise(T.iloc[:mid]), summarise(T.iloc[mid:])
    print("  OUT OF SAMPLE. Their pre-registered bar: the second half must hold.")
    print(f"  {'half':<12}{'trades':>8}{'net $':>11}{'PF':>7}{'WR':>7}")
    for name, d in (("1st", first), ("2nd", second)):
        print(f"  {name:<12}{d['trades']:>8}{d['net']:>11,.0f}{d['pf']:>7.2f}{d['wr']:>7.0%}")
    years = {}
    print()
    print(f"  {'year':<12}{'trades':>8}{'net $':>11}{'PF':>7}{'WR':>7}")
    T["_yr"] = pd.to_datetime(T["session_date"]).dt.year
    for yr, g in T.groupby("_yr"):
        d = summarise(g)
        years[int(yr)] = d
        print(f"  {yr:<12}{d['trades']:>8}{d['net']:>11,.0f}{d['pf']:>7.2f}{d['wr']:>7.0%}")
    print()

    # ---- gate 2: the account simulation on REAL geometries ------------------
    daily = T.groupby("session_date")["net"].sum().sort_index()
    print(f"  ACCOUNT SIMULATION on {len(daily)} trading sessions, "
          f"${daily.mean():.2f}/session, sd ${daily.std(ddof=1):.0f}")
    print("  Block bootstrap, mean block 10, so losing clusters survive.")
    print()
    print(f"  {'account':<8}{'buffer':>8}{'target':>8}{'mult':>6}{'B/sd':>7}"
          f"{'PASS':>7}{'luck':>7}{'LIFT':>7}{'BREACH':>8}{'mo':>6}{'E[fees]':>10}")
    rng = np.random.default_rng(args.seed)
    series = daily.to_numpy()
    edge_free = series - series.mean()
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
                   "pass_no_edge": null["pass"],
                   "lift": res["pass"] - null["pass"], **res}
            acct_rows.append(row)
            print(f"  {acct:<8}{ar.mll_buffer:>8,.0f}{ar.profit_target:>8,.0f}"
                  f"{mult:>6.2f}{row['b_over_sd']:>7.1f}{res['pass']:>7.0%}"
                  f"{null['pass']:>7.0%}{row['lift']:>+7.0%}{res['breach']:>8.0%}"
                  f"{res['sessions_to_pass'] / SESSIONS_PER_MONTH:>6.1f}"
                  f"{res['cost']:>10,.0f}")
        print()

    # ---- gate 3: rotation null on the session series -----------------------
    print("  ROTATION NULL. Could the session sequence produce this by chance?")
    obs = float(series.mean() / (series.std(ddof=1) / np.sqrt(len(series))))
    null_t = []
    for _ in range(2000):
        b = stationary_bootstrap(edge_free, len(series), rng)
        null_t.append(b.mean() / (b.std(ddof=1) / np.sqrt(len(b))))
    null_t = np.array(null_t)
    p = float((null_t >= obs).mean())
    print(f"    observed t {obs:+.2f} | null 95th pct {np.percentile(null_t, 95):+.2f} "
          f"| one-sided p {p:.4f}")
    print()

    print("=" * 82)
    print("HOW TO READ THIS:")
    print("  1. PF and net are the easy gates. FRAGILITY and BREACH are the ones that")
    print("     killed every previous candidate in both projects.")
    print("  2. `luck` re-runs each account with the mean removed. `LIFT` is what the")
    print("     strategy contributes over a same-volatility, same-tail coin flip.")
    print("  3. The sample is ~2 years and one regime. It cannot be crash-tested, and it")
    print("     spans a metals bull that the source project itself flags.")
    print("  4. Costs ASSUMED and roll guard OFF. Contract specs verified against CME")
    print("     2026-08-07; MNG was wrong by 2.5x and is corrected.")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(
            {"per_symbol": per_symbol, "combined": combined,
             "oos": {"first": first, "second": second},
             "by_year": {str(k): v for k, v in years.items()},
             "fragility": {str(k): v for k, v in frag.items()},
             "accounts": acct_rows, "null_p": p, "observed_t": obs},
            indent=2, default=str))
        print(f"\nwritten to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
