#!/usr/bin/env python3
"""
Consolidate every imported bar into one portable file, with an integrity report.

Emits a single long-format table across all instruments, contracts and bar sizes:

    symbol, contract_month, bar_size, timestamp_utc, open, high, low, close, volume

Per-contract and UNADJUSTED. Contracts are NOT stitched into a continuous series here,
because stitching is a decision (which roll rule, which adjustment) and baking it into the
export would hide that decision from whoever reads the file next. The roll rule this project
uses is documented in the companion README.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SOURCES = (("data_history", "30min"), ("data_5min", "5min"))


def load_all(root: Path) -> tuple[pd.DataFrame, list[dict]]:
    frames, metas = [], []
    for sub, bar_size in SOURCES:
        base = root / sub
        if not base.is_dir():
            continue
        for pq in sorted(base.glob("*/*.parquet")):
            df = pd.read_parquet(pq)
            df["bar_size"] = bar_size
            frames.append(df)
            mj = pq.with_suffix("").with_suffix(".meta.json")
            if mj.exists():
                metas.append(json.loads(mj.read_text()))
    if not frames:
        raise SystemExit("no parquet files found")
    cols = ["symbol", "contract_month", "bar_size", "timestamp_utc",
            "open", "high", "low", "close", "volume"]
    out = pd.concat(frames, ignore_index=True)[cols]
    out = out.sort_values(["symbol", "bar_size", "contract_month", "timestamp_utc"])
    return out.reset_index(drop=True), metas


def integrity(df: pd.DataFrame) -> list[str]:
    """Checks that must pass before this file is handed to anyone."""
    notes = []
    key = ["symbol", "contract_month", "bar_size", "timestamp_utc"]
    dupes = int(df.duplicated(subset=key).sum())
    notes.append(f"duplicate (symbol, contract, bar_size, timestamp) rows: {dupes}")

    bad = df[(df["high"] < df["low"]) |
             (df["open"] > df["high"]) | (df["open"] < df["low"]) |
             (df["close"] > df["high"]) | (df["close"] < df["low"])]
    notes.append(f"rows violating low <= open/close <= high: {len(bad)}")

    nn = int(df[["open", "high", "low", "close"]].isna().sum().sum())
    notes.append(f"null OHLC values: {nn}")

    nonpos = int((df[["open", "high", "low", "close"]] <= 0).sum().sum())
    notes.append(f"non-positive prices: {nonpos}")

    negvol = int((df["volume"] < 0).sum())
    notes.append(f"negative volume: {negvol}")
    return notes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--out", type=Path, default=Path("export/futures_bars.parquet"))
    ap.add_argument("--also-csv", action="store_true")
    args = ap.parse_args(argv)

    df, metas = load_all(args.root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False, compression="zstd")

    print("CONSOLIDATED BAR EXPORT")
    print("=" * 78)
    print(f"{len(df):,} bars, {df['symbol'].nunique()} instruments, "
          f"{df['contract_month'].nunique()} contract months")
    print()
    print(f"  {'symbol':<8}{'bars':>10}{'contracts':>11}{'first':>13}{'last':>13}")
    for (sym, bs), g in df.groupby(["symbol", "bar_size"], sort=True):
        print(f"  {sym + ' ' + bs:<8}{len(g):>10,}{g['contract_month'].nunique():>11}"
              f"{str(g['timestamp_utc'].min())[:10]:>13}"
              f"{str(g['timestamp_utc'].max())[:10]:>13}")

    print("\n  INTEGRITY")
    for n in integrity(df):
        print(f"    {n}")

    size = args.out.stat().st_size
    print(f"\n  {args.out} -> {size / 1e6:.1f} MB")

    if args.also_csv:
        csv = args.out.with_suffix(".csv.gz")
        df.to_csv(csv, index=False, compression="gzip")
        print(f"  {csv} -> {csv.stat().st_size / 1e6:.1f} MB")

    tzs = sorted({m.get("source_timezone", "?") for m in metas})
    adj = sorted({m.get("adjustment", "?") for m in metas})
    print(f"\n  source timezones seen: {tzs}   adjustment: {adj}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
