#!/usr/bin/env python3
"""
Confirmatory test of the ES/NQ spread: is its mean reversion an execution artifact?

Implements `docs/PREREGISTRATION_2026-08-12_ESNQ_SPREAD.md` exactly. Committed before this
file was run. Nothing here may be changed after seeing a result.

Fade the preceding q-bar move in log(NQ) - log(ES), hold q bars, non-overlapping. One MES
against the dollar-neutral quantity of MNQ, ratio computed causally from the prior session.

The one-bar-delay column is the primary criterion. The diagnostic showed the spread's
autocorrelation is entirely at lag 1, which is the signature of bid-ask bounce plus stale
non-synchronous bar closes, so this test exists to confirm that a step-over kills it.
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

MES_PT, MNQ_PT = 5.0, 2.0
MES_RT, MNQ_RT = 3.70, 2.20             # standing convention
MES_RT_ADV, MNQ_RT_ADV = 4.95, 4.70     # adverse measured model
HORIZONS = (1, 2, 4)
WINDOWS = {"ALL": None, "ASIA": (-930, -390), "NY": (0, 390)}
DELAY_KEEP = 0.60
BOOT_MIN_N = 700


def aligned(start: str, end: str) -> pd.DataFrame:
    def load(sym):
        c = build_continuous("data_history", sym, bar_size="30min")
        c = c[~c["thin_session"]].copy()
        c["mso"] = minutes_since_open(c)
        sd = c["session_date"].astype(str)
        return c[(sd >= start) & (sd <= end)]

    es, nq = load("ES"), load("NQ")
    j = (es[["timestamp_utc", "session_date", "contract_month", "mso", "close"]]
         .rename(columns={"close": "es", "contract_month": "cm_es"})
         .merge(nq[["timestamp_utc", "contract_month", "close"]]
                .rename(columns={"close": "nq", "contract_month": "cm_nq"}),
                on="timestamp_utc"))
    j = j.sort_values("timestamp_utc").reset_index(drop=True)
    # causal dollar-neutral ratio: MNQ contracts per 1 MES, from the PRIOR session's closes
    last = j.groupby("session_date")[["es", "nq"]].last()
    ratio = (MES_PT * last["es"]) / (MNQ_PT * last["nq"])
    j["ratio"] = j["session_date"].map(ratio.shift(1))
    return j.dropna(subset=["ratio"])


def blocks(j: pd.DataFrame, win):
    """Per contiguous (session, contract-pair) run: log ES, log NQ, and the hedge ratio."""
    out = []
    for _, g in j.groupby(["session_date", "cm_es", "cm_nq"], sort=True):
        g = g.sort_values("mso")
        if win is not None:
            g = g[(g["mso"] >= win[0]) & (g["mso"] < win[1])]
        if len(g) < 6:
            continue
        m = g["mso"].to_numpy()
        step = int(np.median(np.diff(m)))
        cuts = np.flatnonzero(np.diff(m) != step) + 1
        arr = (np.log(g["es"].to_numpy(float)), np.log(g["nq"].to_numpy(float)),
               g["ratio"].to_numpy(float), g["es"].to_numpy(float),
               g["nq"].to_numpy(float))
        for p in np.split(np.arange(len(m)), cuts):
            if len(p) >= 6:
                out.append(tuple(a[p] for a in arr))
    return out


def fade(bs, q: int, delay: int = 0) -> np.ndarray:
    """Fade the prior q-bar spread move; P&L in dollars for 1 MES + ratio MNQ."""
    pnl = []
    for les, lnq, ratio, es, nq in bs:
        t = q
        while t + delay + q < len(les):
            prior = (lnq[t] - les[t]) - (lnq[t - q] - les[t - q])
            if prior != 0.0:
                d = -1.0 if prior > 0 else 1.0      # fade
                e = t + delay
                # long spread = long NQ, short ES, in dollar-neutral size
                leg_nq = d * (nq[e + q] - nq[e]) * MNQ_PT * ratio[e]
                leg_es = -d * (es[e + q] - es[e]) * MES_PT
                pnl.append(leg_nq + leg_es)
            t += 2 * q + delay
    return np.asarray(pnl, dtype=float)


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
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    j = aligned(args.start, args.end)
    med_ratio = float(j["ratio"].median())
    rt = MES_RT + med_ratio * MNQ_RT
    rt_adv = MES_RT_ADV + med_ratio * MNQ_RT_ADV

    print("ES/NQ SPREAD -- CONFIRMATORY. IS THE REVERSION AN EXECUTION ARTIFACT?")
    print("=" * 100)
    print(f"{len(j):,} aligned 30-min bars, {j.session_date.nunique():,} sessions "
          f"{args.start[:4]}-{args.end[:4]}. Pre-registered. Runs ONCE.")
    print(f"1 MES vs {med_ratio:.2f} MNQ (causal dollar-neutral). "
          f"Pair round turn ${rt:.2f} standard, ${rt_adv:.2f} adverse.")
    print("The DELAY column is the primary criterion.")
    print()
    print(f"  {'window':<8}{'q':>3}{'min':>6}{'trades':>9}{'raw $':>10}{'t':>8}{'p':>8}"
          f"{'delay1 $':>11}{'t':>8}{'keep':>8}{'net $':>9}")

    rng = np.random.default_rng(args.seed)
    res = {}
    for win, rngw in WINDOWS.items():
        bs = blocks(j, rngw)
        for q in HORIZONS:
            s = score(fade(bs, q), args.draws, rng)
            if s.get("n", 0) < 30:
                continue
            d1 = score(fade(bs, q, delay=1), 0, rng)
            keep = (d1["usd"] / s["usd"]) if s["usd"] > 0 else float("nan")
            res[f"{win}/q{q}"] = {**s, "delay1_usd": d1["usd"], "delay1_t": d1["t"],
                                  "keep": keep, "rt": rt, "rt_adv": rt_adv}
            print(f"  {win:<8}{q:>3}{q * 30:>6}{s['n']:>9,}{s['usd']:>10.3f}{s['t']:>8.2f}"
                  f"{s['p']:>8.4f}{d1['usd']:>11.3f}{d1['t']:>8.2f}"
                  f"{(f'{keep:.0%}' if keep == keep else '-'):>8}{s['usd'] - rt:>9.2f}"
                  f"{'' if s['p_reliable'] else ' *'}")

    alpha = 0.05 / len(res)
    print("\n" + "=" * 100)
    print(f"  PRE-REGISTERED DECISION (Bonferroni across {len(res)}, p < {alpha:.4f})")
    print(f"  {'cell':<12}{'raw>0':>8}{'p<a':>6}{'keeps 60%':>11}{'>cost':>8}   verdict")
    verdicts = {}
    for k, s in res.items():
        cs = (s["usd"] > 0, s["p"] < alpha,
              s["keep"] == s["keep"] and s["keep"] >= DELAY_KEEP, s["usd"] > s["rt"])
        verdicts[k] = all(cs)
        y = lambda b: "yes" if b else "no"              # noqa: E731
        print(f"  {k:<12}{y(cs[0]):>8}{y(cs[1]):>6}{y(cs[2]):>11}{y(cs[3]):>8}   "
              f"{'PASS' if all(cs) else 'FAIL'}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"cells": res, "alpha": alpha,
                                           "verdicts": verdicts,
                                           "median_ratio": med_ratio},
                                          indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
