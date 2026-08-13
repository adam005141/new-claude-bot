#!/usr/bin/env python3
"""
Volume-conditioned reversion: does the heavy-bar lag-2 term survive delayed execution?

Implements `docs/PREREGISTRATION_2026-08-12_VOLUME_CONDITIONED.md` exactly. Committed
before this file was run. Nothing here may be changed after seeing a result.

Fade the preceding q-bar move, hold q bars, non-overlapping, conditioned on the relative
volume tercile of the SIGNAL bar. THIN and MID are controls.

The delay column is primary and the prediction is a contrast: THIN is lag-1 only so delay
should destroy it, HEAVY has lag-2 structure so delay should largely preserve it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.feasibility import stationary_bootstrap  # noqa: E402
from tools.flow_structure import prepare  # noqa: E402

POINT, COST_RT = 5.0, 3.70
HORIZONS = (1, 2, 4, 8)
DELAY_KEEP = 0.60
BOOT_MIN_N = 700


def runs(c: pd.DataFrame):
    """(close, relvol) arrays per contiguous block, so nothing spans a roll or the halt."""
    out = []
    for _, g in c.groupby("blk", sort=False):
        if len(g) < 6:
            continue
        out.append((g["close"].to_numpy(float), g["relvol"].to_numpy(float)))
    return out


def fade(blocks, q: int, lo: float, hi: float, delay: int = 0) -> np.ndarray:
    """Fade the prior q-bar move when the signal bar's relvol is in [lo, hi)."""
    pnl = []
    for px, rv in blocks:
        t = q
        while t + delay + q < len(px):
            v = rv[t]
            if np.isfinite(v) and lo <= v < hi:
                prior = px[t] - px[t - q]
                if prior != 0.0:
                    d = -1.0 if prior > 0 else 1.0
                    e = t + delay
                    pnl.append(d * (px[e + q] - px[e]))
                    t += 2 * q + delay
                    continue
            t += 1
    return np.asarray(pnl, dtype=float) * POINT


def _boot_t(ef, n, rng) -> float:
    b = stationary_bootstrap(ef, n, rng)
    s = b.std(ddof=1)
    return float(b.mean() / (s / np.sqrt(len(b)))) if s > 0 else 0.0


def score(usd, draws, rng) -> dict:
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
    ap.add_argument("--symbol", default="ES")
    ap.add_argument("--data", default="data_5min")
    ap.add_argument("--bar", default="5min")
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--draws", type=int, default=800)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    c = prepare(args.symbol, args.data, args.bar, args.start, args.end)
    valid = c["relvol"].notna() & c["ret"].notna()
    lo_q, hi_q = c.loc[valid, "relvol"].quantile([1 / 3, 2 / 3]).to_numpy()
    bands = {"THIN": (0.0, lo_q), "MID": (lo_q, hi_q), "HEAVY": (hi_q, np.inf)}
    blocks = runs(c)

    print(f"VOLUME-CONDITIONED REVERSION, {args.symbol} {args.bar}")
    print("=" * 96)
    print(f"{c['session_date'].nunique():,} sessions {args.start[:4]}-{args.end[:4]}. "
          f"Tercile cuts {lo_q:.2f} / {hi_q:.2f}. Pre-registered. Runs ONCE.")
    print("THIN and MID are CONTROLS. The delay column is primary.")
    print()
    print(f"  {'band':<7}{'q':>3}{'min':>5}{'trades':>9}{'raw $':>9}{'t':>8}{'p':>8}"
          f"{'delay1 $':>10}{'t':>8}{'keep':>8}{'net $':>9}")

    rng = np.random.default_rng(args.seed)
    res = {}
    for name, (lo, hi) in bands.items():
        for q in HORIZONS:
            s = score(fade(blocks, q, lo, hi), args.draws, rng)
            if s.get("n", 0) < 30:
                continue
            d1 = score(fade(blocks, q, lo, hi, delay=1), 0, rng)
            keep = (d1["usd"] / s["usd"]) if s["usd"] > 0 else float("nan")
            res[f"{name}/q{q}"] = {**s, "delay1_usd": d1["usd"], "delay1_t": d1["t"],
                                   "keep": keep}
            print(f"  {name:<7}{q:>3}{q * 5:>5}{s['n']:>9,}{s['usd']:>9.3f}{s['t']:>8.2f}"
                  f"{s['p']:>8.4f}{d1['usd']:>10.3f}{d1['t']:>8.2f}"
                  f"{(f'{keep:.0%}' if keep == keep else '-'):>8}"
                  f"{s['usd'] - COST_RT:>9.2f}{'' if s['p_reliable'] else ' *'}")

    alpha = 0.05 / len(res)
    print("\n" + "=" * 96)
    print(f"  PRE-REGISTERED DECISION (Bonferroni across {len(res)}, p < {alpha:.4f})")
    print(f"  {'cell':<12}{'raw>0':>8}{'p<a':>6}{'keeps 60%':>11}{'>cost':>8}   verdict")
    verdicts = {}
    for k, s in res.items():
        cs = (s["usd"] > 0, s["p"] < alpha,
              s["keep"] == s["keep"] and s["keep"] >= DELAY_KEEP, s["usd"] > COST_RT)
        verdicts[k] = all(cs)
        y = lambda b: "yes" if b else "no"              # noqa: E731
        print(f"  {k:<12}{y(cs[0]):>8}{y(cs[1]):>6}{y(cs[2]):>11}{y(cs[3]):>8}   "
              f"{'PASS' if all(cs) else 'FAIL'}")

    print("\n  THE REGISTERED CONTRAST: THIN should collapse under delay, HEAVY survive.")
    for band in ("THIN", "HEAVY"):
        ks = [k for k in res if k.startswith(band)]
        keeps = [res[k]["keep"] for k in ks if res[k]["keep"] == res[k]["keep"]]
        if keeps:
            print(f"    {band:<6} median keep across horizons: {np.median(keeps):.0%}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"cells": res, "alpha": alpha,
                                           "verdicts": verdicts,
                                           "cuts": [float(lo_q), float(hi_q)]},
                                          indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
