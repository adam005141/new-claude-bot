#!/usr/bin/env python3
"""
Cross-session range breakouts: Asia into London, London into NY, NY open into NY.

Implements `docs/PREREGISTRATION_2026-08-10_CROSS_SESSION.md` exactly. Committed before
this file was run against ES. Nothing here may be changed after seeing a result.

Two-sided by design. Leg B and the commodity ORB were both long only, and Block A's
post-mortem named that as the likely cause of failure: a long-only breakout is a
trend-following structure that cannot work when the trend is absent or against it.
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

POINT, TICK = 5.0, 0.25              # priced as MES
HALF_SPREAD_TICKS, BASE_SLIP_TICKS = 0.5, 0.5
COMMISSION_RT = 1.20
MIN_RANGE_PTS = 1.00                 # 4 ticks; a stop must cover the 0.5 pt round trip
BUFFER_TICKS = 1.0

# arm -> (reference window, trade window), in minutes since the 09:30 ET open
ARMS = {
    "A2L":  ((-930, -390), (-390, 0)),
    "L2N":  ((-390, 0), (0, 390)),
    "NYOR": ((0, 60), (60, 390)),
}


def run_arm(c: pd.DataFrame, ref: tuple[int, int], trade: tuple[int, int],
            spread_mult: float = 1.0) -> pd.DataFrame:
    """One trade per session: first break of the reference range, either direction."""
    side_ticks = HALF_SPREAD_TICKS * spread_mult + BASE_SLIP_TICKS
    cost = 2.0 * side_ticks * TICK * POINT + COMMISSION_RT
    buf = BUFFER_TICKS * TICK

    rows = []
    for sd, s in c.groupby("session_date", sort=True):
        r = s[(s["mso"] >= ref[0]) & (s["mso"] < ref[1])]
        w = s[(s["mso"] >= trade[0]) & (s["mso"] < trade[1])].sort_values("mso")
        if r.empty or len(w) < 2:
            continue
        hi, lo = r["high"].max(), r["low"].min()
        if (hi - lo) < MIN_RANGE_PTS:
            continue
        up, dn = hi + buf, lo - buf

        pos = None
        for i in range(len(w)):
            b = w.iloc[i]
            last = i == len(w) - 1
            if pos is None:
                # A bar that spans both levels is ambiguous about which came first.
                # Resolved against the strategy: take the side that ends up losing on
                # that bar, rather than assuming the favourable ordering.
                hit_up, hit_dn = b["high"] >= up, b["low"] <= dn
                if hit_up and hit_dn:
                    took = "long" if b["close"] < b["open"] else "short"
                elif hit_up:
                    took = "long"
                elif hit_dn:
                    took = "short"
                else:
                    continue
                if took == "long":
                    entry = up if b["open"] <= up else b["open"]
                    stop = lo
                else:
                    entry = dn if b["open"] >= dn else b["open"]
                    stop = hi
                pos = {"dir": 1 if took == "long" else -1, "entry": entry,
                       "stop": stop, "i": i, "entry_utc": b["timestamp_utc"]}
                continue

            px = reason = None
            if pos["dir"] == 1 and b["low"] <= pos["stop"]:
                px, reason = min(pos["stop"], b["open"]), "stop"
            elif pos["dir"] == -1 and b["high"] >= pos["stop"]:
                px, reason = max(pos["stop"], b["open"]), "stop"
            elif last:
                px, reason = b["close"], "eow"
            if px is not None:
                gross = (px - pos["entry"]) * pos["dir"] * POINT
                rows.append({"session_date": sd, "dir": pos["dir"], "reason": reason,
                             "ref_range": hi - lo, "gross": gross,
                             "net": gross - cost,
                             # additive only: recorded for the trade ledger, never read
                             # by the P&L above, so these cannot change any result
                             "contract": s["contract_month"].iloc[0],
                             "ref_hi": hi, "ref_lo": lo, "stop_px": pos["stop"],
                             "entry_utc": pos["entry_utc"],
                             "exit_utc": b["timestamp_utc"],
                             "entry_px": pos["entry"], "exit_px": px,
                             "cost": cost})
                pos = None
                break
    return pd.DataFrame(rows)


def score(trades: pd.DataFrame, all_sessions: list, draws: int, rng) -> dict:
    if trades.empty:
        return {"trades": 0}
    by_sess = trades.groupby("session_date")["net"].sum()
    series = pd.Series(0.0, index=pd.Index(all_sessions, name="session_date"))
    series.loc[by_sess.index] = by_sess.to_numpy()
    x = series.to_numpy()

    n = len(x)
    sd_all = x.std(ddof=1)
    sharpe_all = float(x.mean() / sd_all) if sd_all > 0 else 0.0
    edge_free = x - x.mean()
    obs_t = float(x.mean() / (sd_all / np.sqrt(n)))
    null_t = []
    for _ in range(draws):
        b = stationary_bootstrap(edge_free, n, rng)
        null_t.append(b.mean() / (b.std(ddof=1) / np.sqrt(len(b))))
    p = float((np.array(null_t) >= obs_t).mean())

    net = trades["net"]
    wins = net[net > 0]
    return {
        "trades": len(trades), "sessions": n, "f": len(trades) / n,
        "net_total": float(net.sum()), "per_trade": float(net.mean()),
        "wr": float(len(wins) / len(net)),
        "long_share": float((trades["dir"] == 1).mean()),
        "stop_share": float((trades["reason"] == "stop").mean()),
        "sharpe_all": sharpe_all, "t": obs_t, "p": p,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data_history")
    ap.add_argument("--symbol", default="ES")
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--draws", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    c = build_continuous(args.data, args.symbol, bar_size="30min")
    c = c[~c["thin_session"] & ~c["entries_blocked"]].copy()
    c["mso"] = minutes_since_open(c)
    sd = c["session_date"].astype(str)
    c = c[(sd >= args.start) & (sd <= args.end)]
    sessions = sorted(c["session_date"].unique())

    print("CROSS-SESSION RANGE BREAKOUTS: A2L / L2N / NYOR")
    print("=" * 84)
    print(f"{args.symbol} priced as MES, 1 contract, two-sided, "
          f"${2 * (HALF_SPREAD_TICKS + BASE_SLIP_TICKS) * TICK * POINT + COMMISSION_RT:.2f}/round trip")
    print(f"{len(sessions)} sessions, {args.start[:4]}-{args.end[:4]}. Pre-registered. "
          f"Runs ONCE.")
    print()
    print(f"  {'arm':<6}{'trades':>8}{'f':>7}{'net $':>10}{'$/trade':>9}{'WR':>7}"
          f"{'long':>7}{'stop':>7}{'Sharpe':>9}{'t':>7}{'p':>8}")

    rng = np.random.default_rng(args.seed)
    res = {}
    for arm, (ref, trade) in ARMS.items():
        t = run_arm(c, ref, trade)
        s = score(t, sessions, args.draws, rng)
        res[arm] = s
        if s["trades"] == 0:
            print(f"  {arm:<6}{'no trades':>8}")
            continue
        print(f"  {arm:<6}{s['trades']:>8}{s['f']:>7.2f}{s['net_total']:>10,.0f}"
              f"{s['per_trade']:>9.2f}{s['wr']:>7.0%}{s['long_share']:>7.0%}"
              f"{s['stop_share']:>7.0%}{s['sharpe_all']:>9.3f}{s['t']:>7.2f}"
              f"{s['p']:>8.4f}")

    alpha = 0.05 / 3
    print("\n" + "=" * 84)
    print(f"  PRE-REGISTERED DECISION (Bonferroni across 3 arms, nominal p < {alpha:.4f})")
    print(f"  {'arm':<6}{'mean>0':>9}{'p<a':>7}{'Sh>0.10':>10}{'2x sign':>10}   verdict")
    rng2 = np.random.default_rng(args.seed)
    verdicts = {}
    for arm, (ref, trade) in ARMS.items():
        s = res[arm]
        if s["trades"] == 0:
            continue
        t2 = run_arm(c, ref, trade, spread_mult=2.0)
        s2 = score(t2, sessions, 200, rng2)
        res[arm]["double_spread_per_trade"] = s2["per_trade"]
        c1 = s["per_trade"] > 0
        c2 = s["p"] < alpha
        c3 = s["sharpe_all"] > 0.10
        c4 = (s2["per_trade"] > 0) == c1 and s2["per_trade"] > 0
        ok = c1 and c2 and c3 and c4
        verdicts[arm] = ok
        print(f"  {arm:<6}{'yes' if c1 else 'no':>9}{'yes' if c2 else 'no':>7}"
              f"{'yes' if c3 else 'no':>10}{'yes' if c4 else 'no':>10}   "
              f"{'PASS' if ok else 'FAIL'}")
        print(f"         2x spread: ${s2['per_trade']:+.2f}/trade")

    print("\n  PER-YEAR $/trade")
    for arm, (ref, trade) in ARMS.items():
        t = run_arm(c, ref, trade)
        if t.empty:
            continue
        yr = t.groupby(pd.to_datetime(t["session_date"]).dt.year)["net"].mean()
        print(f"    {arm:<6}" + "  ".join(f"{y}:{v:+.1f}" for y, v in yr.items()))

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"arms": res, "alpha": alpha,
                                           "verdicts": verdicts}, indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
