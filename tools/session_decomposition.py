#!/usr/bin/env python3
"""
Where in the session do the returns actually happen?

WHY THIS EXISTS
---------------
The barrier screen measured intraday drift at between -0.0061R and +0.0006R across every
geometry, over 387 development sessions in which the index rose roughly a third. Zero
intraday drift and a large index gain cannot both be true unless the gain happened outside
RTH. Every result in this project up to 2026-08-06 was produced with RTH-only bars, so the
window that would carry it had never been looked at.

The firm rule turned out to permit it: positions may be held overnight and must be flat
only for the CME daily halt, 17:00-18:00 ET. That halt lands exactly on the 18:00 session
roll, so a trade can run from the Globex open through to the following afternoon without
ever crossing a session boundary.

WHAT IS MEASURED
----------------
Each session date is split into windows that a compliant trade could actually hold, and
each is reported as a standalone buy-and-hold:

    GLOBEX_TO_OPEN   18:00 ET  ->  09:30 ET     the overnight, ~15.5h
    RTH              09:30 ET  ->  16:00 ET     the cash session, 6.5h
    POST_CLOSE       16:00 ET  ->  16:50 ET     the futures hour before the halt
    FULL_SESSION     18:00 ET  ->  16:50 ET     everything, flat before the break

Every window sits inside one session date, so all four respect the flat rule with no
position ever held through the halt.

WHAT THIS IS AND IS NOT
-----------------------
An overnight long is not alpha. It is the equity risk premium plus whatever the
overnight-versus-intraday literature describes, harvested with a timing rule. That
distinction matters for what to expect out of sample: a risk premium is compensation for
bearing risk, so it should persist, and it should also hurt exactly when risk shows up.

Which is why the gap-risk section is not optional. An overnight position cannot be stopped
out while the market is halted or gapping, so the relevant question for a $2,000 MLL is
not the average but the worst move in the sample, and how close it comes to ending the
account in one night.
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
from engine.overnight import minutes_since_open  # noqa: E402

# Window boundaries in minutes from the 09:30 ET open. Negative is before it.
WINDOWS = {
    "GLOBEX_TO_OPEN": (-930, 0),      # 18:00 ET -> 09:30 ET
    "RTH":            (0, 390),       # 09:30 ET -> 16:00 ET
    "POST_CLOSE":     (390, 440),     # 16:00 ET -> 16:50 ET
    "FULL_SESSION":   (-930, 440),    # 18:00 ET -> 16:50 ET, flat before the halt
}


def window_returns(df: pd.DataFrame, mso: pd.Series,
                   lo: float, hi: float) -> pd.Series:
    """
    Point change from the first bar at or after `lo` to the last bar before `hi`,
    per session. Entry and exit are both real bars, so nothing is assumed to fill at a
    price that never traded.
    """
    inside = (mso >= lo) & (mso < hi)
    frame = pd.DataFrame({"sd": df["session_date"].values,
                          "close": df["close"].where(inside).values,
                          "open": df["open"].where(inside).values})
    g = frame.groupby("sd", sort=True)
    entry = g["open"].first()
    exit_ = g["close"].last()
    return (exit_ - entry).dropna()


def window_excursion(df: pd.DataFrame, mso: pd.Series,
                     lo: float, hi: float) -> pd.DataFrame:
    """
    Per session: the window's final return AND its maximum adverse excursion for a long,
    both in index points, measured from the entry bar's open.

    The MAE is what makes a stop modellable. Without it a stop can only be applied to the
    session's FINAL return, which silently keeps every session that traded through the stop
    level and recovered. That is look-ahead, and on this data it was worth about $40 a
    session against a real edge of $8.68.
    """
    inside = (mso >= lo) & (mso < hi)
    frame = pd.DataFrame({"sd": df["session_date"].values,
                          "open": df["open"].where(inside).values,
                          "low": df["low"].where(inside).values,
                          "close": df["close"].where(inside).values})
    g = frame.groupby("sd", sort=True)
    entry = g["open"].first()
    out = pd.DataFrame({
        "final": g["close"].last() - entry,
        "mae": g["low"].min() - entry,          # <= 0 by construction
    }).dropna()
    return out


def describe(name: str, r: pd.Series, point_value: float, rt_points: float) -> dict:
    n = len(r)
    mean = float(r.mean())
    sd = float(r.std(ddof=1))
    # One round trip per session held. Sharpe uses the NET series, since a gross Sharpe
    # on a strategy that trades daily is not a number anyone can act on.
    net = r - rt_points
    ann = np.sqrt(252)
    return {
        "window": name, "sessions": n,
        "mean_points": mean, "sd_points": sd,
        "total_points": float(r.sum()),
        "mean_usd": mean * point_value,
        "net_mean_usd": float(net.mean()) * point_value,
        "net_total_usd": float(net.sum()) * point_value,
        "hit_rate": float((r > 0).mean()),
        "sharpe_net": float(net.mean() / net.std(ddof=1) * ann) if net.std(ddof=1) else 0.0,
        # Both are reported because they differ a lot and only one is decision-relevant.
        # Cost is a constant per session, so it shifts the mean without touching the sd:
        # the gross t can clear 2 while the net t, which is what an account actually
        # earns, sits near 1. Reporting gross alone overstates the case.
        "t_gross": float(mean / (sd / np.sqrt(n))) if sd > 0 and n > 1 else 0.0,
        "t_net": float(net.mean() / (sd / np.sqrt(n))) if sd > 0 and n > 1 else 0.0,
        "worst_points": float(r.min()), "best_points": float(r.max()),
        "p01_points": float(r.quantile(0.01)), "p05_points": float(r.quantile(0.05)),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data")
    ap.add_argument("--symbols", nargs="+", default=["MES"])
    ap.add_argument("--price-source")
    ap.add_argument("--measured-costs", type=Path)
    ap.add_argument("--cost-scenario", choices=sorted(COST_SCENARIOS), default="adverse")
    ap.add_argument("--cost-session",
                    help="Charge one session's MEASURED spread instead of the all-day "
                         "figure. This matters more here than anywhere else in the "
                         "project: the overnight window is ENTERED at 18:00 ET, the "
                         "thinnest moment of the day, and the all-day number is dominated "
                         "by RTH. Try ASIA.")
    ap.add_argument("--decision-minutes", type=int, default=5)
    ap.add_argument("--dev-fraction", type=float, default=0.50)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    print("SESSION DECOMPOSITION")
    print("=" * 78)
    print("Buy and hold each window, one contract, development split only.")
    print("Every window is flat before the 17:00 ET halt and never crosses a session.")
    print()

    summary = {}
    for symbol in args.symbols:
        inst = INSTRUMENTS[symbol]
        costs = (measured_cost_models(args.measured_costs, symbol,
                                      session=args.cost_session)[args.cost_scenario]
                 if args.measured_costs else COST_SCENARIOS[args.cost_scenario])
        rt_points = costs.round_trip_points(inst)

        data_symbol = args.price_source or symbol
        bars = resample(build_continuous(args.data, data_symbol), args.decision_minutes)
        sessions = sorted(bars["session_date"].unique())
        keep = set(sessions[:int(len(sessions) * args.dev_fraction)])
        bars = bars[bars["session_date"].isin(keep)].reset_index(drop=True)
        mso = minutes_since_open(bars)

        print(f"--- {symbol}" + (f" (bars from {data_symbol})" if args.price_source else "")
              + " ---")
        print(f"  {len(bars):,} bars over {len(keep)} development sessions")
        print(f"  round trip {rt_points:.3f} points = ${costs.round_trip_usd(inst):.2f}, "
              f"point value ${inst.point_value:.2f}")
        print()

        rows = []
        for name, (lo, hi) in WINDOWS.items():
            r = window_returns(bars, mso, lo, hi)
            if r.empty:
                continue
            rows.append(describe(name, r, inst.point_value, rt_points))

        print(f"  {'window':<16}{'n':>6}{'mean pts':>10}{'net $/sess':>12}"
              f"{'net total $':>13}{'hit':>7}{'t gross':>9}{'t NET':>8}{'Sharpe':>8}")
        for d in rows:
            print(f"  {d['window']:<16}{d['sessions']:>6}{d['mean_points']:>10.3f}"
                  f"{d['net_mean_usd']:>12.2f}{d['net_total_usd']:>13,.0f}"
                  f"{d['hit_rate']:>7.1%}{d['t_gross']:>9.2f}{d['t_net']:>8.2f}"
                  f"{d['sharpe_net']:>8.2f}")
        print()
        print("  `net` charges one round trip per session held.")
        print("  READ t NET, NOT t GROSS. Cost is a constant per session, so it moves the")
        print("  mean without touching the standard deviation: the gross t can clear 2")
        print("  while the net t, which is what an account actually earns, sits near 1.")
        print("  Neither is corrected for the four windows tested.")
        print()

        # ---- gap risk, which is the part that decides whether this is survivable ----
        print("  GAP RISK. An overnight position cannot be stopped during the halt or")
        print("  through a gap, so the account is exposed to the whole move, not to a")
        print("  stop distance. Sized at ONE contract against the $2,000 MLL buffer:")
        print()
        prop = PropRules()
        print(f"  {'window':<16}{'worst pt':>10}{'worst $':>10}{'p01 $':>9}{'p05 $':>9}"
              f"{'% of MLL':>10}")
        for d in rows:
            worst_usd = d["worst_points"] * inst.point_value
            print(f"  {d['window']:<16}{d['worst_points']:>10.2f}{worst_usd:>10.0f}"
                  f"{d['p01_points'] * inst.point_value:>9.0f}"
                  f"{d['p05_points'] * inst.point_value:>9.0f}"
                  f"{abs(worst_usd) / prop.mll_buffer:>9.0%}")
        print()

        summary[symbol] = {"round_trip_points": rt_points, "sessions": len(keep),
                           "windows": rows}

    print("=" * 78)
    print("HOW TO READ THIS:")
    print("  1. An overnight long is NOT alpha. It is the equity risk premium plus the")
    print("     overnight/intraday effect, harvested with a timing rule. Expect it to")
    print("     persist AND to hurt precisely when risk arrives.")
    print("  2. The development split is a bull market. A positive overnight number here")
    print("     is exactly what that sample produces. It is a reason to test out of")
    print("     sample, not a reason to believe it.")
    print("  3. Gap risk is the binding constraint, not expectancy. One night at the")
    print("     wrong size ends the account, and no stop can prevent it.")
    print("  4. Development split only. Validation and lockbox remain untouched.")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, indent=2, default=str))
        print(f"\nwritten to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
