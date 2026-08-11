#!/usr/bin/env python3
"""
The corrected 4-hour trend filter, and four confluence structures, on ES 5-minute bars.

Implements `docs/PREREGISTRATION_2026-08-11_TREND_CONFLUENCE.md` exactly. Committed before
this file was run. Nothing here may be changed after seeing a result.

  TREND4H-FIX   L2N breakout, 4-hour trend indexed on the FULL session series
  TREND4H-FVG   the FVG retracement entry, same corrected trend filter
  IFVG          inversion entry alone, run to establish the base rate
  SWEEP-FVG     sweep and reclaim, then a gap in the reclaim direction
  SWEEP-IFVG    sweep and reclaim, then an inversion in the reclaim direction

TREND4H-FIX is contaminated: the 63 late-break sessions from the previous run have been
seen. It is reported twice and the decontaminated number decides it.

A no-stop diagnostic runs alongside every arm. It attributes failure. It cannot pass.

Raw P&L: (exit - entry) x $5 x 1 contract.
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
COST_RT = 3.70                 # shown alongside, never deducted from the headline
NY = (0, 390)
LON = (-390, 0)
FVG_WINDOW = 12                # bars allowed for the retracement into a zone
SWEEP_WINDOW = 6               # bars allowed for the reclaim
TREND_BARS = 48                # 4 hours of 5-minute bars
MIN_TRADES = 100               # below this an arm is NOT SCORED, not failed

ARMS = ("TREND4H-FIX", "TREND4H-FVG", "IFVG", "SWEEP-FVG", "SWEEP-IFVG")
EXPECT = {"TREND4H-FIX": "45-60%", "TREND4H-FVG": "45-55%", "IFVG": "35-60%",
          "SWEEP-FVG": "25-45%", "SWEEP-IFVG": "15-35%"}


# --------------------------------------------------------------------------- session views

def session_views(s: pd.DataFrame):
    """Full session sorted by mso, plus the NY sub-window and its offset into the full."""
    full = s.sort_values("mso").reset_index(drop=True)
    ny_mask = (full["mso"] >= NY[0]) & (full["mso"] < NY[1])
    if not ny_mask.any():
        return None
    off = int(np.flatnonzero(ny_mask.to_numpy())[0])
    w = full.loc[ny_mask].reset_index(drop=True)
    return full, w, off


def trend_sign(full_close: np.ndarray, abs_i: int) -> float:
    """Sign of the 4-hour change, indexed on the FULL session series. 0 if unavailable."""
    j = abs_i - TREND_BARS
    if j < 0:
        return 0.0
    return float(np.sign(full_close[abs_i] - full_close[j]))


# ------------------------------------------------------------------------------ exit rules

def walk_exit(w, start, d, entry, stop, use_stop: bool):
    """Exit on the stop (if armed) or at the last bar of the NY window."""
    n = len(w)
    if start >= n:
        return None
    lo = w["low"].to_numpy(dtype=float)
    hi = w["high"].to_numpy(dtype=float)
    op = w["open"].to_numpy(dtype=float)
    cl = w["close"].to_numpy(dtype=float)
    for k in range(start, n):
        if use_stop:
            if d == 1 and lo[k] <= stop:
                return min(stop, op[k]) - entry
            if d == -1 and hi[k] >= stop:
                return entry - max(stop, op[k])
        if k == n - 1:
            return (cl[k] - entry) * d
    return None


# -------------------------------------------------------------------------- gap structures

def find_gaps(hi: np.ndarray, lo: np.ndarray):
    """Every 3-bar imbalance in the window, as (bar, direction, zone_low, zone_high)."""
    out = []
    for i in range(2, len(hi)):
        if lo[i] > hi[i - 2]:
            out.append((i, 1, hi[i - 2], lo[i]))
        elif hi[i] < lo[i - 2]:
            out.append((i, -1, hi[i], lo[i - 2]))
    return out


def _in_range(i, start, within):
    return i >= start and (within is None or i <= start + within)


def fvg_entry(w, gaps, start: int, want_dir: int | None, use_stop: bool, within=None):
    """First gap in range whose zone is retraced within FVG_WINDOW bars."""
    hi, lo = w["high"].to_numpy(dtype=float), w["low"].to_numpy(dtype=float)
    for i, d, zlo, zhi in gaps:
        if not _in_range(i, start, within) or (want_dir is not None and d != want_dir):
            continue
        entry = zhi if d == 1 else zlo
        stop = (zlo - TICK) if d == 1 else (zhi + TICK)
        for j in range(i + 1, min(i + 1 + FVG_WINDOW, len(w))):
            if (lo[j] <= entry) if d == 1 else (hi[j] >= entry):
                r = walk_exit(w, j + 1, d, entry, stop, use_stop)
                return None if r is None else {"pts": r, "dir": d}
        return {"pts": 0.0, "dir": d, "skipped": True}
    return None


def ifvg_entry(w, gaps, start: int, want_dir: int | None, use_stop: bool, within=None):
    """A gap whose far side is closed through, then retested from the other direction.

    A bearish gap [zlo, zhi] inverts when a close exceeds zhi; it then acts as support and
    the trade is long. A bullish gap inverts on a close below zlo and the trade is short.
    A gap that never inverts is not a signal, so the scan moves on to the next gap; the
    first gap that DOES invert is the signal, taken if retested and skipped if not.
    """
    hi, lo = w["high"].to_numpy(dtype=float), w["low"].to_numpy(dtype=float)
    cl = w["close"].to_numpy(dtype=float)
    for i, d, zlo, zhi in gaps:
        nd = -d                                   # the inverted, tradeable direction
        if not _in_range(i, start, within) or (want_dir is not None and nd != want_dir):
            continue
        for k in range(i + 1, len(w)):
            if not ((cl[k] > zhi) if nd == 1 else (cl[k] < zlo)):
                continue
            entry = zhi if nd == 1 else zlo       # retest of the inverted zone edge
            stop = (zlo - TICK) if nd == 1 else (zhi + TICK)
            for j in range(k + 1, len(w)):
                if (lo[j] <= entry) if nd == 1 else (hi[j] >= entry):
                    r = walk_exit(w, j + 1, nd, entry, stop, use_stop)
                    return None if r is None else {"pts": r, "dir": nd}
            return {"pts": 0.0, "dir": nd, "skipped": True}
    return None


def sweep_reclaim(w, prev_hi, prev_lo):
    """First sweep of a prior session extreme with a close back through it. Returns
    (reclaim_bar, direction) or ('skipped', direction) if it never reclaimed."""
    hi, lo = w["high"].to_numpy(dtype=float), w["low"].to_numpy(dtype=float)
    cl = w["close"].to_numpy(dtype=float)
    for i in range(len(w) - 2):
        for d, lvl, broke in ((1, prev_lo, lo[i] < prev_lo), (-1, prev_hi, hi[i] > prev_hi)):
            if not broke:
                continue
            for j in range(i, min(i + SWEEP_WINDOW, len(w))):
                if (cl[j] > lvl) if d == 1 else (cl[j] < lvl):
                    return j, d
            return None, d
    return None, None


# ----------------------------------------------------------------------------------- arms

def l2n_trend(s, use_stop: bool):
    v = session_views(s)
    if v is None:
        return None
    full, w, off = v
    r = s[(s["mso"] >= LON[0]) & (s["mso"] < LON[1])]
    if r.empty or len(w) < 4:
        return None
    rhi, rlo = float(r["high"].max()), float(r["low"].min())
    if rhi - rlo < 1.0:
        return None
    up, dn = rhi + TICK, rlo - TICK
    fc = full["close"].to_numpy(dtype=float)
    for i in range(len(w) - 2):
        b = w.iloc[i]
        hu, hd = b["high"] >= up, b["low"] <= dn
        if not (hu or hd):
            continue
        d = 1 if (hu and not hd) else (-1 if hd and not hu else
                                       (1 if b["close"] < b["open"] else -1))
        level, stop = (up, rlo) if d == 1 else (dn, rhi)
        entry = level if ((b["open"] <= level) if d == 1 else (b["open"] >= level)) \
            else float(b["open"])
        # the previous run's defect: i < TREND_BARS inside the NY window. Recorded so the
        # contaminated 63 can be identified and removed.
        late = i >= TREND_BARS
        if trend_sign(fc, i + off) != d:
            return {"pts": 0.0, "dir": d, "skipped": True, "late": late}
        rr = walk_exit(w, i + 1, d, entry, stop, use_stop)
        return None if rr is None else {"pts": rr, "dir": d, "late": late}
    return None


def fvg_trend(s, use_stop: bool):
    v = session_views(s)
    if v is None:
        return None
    full, w, off = v
    if len(w) < 8:
        return None
    hi, lo = w["high"].to_numpy(dtype=float), w["low"].to_numpy(dtype=float)
    fc = full["close"].to_numpy(dtype=float)
    gaps = find_gaps(hi, lo)
    if not gaps:
        return None
    i, d, zlo, zhi = gaps[0]
    if trend_sign(fc, i + off) != d:
        return {"pts": 0.0, "dir": d, "skipped": True}
    return fvg_entry(w, [gaps[0]], 0, None, use_stop)


def ifvg_alone(s, use_stop: bool):
    v = session_views(s)
    if v is None:
        return None
    _, w, _ = v
    if len(w) < 8:
        return None
    gaps = find_gaps(w["high"].to_numpy(dtype=float), w["low"].to_numpy(dtype=float))
    return None if not gaps else ifvg_entry(w, gaps, 0, None, use_stop)


def sweep_then(s, prev_hi, prev_lo, kind: str, use_stop: bool):
    if prev_hi is None:
        return None
    v = session_views(s)
    if v is None:
        return None
    _, w, _ = v
    if len(w) < 8:
        return None
    j, d = sweep_reclaim(w, prev_hi, prev_lo)
    if d is None:
        return None                       # no sweep at all: not a signal for this arm
    if j is None:
        return {"pts": 0.0, "dir": d, "skipped": True}   # swept, never reclaimed
    gaps = find_gaps(w["high"].to_numpy(dtype=float), w["low"].to_numpy(dtype=float))
    # SWEEP-FVG requires the gap to form within 12 bars of the reclaim; SWEEP-IFVG allows
    # the inversion anywhere later in the session, per the registration text.
    r = (fvg_entry(w, gaps, j, d, use_stop, within=FVG_WINDOW) if kind == "FVG"
         else ifvg_entry(w, gaps, j, d, use_stop))
    return {"pts": 0.0, "dir": d, "skipped": True} if r is None else r


# --------------------------------------------------------------------------------- scoring

def score(rows, draws, rng, subset=None):
    t = pd.DataFrame(rows)
    if t.empty:
        return {"signals": 0, "taken": 0}
    t["skipped"] = t.get("skipped", False)
    t["skipped"] = t["skipped"].fillna(False).astype(bool)
    if subset is not None:
        t = t[subset(t)]
        if t.empty:
            return {"signals": 0, "taken": 0}
    taken = t[~t["skipped"]]
    out = {"signals": len(t), "taken": len(taken),
           "take_rate": len(taken) / len(t) if len(t) else 0.0}
    if len(taken) < MIN_TRADES:
        return out
    usd = taken["pts"].to_numpy(dtype=float) * POINT
    se = usd.std(ddof=1) / np.sqrt(len(usd))
    k = max(1, int(0.05 * len(usd)))
    trim = np.sort(usd)[:-k]
    ef = usd - usd.mean()
    p = float(np.mean([stationary_bootstrap(ef, len(usd), rng).mean() / se >= usd.mean()
                       for _ in range(draws)])) if draws else 1.0
    out.update({"pts": float(usd.mean() / POINT), "usd": float(usd.mean()),
                "usd_net": float(usd.mean() - COST_RT), "total": float(usd.sum()),
                "wr": float((usd > 0).mean()), "t": float(usd.mean() / se),
                "t_trim": float(trim.mean() / (trim.std(ddof=1) / np.sqrt(len(trim)))),
                "p": p})
    return out


def collect(groups, prior_ext, arm: str, use_stop: bool):
    rows = []
    for sd_, s in groups:
        if arm == "TREND4H-FIX":
            r = l2n_trend(s, use_stop)
        elif arm == "TREND4H-FVG":
            r = fvg_trend(s, use_stop)
        elif arm == "IFVG":
            r = ifvg_alone(s, use_stop)
        else:
            ph, pl = prior_ext[sd_]
            r = sweep_then(s, ph, pl, "FVG" if arm == "SWEEP-FVG" else "IFVG", use_stop)
        if r is not None:
            rows.append(r)
    return rows


def fmt(arm, sc, expect):
    if sc.get("taken", 0) < MIN_TRADES:
        return (f"  {arm:<13}{sc.get('signals', 0):>8}{sc.get('taken', 0):>7}"
                f"{sc.get('take_rate', 0):>7.0%}{expect:>10}   under {MIN_TRADES}, NOT SCORED")
    return (f"  {arm:<13}{sc['signals']:>8}{sc['taken']:>7}{sc['take_rate']:>7.0%}"
            f"{expect:>10}{sc['pts']:>8.3f}{sc['usd']:>9.2f}{sc['usd_net']:>8.2f}"
            f"{sc['total']:>10,.0f}{sc['wr']:>6.0%}{sc['t']:>7.2f}"
            f"{sc['t_trim']:>7.2f}{sc['p']:>7.4f}")


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
    prior_ext, prev = {}, (None, None)
    for sd_, s in groups:
        prior_ext[sd_] = prev
        prev = (float(s["high"].max()), float(s["low"].min()))

    hdr = (f"  {'arm':<13}{'signals':>8}{'taken':>7}{'take%':>7}{'expect':>10}"
           f"{'pts':>8}{'$/trade':>9}{'net $':>8}{'total $':>10}{'WR':>6}"
           f"{'t':>7}{'t-5%':>7}{'p':>7}")

    print("4-HOUR TREND, CORRECTED, AND FOUR CONFLUENCE STRUCTURES -- RAW ENTRY/EXIT")
    print("=" * 100)
    print(f"ES 5-minute, {len(groups)} sessions {args.start[:4]}-{args.end[:4]}, "
          f"$5/pt, 1 contract. Pre-registered. Runs ONCE.")
    print()
    print(hdr)

    rng = np.random.default_rng(args.seed)
    res, raw = {}, {}
    for arm in ARMS:
        rows = collect(groups, prior_ext, arm, use_stop=True)
        raw[arm] = rows
        sc = score(rows, args.draws, rng)
        res[arm] = sc
        print(fmt(arm, sc, EXPECT[arm]))

    # --- pre-specified decontamination of TREND4H-FIX -------------------------------------
    print("\n" + "-" * 100)
    print("  DECONTAMINATION: TREND4H-FIX with the 63 already-seen late-break sessions removed")
    clean = score(raw["TREND4H-FIX"], args.draws, rng,
                  subset=lambda t: ~t.get("late", pd.Series(False, index=t.index))
                  .fillna(False).astype(bool))
    res["TREND4H-FIX-CLEAN"] = clean
    print(hdr)
    print(fmt("  (clean)", clean, EXPECT["TREND4H-FIX"]))

    # --- no-stop diagnostic: attribution only, cannot pass --------------------------------
    print("\n" + "-" * 100)
    print("  DIAGNOSTIC, NO STOP, FLAT AT THE NY CLOSE. Attributes failure. Cannot pass.")
    print(hdr)
    diag = {}
    for arm in ARMS:
        sc = score(collect(groups, prior_ext, arm, use_stop=False), args.draws, rng)
        diag[arm] = sc
        print(fmt(arm, sc, EXPECT[arm]))

    alpha = 0.05 / 5
    print("\n" + "=" * 100)
    print(f"  PRE-REGISTERED DECISION (Bonferroni across 5 arms, p < {alpha:.3f})")
    print(f"  {'arm':<13}{'mean>0':>9}{'p<a':>7}{'t-5%>2':>9}   verdict")
    verdicts = {}
    for arm in ARMS:
        sc = res["TREND4H-FIX-CLEAN"] if arm == "TREND4H-FIX" else res[arm]
        if sc.get("taken", 0) < MIN_TRADES:
            print(f"  {arm:<13}{'--':>9}{'--':>7}{'--':>9}   NOT SCORED")
            continue
        cs = (sc["usd"] > 0, sc["p"] < alpha, sc["t_trim"] > 2.0)
        ok = all(cs)
        verdicts[arm] = ok
        y = lambda b: "yes" if b else "no"              # noqa: E731
        note = "   (decontaminated)" if arm == "TREND4H-FIX" else ""
        print(f"  {arm:<13}{y(cs[0]):>9}{y(cs[1]):>7}{y(cs[2]):>9}   "
              f"{'PASS' if ok else 'FAIL'}{note}")

    if any(verdicts.values()):
        print("\n  A PASS IS NOT A RESULT. Cumulative trial count is forty-three.")
        print("  It is a hypothesis for the untouched 2017-2023 set.")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(
            {"arms": res, "diagnostic_no_stop": diag, "alpha": alpha,
             "verdicts": verdicts}, indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
