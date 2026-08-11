#!/usr/bin/env python3
"""
BASE, TOM and DOW arms of the event-conditioned overnight pre-registration.

See `docs/PREREGISTRATION_2026-08-09_EVENT_OVERNIGHT.md`, written before any pre-2024 ES
data existed on disk, plus Amendments 1 and 2. Nothing here may be changed after seeing a
result. The FOMC arm is held pending a sourced announcement calendar.

WHAT IS HELD
------------
Enter at the session open, **18:00 ET**, exit at **09:30 ET**. Forced by the account rules:
flat is required through the 17:00-18:00 ET maintenance halt, so a continuous 16:00-to-09:30
hold is not tradeable. Same window Leg D used.

One MES contract. Size is irrelevant to every criterion here except the dollar columns,
because size scales edge and noise identically and cannot move Sharpe.

Session dates run 18:00 ET the previous evening to 17:00 ET, so a single session_date
contains both the entry bar (mso -930) and the exit bar (mso 0). The hold never crosses a
session boundary, which is what makes the roll and thin-session guards sufficient.

COSTS
-----
MES at one tick of spread plus half a tick of slippage per side, which is this project's
measured adverse model from 348,857 MES quote-bars. That gives $1.25 a side, $2.50 round
turn, plus $1.20 commission, so **$3.70 a night**.

Stated plainly: that spread was measured on RECENT data, and it is applied here to
2009-2016. Two things push in opposite directions and neither is quantified.

  * ES has been one tick wide for most of its life, because its tick is large relative to
    its volatility, so the spread itself probably transfers.
  * But entry is at 18:00 ET, the thinnest moment of the session, where the book is wider
    than the RTH figure this model was measured in.

A 2x sensitivity is reported for exactly this reason. If a result survives at 1x and dies
at 2x, it is not a result.

DOW IS DELIBERATELY HANDICAPPED
-------------------------------
The weekday is chosen on **2009-2012** and then applied unchanged to **2013-2016**, and only
the 2013-2016 half is scored. Choosing on the full sample and reporting the winner would be
selection dressed as a finding. Under Amendment 1 the selection window is 2009-2012 rather
than the registered 2008-2012, because 2008 does not exist in the archive.

Because DOW is scored on a different span from BASE and TOM, BASE is reported on that same
2013-2016 span as well, so criterion 4 compares like with like.
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

MES_POINT = 5.0
MES_TICK = 0.25
HALF_SPREAD_TICKS = 0.5      # ES quotes one tick wide
BASE_SLIP_TICKS = 0.5        # latency and adverse selection allowance
COMMISSION_RT = 1.20

ENTRY_MSO = -930             # 18:00 ET, the session open
EXIT_MSO = 0                 # 09:30 ET


def overnight_pnl(data: str, symbol: str, spread_mult: float = 1.0) -> pd.DataFrame:
    """One row per session: the 18:00 ET to 09:30 ET hold, net of costs."""
    c = build_continuous(data, symbol, bar_size="30min")
    c = c[~c["thin_session"] & ~c["entries_blocked"]].copy()
    c["mso"] = minutes_since_open(c)

    ent = (c[c["mso"] == ENTRY_MSO]
           .sort_values("timestamp_utc")
           .groupby("session_date")
           .first()[["open", "contract_month"]]
           .rename(columns={"open": "entry", "contract_month": "cm_in"}))
    ext = (c[c["mso"] == EXIT_MSO]
           .sort_values("timestamp_utc")
           .groupby("session_date")
           .first()[["open", "contract_month"]]
           .rename(columns={"open": "exit", "contract_month": "cm_out"}))

    d = ent.join(ext, how="inner")
    # A hold that changes contract mid-flight is not a hold. Should never happen given the
    # session-date construction, so it is asserted rather than silently tolerated.
    mixed = int((d["cm_in"] != d["cm_out"]).sum())
    if mixed:
        raise ValueError(f"{symbol}: {mixed} sessions change contract between 18:00 and "
                         f"09:30; the session-date construction is wrong")

    side = HALF_SPREAD_TICKS * spread_mult + BASE_SLIP_TICKS
    cost = 2.0 * side * MES_TICK * MES_POINT + COMMISSION_RT
    d = d.reset_index()
    d["gross"] = (d["exit"] - d["entry"]) * MES_POINT
    d["net"] = d["gross"] - cost
    d["date"] = pd.to_datetime(d["session_date"])
    return d.sort_values("date").reset_index(drop=True)


def tag_windows(d: pd.DataFrame) -> pd.DataFrame:
    """Mark the turn-of-month sessions: last trading day of a month, and the first three."""
    d = d.copy()
    ym = d["date"].dt.to_period("M")
    rank_in = d.groupby(ym).cumcount()                      # 0,1,2,... from month start
    rank_out = d.groupby(ym).cumcount(ascending=False)      # 0 on the last of the month
    d["tom"] = (rank_in <= 2) | (rank_out == 0)
    d["dow"] = d["date"].dt.dayofweek
    return d


def score(full: pd.DataFrame, mask: pd.Series, draws: int, rng) -> dict:
    """
    Score one arm over EVERY session in the window, zero on nights not traded.

    That is the series the account actually experiences, and it is what makes
    Sharpe_all = sqrt(f) * Sharpe_on_trading_nights fall out rather than being asserted.
    """
    series = np.where(mask.to_numpy(), full["net"].to_numpy(), 0.0)
    traded = full.loc[mask, "net"].to_numpy()
    n_all, n_tr = len(series), len(traded)
    if n_tr < 2:
        return {"n_sessions": n_all, "n_traded": n_tr}

    sd_all = series.std(ddof=1)
    sharpe_all = float(series.mean() / sd_all) if sd_all > 0 else 0.0
    sharpe_tr = float(traded.mean() / traded.std(ddof=1)) if traded.std(ddof=1) > 0 else 0.0

    edge_free = series - series.mean()
    obs_t = float(series.mean() / (sd_all / np.sqrt(n_all)))
    null_t = []
    for _ in range(draws):
        b = stationary_bootstrap(edge_free, n_all, rng)
        null_t.append(b.mean() / (b.std(ddof=1) / np.sqrt(len(b))))
    p = float((np.array(null_t) >= obs_t).mean())

    return {
        "n_sessions": n_all, "n_traded": n_tr, "f": n_tr / n_all,
        "net_total": float(traded.sum()),
        "mean_per_night": float(traded.mean()),
        "mean_per_session": float(series.mean()),
        "sharpe_all": sharpe_all, "sharpe_traded": sharpe_tr,
        "t": obs_t, "p": p,
    }


def show(name: str, s: dict) -> None:
    if s.get("n_traded", 0) < 2:
        print(f"  {name:<6}{'insufficient nights':>30}")
        return
    print(f"  {name:<6}{s['n_sessions']:>9}{s['n_traded']:>9}{s['f']:>7.2f}"
          f"{s['net_total']:>11,.0f}{s['mean_per_night']:>11.2f}"
          f"{s['sharpe_traded']:>9.3f}{s['sharpe_all']:>10.3f}{s['p']:>9.4f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data_history")
    ap.add_argument("--symbol", default="ES")
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--dow-split", default="2012-12-31",
                    help="DOW weekday chosen on or before this date, scored after it")
    ap.add_argument("--draws", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    d = tag_windows(overnight_pnl(args.data, args.symbol))
    d = d[(d["date"] >= args.start) & (d["date"] <= args.end)].reset_index(drop=True)

    print("OVERNIGHT ARMS: BASE / TOM / DOW")
    print("=" * 82)
    print(f"{args.symbol} priced as MES, 1 contract, 18:00 ET -> 09:30 ET, "
          f"${2 * (HALF_SPREAD_TICKS + BASE_SLIP_TICKS) * MES_TICK * MES_POINT + COMMISSION_RT:.2f}/night cost")
    print(f"{len(d)} sessions, {d['date'].min().date()} to {d['date'].max().date()}")
    print("Pre-registered. FOMC arm held pending a sourced calendar. This runs ONCE.")
    print()
    print(f"  {'arm':<6}{'sessions':>9}{'nights':>9}{'f':>7}{'net $':>11}"
          f"{'$/night':>11}{'Sh(trade)':>9}{'Sh(all)':>10}{'p':>9}")

    rng = np.random.default_rng(args.seed)
    res = {}
    res["BASE"] = score(d, pd.Series(True, index=d.index), args.draws, rng)
    show("BASE", res["BASE"])
    res["TOM"] = score(d, d["tom"], args.draws, rng)
    show("TOM", res["TOM"])

    # ---- DOW: pick on the early half, score on the late half ----------------
    early = d[d["date"] <= args.dow_split]
    late = d[d["date"] > args.dow_split].reset_index(drop=True)
    by_day = early.groupby("dow")["net"].mean()
    pick = int(by_day.idxmax())
    names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    print()
    print(f"  DOW selection on {early['date'].min().date()}..{args.dow_split}, "
          f"mean $/night by weekday:")
    print("    " + "  ".join(f"{names[k]} {v:+.2f}" for k, v in by_day.items() if k < 5))
    print(f"    chosen: {names[pick]}. Frozen; scored only on "
          f"{late['date'].min().date()} onward.")
    print()
    res["DOW"] = score(late, late["dow"] == pick, args.draws, rng)
    res["BASE_late"] = score(late, pd.Series(True, index=late.index), args.draws, rng)
    print(f"  {'arm':<6}{'sessions':>9}{'nights':>9}{'f':>7}{'net $':>11}"
          f"{'$/night':>11}{'Sh(trade)':>9}{'Sh(all)':>10}{'p':>9}")
    show("DOW", res["DOW"])
    show("BASE*", res["BASE_late"])
    print("    BASE* is BASE restricted to the DOW scoring window, so criterion 4")
    print("    compares like with like.")

    # ---- the pre-registered decision ---------------------------------------
    # Amendment 2: with FOMC held, Bonferroni runs across TWO conditioning arms.
    alpha = 0.05 / 2
    print("\n" + "=" * 82)
    print(f"  PRE-REGISTERED DECISION (Bonferroni across 2 conditioning arms, "
          f"nominal p < {alpha:.4f})")
    print(f"  {'arm':<6}{'mean>0':>9}{'p<a':>8}{'Sh>0.10':>9}{'>BASE':>8}   verdict")
    verdicts = {}
    for arm in ("TOM", "DOW"):
        s = res[arm]
        base = res["BASE"] if arm == "TOM" else res["BASE_late"]
        c1 = s["mean_per_session"] > 0
        c2 = s["p"] < alpha
        c3 = s["sharpe_all"] > 0.10
        c4 = s["sharpe_all"] > base["sharpe_all"]
        ok = c1 and c2 and c3 and c4
        verdicts[arm] = ok
        print(f"  {arm:<6}{'yes' if c1 else 'no':>9}{'yes' if c2 else 'no':>8}"
              f"{'yes' if c3 else 'no':>9}{'yes' if c4 else 'no':>8}   "
              f"{'PASS' if ok else 'FAIL'}")
    b = res["BASE"]
    print(f"\n  BASE (control, not corrected): Sharpe_all {b['sharpe_all']:.3f}, "
          f"p {b['p']:.4f}, ${b['mean_per_night']:.2f}/night")

    # ---- 2x spread sensitivity ---------------------------------------------
    d2 = tag_windows(overnight_pnl(args.data, args.symbol, spread_mult=2.0))
    d2 = d2[(d2["date"] >= args.start) & (d2["date"] <= args.end)].reset_index(drop=True)
    rng2 = np.random.default_rng(args.seed)
    print("\n  2x SPREAD SENSITIVITY (registered in advance)")
    print(f"  {'arm':<6}{'Sh(all)':>10}{'$/night':>11}")
    for arm, mask in (("BASE", pd.Series(True, index=d2.index)), ("TOM", d2["tom"])):
        s = score(d2, mask, 200, rng2)
        print(f"  {arm:<6}{s['sharpe_all']:>10.3f}{s['mean_per_night']:>11.2f}")

    print("\n  PER-YEAR, BASE arm")
    yr = d.groupby(d["date"].dt.year)["net"]
    print("    " + "  ".join(f"{y}:{v.mean():+.1f}" for y, v in yr))

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(
            {"arms": res, "dow_pick": names[pick], "alpha": alpha,
             "verdicts": verdicts}, indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
