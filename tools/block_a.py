#!/usr/bin/env python3
"""
Block A of the regime pre-registration: does the commodity ORB work outside the bull?

Runs the frozen strategy on 2011-2013 gold, silver and copper. See
`docs/PREREGISTRATION_2026-08-07_REGIME.md`, committed before any pre-2024 data existed
on disk. Nothing here may be changed after seeing a result.

DECISION RULE, FIXED IN ADVANCE. Pass requires all three:

  1. pooled mean net > $0 per trade
  2. rotation-null one-sided p < 0.05
  3. at least 2 of 3 metals individually positive

A positive but SMALLER edge than the $37/trade in-sample figure is a pass. A long-only
breakout should earn less in a bear market.

REGISTERED PREDICTION: positive but well below in-sample, roughly $5-25 per trade, p < 0.05
pooled, gold strongest, 2013 alone negative or near zero. Confidence moderate; the honest
alternative is that a long-only opening-range breakout is a trend-following structure that
simply does not work in a three-year downtrend.

Two choices recorded in the pre-registration and repeated here because they shape the
result. The session window is restricted to the same 15 bars the 2024-26 sample carried,
so the comparison changes one thing rather than two. And 2026-measured spreads are applied
to 2011 trades, which favours the strategy, because spreads were wider then. A failure is
therefore decisive and a pass is optimistic.
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
from tools.import_stitched import SPECS  # noqa: E402
from tools.measured_costs import BASE_SLIP_TICKS, apply_cost, cap_qty, spread_stats  # noqa: E402
from tools.orb_commodity import OrbConfig, drop_top_n, run_orb, summarise  # noqa: E402

# The parquet symbol is the full-size root; the tradeable instrument and its costs are the
# micro. Same price series, and the micro is what a small account can actually trade. This
# substitution is inherited from the source project and applies to silver and copper there
# too.
SYMBOLS = {"GC": "MGC", "SI": "SI", "HG": "HG"}


def trades_for(sym: str, data: str, start: str, end: str, cfg: OrbConfig,
               spread_mult: float = 1.0, counts: dict | None = None) -> pd.DataFrame:
    spec_key = SYMBOLS[sym]
    c = build_continuous(data, sym, bar_size="30min")
    c = c[~c["thin_session"] & ~c["entries_blocked"]].copy()
    c["mso"] = minutes_since_open(c)
    c = c[(c["mso"] >= 0) & (c["mso"] <= 420)]
    sd = c["session_date"].astype(str)
    c = c[(sd >= start) & (sd <= end)]
    if c.empty:
        return pd.DataFrame()

    zero = OrbConfig(**{**cfg.__dict__, "slip_ticks_per_side": 0.0,
                        "commission_round_turn": 0.0})
    if counts is not None:
        counts[sym] = int(c["session_date"].nunique())
    t = run_orb(c, SPECS[spec_key], zero)
    if t.empty:
        return t
    d = spread_stats(spec_key)
    t = cap_qty(t, d["depth_med"])
    side = np.full(len(t), d["half_spread_ticks"] * spread_mult + BASE_SLIP_TICKS)
    t = apply_cost(t, spec_key, side, cfg.commission_round_turn)
    t["symbol"] = sym
    return t


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="data_history")
    ap.add_argument("--start", default="2011-01-01")
    ap.add_argument("--end", default="2013-12-31")
    ap.add_argument("--draws", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(argv)

    cfg = OrbConfig()
    print("BLOCK A: 2011-2013, gold / silver / copper")
    print("=" * 78)
    print("Frozen config, CAPPED costs, 15-bar window. Pre-registered before the data")
    print("existed on disk. This runs ONCE.")
    print()

    per, frames, counts = {}, [], {}
    print(f"  {'sym':<5}{'sessions':>10}{'trades':>8}{'rate':>7}{'net $':>11}"
          f"{'PF':>7}{'WR':>7}{'$/trade':>10}")
    for sym in SYMBOLS:
        t = trades_for(sym, args.data, args.start, args.end, cfg, counts=counts)
        if t.empty:
            per[sym] = {"trades": 0}
            print(f"  {sym:<5}{'no trades':>10}")
            continue
        s = summarise(t)
        per[sym] = s
        frames.append(t)
        n_sess = counts[sym]
        rate = f"{s['trades'] / n_sess:.0%}"
        print(f"  {sym:<5}{n_sess:>10}{s['trades']:>8}{rate:>7}{s['net']:>11,.0f}"
              f"{s['pf']:>7.2f}{s['wr']:>7.0%}{s['net'] / s['trades']:>10,.0f}")

    if not frames:
        print("\n  no trades in the block: nothing to decide")
        return 1

    allt = pd.concat(frames, ignore_index=True)
    tot = summarise(allt)
    per["ALL"] = tot
    mu = tot["net"] / tot["trades"]
    sd = allt["net"].std(ddof=1)
    se = sd / np.sqrt(len(allt))
    print(f"  {'ALL':<5}{sum(counts.values()):>10}{tot['trades']:>8}"
          f"{tot['trades'] / sum(counts.values()):>7.0%}{tot['net']:>11,.0f}"
          f"{tot['pf']:>7.2f}{tot['wr']:>7.0%}{mu:>10,.0f}")
    print(f"\n  pooled: ${mu:,.2f}/trade, sd ${sd:,.0f}, se ${se:,.2f}, "
          f"95% CI ${mu - 1.96 * se:,.0f} to ${mu + 1.96 * se:,.0f}")

    # ---- rotation null on the pooled per-session series ---------------------
    daily = allt.groupby("session_date")["net"].sum().sort_index()
    series = daily.to_numpy()
    edge_free = series - series.mean()
    obs_t = float(series.mean() / (series.std(ddof=1) / np.sqrt(len(series))))
    rng = np.random.default_rng(args.seed)
    null_t = []
    for _ in range(args.draws):
        b = stationary_bootstrap(edge_free, len(series), rng)
        null_t.append(b.mean() / (b.std(ddof=1) / np.sqrt(len(b))))
    null_t = np.array(null_t)
    p = float((null_t >= obs_t).mean())
    print(f"  rotation null on {len(series)} sessions: observed t {obs_t:+.2f}, "
          f"null 95th {np.percentile(null_t, 95):+.2f}, one-sided p {p:.4f}")

    # ---- the pre-registered decision ---------------------------------------
    positives = sum(1 for s in SYMBOLS if per[s]["trades"] and per[s]["net"] > 0)
    c1, c2, c3 = mu > 0, p < 0.05, positives >= 2
    print("\n" + "=" * 78)
    print("  PRE-REGISTERED DECISION")
    print(f"    1. pooled mean > $0/trade      ${mu:>9,.2f}   {'PASS' if c1 else 'FAIL'}")
    print(f"    2. rotation-null p < 0.05      {p:>10.4f}   {'PASS' if c2 else 'FAIL'}")
    print(f"    3. >=2 of 3 metals positive    {positives:>7} of 3   {'PASS' if c3 else 'FAIL'}")
    verdict = "PASS" if (c1 and c2 and c3) else "FAIL"
    print(f"\n    BLOCK A: {verdict}")

    # ---- robustness, registered in advance, reported whatever it shows ------
    print("\n  ROBUSTNESS (registered in advance)")
    d2 = pd.concat([trades_for(s, args.data, args.start, args.end, cfg, spread_mult=2.0)
                    for s in SYMBOLS], ignore_index=True)
    s2 = summarise(d2)
    print(f"    2x measured spread:  ${s2['net'] / s2['trades']:>8,.2f}/trade  "
          f"PF {s2['pf']:.2f}   "
          f"{'sign holds' if s2['net'] > 0 else 'SIGN FLIPS -- pass withdrawn'}")
    d10 = drop_top_n(allt, 10)
    print(f"    drop best 10 trades: ${d10['net'] / d10['trades']:>8,.2f}/trade  "
          f"PF {d10['pf']:.2f}")
    print(f"    {'year':<8}{'trades':>8}{'net $':>11}{'PF':>7}{'$/trade':>10}")
    years = {}
    allt["_y"] = pd.to_datetime(allt["session_date"]).dt.year
    for y, g in allt.groupby("_y"):
        s = summarise(g)
        years[int(y)] = s
        print(f"    {y:<8}{s['trades']:>8}{s['net']:>11,.0f}{s['pf']:>7.2f}"
              f"{s['net'] / s['trades']:>10,.0f}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({
            "block": "A", "window": [args.start, args.end],
            "per_symbol": per, "pooled_per_trade": mu, "se": se,
            "rotation_p": p, "observed_t": obs_t,
            "criteria": {"mean_positive": bool(c1), "p_below_05": bool(c2),
                         "two_of_three": bool(c3)},
            "verdict": verdict,
            "robustness": {"double_spread": s2, "drop_top_10": d10,
                           "by_year": {str(k): v for k, v in years.items()}},
        }, indent=2, default=float))
        print(f"\n  report -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
