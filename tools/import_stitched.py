#!/usr/bin/env python3
"""
Import pre-stitched 5-minute CSVs from the sibling `adam005141/claude` project.

WHY
---
That project ran five intraday momentum structures across MES, MNQ, M2K and MGC and
reached a meta-finding this project's four failures are consistent with:

    the equity index micros do not carry a standalone intraday momentum edge;
    gold carries every one of them. Intraday directional momentum is a
    commodity phenomenon in the 2024-26 sample, not an equity-index one.

This project has tested MES and MNQ exclusively. That is precisely the universe the other
project found empty, so the four legs closed here are the same result reached twice.

Its follow-on, a five-commodity ORB basket, is reported at PF 1.47 with a 7% blow rate on a
$4,000 box. That claim was produced by that project's own engine and economics simulator.
Importing the raw bars lets it be re-tested with THIS project's apparatus, which was built
independently and contains gates the other one does not: family-wise nulls, a path-expectancy
screen, and a block-bootstrapped account simulation.

An independent check on someone else's headline number is worth more than another strategy.

WHAT IS LOST IN TRANSLATION, STATED UP FRONT
--------------------------------------------
These files are already stitched across contract months, so the roll is baked in and
invisible. That means:

  * `entries_blocked` cannot be reconstructed. This engine normally refuses entries within
    five sessions of expiry and during a roll session; that guard is OFF for imported data.
  * The stitching method is not recorded in the file. If it was back-adjusted, absolute
    price levels are not tradeable levels, though bar-to-bar changes still are.
  * There is no BID/ASK, so costs for these instruments are ASSUMED, not measured. Every
    earlier result in this project used measured spreads; these will not.

CONTRACT SPECIFICATIONS: VERIFIED 2026-08-07
--------------------------------------------
Checked against CME product pages and broker specification sheets. One was wrong.

    MGC  10 troy oz,     tick 0.10   = $1.00    -> $10/pt      confirmed
    MCL  100 barrels,    tick 0.01   = $1.00    -> $100/pt     confirmed
    SIL  1,000 troy oz,  tick 0.005  = $5.00    -> $1,000/pt   confirmed
    MHG  2,500 lb,       tick 0.0005 = $1.25    -> $2,500/pt   confirmed
    MNG  1,000 MMBtu,    tick 0.001  = $1.00    -> $1,000/pt   **CORRECTED**

MNG was carried at 2,500 MMBtu and $2,500/pt, which is 2.5x too high. The micro is 1/10th
of the 10,000 MMBtu NG contract, so it is 1,000 MMBtu. The error came from assuming it
mirrored MHG's 2,500-unit size.

The dollar P&L turns out to be largely insensitive to this, because position size is
derived from a dollar risk budget: `qty = budget // (stop_distance * point_value)`, so
halving the point value roughly doubles the quantity and the dollar risk is unchanged. What
it DOES change is the integer rounding and which days the max-risk guard rejects, so the
result is re-run rather than adjusted arithmetically.

Note the SI, HG and NG files carry FULL-SIZE price series. They are priced here with MICRO
specifications, which is correct: the price series are identical, and the micro is the
contract actually tradeable in a small account. That substitution is inherited from the
source project.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.sessions import session_dates  # noqa: E402

# symbol -> (point value USD, tick size, tick value USD)
# VERIFIED against CME 2026-08-07. See the module docstring for sources and the one
# correction (MNG).
SPECS: dict[str, tuple[float, float, float]] = {
    "MGC": (10.0, 0.10, 1.00),        # micro gold, 10 oz
    "MCL": (100.0, 0.01, 1.00),       # micro crude, 100 bbl
    "SI":  (1000.0, 0.005, 5.00),     # priced as MICRO silver (SIL), 1,000 oz
    "HG":  (2500.0, 0.0005, 1.25),    # priced as MICRO copper (MHG), 2,500 lb
    "NG":  (1000.0, 0.001, 1.00),     # priced as MICRO nat gas (MNG), 1,000 MMBtu
    "MES": (5.0, 0.25, 1.25),
    "MNQ": (2.0, 0.25, 0.50),
    "M2K": (5.0, 0.10, 0.50),
}


def convert(src: Path, out_dir: Path, symbol: str) -> Path:
    df = pd.read_csv(src)
    df["timestamp_utc"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.drop(columns=["timestamp"]).sort_values("timestamp_utc")
    df["session_date"] = session_dates(pd.DatetimeIndex(df["timestamp_utc"])).values
    df["symbol"] = symbol
    # Single synthetic contract. The file is already stitched, so there is no roll to
    # model and the expiry guard cannot be reconstructed. December 2099 rather than a
    # sentinel like 999999: the engine derives an expiry date from the contract month, and
    # a non-month raises. Far enough out that the near-expiry guard never fires, which is
    # the correct behaviour for data whose rolls are already baked in.
    df["contract_month"] = "209912"
    df["entries_blocked"] = False
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{symbol}_209912_1min_TRADES.parquet"
    df.to_parquet(dest, index=False)
    return dest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="directory of *_5min_stitched.csv")
    ap.add_argument("--out", default="data_commodity")
    ap.add_argument("--symbols", nargs="+", default=sorted(SPECS))
    args = ap.parse_args(argv)

    src, out = Path(args.src), Path(args.out)
    print("IMPORT PRE-STITCHED BARS")
    print("=" * 74)
    print("Roll guard is OFF for this data: the files are already stitched, so expiry and")
    print("roll sessions cannot be reconstructed. Costs will be ASSUMED, not measured.")
    print("Contract specifications verified against CME 2026-08-07; MNG was wrong by 2.5x")
    print("and is corrected here.")
    print()

    n = 0
    for sym in args.symbols:
        f = src / f"{sym}_5min_stitched.csv"
        if not f.exists():
            print(f"  {sym:<5} no file at {f}")
            continue
        dest = convert(f, out, sym)
        got = pd.read_parquet(dest)
        pv, ts, tv = SPECS[sym]
        print(f"  {sym:<5} {len(got):>7,} bars  "
              f"{got['session_date'].nunique():>4} sessions  "
              f"{got['session_date'].min()} to {got['session_date'].max()}  "
              f"${pv:g}/pt")
        n += 1
    print(f"\n{n} symbols written to {out}/")
    print("\nNOTE: the bar interval is 5 minutes, but the filename says 1min because the")
    print("engine's discovery pattern keys on it. Pass --decision-minutes 5 downstream and")
    print("the resampler is a no-op; anything smaller would silently upsample.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
