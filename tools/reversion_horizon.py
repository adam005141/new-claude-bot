#!/usr/bin/env python3
"""
At what holding horizon does the measured mean reversion cover its cost?

Implements `docs/PREREGISTRATION_2026-08-11_REVERSION_HORIZON.md` exactly. Committed before
this file was run. Nothing here may be changed after seeing a result.

At the close of bar t, having seen the return over the preceding q bars, take the OPPOSITE
side and hold exactly q bars. Non-overlapping, so trades are independent. No stop, no
filter: this measures the ceiling of the family, and a stop can only subtract from it.

Edge scales as sqrt(q); cost does not scale. So this sweep produces a ceiling, and a
negative result closes reversion rather than leaving it open to another variant.
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

POINT = 5.0
COST_RT = 3.70
HORIZONS = (1, 2, 3, 6, 12, 24, 48, 78)
BOOT_MIN_N = 700


def runs(c: pd.DataFrame) -> list[np.ndarray]:
    """Close arrays for each contiguous (session, contract) run with no gap in mso."""
    out = []
    for _, g in c.groupby(["session_date", "contract_month"], sort=True):
        g = g.sort_values("mso")
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


def fade(px_runs: list[np.ndarray], q: int) -> np.ndarray:
    """Non-overlapping: observe [t-q, t], take the opposite side, hold q bars. Points."""
    pnl = []
    for px in px_runs:
        # need 2q+1 points for one trade; step by 2q so signal and holding never overlap
        t = q
        while t + q < len(px):
            prior = px[t] - px[t - q]
            if prior != 0.0:
                d = -1.0 if prior > 0 else 1.0
                pnl.append(d * (px[t + q] - px[t]))
            t += 2 * q
    return np.asarray(pnl, dtype=float)


def _boot_t(ef, n, rng) -> float:
    b = stationary_bootstrap(ef, n, rng)
    s = b.std(ddof=1)
    return float(b.mean() / (s / np.sqrt(len(b)))) if s > 0 else 0.0


def score(pts: np.ndarray, draws: int, rng) -> dict:
    usd = pts * POINT
    n = len(usd)
    se = usd.std(ddof=1) / np.sqrt(n)
    t = float(usd.mean() / se)
    k = max(1, int(0.05 * n))
    trim = np.sort(usd)[:-k]
    ef = usd - usd.mean()
    p = float(np.mean([_boot_t(ef, n, rng) >= t for _ in range(draws)])) if draws else 1.0
    return {"n": n, "usd": float(usd.mean()), "usd_net": float(usd.mean() - COST_RT),
            "total": float(usd.sum()), "wr": float((usd > 0).mean()),
            "sd": float(usd.std(ddof=1)), "t": t,
            "t_trim": float(trim.mean() / (trim.std(ddof=1) / np.sqrt(len(trim)))),
            "p": p, "p_reliable": bool(n >= BOOT_MIN_N)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data_5min")
    ap.add_argument("--symbol", default="ES")
    ap.add_argument("--bar", default="5min")
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    c = build_continuous(args.data, args.symbol, bar_size=args.bar)
    c = c[~c["thin_session"]].copy()
    c["mso"] = minutes_since_open(c)
    sd = c["session_date"].astype(str)
    c = c[(sd >= args.start) & (sd <= args.end)]
    px_runs = runs(c)

    print("REVERSION EDGE VERSUS HOLDING HORIZON -- CEILING CALCULATION")
    print("=" * 96)
    print(f"{args.symbol} {args.bar}, {c['session_date'].nunique():,} sessions "
          f"{args.start[:4]}-{args.end[:4]}. Non-overlapping, no stop, no filter.")
    print("Pre-registered. Runs ONCE.")
    print()
    print(f"  {'q':>4}{'minutes':>9}{'trades':>9}{'raw $/tr':>10}{'net $/tr':>10}"
          f"{'total $':>12}{'WR':>6}{'sd':>8}{'t':>8}{'t-5%':>8}{'p':>8}")

    rng = np.random.default_rng(args.seed)
    res = {}
    for q in HORIZONS:
        pts = fade(px_runs, q)
        if len(pts) < 30:
            continue
        s = score(pts, args.draws, rng)
        res[q] = s
        print(f"  {q:>4}{q * 5:>9}{s['n']:>9,}{s['usd']:>10.3f}{s['usd_net']:>10.3f}"
              f"{s['total']:>12,.0f}{s['wr']:>6.1%}{s['sd']:>8.1f}{s['t']:>8.2f}"
              f"{s['t_trim']:>8.2f}{s['p']:>8.4f}{'' if s['p_reliable'] else ' *'}")

    alpha = 0.05 / len(HORIZONS)
    print("\n" + "=" * 96)
    print(f"  PRE-REGISTERED DECISION (Bonferroni across {len(HORIZONS)}, p < {alpha:.5f})")
    print(f"  {'q':>4}{'raw>0':>8}{'p<a':>6}{'t-5%>2':>9}{'>cost':>8}   "
          f"{'measurement':<14}strategy")
    verdicts = {}
    for q, s in res.items():
        meas = (s["usd"] > 0, s["p"] < alpha, s["t_trim"] > 2.0)
        cost_ok = s["usd"] > COST_RT
        verdicts[q] = {"measurement": all(meas), "strategy": all(meas) and cost_ok}
        y = lambda b: "yes" if b else "no"              # noqa: E731
        print(f"  {q:>4}{y(meas[0]):>8}{y(meas[1]):>6}{y(meas[2]):>9}{y(cost_ok):>8}   "
              f"{('PASS' if all(meas) else 'FAIL'):<14}"
              f"{'PASS' if verdicts[q]['strategy'] else 'FAIL'}")

    best = max(res, key=lambda k: res[k]["usd"])
    b = res[best]
    print(f"\n  CEILING: best horizon q={best} ({best * 5} min) at ${b['usd']:.3f} a trade.")
    print(f"  Round turn is ${COST_RT:.2f}. Edge is {b['usd'] / COST_RT:.0%} of cost.")
    if b["usd"] <= COST_RT:
        need = COST_RT / b["usd"] if b["usd"] > 0 else float("inf")
        print(f"  To clear cost the edge would have to be {need:.1f}x larger. Since edge")
        print("  scales as sqrt(q), that needs roughly "
              f"{need ** 2:.0f}x the holding time, or {best * 5 * need ** 2 / 390:.1f} "
              "full NY sessions per trade.")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(
            {"horizons": res, "alpha": alpha, "verdicts": verdicts,
             "cost_rt": COST_RT}, indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
