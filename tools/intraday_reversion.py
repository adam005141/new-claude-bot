#!/usr/bin/env python3
"""
Intraday mean reversion on ES, with a higher-timeframe filter.

Implements `docs/PREREGISTRATION_2026-08-10_INTRADAY_REVERSION.md` exactly. Committed
before this file was run. Nothing here may be changed after seeing a result.

Session VWAP anchor on 5-minute bars, NY window only. Fade extensions of 2.0 sigma back to
the anchor, stop at 4.0, flat by the NY close.

  REV      fade every qualifying extension
  REV-HTF  fade only when the 60-minute move at signal time is under 1.0 session sigma,
           i.e. only when the higher timeframe is range-bound rather than directional

k_entry 2.0 and the 12-bar warm-up are carried verbatim from Leg A's registered config.
The stop at 4.0 is twice the entry. None of the three is a range to be searched.
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
K_ENTRY, K_STOP = 2.0, 4.0
MIN_BARS = 12                 # warm-up before any signal, from Leg A
HTF_BARS = 12                 # 60 minutes of 5-minute bars
HTF_MAX_SIGMA = 1.0
NY = (0, 390)


def session_trades(s: pd.DataFrame, mode: str, cost: float) -> dict | None:
    """One trade per session: first extension of K_ENTRY sigma from session VWAP."""
    w = s[(s["mso"] >= NY[0]) & (s["mso"] < NY[1])].sort_values("mso")
    if len(w) < MIN_BARS + 3:
        return None

    px = w["close"].to_numpy(dtype=float)
    hi = w["high"].to_numpy(dtype=float)
    lo = w["low"].to_numpy(dtype=float)
    op = w["open"].to_numpy(dtype=float)
    vol = pd.to_numeric(w["volume"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    tp = (hi + lo + px) / 3.0

    # causal session VWAP; falls back to a running mean where volume is absent
    cv = np.cumsum(vol)
    vwap = np.where(cv > 0, np.cumsum(tp * vol) / np.maximum(cv, 1e-12),
                    np.cumsum(tp) / np.arange(1, len(tp) + 1))
    spread = px - vwap
    sd = pd.Series(spread).expanding(min_periods=MIN_BARS).std(ddof=1).to_numpy()

    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.where(sd > 0, spread / sd, np.nan)

    for i in range(MIN_BARS, len(w) - 1):
        if not np.isfinite(z[i]) or abs(z[i]) < K_ENTRY:
            continue
        d = -1 if z[i] > 0 else 1          # fade: short when extended up

        if mode == "REV-HTF":
            j = i - HTF_BARS
            if j < 0 or not np.isfinite(sd[i]) or sd[i] <= 0:
                return {"state": "skipped", "net": 0.0, "cf": None}
            htf = abs(px[i] - px[j]) / sd[i]
            if htf >= HTF_MAX_SIGMA:
                cf = _walk(i, d, px, hi, lo, op, vwap, sd, cost)
                return {"state": "skipped", "net": 0.0, "cf": cf}

        net = _walk(i, d, px, hi, lo, op, vwap, sd, cost)
        if net is None:
            return None
        return {"state": "taken", "net": net, "cf": None, "dir": d}
    return None


def _walk(i, d, px, hi, lo, op, vwap, sd, cost):
    """Enter at the close of bar i, exit on the anchor, the stop, or the session end."""
    entry = px[i]
    for k in range(i + 1, len(px)):
        stop_px = vwap[k] + d * -1 * K_STOP * sd[k]     # 4 sigma further against us
        if d == 1 and lo[k] <= stop_px:
            return (min(stop_px, op[k]) - entry) * POINT - cost
        if d == -1 and hi[k] >= stop_px:
            return (entry - max(stop_px, op[k])) * POINT - cost
        # target: price back at the anchor
        if (d == 1 and hi[k] >= vwap[k]) or (d == -1 and lo[k] <= vwap[k]):
            return (vwap[k] - entry) * d * POINT - cost
        if k == len(px) - 1:
            return (px[k] - entry) * d * POINT - cost
    return None


def run(c: pd.DataFrame, mode: str, spread_mult: float = 1.0) -> pd.DataFrame:
    cost = 2.0 * 1.0 * spread_mult * TICK * POINT + COMMISSION_RT
    rows = []
    for sd_, s in c.groupby("session_date", sort=True):
        r = session_trades(s, mode, cost)
        if r is None:
            continue
        rows.append({"session_date": sd_, **r})
    return pd.DataFrame(rows)


def score(t, sessions, draws, rng):
    if t.empty:
        return {"signals": 0}
    ser = pd.Series(0.0, index=pd.Index(sessions, name="session_date"))
    bys = t.groupby("session_date")["net"].sum()
    ser.loc[bys.index] = bys.to_numpy()
    x = ser.to_numpy()
    s_ = x.std(ddof=1)
    ef = x - x.mean()
    obs = float(x.mean() / (s_ / np.sqrt(len(x)))) if s_ > 0 else 0.0
    p = 1.0
    if draws:
        nt = [stationary_bootstrap(ef, len(x), rng) for _ in range(draws)]
        p = float(np.mean([b.mean() / (b.std(ddof=1) / np.sqrt(len(b))) >= obs for b in nt]))
    taken = t[t["state"] == "taken"]
    skipped = t[t["state"] == "skipped"]
    cfs = skipped["cf"].dropna() if "cf" in skipped else pd.Series(dtype=float)
    return {
        "signals": len(t), "taken": len(taken), "take_rate": len(taken) / len(t),
        "per_taken": float(taken["net"].mean()) if len(taken) else 0.0,
        "per_signal": float(t["net"].sum() / len(t)),
        "gross_per_taken": float(taken["net"].mean()) + 3.70 if len(taken) else 0.0,
        "wr": float((taken["net"] > 0).mean()) if len(taken) else 0.0,
        "skipped_cf": float(cfs.mean()) if len(cfs) else np.nan,
        "sharpe_all": float(x.mean() / s_) if s_ > 0 else 0.0,
        "t": obs, "p": p,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data_5min")
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--draws", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    c = build_continuous(args.data, "ES", bar_size="5min")
    c = c[~c["thin_session"] & ~c["entries_blocked"]].copy()
    c["mso"] = minutes_since_open(c)
    sd = c["session_date"].astype(str)
    c = c[(sd >= args.start) & (sd <= args.end)]
    sessions = sorted(c["session_date"].unique())

    print("INTRADAY MEAN REVERSION, ES 5-MIN, NY SESSION")
    print("=" * 88)
    print(f"{len(sessions)} sessions {args.start[:4]}-{args.end[:4]}, VWAP anchor, "
          f"fade at {K_ENTRY}σ, stop {K_STOP}σ, $3.70 RT")
    print("Funded-account bars dropped; costs retained. Pre-registered. Runs ONCE.")
    print()
    print(f"  {'arm':<9}{'signals':>8}{'taken':>7}{'take%':>7}{'gross/tk':>10}"
          f"{'net/tk':>9}{'net/sig':>9}{'WR':>6}{'skip CF':>9}{'Sharpe':>9}{'p':>8}")

    rng = np.random.default_rng(args.seed)
    res = {}
    for mode in ("REV", "REV-HTF"):
        t = run(c, mode)
        s = score(t, sessions, args.draws, rng)
        res[mode] = s
        cf = s.get("skipped_cf")
        print(f"  {mode:<9}{s['signals']:>8}{s['taken']:>7}{s['take_rate']:>7.0%}"
              f"{s['gross_per_taken']:>10.2f}{s['per_taken']:>9.2f}{s['per_signal']:>9.2f}"
              f"{s['wr']:>6.0%}{(f'{cf:+.2f}' if cf == cf else '-'):>9}"
              f"{s['sharpe_all']:>9.3f}{s['p']:>8.4f}")

    alpha = 0.05 / 2
    print("\n" + "=" * 88)
    print(f"  PRE-REGISTERED DECISION (Bonferroni across 2 arms, p < {alpha:.4f})")
    print(f"  {'arm':<9}{'mean>0':>9}{'p<a':>7}{'2x sign':>9}   verdict")
    rng2 = np.random.default_rng(args.seed)
    verdicts = {}
    for mode in ("REV", "REV-HTF"):
        s = res[mode]
        s2 = score(run(c, mode, spread_mult=2.0), sessions, 0, rng2)
        res[mode]["double_spread"] = s2["per_signal"]
        cs = (s["per_signal"] > 0, s["p"] < alpha, s2["per_signal"] > 0)
        ok = all(cs)
        verdicts[mode] = ok
        y = lambda b: "yes" if b else "no"              # noqa: E731
        print(f"  {mode:<9}{y(cs[0]):>9}{y(cs[1]):>7}{y(cs[2]):>9}   "
              f"{'PASS' if ok else 'FAIL'}   2x: ${s2['per_signal']:+.2f}/signal")

    if any(verdicts.values()):
        print("\n  A PASS HERE IS NOT A RESULT. Cumulative trial count is 33 and this")
        print("  re-opens a closed leg. It is a hypothesis for the untouched 2017-2023 set.")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"arms": res, "alpha": alpha,
                                           "verdicts": verdicts}, indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
