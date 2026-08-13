#!/usr/bin/env python3
"""
Passive execution on SI/ASIA/q4: can a better fill close a 4.3x cost gap?

Implements `docs/PREREGISTRATION_2026-08-12_PASSIVE_EXECUTION.md` exactly. Committed before
this file was run. Nothing here may be changed after seeing a result.

The signal is unchanged from run 34 and is not re-tuned: fade the preceding 4-bar (2-hour)
move in Asian-session silver, hold 4 bars, non-overlapping, both directions.

Only execution varies. A limit rests at close(signal) + m ticks in the favourable direction
and fills only if the next bar trades STRICTLY THROUGH it. Every unfilled signal is recorded
with zero and its TAKE counterfactual computed; statistics run over all signals.

Thirty-minute OHLC cannot model queue position. This simulation is therefore optimistic in
the direction of passing, which is why a failure here is strong evidence and a pass is only
a hypothesis for tick data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.data import build_continuous  # noqa: E402
from engine.overnight import minutes_since_open  # noqa: E402
from tools.feasibility import stationary_bootstrap  # noqa: E402

POINT, TICK = 1000.0, 0.005          # micro silver: $1,000 per point, 0.005 tick = $5.00
SPREAD_TICKS = 3                     # measured
COMMISSION_RT = 1.20                 # carried from the MES model, NOT measured for SIL
COMMISSION_RT_HIGH = 2.50            # reported alongside
ASIA = (-930, -390)
Q = 4
MS = (0, 1, 3)
BOOT_MIN_N = 700

TICK_USD = TICK * POINT              # $5.00
COSTS = {"TAKE": 2 * SPREAD_TICKS * TICK_USD + COMMISSION_RT,
         "PASSIVE-ENTRY": SPREAD_TICKS * TICK_USD + COMMISSION_RT,
         "PASSIVE-BOTH": COMMISSION_RT}


def runs(c: pd.DataFrame):
    out = []
    for _, g in c.groupby(["session_date", "contract_month"], sort=True):
        g = g.sort_values("mso")
        g = g[(g["mso"] >= ASIA[0]) & (g["mso"] < ASIA[1])]
        m = g["mso"].to_numpy()
        if len(m) < Q * 2 + 2:
            continue
        step = int(np.median(np.diff(m)))
        cuts = np.flatnonzero(np.diff(m) != step) + 1
        arr = (g["open"].to_numpy(float), g["high"].to_numpy(float),
               g["low"].to_numpy(float), g["close"].to_numpy(float))
        for p in np.split(np.arange(len(m)), cuts):
            if len(p) >= Q * 2 + 2:
                out.append(tuple(a[p] for a in arr))
    return out


def simulate(blocks, arm: str, m: int) -> pd.DataFrame:
    """One row per SIGNAL. Unfilled signals carry 0 and a TAKE counterfactual."""
    rows = []
    for op, hi, lo, cl in blocks:
        t = Q
        while t + Q < len(cl):
            prior = cl[t] - cl[t - Q]
            if prior == 0.0:
                t += 1
                continue
            d = -1.0 if prior > 0 else 1.0          # fade
            take_entry = cl[t]
            take_exit = cl[t + Q]
            take_pts = d * (take_exit - take_entry)

            if arm == "TAKE":
                rows.append({"state": "filled", "pts": take_pts, "cf": np.nan})
                t += 2 * Q
                continue

            # Passive ENTRY rests on the favourable side of the last trade: a short (d<0)
            # offers ABOVE the market, a long bids BELOW it. Filled only if the next bar
            # trades strictly through.
            limit = take_entry - d * m * TICK
            nb = t + 1
            through = (hi[nb] > limit) if d < 0 else (lo[nb] < limit)
            if not through:
                rows.append({"state": "unfilled", "pts": 0.0, "cf": take_pts * POINT})
                t += 2 * Q
                continue

            exit_i = min(t + Q, len(cl) - 1)
            if arm == "PASSIVE-ENTRY":
                pts = d * (cl[exit_i] - limit)
                rows.append({"state": "filled", "pts": pts, "cf": np.nan})
            else:
                # Passive EXIT rests on the favourable side of the exit bar's close: closing
                # a short means BUYING, so it bids below; closing a long offers above. If the
                # following bar does not trade through, exit at market on that bar's close.
                ex_lim = cl[exit_i] + d * m * TICK
                nxt = exit_i + 1
                hit = (nxt < len(cl)
                       and ((lo[nxt] < ex_lim) if d < 0 else (hi[nxt] > ex_lim)))
                if hit:
                    pts, filled_exit = d * (ex_lim - limit), True
                elif nxt < len(cl):
                    pts, filled_exit = d * (cl[nxt] - limit), False
                else:
                    pts, filled_exit = d * (cl[exit_i] - limit), False
                rows.append({"state": "filled", "pts": pts, "cf": np.nan,
                             "exit_passive": filled_exit})
            t += 2 * Q
    return pd.DataFrame(rows)


def _boot_t(ef, n, rng) -> float:
    b = stationary_bootstrap(ef, n, rng)
    s = b.std(ddof=1)
    return float(b.mean() / (s / np.sqrt(len(b)))) if s > 0 else 0.0


def score(t: pd.DataFrame, arm: str, draws: int, rng) -> dict:
    usd = t["pts"].to_numpy(float) * POINT           # per SIGNAL, unfilled counted as 0
    n = len(usd)
    if n < 30:
        return {"n": n}
    se = usd.std(ddof=1) / np.sqrt(n)
    tt = float(usd.mean() / se)
    ef = usd - usd.mean()
    p = float(np.mean([_boot_t(ef, n, rng) >= tt for _ in range(draws)])) if draws else 1.0
    filled = t[t["state"] == "filled"]
    cf = t.loc[t["state"] == "unfilled", "cf"].dropna()
    return {"n": n, "filled": len(filled), "fill_rate": len(filled) / n,
            "usd_per_signal": float(usd.mean()),
            "usd_per_fill": float(filled["pts"].mean() * POINT) if len(filled) else 0.0,
            "cf_unfilled": float(cf.mean()) if len(cf) else np.nan,
            "exit_passive_rate": (float(filled["exit_passive"].mean())
                                  if "exit_passive" in filled and len(filled) else np.nan),
            "t": tt, "p": p, "rt": COSTS[arm], "rt_high": COSTS[arm] - COMMISSION_RT
            + COMMISSION_RT_HIGH, "p_reliable": bool(n >= BOOT_MIN_N)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--draws", type=int, default=800)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    c = build_continuous("data_history", "SI", bar_size="30min")
    c = c[~c["thin_session"]].copy()
    c["mso"] = minutes_since_open(c)
    sd = c["session_date"].astype(str)
    c = c[(sd >= args.start) & (sd <= args.end)]
    blocks = runs(c)

    print("PASSIVE EXECUTION ON SI/ASIA/q4 -- CAN A BETTER FILL CLOSE A 4.3x COST GAP?")
    print("=" * 104)
    print(f"Micro silver, Asian session, {args.start[:4]}-{args.end[:4]}. Signal unchanged "
          "from run 34. Pre-registered. Runs ONCE.")
    print("Statistics are PER SIGNAL; unfilled signals count as zero and carry a TAKE "
          "counterfactual.")
    print("30-min OHLC cannot model queue position, so this sim is OPTIMISTIC toward "
          "passing.")
    print()
    print(f"  {'arm':<15}{'m':>3}{'signals':>9}{'fill%':>7}{'exp fill':>10}{'$/signal':>10}"
          f"{'$/fill':>9}{'unfilled CF':>13}{'t':>7}{'p':>8}{'RT':>8}{'net':>9}")

    rng = np.random.default_rng(args.seed)
    expect = {0: "85-95%", 1: "70-85%", 3: "40-65%"}
    res = {}
    for arm in ("TAKE", "PASSIVE-ENTRY", "PASSIVE-BOTH"):
        for m in (MS if arm != "TAKE" else (0,)):
            s = score(simulate(blocks, arm, m), arm, args.draws, rng)
            if s.get("n", 0) < 30:
                continue
            key = f"{arm}/m{m}"
            res[key] = s
            cf = s["cf_unfilled"]
            print(f"  {arm:<15}{m:>3}{s['n']:>9,}{s['fill_rate']:>7.0%}"
                  f"{(expect[m] if arm != 'TAKE' else '-'):>10}"
                  f"{s['usd_per_signal']:>10.2f}{s['usd_per_fill']:>9.2f}"
                  f"{(f'{cf:+.2f}' if cf == cf else '-'):>13}{s['t']:>7.2f}{s['p']:>8.4f}"
                  f"{s['rt']:>8.2f}{s['usd_per_signal'] - s['rt']:>9.2f}"
                  f"{'' if s['p_reliable'] else ' *'}")

    alpha = 0.05 / len(res)
    print("\n" + "=" * 104)
    print(f"  PRE-REGISTERED DECISION (Bonferroni across {len(res)}, p < {alpha:.4f})")
    print(f"  {'cell':<20}{'mean>0':>8}{'p<a':>6}{'>cost':>8}{'CF<=fill':>10}   verdict")
    verdicts = {}
    for k, s in res.items():
        cf = s["cf_unfilled"]
        cs = (s["usd_per_signal"] > 0, s["p"] < alpha,
              s["usd_per_signal"] > s["rt"],
              not (cf == cf) or cf <= s["usd_per_fill"])
        verdicts[k] = all(cs)
        y = lambda b: "yes" if b else "no"              # noqa: E731
        print(f"  {k:<20}{y(cs[0]):>8}{y(cs[1]):>6}{y(cs[2]):>8}{y(cs[3]):>10}   "
              f"{'PASS' if all(cs) else 'FAIL'}")

    print(f"\n  At the conservative ${COMMISSION_RT_HIGH:.2f} commission instead of "
          f"${COMMISSION_RT:.2f}:")
    for k, s in res.items():
        print(f"    {k:<20} net ${s['usd_per_signal'] - s['rt_high']:>8.2f}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"cells": res, "alpha": alpha,
                                           "verdicts": verdicts}, indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
