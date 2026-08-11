#!/usr/bin/env python3
"""
Four more entry rules on the three cross-session structures.

Implements `docs/PREREGISTRATION_2026-08-10_ENTRY_VARIANTS.md` exactly. Committed before
this file was run. Nothing here may be changed after seeing a result.

  IMMEDIATE  control: market at the level on the bar that breaks it
  CONFIRM    next bar's open, only if the break bar CLOSED beyond the level  [POST-HOC]
  STRONG     at the level, only if the break bar closed in the top/bottom quartile of itself
  VOLUME     at the level, only if the break bar's volume > 1.5x the reference median
  DAYBIAS    at the level, only if the direction agrees with price against the 18:00 ET open

CONFIRM is derived from the previous result and is circular on this data. It is run as the
mechanically indicated next step, and a positive here is a hypothesis for 2017-2023, not a
finding.

Every skipped signal is recorded with zero P&L and its IMMEDIATE counterfactual computed.
Three of these four are filters, and a filter's whole risk is that it removes winners.
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

POINT, TICK = 5.0, 0.25
COMMISSION_RT = 1.20
MIN_RANGE_PTS = 1.00
BUFFER_TICKS = 1.0
STRONG_QUANTILE = 0.25          # break bar must close in the top/bottom quarter of itself
VOLUME_MULT = 1.5               # ... or carry 1.5x the reference window's median volume

ARMS = {"A2L": ((-930, -390), (-390, 0)),
        "L2N": ((-390, 0), (0, 390)),
        "NYOR": ((0, 60), (60, 390))}
MODES = ("IMMEDIATE", "CONFIRM", "STRONG", "VOLUME", "DAYBIAS")


def _resolve(w, start, d, entry, stop, cost):
    if start >= len(w):
        return None
    for k in range(start, len(w)):
        b = w.iloc[k]
        if d == 1 and b["low"] <= stop:
            return (min(stop, b["open"]) - entry) * POINT - cost
        if d == -1 and b["high"] >= stop:
            return (entry - max(stop, b["open"])) * POINT - cost
        if k == len(w) - 1:
            return (b["close"] - entry) * d * POINT - cost
    return None


def run(c: pd.DataFrame, ref, trade, mode: str, spread_mult: float = 1.0) -> pd.DataFrame:
    cost = 2.0 * 1.0 * spread_mult * TICK * POINT + COMMISSION_RT
    buf = BUFFER_TICKS * TICK
    rows = []

    for sd, s in c.groupby("session_date", sort=True):
        r = s[(s["mso"] >= ref[0]) & (s["mso"] < ref[1])]
        w = s[(s["mso"] >= trade[0]) & (s["mso"] < trade[1])].sort_values("mso")
        if r.empty or len(w) < 3:
            continue
        hi, lo = r["high"].max(), r["low"].min()
        if (hi - lo) < MIN_RANGE_PTS:
            continue
        up, dn = hi + buf, lo - buf

        brk = None
        for i in range(len(w)):
            b = w.iloc[i]
            hu, hd = b["high"] >= up, b["low"] <= dn
            if hu and hd:
                took = 1 if b["close"] < b["open"] else -1
            elif hu:
                took = 1
            elif hd:
                took = -1
            else:
                continue
            brk = (i, took)
            break
        if brk is None:
            continue
        i0, d = brk
        level, stop = (up, lo) if d == 1 else (dn, hi)
        bb = w.iloc[i0]

        # counterfactual under IMMEDIATE, computed for every signal so a filtered-out
        # trade can be charged for what it would have earned
        imm_entry = level if (bb["open"] <= level if d == 1 else bb["open"] >= level) \
            else bb["open"]
        cf = _resolve(w, i0 + 1, d, imm_entry, stop, cost)

        take, entry, start = True, imm_entry, i0 + 1
        if mode == "CONFIRM":
            beyond = bb["close"] > level if d == 1 else bb["close"] < level
            if not beyond or i0 + 1 >= len(w):
                take = False
            else:
                entry, start = w.iloc[i0 + 1]["open"], i0 + 2
        elif mode == "STRONG":
            rng = bb["high"] - bb["low"]
            if rng <= 0:
                take = False
            else:
                pos = (bb["close"] - bb["low"]) / rng
                take = pos >= 1 - STRONG_QUANTILE if d == 1 else pos <= STRONG_QUANTILE
        elif mode == "VOLUME":
            med = r["volume"].median()
            take = bool(med > 0 and bb["volume"] > VOLUME_MULT * med)
        elif mode == "DAYBIAS":
            o = s.sort_values("mso")["open"].iloc[0]     # the 18:00 ET session open
            take = (level > o) if d == 1 else (level < o)

        if not take:
            rows.append({"session_date": sd, "dir": d, "state": "skipped",
                         "net": 0.0, "counterfactual": cf})
            continue
        net = _resolve(w, start, d, entry, stop, cost)
        if net is None:
            continue
        rows.append({"session_date": sd, "dir": d, "state": "taken",
                     "net": net, "counterfactual": cf})
    return pd.DataFrame(rows)


def score(t, sessions, draws, rng):
    if t.empty:
        return {"signals": 0}
    ser = pd.Series(0.0, index=pd.Index(sessions, name="session_date"))
    bys = t.groupby("session_date")["net"].sum()
    ser.loc[bys.index] = bys.to_numpy()
    x = ser.to_numpy()
    sd = x.std(ddof=1)
    sharpe = float(x.mean() / sd) if sd > 0 else 0.0
    ef = x - x.mean()
    obs = float(x.mean() / (sd / np.sqrt(len(x))))
    # numerator and denominator must come from the SAME resample. Drawing two independent
    # ones decorrelates them and over-disperses the null t, which errs conservative -- every
    # cell here failed, so no verdict moves -- but it is still the wrong statistic.
    def _boot_t():
        b = stationary_bootstrap(ef, len(x), rng)
        s = b.std(ddof=1)
        return b.mean() / (s / np.sqrt(len(b))) if s > 0 else 0.0

    p = float(np.mean([_boot_t() >= obs for _ in range(draws)])) if draws else 1.0
    taken = t[t["state"] == "taken"]
    skipped = t[t["state"] == "skipped"]
    return {
        "signals": len(t), "taken": len(taken), "take_rate": len(taken) / len(t),
        "per_taken": float(taken["net"].mean()) if len(taken) else 0.0,
        "per_signal": float(t["net"].sum() / len(t)),
        "skipped_cf": float(skipped["counterfactual"].mean()) if len(skipped) else np.nan,
        "sharpe_all": sharpe, "t": obs, "p": p,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data_5min")
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--draws", type=int, default=600)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    c = build_continuous(args.data, "ES", bar_size="5min")
    c = c[~c["thin_session"] & ~c["entries_blocked"]].copy()
    c["mso"] = minutes_since_open(c)
    sd = c["session_date"].astype(str)
    c = c[(sd >= args.start) & (sd <= args.end)]
    sessions = sorted(c["session_date"].unique())

    print("ENTRY VARIANTS: CONFIRM / STRONG / VOLUME / DAYBIAS")
    print("=" * 90)
    print(f"ES as MES, 1 contract, {len(sessions)} sessions. All market entries, $3.70 RT.")
    print("Every skipped signal counted at zero with its IMMEDIATE counterfactual shown.")
    print("CONFIRM is POST-HOC. Pre-registered. Runs ONCE.")
    print()
    print(f"  {'arm':<6}{'mode':<11}{'signals':>8}{'taken':>7}{'take%':>7}"
          f"{'$/taken':>9}{'$/signal':>10}{'skipped CF':>12}{'Sharpe':>9}{'p':>8}")

    rng = np.random.default_rng(args.seed)
    res = {}
    for arm, (ref, tr) in ARMS.items():
        for mode in MODES:
            t = run(c, ref, tr, mode)
            s = score(t, sessions, args.draws, rng)
            res[f"{arm}/{mode}"] = s
            cf = s.get("skipped_cf")
            print(f"  {arm:<6}{mode:<11}{s['signals']:>8}{s['taken']:>7}"
                  f"{s['take_rate']:>7.0%}{s['per_taken']:>9.2f}{s['per_signal']:>10.2f}"
                  f"{(f'{cf:+.2f}' if cf == cf else '-'):>12}"
                  f"{s['sharpe_all']:>9.3f}{s['p']:>8.4f}")
        print()

    alpha = 0.05 / 12
    print("=" * 90)
    print(f"  PRE-REGISTERED DECISION (Bonferroni across 12 cells, p < {alpha:.4f})")
    print(f"  {'cell':<20}{'mean>0':>8}{'p<a':>7}{'Sh>0.10':>9}{'2x':>6}{'>ctrl':>7}   verdict")
    rng2 = np.random.default_rng(args.seed)
    verdicts = {}
    for arm, (ref, tr) in ARMS.items():
        base = res[f"{arm}/IMMEDIATE"]
        for mode in MODES[1:]:
            s = res[f"{arm}/{mode}"]
            s2 = score(run(c, ref, tr, mode, spread_mult=2.0), sessions, 0, rng2)
            res[f"{arm}/{mode}"]["double_spread"] = s2["per_signal"]
            cs = (s["per_signal"] > 0, s["p"] < alpha, s["sharpe_all"] > 0.10,
                  s2["per_signal"] > 0, s["sharpe_all"] > base["sharpe_all"])
            ok = all(cs)
            verdicts[f"{arm}/{mode}"] = ok
            y = lambda b: "yes" if b else "no"          # noqa: E731
            print(f"  {arm + '/' + mode:<20}{y(cs[0]):>8}{y(cs[1]):>7}{y(cs[2]):>9}"
                  f"{y(cs[3]):>6}{y(cs[4]):>7}   {'PASS' if ok else 'FAIL'}")

    if any(verdicts.values()):
        print("\n  NOTE: any PASS here is EXPLORATORY. It is a hypothesis for the untouched")
        print("  2017-2023 set, not a result, and CONFIRM additionally is post-hoc.")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"cells": res, "alpha": alpha,
                                           "verdicts": verdicts}, indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
