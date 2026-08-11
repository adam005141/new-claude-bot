#!/usr/bin/env python3
"""
Does 5-minute entry timing rescue a structure with no signal?

Implements `docs/PREREGISTRATION_2026-08-10_ENTRY_TIMING.md` exactly. Committed before this
file was run. Nothing here may be changed after seeing a result.

Three structures (unchanged from the cross-session test) x three entry modes:

  IMMEDIATE   market at the level on the 5-min bar that breaks it. Control, and a check
              that 5-minute reproduces the 30-minute result.
  PULLBACK    resting limit AT the level, filled only if price trades strictly THROUGH it
              within 6 five-minute bars. No fill, no trade.
  BIAS        as PULLBACK, and the break must agree with the prior session's midpoint.

THE LOAD-BEARING RULE: a skipped trade is not free and is not dropped. Every statistic runs
over EVERY session, with zero on sessions that signalled and did not fill. Reporting only
the filled trades would make any pullback rule look excellent and be wrong, because the
signals that never pull back are disproportionately the ones that ran.
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
FILL_WINDOW_BARS = 6          # one 30-minute bar, the resolution of the setup

ARMS = {"A2L": ((-930, -390), (-390, 0)),
        "L2N": ((-390, 0), (0, 390)),
        "NYOR": ((0, 60), (60, 390))}

# entry ticks, exit ticks. A resting limit crosses no spread on entry but still carries a
# latency/queue allowance; the exit is always a market order.
COSTS = {"IMMEDIATE": (1.0, 1.0), "PULLBACK": (0.5, 1.0), "BIAS": (0.5, 1.0)}


def prior_session_mid(c: pd.DataFrame) -> dict:
    """Midpoint of each session's full range, keyed by the NEXT session. Causal."""
    g = c.groupby("session_date")
    mid = ((g["high"].max() + g["low"].min()) / 2.0).sort_index()
    return dict(zip(mid.index[1:], mid.to_numpy()[:-1]))


def run(c: pd.DataFrame, ref: tuple[int, int], trade: tuple[int, int], mode: str,
        mids: dict, spread_mult: float = 1.0) -> pd.DataFrame:
    ent_t, exit_t = COSTS[mode]
    cost = (ent_t * spread_mult + exit_t * spread_mult) * TICK * POINT + COMMISSION_RT
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

        # --- locate the break -------------------------------------------------
        brk = None
        for i in range(len(w)):
            b = w.iloc[i]
            hu, hd = b["high"] >= up, b["low"] <= dn
            if hu and hd:
                took = "long" if b["close"] < b["open"] else "short"
            elif hu:
                took = "long"
            elif hd:
                took = "short"
            else:
                continue
            brk = (i, 1 if took == "long" else -1)
            break
        if brk is None:
            continue
        i0, d = brk
        level, stop = (up, lo) if d == 1 else (dn, hi)

        if mode == "BIAS":
            m = mids.get(sd)
            if m is None:
                continue
            want = 1 if level > m else -1
            if want != d:
                rows.append({"session_date": sd, "dir": d, "state": "bias_blocked",
                             "net": 0.0, "counterfactual": np.nan})
                continue

        # --- entry ------------------------------------------------------------
        if mode == "IMMEDIATE":
            b = w.iloc[i0]
            entry = level if (b["open"] <= level if d == 1 else b["open"] >= level) \
                else b["open"]
            start = i0 + 1
        else:
            # resting limit at the level; fills only on a strict trade-through
            entry = start = None
            for j in range(i0 + 1, min(i0 + 1 + FILL_WINDOW_BARS, len(w))):
                b = w.iloc[j]
                through = (b["low"] <= level - TICK) if d == 1 else (b["high"] >= level + TICK)
                if through:
                    entry, start = level, j + 1
                    break
            if entry is None:
                # counterfactual: what IMMEDIATE would have earned on this signal
                cf = _resolve(w, i0 + 1, d, level, stop,
                              (COSTS["IMMEDIATE"][0] + COSTS["IMMEDIATE"][1])
                              * spread_mult * TICK * POINT + COMMISSION_RT)
                rows.append({"session_date": sd, "dir": d, "state": "no_fill",
                             "net": 0.0, "counterfactual": cf})
                continue

        net = _resolve(w, start, d, entry, stop, cost)
        if net is None:
            continue
        rows.append({"session_date": sd, "dir": d, "state": "filled",
                     "net": net, "counterfactual": np.nan})
    return pd.DataFrame(rows)


def _resolve(w: pd.DataFrame, start: int, d: int, entry: float, stop: float,
             cost: float) -> float | None:
    """Walk forward from `start` to the stop or the end of the window."""
    if start >= len(w):
        return None
    for k in range(start, len(w)):
        b = w.iloc[k]
        last = k == len(w) - 1
        if d == 1 and b["low"] <= stop:
            return (min(stop, b["open"]) - entry) * POINT - cost
        if d == -1 and b["high"] >= stop:
            return (entry - max(stop, b["open"])) * POINT - cost
        if last:
            return (b["close"] - entry) * d * POINT - cost
    return None


def score(t: pd.DataFrame, sessions: list, draws: int, rng) -> dict:
    if t.empty:
        return {"signals": 0}
    ser = pd.Series(0.0, index=pd.Index(sessions, name="session_date"))
    bys = t.groupby("session_date")["net"].sum()
    ser.loc[bys.index] = bys.to_numpy()
    x = ser.to_numpy()
    sd_all = x.std(ddof=1)
    sharpe = float(x.mean() / sd_all) if sd_all > 0 else 0.0
    ef = x - x.mean()
    obs = float(x.mean() / (sd_all / np.sqrt(len(x))))
    null = [stationary_bootstrap(ef, len(x), rng) for _ in range(draws)]
    p = float(np.mean([b.mean() / (b.std(ddof=1) / np.sqrt(len(b))) >= obs for b in null]))
    filled = t[t["state"] == "filled"]
    nofill = t[t["state"] == "no_fill"]
    return {
        "signals": len(t), "filled": len(filled),
        "fill_rate": len(filled) / len(t),
        "blocked": int((t["state"] == "bias_blocked").sum()),
        "per_filled": float(filled["net"].mean()) if len(filled) else 0.0,
        "per_signal": float(t["net"].sum() / len(t)),
        "missed_cf": float(nofill["counterfactual"].mean()) if len(nofill) else np.nan,
        "net_total": float(t["net"].sum()),
        "sharpe_all": sharpe, "t": obs, "p": p,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data_5min")
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--draws", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    c = build_continuous(args.data, "ES", bar_size="5min")
    c = c[~c["thin_session"] & ~c["entries_blocked"]].copy()
    c["mso"] = minutes_since_open(c)
    sd = c["session_date"].astype(str)
    c = c[(sd >= args.start) & (sd <= args.end)]
    sessions = sorted(c["session_date"].unique())
    mids = prior_session_mid(c)

    print("5-MINUTE ENTRY TIMING")
    print("=" * 92)
    print(f"ES as MES, 1 contract, {len(sessions)} sessions {args.start[:4]}-{args.end[:4]}")
    print(f"limit fills only on a strict trade-through, within {FILL_WINDOW_BARS} bars")
    print("ALL statistics over EVERY session, zero on non-fills. Pre-registered. Runs ONCE.")
    print()
    print(f"  {'arm':<6}{'mode':<11}{'signals':>8}{'filled':>8}{'fill%':>7}"
          f"{'$/filled':>10}{'$/signal':>10}{'missed':>9}{'Sharpe':>9}{'p':>8}")

    rng = np.random.default_rng(args.seed)
    res = {}
    for arm, (ref, tr) in ARMS.items():
        for mode in ("IMMEDIATE", "PULLBACK", "BIAS"):
            t = run(c, ref, tr, mode, mids)
            s = score(t, sessions, args.draws, rng)
            res[f"{arm}/{mode}"] = s
            mc = s.get("missed_cf")
            print(f"  {arm:<6}{mode:<11}{s['signals']:>8}{s['filled']:>8}"
                  f"{s['fill_rate']:>7.0%}{s['per_filled']:>10.2f}{s['per_signal']:>10.2f}"
                  f"{(f'{mc:+.2f}' if mc == mc else '-'):>9}"
                  f"{s['sharpe_all']:>9.3f}{s['p']:>8.4f}")
        print()

    alpha = 0.05 / 6
    print("=" * 92)
    print(f"  PRE-REGISTERED DECISION (Bonferroni across 6 non-control cells, "
          f"nominal p < {alpha:.4f})")
    print(f"  {'cell':<18}{'mean>0':>8}{'p<a':>7}{'Sh>0.10':>9}{'2x sign':>9}"
          f"{'>control':>10}   verdict")
    rng2 = np.random.default_rng(args.seed)
    verdicts = {}
    for arm, (ref, tr) in ARMS.items():
        base = res[f"{arm}/IMMEDIATE"]
        for mode in ("PULLBACK", "BIAS"):
            s = res[f"{arm}/{mode}"]
            t2 = run(c, ref, tr, mode, mids, spread_mult=2.0)
            s2 = score(t2, sessions, 100, rng2)
            res[f"{arm}/{mode}"]["double_spread"] = s2["per_signal"]
            c1 = s["per_signal"] > 0
            c2 = s["p"] < alpha
            c3 = s["sharpe_all"] > 0.10
            c4 = s2["per_signal"] > 0
            c5 = s["sharpe_all"] > base["sharpe_all"]
            ok = all((c1, c2, c3, c4, c5))
            verdicts[f"{arm}/{mode}"] = ok
            f = lambda b: "yes" if b else "no"        # noqa: E731
            print(f"  {arm + '/' + mode:<18}{f(c1):>8}{f(c2):>7}{f(c3):>9}{f(c4):>9}"
                  f"{f(c5):>10}   {'PASS' if ok else 'FAIL'}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"cells": res, "alpha": alpha,
                                           "verdicts": verdicts}, indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
