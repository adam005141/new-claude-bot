#!/usr/bin/env python3
"""
Trade-by-trade ledgers for the ES volume-conditioned cells, with a paired delay column.

Same treatment as `tools/trade_log.py` gave SI/ASIA/q4. Emits one row per trade with the
signal bar, its relative volume (so the tercile assignment is auditable), entry and exit
timestamps and prices, points, gross, net and a running balance.

Each ledger must reproduce the mean reported in run 38 exactly. That is the test of whether
the ledger is faithful, and it is asserted rather than eyeballed.

The `delayed_gross` column is a DIAGNOSTIC: it is what the SAME signal would have returned
under one-bar-delayed execution. It will not exactly equal the separately reported delayed
figure, because that run re-stepped through the series with its own non-overlap spacing and
therefore selected a different set of signals. Both are correct; they answer slightly
different questions.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.flow_structure import prepare  # noqa: E402

POINT, COST_RT = 5.0, 3.70
CELLS = (("THIN", 1), ("THIN", 2), ("HEAVY", 1), ("HEAVY", 2))
# means reported in run 38, per docs/RESULTS_VOLUME_CONDITIONED_2026-08-12.md
REPORTED = {("THIN", 1): 0.256, ("THIN", 2): 0.211,
            ("HEAVY", 1): 0.120, ("HEAVY", 2): 0.143}


def build(c: pd.DataFrame, q: int, lo: float, hi: float) -> pd.DataFrame:
    """Replicates tools/volume_conditioned.fade stepping exactly, but records each trade."""
    rows = []
    for _, g in c.groupby("blk", sort=False):
        if len(g) < 6:
            continue
        px = g["close"].to_numpy(float)
        rv = g["relvol"].to_numpy(float)
        ts = g["timestamp_utc"].to_numpy()
        sd = g["session_date"].to_numpy()
        cm = g["contract_month"].to_numpy()
        t = q
        while t + q < len(px):
            v = rv[t]
            if np.isfinite(v) and lo <= v < hi:
                prior = px[t] - px[t - q]
                if prior != 0.0:
                    d = -1 if prior > 0 else 1
                    pts = d * (px[t + q] - px[t])
                    dly = (d * (px[t + 1 + q] - px[t + 1])
                           if t + 1 + q < len(px) else np.nan)
                    rows.append({
                        "session_date": sd[t], "contract": str(cm[t]),
                        "dir": "SHORT" if d < 0 else "LONG",
                        "signal_from_utc": pd.Timestamp(ts[t - q]),
                        "entry_utc": pd.Timestamp(ts[t]),
                        "exit_utc": pd.Timestamp(ts[t + q]),
                        "signal_relvol": round(float(v), 3),
                        "prior_move_pts": round(float(prior), 4),
                        "entry_px": float(px[t]), "exit_px": float(px[t + q]),
                        "points": round(float(pts), 4),
                        "gross_usd": round(float(pts) * POINT, 2),
                        "net_usd": round(float(pts) * POINT - COST_RT, 2),
                        "delayed_gross_usd": (round(float(dly) * POINT, 2)
                                              if dly == dly else np.nan),
                    })
                    t += 2 * q
                    continue
            t += 1
    t_ = pd.DataFrame(rows).sort_values("entry_utc").reset_index(drop=True)
    t_["cum_gross"] = t_["gross_usd"].cumsum().round(2)
    t_["cum_net"] = t_["net_usd"].cumsum().round(2)
    return t_


def path_stats(x: np.ndarray) -> dict:
    eq = np.cumsum(x)
    dd = eq - np.maximum.accumulate(eq)
    streak = worst = 0
    for v in x:
        streak = streak + 1 if v < 0 else 0
        worst = max(worst, streak)
    return {"total": eq[-1], "max_dd": dd.min(), "streak": worst,
            "worst": x.min(), "best": x.max(), "wr": float((x > 0).mean())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--outdir", type=Path, default=Path("export"))
    args = ap.parse_args(argv)

    c = prepare("ES", "data_5min", "5min", args.start, args.end)
    valid = c["relvol"].notna() & c["ret"].notna()
    lo_q, hi_q = c.loc[valid, "relvol"].quantile([1 / 3, 2 / 3]).to_numpy()
    bands = {"THIN": (0.0, lo_q), "HEAVY": (hi_q, np.inf)}

    print("TRADE LEDGERS: ES 5-min volume-conditioned cells, MES at $5/pt")
    print("=" * 100)
    print(f"Tercile cuts {lo_q:.2f} / {hi_q:.2f}. Round turn ${COST_RT:.2f}.")
    print(f"\n  {'cell':<10}{'trades':>9}{'mean $':>9}{'reported':>10}{'match':>8}"
          f"{'gross tot':>12}{'net tot':>12}{'maxDD gr':>11}{'WR':>7}{'streak':>8}"
          f"{'paired delay $':>16}")

    args.outdir.mkdir(parents=True, exist_ok=True)
    for band, q in CELLS:
        t = build(c, q, *bands[band])
        name = f"ES_{band}_q{q}"
        t.to_csv(args.outdir / f"{name}_trades.csv", index=False)
        mean = t["gross_usd"].mean()
        rep = REPORTED[(band, q)]
        ok = abs(mean - rep) < 0.006
        g = path_stats(t["gross_usd"].to_numpy())
        n = path_stats(t["net_usd"].to_numpy())
        dly = t["delayed_gross_usd"].mean()
        print(f"  {band + '/q' + str(q):<10}{len(t):>9,}{mean:>9.3f}{rep:>10.3f}"
              f"{('OK' if ok else '** NO **'):>8}{g['total']:>12,.0f}{n['total']:>12,.0f}"
              f"{g['max_dd']:>11,.0f}{g['wr']:>7.1%}{n['streak']:>8}{dly:>16.3f}")
        if not ok:
            print(f"      LEDGER DOES NOT REPRODUCE THE REPORTED MEAN "
                  f"({mean:.4f} vs {rep:.4f}) -- do not trust this ledger")

    print(f"\n  exact tercile cuts: lo={lo_q!r} hi={hi_q!r}")
    print("  (audit against these, NOT the 2-decimal display values: an audit that used")
    print("   1.34 instead of 1.337926 falsely flagged 222 HEAVY trades as out of band)")
    print(f"\n  ledgers -> {args.outdir}/ES_<band>_q<n>_trades.csv")
    print("\n  'paired delay $' is the same signals executed one bar late. It is a")
    print("  diagnostic and will not equal run 38's delayed figure, which re-stepped")
    print("  the series and so selected a different set of signals.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
