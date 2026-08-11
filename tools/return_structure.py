#!/usr/bin/env python3
"""
Measure the return-generating process directly. This is a DIAGNOSTIC, not a strategy.

Forty-three strategy cells have been tested on this data. Every one of them is a directional
bet that assumes ES returns carry exploitable serial dependence at some horizon. That
assumption has never been measured. This measures it.

Three things, all standard and none of them a strategy:

  1. Autocorrelation of returns at lags 1..30, with Bartlett standard errors
  2. Lo-MacKinlay variance ratios with the heteroskedasticity-robust z-statistic, which is
     the canonical test of whether a series is a random walk. VR > 1 means trending,
     VR < 1 means mean-reverting, VR = 1 means nothing to time.
  3. The dollar translation: for a measured lag-1 autocorrelation rho and per-bar sigma, a
     sign-following trade earns approximately rho * sigma * sqrt(2/pi) per bar. That number
     is the CEILING on what any 1-bar timing rule can extract, before costs.

Returns are computed strictly within (contract, session) blocks, so no return ever spans a
roll or the overnight maintenance halt.

No pre-registration, because nothing here is a trading rule and nothing here can pass or
fail. It is a property of the data. What it constrains is which strategies are worth
writing at all.
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

POINT = 5.0
WINDOWS = {"ALL": None, "ASIA": (-930, -390), "LONDON": (-390, 0), "NY": (0, 390)}


def blocks(c: pd.DataFrame, lo=None, hi=None) -> list[np.ndarray]:
    """Log-return arrays, one per contiguous (contract, session) run of bars."""
    out = []
    for _, g in c.groupby(["session_date", "contract_month"], sort=True):
        g = g.sort_values("mso")
        if lo is not None:
            g = g[(g["mso"] >= lo) & (g["mso"] < hi)]
        if len(g) < 12:
            continue
        px = g["close"].to_numpy(dtype=float)
        # a gap in mso means missing bars; split so no return spans a hole
        step = int(np.median(np.diff(g["mso"].to_numpy())))
        cuts = np.flatnonzero(np.diff(g["mso"].to_numpy()) != step) + 1
        for part in np.split(np.arange(len(px)), cuts):
            if len(part) < 12:
                continue
            p = px[part]
            out.append(np.diff(np.log(p)))
    return [b for b in out if len(b) >= 10]


def autocorr(r: np.ndarray, max_lag: int) -> tuple[np.ndarray, float]:
    """Sample autocorrelation and the Bartlett standard error 1/sqrt(n)."""
    r = r - r.mean()
    denom = float(r @ r)
    ac = np.array([float(r[k:] @ r[:-k]) / denom for k in range(1, max_lag + 1)])
    return ac, 1.0 / np.sqrt(len(r))


def variance_ratio(r: np.ndarray, q: int) -> tuple[float, float]:
    """Lo-MacKinlay VR(q) with the heteroskedasticity-robust z-statistic."""
    n = len(r)
    if n < q * 4:
        return np.nan, np.nan
    mu = r.mean()
    e = r - mu
    var1 = float(e @ e) / (n - 1)
    # overlapping q-period returns
    cs = np.concatenate([[0.0], np.cumsum(r)])
    rq = cs[q:] - cs[:-q] - q * mu
    m = q * (n - q + 1) * (1 - q / n)
    varq = float(rq @ rq) / m
    vr = varq / var1
    # robust variance of VR under heteroskedasticity
    s2 = float(e @ e)
    theta = 0.0
    for j in range(1, q):
        num = float((e[j:] ** 2) @ (e[:-j] ** 2))
        delta = num / (s2 ** 2) * n
        theta += (2.0 * (q - j) / q) ** 2 * delta
    z = (vr - 1.0) / np.sqrt(theta / n) if theta > 0 else np.nan
    return vr, z


def pooled(bs: list[np.ndarray], max_lag: int):
    """Pool blocks for autocorrelation without letting a return span a block edge."""
    n = sum(len(b) for b in bs)
    num = np.zeros(max_lag)
    den = 0.0
    mu = float(np.concatenate(bs).mean())
    for b in bs:
        e = b - mu
        den += float(e @ e)
        for k in range(1, max_lag + 1):
            if len(e) > k:
                num[k - 1] += float(e[k:] @ e[:-k])
    return num / den, 1.0 / np.sqrt(n), n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data_5min")
    ap.add_argument("--symbol", default="ES")
    ap.add_argument("--bar", default="5min")
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    c = build_continuous(args.data, args.symbol, bar_size=args.bar)
    c = c[~c["thin_session"]].copy()
    c["mso"] = minutes_since_open(c)
    sd = c["session_date"].astype(str)
    c = c[(sd >= args.start) & (sd <= args.end)]

    print(f"RETURN STRUCTURE OF {args.symbol} {args.bar} -- DIAGNOSTIC, NOT A STRATEGY")
    print("=" * 92)
    print(f"{c['session_date'].nunique():,} sessions {args.start[:4]}-{args.end[:4]}. "
          "Returns never span a roll or the overnight halt.")

    res = {}
    print(f"\n  {'window':<8}{'bars':>10}{'sigma/bar':>11}{'ac1':>9}{'ac2':>9}"
          f"{'ac3':>9}{'ac5':>9}{'2se':>8}{'ceiling $/bar':>15}")
    for name, w in WINDOWS.items():
        bs = blocks(c, *(w if w else (None, None)))
        if not bs:
            continue
        ac, se, n = pooled(bs, 30)
        allr = np.concatenate(bs)
        sigma = float(allr.std(ddof=1))
        px = float(c["close"].median())
        # sign-following ceiling: rho * sigma * sqrt(2/pi), in log units -> points -> dollars
        ceil = abs(ac[0]) * sigma * np.sqrt(2 / np.pi) * px * POINT
        res[name] = {"bars": n, "sigma": sigma, "ac": ac.tolist(), "se": se,
                     "ceiling_usd_per_bar": ceil}
        print(f"  {name:<8}{n:>10,}{sigma * 1e4:>10.2f}bp{ac[0]:>9.4f}{ac[1]:>9.4f}"
              f"{ac[2]:>9.4f}{ac[4]:>9.4f}{2 * se:>8.4f}{ceil:>14.2f}")

    print("\n  Bartlett 2-sigma band is the '2se' column. An autocorrelation inside it is")
    print("  indistinguishable from zero. 'ceiling' is the most a perfect 1-bar sign-timing")
    print(f"  rule could earn per bar at that rho, BEFORE the ${3.70:.2f} round turn.")

    print(f"\n  LO-MACKINLAY VARIANCE RATIOS (robust z; |z| > 2 rejects a random walk)")
    print(f"  {'window':<8}" + "".join(f"{'q=' + str(q):>16}" for q in (2, 4, 8, 16, 32)))
    for name, w in WINDOWS.items():
        if name not in res:
            continue
        bs = blocks(c, *(w if w else (None, None)))
        r = np.concatenate(bs)
        cells, vrs = [], {}
        for q in (2, 4, 8, 16, 32):
            vr, z = variance_ratio(r, q)
            vrs[q] = {"vr": vr, "z": z}
            cells.append(f"{vr:>10.3f}/{z:>+5.1f}")
        res[name]["vr"] = vrs
        print(f"  {name:<8}" + "".join(f"{x:>16}" for x in cells))

    # session-to-session, the horizon every one of the 43 cells actually traded
    ses = (c.groupby("session_date")["close"].last().pct_change().dropna())
    sr = np.log1p(ses.to_numpy())
    ac_s, se_s = autocorr(sr, 10)
    print(f"\n  SESSION-TO-SESSION ({len(sr):,} sessions), 2se = {2 * se_s:.4f}")
    print("  " + "  ".join(f"lag{k + 1} {ac_s[k]:+.3f}" for k in range(5)))
    vr_s = {q: variance_ratio(sr, q) for q in (2, 4, 8)}
    print("  " + "  ".join(f"VR({q}) {v:.3f}/z{z:+.1f}" for q, (v, z) in vr_s.items()))
    res["SESSION"] = {"n": len(sr), "ac": ac_s.tolist(), "se": se_s,
                      "vr": {q: {"vr": v, "z": z} for q, (v, z) in vr_s.items()}}

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(res, indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
