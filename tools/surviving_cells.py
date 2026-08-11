#!/usr/bin/env python3
"""
Test the four (instrument, window) cells that survived bid-ask bounce dilution.

Implements `docs/PREREGISTRATION_2026-08-11_SURVIVING_CELLS.md` exactly. Committed before
this file was run. Nothing here may be changed after seeing a result.

Same direct, assumption-free trade as run 33: observe the preceding q bars, take a position,
hold q bars, non-overlapping. Reverting cells fade; trending cells follow.

The one-bar-delay column is a headline. A cell whose edge does not survive delayed execution
is a microstructure artifact regardless of its t-statistic.
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

# instrument -> (micro point value, measured round turn in dollars)
INSTR = {"ES": (5.0, 3.70), "GC": (10.0, 5.20), "SI": (1000.0, 31.20)}
WINDOWS = {"ASIA": (-930, -390), "LONDON": (-390, 0), "NY": (0, 390)}
HORIZONS = (1, 2, 4, 8)
DELAY_KEEP = 0.60          # fraction of the edge that must survive one bar of delay
BOOT_MIN_N = 700

# (symbol, window, direction) -- direction +1 follows the prior move, -1 fades it
CELLS = (("ES", "LONDON", -1),
         ("SI", "ASIA", -1),
         ("SI", "LONDON", -1),
         ("GC", "NY", +1),
         ("SI", "NY", +1))


def runs(c: pd.DataFrame, lo: int, hi: int) -> list[np.ndarray]:
    """Close arrays per contiguous (session, contract) run inside the window, no mso gaps."""
    out = []
    for _, g in c.groupby(["session_date", "contract_month"], sort=True):
        g = g.sort_values("mso")
        g = g[(g["mso"] >= lo) & (g["mso"] < hi)]
        m = g["mso"].to_numpy()
        if len(m) < 4:
            continue
        step = int(np.median(np.diff(m)))
        cuts = np.flatnonzero(np.diff(m) != step) + 1
        px = g["close"].to_numpy(dtype=float)
        for part in np.split(np.arange(len(px)), cuts):
            if len(part) >= 4:
                out.append(px[part])
    return out


def trade(px_runs, q: int, sign: int, delay: int = 0) -> np.ndarray:
    """Observe [t-q, t], take `sign` x that direction, execute after `delay`, hold q."""
    out = []
    for px in px_runs:
        t = q
        while t + delay + q < len(px):
            prior = px[t] - px[t - q]
            if prior != 0.0:
                d = float(np.sign(prior)) * sign
                e = t + delay
                out.append(d * (px[e + q] - px[e]))
            t += 2 * q + delay
    return np.asarray(out, dtype=float)


def _boot_t(ef, n, rng) -> float:
    b = stationary_bootstrap(ef, n, rng)
    s = b.std(ddof=1)
    return float(b.mean() / (s / np.sqrt(len(b)))) if s > 0 else 0.0


def score(pts, point, draws, rng) -> dict:
    usd = pts * point
    n = len(usd)
    if n < 30:
        return {"n": n}
    se = usd.std(ddof=1) / np.sqrt(n)
    t = float(usd.mean() / se)
    ef = usd - usd.mean()
    p = float(np.mean([_boot_t(ef, n, rng) >= t for _ in range(draws)])) if draws else 1.0
    return {"n": n, "usd": float(usd.mean()), "t": t, "p": p,
            "wr": float((usd > 0).mean()), "p_reliable": bool(n >= BOOT_MIN_N)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data_history")
    ap.add_argument("--bar", default="30min")
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    loaded = {}
    for sym in sorted({s for s, _, _ in CELLS}):
        c = build_continuous(args.data, sym, bar_size=args.bar)
        c = c[~c["thin_session"]].copy()
        c["mso"] = minutes_since_open(c)
        sd = c["session_date"].astype(str)
        loaded[sym] = c[(sd >= args.start) & (sd <= args.end)]

    print("CELLS SURVIVING BOUNCE DILUTION -- 30-MIN BARS")
    print("=" * 104)
    print(f"{args.start[:4]}-{args.end[:4]}. Non-overlapping, no stop, no filter. "
          "Pre-registered. Runs ONCE.")
    print("A cell whose edge does not survive one bar of delay is an artifact, "
          "whatever its t.")
    print()
    print(f"  {'cell':<16}{'dir':>5}{'q':>3}{'min':>6}{'trades':>9}{'raw $':>9}{'t':>7}"
          f"{'p':>8}{'net $':>9}{'delay1 $':>10}{'keep':>7}{'RT $':>8}")

    rng = np.random.default_rng(args.seed)
    res, alpha = {}, 0.05 / (len(CELLS) * len(HORIZONS))
    for sym, win, sign in CELLS:
        point, rt = INSTR[sym]
        R = runs(loaded[sym], *WINDOWS[win])
        for q in HORIZONS:
            s = score(trade(R, q, sign), point, args.draws, rng)
            if s.get("n", 0) < 30:
                continue
            d1 = score(trade(R, q, sign, delay=1), point, 0, rng)
            keep = (d1["usd"] / s["usd"]) if s["usd"] > 0 else float("nan")
            key = f"{sym}/{win}/q{q}"
            res[key] = {**s, "delay1_usd": d1.get("usd"), "keep": keep,
                        "round_turn": rt, "sign": sign}
            print(f"  {sym + '/' + win:<16}{'follow' if sign > 0 else 'fade':>7}"[:21]
                  + f"{q:>3}{q * 30:>6}{s['n']:>9,}{s['usd']:>9.3f}{s['t']:>7.2f}"
                  f"{s['p']:>8.4f}{s['usd'] - rt:>9.2f}{d1['usd']:>10.3f}"
                  f"{(f'{keep:.0%}' if keep == keep else '-'):>7}{rt:>8.2f}"
                  f"{'' if s['p_reliable'] else ' *'}")

    print("\n" + "=" * 104)
    print(f"  PRE-REGISTERED DECISION (Bonferroni across {len(res)} cells, p < {alpha:.4f})")
    print(f"  {'cell':<18}{'raw>0':>8}{'p<a':>6}{'keeps 60%':>11}{'>cost':>8}   "
          f"{'measurement':<14}strategy")
    verdicts = {}
    for k, s in res.items():
        meas = (s["usd"] > 0, s["p"] < alpha,
                s["keep"] == s["keep"] and s["keep"] >= DELAY_KEEP)
        cost_ok = s["usd"] > s["round_turn"]
        verdicts[k] = {"measurement": all(meas), "strategy": all(meas) and cost_ok}
        y = lambda b: "yes" if b else "no"              # noqa: E731
        print(f"  {k:<18}{y(meas[0]):>8}{y(meas[1]):>6}{y(meas[2]):>11}{y(cost_ok):>8}   "
              f"{('PASS' if all(meas) else 'FAIL'):<14}"
              f"{'PASS' if verdicts[k]['strategy'] else 'FAIL'}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"cells": res, "alpha": alpha,
                                           "verdicts": verdicts}, indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
