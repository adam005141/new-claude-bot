#!/usr/bin/env python3
"""
Is the spread saving from a resting limit order real, or is it adverse selection?

WHY THIS IS THE LAST LEVER WORTH MEASURING
------------------------------------------
The edge budget priced every way of improving the per-session Sharpe. Position size cannot
touch it, since size multiplies edge and noise identically. Variance reduction is worth
+25%. Cost is worth +79%, and it is the only lever that is pure execution: no new signal,
no new data.

The reason cost is so large is that the round trip is $4.95 against a gross overnight edge
of $11.25, or 44% of the edge. Leg D crossed the spread twice a day for a position it held
fifteen hours. A scheduled exposure has no signal urgency, so a resting limit is available
in a way it is not for a breakout.

WHY THE SAVING MIGHT BE ENTIRELY FICTIONAL
------------------------------------------
A resting buy limit fills preferentially when price is falling. It fills on the sessions
that go against you and misses the ones that gap away, so the filled subset is worse than
the unfilled one by construction. That is adverse selection, and for a passive order it is
typically of the same order as the spread it saves.

Assuming the saving without measuring the selection is exactly the error that produced a
100% pass rate in the feasibility sweep. So this tool measures both and reports the NET:

    net benefit = spread saved  -  (E[session return | filled] - E[session return])

If the second term matches the first, the lever is worth nothing and the edge budget
closes with no realistic path to an acceptable pass rate.

WHAT IS MEASURED
----------------
Using MES BID and ASK bars, per session, at the 18:00 ET Globex open:

    fill rate      does a buy limit resting `offset` ticks below the ask get filled
                   within `wait` minutes
    saving         fill price against the market price it replaces
    selection      the session's own outcome conditional on having been filled
    net            saving minus selection, which is the only number that matters
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.config import INSTRUMENTS  # noqa: E402
from engine.data import build_continuous, resample  # noqa: E402
from engine.overnight import minutes_since_open  # noqa: E402

OPEN_MSO = -930.0          # 18:00 ET, the Globex open
EXIT_MSO = 0.0             # 09:30 ET, the RTH open


def load_side(data_dir: str, symbol: str, what: str, minutes: int) -> pd.DataFrame:
    df = resample(build_continuous(data_dir, symbol, what=what), minutes)
    df["mso"] = minutes_since_open(df)
    return df


def measure(bid: pd.DataFrame, ask: pd.DataFrame, trades: pd.DataFrame,
            inst, offset_ticks: float, wait_minutes: float) -> pd.DataFrame:
    """
    One row per session: whether a resting buy limit filled, at what price, and what the
    session then did.

    The limit rests `offset_ticks` BELOW the prevailing ask at 18:00 ET. It fills when the
    ask trades down to it, which is the correct condition for a buy: somebody must be
    willing to sell at your price. Using the bid instead would assume you are filled merely
    because the market quoted your level, which no queue grants.
    """
    rows = []
    for sd, a in ask.groupby("session_date", sort=True):
        b = bid[bid["session_date"] == sd]
        t = trades[trades["session_date"] == sd]
        arm = a[(a["mso"] >= OPEN_MSO) & (a["mso"] < OPEN_MSO + wait_minutes)]
        exitb = t[(t["mso"] >= EXIT_MSO)]
        if arm.empty or exitb.empty or b.empty:
            continue

        market_price = float(arm["open"].iloc[0])          # what crossing costs now
        limit_price = market_price - offset_ticks * inst.tick_size
        # Filled if the ask ever trades down to the limit inside the window.
        filled = bool((arm["low"] <= limit_price).any())
        exit_price = float(exitb["close"].iloc[0])

        rows.append({
            "session_date": sd, "filled": filled,
            "market_price": market_price, "limit_price": limit_price,
            "exit_price": exit_price,
            "ret_from_market": exit_price - market_price,
            "ret_from_limit": exit_price - limit_price,
        })
    return pd.DataFrame(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--symbol", default="MES")
    ap.add_argument("--decision-minutes", type=int, default=1)
    ap.add_argument("--offsets", type=float, nargs="+", default=[0.0, 1.0, 2.0])
    ap.add_argument("--waits", type=float, nargs="+", default=[5, 15, 30, 60])
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    inst = INSTRUMENTS[args.symbol]
    try:
        bid = load_side(args.data, args.symbol, "BID", args.decision_minutes)
        ask = load_side(args.data, args.symbol, "ASK", args.decision_minutes)
        trades = load_side(args.data, args.symbol, "TRADES", args.decision_minutes)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        print("\nThis tool needs BID and ASK bars, which exist for MES and MNQ but not")
        print("for the Barchart ES proxy. Run it on the instrument you actually trade.")
        return 1

    print("LIMIT ENTRY: SAVING versus ADVERSE SELECTION")
    print("=" * 78)
    print(f"{args.symbol} | buy limit resting below the 18:00 ET ask | "
          f"tick ${inst.tick_value:.2f}")
    print()
    print("  A passive buy fills when price comes DOWN to it, so the filled sessions are")
    print("  worse than average by construction. `selection` is that penalty, measured")
    print("  as the filled sessions' own outcome against every session's. Only `net`")
    print("  matters, and it is what the edge budget should be credited.")
    print()
    print(f"  {'offset':>7}{'wait':>7}{'fills':>8}{'fill %':>8}"
          f"{'saving $':>10}{'selection $':>13}{'NET $':>9}")

    out = []
    for off in args.offsets:
        for wait in args.waits:
            m = measure(bid, ask, trades, inst, off, wait)
            if m.empty:
                continue
            n_fill = int(m["filled"].sum())
            if n_fill < 20:
                continue
            fill_rate = n_fill / len(m)
            # Saving is the price improvement actually obtained, in dollars.
            saving = off * inst.tick_value
            # Selection: what the filled sessions did, against what all sessions did,
            # both measured from the SAME market reference so the comparison is clean.
            sel = (m.loc[m["filled"], "ret_from_market"].mean()
                   - m["ret_from_market"].mean()) * inst.point_value
            net = saving + sel
            out.append({"offset_ticks": off, "wait_minutes": wait, "fills": n_fill,
                        "sessions": len(m), "fill_rate": fill_rate,
                        "saving_usd": saving, "selection_usd": sel, "net_usd": net})
            print(f"  {off:>7.1f}{wait:>7.0f}{n_fill:>8}{fill_rate:>8.0%}"
                  f"{saving:>10.2f}{sel:>13.2f}{net:>9.2f}")

    print()
    if out:
        best = max(out, key=lambda r: r["net_usd"])
        print(f"  BEST NET: ${best['net_usd']:.2f} per filled session at "
              f"{best['offset_ticks']:.0f} ticks / {best['wait_minutes']:.0f} min, "
              f"filling {best['fill_rate']:.0%} of sessions.")
        print()
        print("  Compare against the round trip it is trying to reduce: "
              f"${4.95:.2f}.")
        print("  And note the fill rate is a second cost: an unfilled session either")
        print("  trades at the market anyway, forfeiting the saving, or is skipped,")
        print("  forfeiting the edge. Neither is free, and the table above prices")
        print("  neither. Treat `net` as an UPPER BOUND on the improvement.")
    print()
    print("=" * 78)
    print("HOW TO READ THIS:")
    print("  1. A net near zero means the spread saving is adverse selection wearing a")
    print("     different name, and the cost lever in the edge budget is fictional.")
    print("  2. A net near the full offset means passive entry genuinely works here,")
    print("     which would be unusual and deserves suspicion before celebration.")
    print("  3. Measured on the instrument's own BID/ASK, not on the ES proxy, so this")
    print("     is a smaller and more recent sample than the strategy results.")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(out, indent=2, default=str))
        print(f"\nwritten to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
