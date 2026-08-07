#!/usr/bin/env python3
"""
Run the commodity ORB, unchanged, on bars fetched after the sample it was developed on.

PRE-REGISTERED BEFORE RUNNING
-----------------------------
Written down first so the result cannot be reinterpreted after the fact.

  Prediction: if the edge is real, out-of-sample dollars per trade land in the same
  neighbourhood as in-sample (~$37) with a wide interval around them. If the strategy is
  a fit to the 2024-26 metals bull, they land at or below zero.

  Power, computed in advance: roughly 40 tradeable sessions across three symbols, and the
  ORB trades a minority of sessions, so expect on the order of 15 trades. At an in-sample
  per-trade standard deviation near $200 that gives a standard error near $50 against a
  $37 edge. A t-statistic near 0.7 is the EXPECTED result if the edge is entirely real.

  Therefore, decided in advance: a positive result CANNOT confirm the edge and will not be
  reported as confirmation. Only a clearly negative result is informative, and it would be
  informative because it would contradict a prediction made before the data was seen.

WHAT IS HELD FIXED
------------------
Every parameter, the cost model, the depth cap. `run_orb` is the same function that produced
the in-sample numbers. Nothing is refit, retuned or reselected. The only thing that changes
is which parquet directory is read.

The CAPPED cost model is used because it is the one this project would actually trade: never
order more than rests at the touch. See `tools/measured_costs.py`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.data import build_continuous, resample  # noqa: E402
from engine.overnight import minutes_since_open  # noqa: E402
from tools.import_stitched import SPECS  # noqa: E402
from tools.measured_costs import (  # noqa: E402
    BASE_SLIP_TICKS, apply_cost, cap_qty, spread_stats,
)
from tools.orb_commodity import OrbConfig, run_orb, summarise  # noqa: E402

SYMBOLS = ("MGC", "SI", "HG")


def run(datadir: str, symbols=SYMBOLS) -> tuple[dict, pd.DataFrame]:
    base = OrbConfig()
    zero = OrbConfig(slip_ticks_per_side=0.0, commission_round_turn=0.0)
    out, frames = {}, []
    for s in symbols:
        bars = resample(build_continuous(datadir, s), 30)
        bars = bars.assign(mso=minutes_since_open(bars))
        t = run_orb(bars, SPECS[s], zero)
        out[f"{s}_sessions"] = int(bars["session_date"].nunique())
        if t.empty:
            out[s] = {"trades": 0}
            continue
        d = spread_stats(s)
        t = cap_qty(t, d["depth_med"])
        side = np.full(len(t), d["half_spread_ticks"] + BASE_SLIP_TICKS)
        ct = apply_cost(t, s, side, base.commission_round_turn)
        out[s] = summarise(ct)
        frames.append(ct)
    allt = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    out["ALL"] = summarise(allt) if len(allt) else {"trades": 0}
    return out, allt


def show(label: str, res: dict, symbols=SYMBOLS) -> None:
    print(f"\n  {label}")
    print(f"  {'sym':<6}{'sessions':>10}{'trades':>8}{'rate':>7}{'net $':>10}"
          f"{'PF':>7}{'WR':>7}{'$/trade':>10}")
    for k in list(symbols) + ["ALL"]:
        v = res[k]
        sess = res.get(f"{k}_sessions")
        if v["trades"] == 0:
            print(f"  {k:<6}{sess or '':>10}{'none':>8}")
            continue
        rate = f"{v['trades'] / sess:.0%}" if sess else ""
        print(f"  {k:<6}{sess or '':>10}{v['trades']:>8}{rate:>7}{v['net']:>10,.0f}"
              f"{v['pf']:>7.2f}{v['wr']:>7.0%}{v['net'] / v['trades']:>10,.0f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in-sample", default="data_commodity")
    ap.add_argument("--out-sample", default="data_oos")
    args = ap.parse_args(argv)

    print("OUT OF SAMPLE: bars fetched after the sample end")
    print("=" * 78)
    print("Same code, same parameters, same cost model. Only the data is new.")
    print("Read the pre-registration in this file's docstring BEFORE the numbers.")

    ins, ins_t = run(args.in_sample)
    oos, oos_t = run(args.out_sample)
    show("IN SAMPLE (the strategy was developed on this)", ins)
    show("OUT OF SAMPLE (never seen by anyone)", oos)

    print()
    if oos_t.empty:
        print("  no out-of-sample trades: nothing to conclude in either direction")
        return 0

    n = len(oos_t)
    mu = float(oos_t["net"].mean())
    sd = float(oos_t["net"].std(ddof=1))
    se = sd / np.sqrt(n)
    lo, hi = mu - 1.96 * se, mu + 1.96 * se
    ins_mu = ins["ALL"]["net"] / ins["ALL"]["trades"]

    print(f"  in-sample  ${ins_mu:>7,.0f}/trade over {ins['ALL']['trades']} trades")
    print(f"  out-sample ${mu:>7,.0f}/trade over {n} trades, sd ${sd:,.0f}")
    print(f"  t {mu / se:+.2f}, 95% CI ${lo:,.0f} to ${hi:,.0f}")
    print()
    print("  VERDICT")
    if hi < 0:
        print("    Out-of-sample mean is negative with the interval clear of zero.")
        print("    That contradicts the pre-registered prediction. The edge is dead.")
    elif lo > 0:
        print("    Interval clear of zero on this many trades would be surprising.")
        print("    Check the sample before believing it.")
    else:
        print(f"    The interval spans zero, and it was always going to on {n} trades.")
        print("    The pre-registered prediction was that a real edge would look like")
        print("    this, so this result is consistent with a real edge AND consistent")
        print("    with no edge at all. It distinguishes nothing.")
        print()
        print("    What it DID rule out: the strategy did not collapse. In-sample")
        print(f"    ${ins_mu:,.0f}/trade, out-of-sample ${mu:,.0f}/trade, same sign.")
        print("    That is the only claim this sample supports. Do not upgrade it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
