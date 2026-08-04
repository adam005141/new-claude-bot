#!/usr/bin/env python3
"""
Derive a MEASURED cost model from downloaded BID/ASK bars.

Until now every cost number in this project has been a prior. The development run showed
the entire MES result living inside one tick of that prior, so the assumption was doing
more work than the strategy. This replaces it with measurement.

Method
------
IBKR serves BID and ASK as separate bar series. Joining them on timestamp gives a
per-minute quoted spread:

    spread_points = ask_close - bid_close
    spread_ticks  = spread_points / tick_size

The three cost scenarios stop being guesses and become percentiles of the observed
distribution:

    base     median spread   typical conditions
    adverse  75th percentile the worse half of minutes
    severe   95th percentile stressed conditions

Spread is reported PER SESSION WINDOW, because it is not constant through the day. If
the opening hour is systematically wider than midday, a strategy that only fires at the
open pays the opening spread, not the daily average. Using a blended number would
understate the cost of exactly the trades being taken.

Limitations, stated plainly
---------------------------
* This measures the QUOTED spread, not the realised one. Queue position, partial fills,
  and the tendency for quotes to widen in the instant an order arrives are invisible in
  bar data. The true cost of a market order is at least this, and usually worse.
* Bar close-to-close sampling misses intra-minute widening.
* No depth. A resting order's fill probability cannot be estimated from this.

So the measured numbers remain a LOWER BOUND on execution cost. They are a large
improvement on a guess, not a substitute for order-book data.

Usage
-----
    python tools/measure_costs.py --data data --out config/measured_costs.json
    python tools/measure_costs.py --data data --by-session
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.config import INSTRUMENTS                      # noqa: E402
from engine.data import discover, load_contract            # noqa: E402
from engine.sessions import classify_index                 # noqa: E402

log = logging.getLogger("measure_costs")

# A quoted spread beyond this is a stale or crossed quote, not a tradable market.
# Keeping them would let a handful of bad prints dominate the upper percentiles.
MAX_PLAUSIBLE_SPREAD_TICKS = 40.0


def load_quotes(data_dir: str | Path, symbol: str,
                bar_size: str = "1min") -> pd.DataFrame:
    """Join BID and ASK series into a per-bar spread series."""
    bids = {c.contract_month: c for c in discover(data_dir, symbol, bar_size, "BID")}
    asks = {c.contract_month: c for c in discover(data_dir, symbol, bar_size, "ASK")}
    shared = sorted(set(bids) & set(asks))
    if not shared:
        raise FileNotFoundError(
            f"no matching BID/ASK pairs for {symbol} under {data_dir}. "
            f'Run: python tools/ibkr_download.py --symbols {symbol} --what BID ASK'
        )

    inst = INSTRUMENTS[symbol]
    frames = []
    for contract in shared:
        bid = load_contract(bids[contract])[["timestamp_utc", "close"]].rename(
            columns={"close": "bid"})
        ask = load_contract(asks[contract])[["timestamp_utc", "close"]].rename(
            columns={"close": "ask"})
        merged = bid.merge(ask, on="timestamp_utc", how="inner")
        merged["contract_month"] = contract
        frames.append(merged)

    df = (pd.concat(frames, ignore_index=True)
          .drop_duplicates(subset=["timestamp_utc", "contract_month"], keep="last")
          .sort_values("timestamp_utc")
          .reset_index(drop=True))

    df["spread_points"] = df["ask"] - df["bid"]
    df["spread_ticks"] = df["spread_points"] / inst.tick_size

    n_raw = len(df)
    # Crossed or zero quotes are not tradable markets; absurd ones are stale prints.
    df = df[(df["spread_ticks"] > 0) & (df["spread_ticks"] <= MAX_PLAUSIBLE_SPREAD_TICKS)]
    dropped = n_raw - len(df)
    if dropped:
        log.info("%s: dropped %d of %d bars (%.2f%%) as crossed, zero, or stale quotes",
                 symbol, dropped, n_raw, 100 * dropped / n_raw)

    df["session"] = classify_index(pd.DatetimeIndex(df["timestamp_utc"])).values
    return df


def summarise(df: pd.DataFrame, label: str) -> dict:
    t = df["spread_ticks"]
    return {
        "label": label,
        "n_bars": int(len(t)),
        "median_ticks": round(float(t.median()), 4),
        "mean_ticks": round(float(t.mean()), 4),
        "p75_ticks": round(float(t.quantile(0.75)), 4),
        "p95_ticks": round(float(t.quantile(0.95)), 4),
        "p99_ticks": round(float(t.quantile(0.99)), 4),
        "max_ticks": round(float(t.max()), 4),
        "pct_at_one_tick": round(float((t <= 1.0).mean()), 4),
    }


def measure(data_dir: str | Path, symbols: list[str],
            by_session: bool = False) -> dict:
    out: dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "method": "quoted spread from IBKR BID/ASK 1-minute bars, close-to-close",
        "caveat": ("Quoted spread is a LOWER BOUND on execution cost. Queue position, "
                   "partial fills, and widening on order arrival are not observable in "
                   "bar data."),
        "scenario_mapping": {"base": "median", "adverse": "p75", "severe": "p95"},
        "instruments": {},
    }

    for symbol in symbols:
        df = load_quotes(data_dir, symbol)
        inst = INSTRUMENTS[symbol]
        entry: dict = {
            "tick_size": inst.tick_size,
            "tick_value_usd": inst.tick_value,
            "point_value_usd": inst.point_value,
            "overall": summarise(df, "ALL"),
        }
        if by_session:
            per = {}
            for session, grp in df.groupby("session", sort=False):
                if len(grp) < 500:          # too thin to characterise
                    continue
                per[str(session)] = summarise(grp, str(session))
            entry["by_session"] = per
        out["instruments"][symbol] = entry

    return out


def print_report(measured: dict) -> None:
    for symbol, entry in measured["instruments"].items():
        o = entry["overall"]
        tv = entry["tick_value_usd"]
        print(f"\n=== {symbol} quoted spread (ticks) ===")
        print(f"  bars measured        {o['n_bars']:>12,}")
        print(f"  median               {o['median_ticks']:>12.3f}"
              f"   round trip ${2*o['median_ticks']*tv:>7.2f}/contract")
        print(f"  mean                 {o['mean_ticks']:>12.3f}")
        print(f"  75th percentile      {o['p75_ticks']:>12.3f}"
              f"   round trip ${2*o['p75_ticks']*tv:>7.2f}/contract")
        print(f"  95th percentile      {o['p95_ticks']:>12.3f}"
              f"   round trip ${2*o['p95_ticks']*tv:>7.2f}/contract")
        print(f"  99th percentile      {o['p99_ticks']:>12.3f}")
        print(f"  share at 1 tick      {o['pct_at_one_tick']:>12.1%}")

        if "by_session" in entry:
            print(f"\n  by session window:")
            print(f"    {'session':<18}{'bars':>10}{'median':>9}{'p75':>8}{'p95':>8}")
            rows = sorted(entry["by_session"].items(),
                          key=lambda kv: -kv[1]["median_ticks"])
            for name, s in rows:
                print(f"    {name:<18}{s['n_bars']:>10,}{s['median_ticks']:>9.3f}"
                      f"{s['p75_ticks']:>8.3f}{s['p95_ticks']:>8.3f}")

            def _find(name: str):
                # str() of a (str, Enum) member differs across Python versions:
                # "RTH_OPEN" on 3.11+, "Session.RTH_OPEN" before. Accept either.
                for key in (name, f"Session.{name}"):
                    if key in entry["by_session"]:
                        return entry["by_session"][key]
                return None

            opens, mid = _find("RTH_OPEN"), _find("RTH_MIDDAY")
            if opens and mid and mid["median_ticks"] > 0:
                ratio = opens["median_ticks"] / mid["median_ticks"]
                print(f"\n    opening hour is {ratio:.2f}x the midday median spread.")
                if ratio > 1.15:
                    print("    A strategy that fires at the open pays the OPENING spread,")
                    print("    not the daily average. Using a blended figure understates it.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--symbols", nargs="+", default=["MES", "MNQ"])
    ap.add_argument("--by-session", action="store_true", default=True)
    ap.add_argument("--out", type=Path, default=Path("config/measured_costs.json"))
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)-7s %(message)s")

    try:
        measured = measure(args.data, args.symbols, args.by_session)
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 1

    print_report(measured)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(measured, indent=2))
    print(f"\nwritten to {args.out}")
    print("\nUse it:  python run_backtest.py --data data --split dev "
          f"--measured-costs {args.out}")
    print("\nNOTE: quoted spread is a LOWER BOUND on real execution cost.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
