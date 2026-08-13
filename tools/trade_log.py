#!/usr/bin/env python3
"""
Emit a trade-by-trade ledger and equity curve for SI/ASIA/q4, the best structure found.

Everything in this project has been reported as per-trade means and t-statistics. The P&L
was always computed from real entry and exit prices on real bars, but no trade log or equity
curve was ever produced, so nobody could inspect an individual trade. Given the bug rate in
this project, that is a real verification gap and this closes it.

One row per trade: dates, timestamps, contract, direction, entry price, exit price, points,
gross dollars, net dollars, and a running balance. Plus path statistics that a mean cannot
show: maximum drawdown, longest losing streak, and worst single trade.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.data import build_continuous  # noqa: E402
from engine.overnight import minutes_since_open  # noqa: E402

POINT, TICK = 1000.0, 0.005
COST_RT = 31.20
ASIA = (-930, -390)
Q = 4


def build(c: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (sd, cm), g in c.groupby(["session_date", "contract_month"], sort=True):
        g = g.sort_values("mso")
        g = g[(g["mso"] >= ASIA[0]) & (g["mso"] < ASIA[1])].reset_index(drop=True)
        if len(g) < Q * 2 + 2:
            continue
        m = g["mso"].to_numpy()
        step = int(np.median(np.diff(m))) if len(m) > 1 else 30
        cuts = np.flatnonzero(np.diff(m) != step) + 1
        for part in np.split(np.arange(len(g)), cuts):
            if len(part) < Q * 2 + 2:
                continue
            sub = g.iloc[part].reset_index(drop=True)
            cl = sub["close"].to_numpy(float)
            ts = sub["timestamp_utc"].to_numpy()
            t = Q
            while t + Q < len(cl):
                prior = cl[t] - cl[t - Q]
                if prior == 0.0:
                    t += 1
                    continue
                d = -1 if prior > 0 else 1
                pts = d * (cl[t + Q] - cl[t])
                rows.append({
                    "session_date": sd, "contract": cm, "dir": "SHORT" if d < 0 else "LONG",
                    "signal_from_utc": pd.Timestamp(ts[t - Q]),
                    "entry_utc": pd.Timestamp(ts[t]), "exit_utc": pd.Timestamp(ts[t + Q]),
                    "prior_move_pts": round(float(prior), 4),
                    "entry_px": float(cl[t]), "exit_px": float(cl[t + Q]),
                    "points": round(float(pts), 4),
                    "gross_usd": round(float(pts) * POINT, 2),
                    "net_usd": round(float(pts) * POINT - COST_RT, 2),
                })
                t += 2 * Q
    t = pd.DataFrame(rows).sort_values("entry_utc").reset_index(drop=True)
    t["cum_gross"] = t["gross_usd"].cumsum().round(2)
    t["cum_net"] = t["net_usd"].cumsum().round(2)
    return t


def path_stats(x: np.ndarray) -> dict:
    eq = np.cumsum(x)
    dd = eq - np.maximum.accumulate(eq)
    streak = worst = 0
    for v in x:
        streak = streak + 1 if v < 0 else 0
        worst = max(worst, streak)
    return {"total": eq[-1], "max_drawdown": dd.min(),
            "longest_losing_streak": worst,
            "worst_trade": x.min(), "best_trade": x.max(),
            "win_rate": float((x > 0).mean())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--out", type=Path, default=Path("export/SI_ASIA_q4_trades.csv"))
    args = ap.parse_args(argv)

    c = build_continuous("data_history", "SI", bar_size="30min")
    c = c[~c["thin_session"]].copy()
    c["mso"] = minutes_since_open(c)
    sd = c["session_date"].astype(str)
    c = c[(sd >= args.start) & (sd <= args.end)]

    t = build(c)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    t.to_csv(args.out, index=False)

    print("TRADE LEDGER: SI / ASIA / q=4, micro silver, taking execution")
    print("=" * 92)
    print(f"{len(t):,} trades, {t.session_date.nunique():,} sessions, "
          f"{t.session_date.min()} -> {t.session_date.max()}")
    print(f"mean gross ${t.gross_usd.mean():.2f}   mean net ${t.net_usd.mean():.2f}   "
          f"round turn ${COST_RT:.2f}")

    print("\nFIRST 5 TRADES")
    cols = ["session_date", "dir", "entry_utc", "entry_px", "exit_utc", "exit_px",
            "points", "gross_usd", "net_usd"]
    print(t[cols].head(5).to_string(index=False))
    print("\nLAST 5 TRADES")
    print(t[cols].tail(5).to_string(index=False))

    print("\n  PATH STATISTICS a mean cannot show")
    print(f"  {'':<24}{'GROSS':>14}{'NET of $31.20':>16}")
    g = path_stats(t.gross_usd.to_numpy())
    n = path_stats(t.net_usd.to_numpy())
    for k in ("total", "max_drawdown", "worst_trade", "best_trade"):
        print(f"  {k:<24}{g[k]:>14,.0f}{n[k]:>16,.0f}")
    print(f"  {'longest losing streak':<24}{g['longest_losing_streak']:>14,}"
          f"{n['longest_losing_streak']:>16,}")
    print(f"  {'win rate':<24}{g['win_rate']:>13.1%}{n['win_rate']:>16.1%}")

    print("\n  BY YEAR")
    y = t.assign(yr=t.session_date.astype(str).str[:4]).groupby("yr").agg(
        trades=("net_usd", "size"), gross=("gross_usd", "sum"), net=("net_usd", "sum"))
    print(y.to_string(float_format=lambda v: f"{v:,.0f}"))

    print(f"\n  ledger -> {args.out}  ({len(t):,} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
