#!/usr/bin/env python3
"""
Three ICT structures and two quant filters on ES 5-minute bars.

Implements `docs/PREREGISTRATION_2026-08-10_ICT_QUANT.md` exactly. Committed before this
file was run. Nothing here may be changed after seeing a result.

  FVG      three-bar imbalance, entry on retracement into the zone
  SWEEP    stop run below the prior session low, entry on the reclaim
  SILVER   the best structure so far, restricted to 10:00-11:00 ET
  TREND4H  L2N breakout filtered by the sign of the 48-bar (4-hour) change
  VOLLOW   L2N breakout, lowest tercile of reference range vs the trailing 60 sessions

ICT ideas are testable only once stated as arithmetic. Anything requiring discretionary
chart reading is excluded rather than approximated.

Raw P&L: (exit - entry) x $5 x 1 contract. A cost-inclusive column is shown alongside.
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
COST_RT = 3.70                 # shown alongside, not deducted from the headline
NY = (0, 390)
LON = (-390, 0)
FVG_WINDOW = 12
SWEEP_WINDOW = 6
TREND_BARS = 48                # 4 hours of 5-minute bars
VOL_LOOKBACK = 60


def _exit_at_end(w, start, d, entry, stop):
    for k in range(start, len(w)):
        b = w.iloc[k]
        if d == 1 and b["low"] <= stop:
            return min(stop, b["open"]) - entry
        if d == -1 and b["high"] >= stop:
            return entry - max(stop, b["open"])
        if k == len(w) - 1:
            return (b["close"] - entry) * d
    return None


def fvg(s):
    """Bullish gap when low[i] > high[i-2]; enter on retracement into the zone."""
    w = s[(s["mso"] >= NY[0]) & (s["mso"] < NY[1])].sort_values("mso").reset_index(drop=True)
    if len(w) < 8:
        return None
    hi, lo = w["high"].to_numpy(), w["low"].to_numpy()
    for i in range(2, len(w) - 3):
        up = lo[i] > hi[i - 2]
        dn = hi[i] < lo[i - 2]
        if not (up or dn):
            continue
        d = 1 if up else -1
        top, bot = (lo[i], hi[i - 2]) if up else (lo[i - 2], hi[i])
        entry = top if up else bot
        stop = bot - TICK if up else top + TICK
        for j in range(i + 1, min(i + 1 + FVG_WINDOW, len(w))):
            touched = lo[j] <= entry if up else hi[j] >= entry
            if touched:
                r = _exit_at_end(w, j + 1, d, entry, stop)
                return None if r is None else {"pts": r, "dir": d}
        return {"pts": 0.0, "dir": d, "skipped": True}
    return None


def sweep(s, prev_hi, prev_lo):
    """Trade below the prior session's low then close back above it within 6 bars."""
    if prev_hi is None:
        return None
    w = s[(s["mso"] >= NY[0]) & (s["mso"] < NY[1])].sort_values("mso").reset_index(drop=True)
    if len(w) < 8:
        return None
    for i in range(len(w) - 2):
        b = w.iloc[i]
        for d, lvl, broke in ((1, prev_lo, b["low"] < prev_lo),
                              (-1, prev_hi, b["high"] > prev_hi)):
            if not broke:
                continue
            ext = b["low"] if d == 1 else b["high"]
            for j in range(i, min(i + SWEEP_WINDOW, len(w))):
                c = w.iloc[j]
                back = c["close"] > lvl if d == 1 else c["close"] < lvl
                if back:
                    r = _exit_at_end(w, j + 1, d, c["close"],
                                     ext - TICK if d == 1 else ext + TICK)
                    return None if r is None else {"pts": r, "dir": d}
            return {"pts": 0.0, "dir": d, "skipped": True}
    return None


def l2n_break(s, filt=None, ctx=None):
    """The L2N breakout, optionally filtered. Returns points, or a skipped marker."""
    r = s[(s["mso"] >= LON[0]) & (s["mso"] < LON[1])]
    w = s[(s["mso"] >= NY[0]) & (s["mso"] < NY[1])].sort_values("mso").reset_index(drop=True)
    if r.empty or len(w) < 4:
        return None
    hi, lo = r["high"].max(), r["low"].min()
    if hi - lo < 1.0:
        return None
    up, dn = hi + TICK, lo - TICK
    px = w["close"].to_numpy()
    for i in range(len(w) - 2):
        b = w.iloc[i]
        hu, hd = b["high"] >= up, b["low"] <= dn
        if not (hu or hd):
            continue
        d = 1 if (hu and not hd) else (-1 if hd and not hu else
                                       (1 if b["close"] < b["open"] else -1))
        level, stop = (up, lo) if d == 1 else (dn, hi)
        entry = level if (b["open"] <= level if d == 1 else b["open"] >= level) else b["open"]

        if filt == "STRONG":
            rng = b["high"] - b["low"]
            ok = rng > 0 and ((b["close"] - b["low"]) / rng >= 0.75 if d == 1
                              else (b["close"] - b["low"]) / rng <= 0.25)
            if not ok:
                return {"pts": 0.0, "dir": d, "skipped": True}
        if filt == "SILVER":
            rng = b["high"] - b["low"]
            strong = rng > 0 and ((b["close"] - b["low"]) / rng >= 0.75 if d == 1
                                  else (b["close"] - b["low"]) / rng <= 0.25)
            if not (strong and 30 <= b["mso"] < 90):     # 10:00-11:00 ET
                return {"pts": 0.0, "dir": d, "skipped": True}
        if filt == "TREND4H":
            j = i - TREND_BARS
            trend = np.sign(px[i] - px[j]) if j >= 0 else 0.0
            if trend == 0 or trend != d:
                return {"pts": 0.0, "dir": d, "skipped": True}
        if filt == "VOLLOW":
            if ctx is None or not ctx:
                return {"pts": 0.0, "dir": d, "skipped": True}

        rr = _exit_at_end(w, i + 1, d, entry, stop)
        return None if rr is None else {"pts": rr, "dir": d}
    return None


def score(rows, draws, rng):
    t = pd.DataFrame(rows)
    if t.empty:
        return {"signals": 0}
    t["skipped"] = t.get("skipped", False)
    t["skipped"] = t["skipped"].fillna(False)
    taken = t[~t["skipped"]]
    if len(taken) < 20:
        return {"signals": len(t), "taken": len(taken)}
    pts = taken["pts"].to_numpy(dtype=float)
    usd = pts * POINT
    se = usd.std(ddof=1) / np.sqrt(len(usd))
    tt = float(usd.mean() / se)
    # concentration: drop the best 5% of trades
    k = max(1, int(0.05 * len(usd)))
    trim = np.sort(usd)[:-k]
    t_trim = float(trim.mean() / (trim.std(ddof=1) / np.sqrt(len(trim))))
    ef = usd - usd.mean()
    p = float(np.mean([stationary_bootstrap(ef, len(usd), rng).mean() /
                       (usd.std(ddof=1) / np.sqrt(len(usd))) >= usd.mean()
                       for _ in range(draws)])) if draws else 1.0
    return {"signals": len(t), "taken": len(taken),
            "take_rate": len(taken) / len(t),
            "pts": float(pts.mean()), "usd": float(usd.mean()),
            "usd_net": float(usd.mean() - COST_RT),
            "total": float(usd.sum()), "wr": float((usd > 0).mean()),
            "t": tt, "t_trim": t_trim, "p": p}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data_5min")
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--draws", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    c = build_continuous(args.data, "ES", bar_size="5min")
    c = c[~c["thin_session"] & ~c["entries_blocked"]].copy()
    c["mso"] = minutes_since_open(c)
    sd = c["session_date"].astype(str)
    c = c[(sd >= args.start) & (sd <= args.end)]

    groups = list(c.groupby("session_date", sort=True))
    # prior-session extremes and the causal low-volatility tercile
    ref_rng, prev = [], (None, None)
    ctx_vol, prior_ext = {}, {}
    for sd_, s in groups:
        prior_ext[sd_] = prev
        prev = (s["high"].max(), s["low"].min())
        r = s[(s["mso"] >= LON[0]) & (s["mso"] < LON[1])]
        cur = (r["high"].max() - r["low"].min()) if not r.empty else np.nan
        ctx_vol[sd_] = (len(ref_rng) >= VOL_LOOKBACK and cur == cur
                        and cur <= np.nanpercentile(ref_rng[-VOL_LOOKBACK:], 33.3))
        if cur == cur:
            ref_rng.append(cur)

    print("ICT STRUCTURES AND QUANT FILTERS -- RAW ENTRY/EXIT")
    print("=" * 94)
    print(f"ES 5-minute, {len(groups)} sessions {args.start[:4]}-{args.end[:4]}, "
          f"$5/pt, 1 contract. Pre-registered. Runs ONCE.")
    print()
    print(f"  {'arm':<10}{'signals':>8}{'taken':>7}{'take%':>7}{'expected':>11}"
          f"{'pts':>8}{'$/trade':>9}{'net $':>8}{'total $':>10}{'WR':>6}"
          f"{'t':>7}{'t-5%':>7}{'p':>7}")

    rng = np.random.default_rng(args.seed)
    expect = {"FVG": "30-50%", "SWEEP": "15-25%", "SILVER": "10-20%",
              "TREND4H": "45-60%", "VOLLOW": "~33%"}
    res = {}
    for arm in ("FVG", "SWEEP", "SILVER", "TREND4H", "VOLLOW"):
        rows = []
        for sd_, s in groups:
            if arm == "FVG":
                r = fvg(s)
            elif arm == "SWEEP":
                ph, pl = prior_ext[sd_]
                r = sweep(s, ph, pl)
            elif arm == "SILVER":
                r = l2n_break(s, "SILVER")
            elif arm == "TREND4H":
                r = l2n_break(s, "TREND4H")
            else:
                r = l2n_break(s, "VOLLOW", ctx_vol.get(sd_, False))
            if r is not None:
                rows.append(r)
        sc = score(rows, args.draws, rng)
        res[arm] = sc
        if sc.get("taken", 0) < 20:
            print(f"  {arm:<10}{sc.get('signals', 0):>8}{sc.get('taken', 0):>7}"
                  f"{'':>7}{expect[arm]:>11}   too few trades to score")
            continue
        print(f"  {arm:<10}{sc['signals']:>8}{sc['taken']:>7}{sc['take_rate']:>7.0%}"
              f"{expect[arm]:>11}{sc['pts']:>8.3f}{sc['usd']:>9.2f}{sc['usd_net']:>8.2f}"
              f"{sc['total']:>10,.0f}{sc['wr']:>6.0%}{sc['t']:>7.2f}"
              f"{sc['t_trim']:>7.2f}{sc['p']:>7.4f}")

    alpha = 0.05 / 5
    print("\n" + "=" * 94)
    print(f"  PRE-REGISTERED DECISION (Bonferroni across 5 arms, p < {alpha:.3f})")
    print(f"  {'arm':<10}{'mean>0':>9}{'p<a':>7}{'|t-5%|>2':>10}   verdict")
    verdicts = {}
    for arm, sc in res.items():
        if sc.get("taken", 0) < 20:
            print(f"  {arm:<10}{'--':>9}{'--':>7}{'--':>10}   NOT SCORED")
            continue
        cs = (sc["usd"] > 0, sc["p"] < alpha, abs(sc["t_trim"]) > 2.0 and sc["t_trim"] > 0)
        ok = all(cs)
        verdicts[arm] = ok
        y = lambda b: "yes" if b else "no"              # noqa: E731
        print(f"  {arm:<10}{y(cs[0]):>9}{y(cs[1]):>7}{y(cs[2]):>10}   "
              f"{'PASS' if ok else 'FAIL'}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"arms": res, "alpha": alpha,
                                           "verdicts": verdicts}, indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
