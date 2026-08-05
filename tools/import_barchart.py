#!/usr/bin/env python3
"""
Import Barchart CSV price history into the project's parquet schema.

The whole point of this file is the timezone check. Everything else is plumbing.

WHY TIMEZONE IS THE DANGER
--------------------------
Barchart writes intraday timestamps in whatever timezone your ACCOUNT is configured
for, and the CSV carries no timezone marker. If the export is in Central Time and we
read it as Eastern, every timestamp shifts by an hour: the 09:30 opening range is built
from 08:30 data, the RTH session filter admits the wrong bars, and the backtest still
runs perfectly and reports plausible numbers. Nothing crashes. Nothing looks wrong.

That is the worst class of bug in this project, so this importer does not accept a
timezone on trust. It INFERS the offset from the data itself: the US equity open
produces an unmistakable volume spike, so the importer locates that spike and works out
which timezone assumption puts it at 09:30 Eastern. If no candidate produces a decisive
spike, it REFUSES to import rather than guess.

Usage
-----
    # Verify the timezone before importing anything
    python tools/import_barchart.py --check downloads/mes_2024_01.csv

    # Import a directory of downloads
    python tools/import_barchart.py --src downloads --out data --symbol MES

    # Override the inference only if you are certain and it failed
    python tools/import_barchart.py --src downloads --out data --symbol MES \\
        --assume-tz America/Chicago
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.sessions import ET                                # noqa: E402

log = logging.getLogger("import_barchart")

# Barchart writes futures symbols as ROOT + MONTH_CODE + 2-DIGIT YEAR, e.g. MESM26.
SYMBOL_RE = re.compile(r"^(?P<root>[A-Z]{1,4}?)(?P<month>[FGHJKMNQUVXZ])(?P<year>\d{2})$")
MONTH_CODES = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
               "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}

# Candidate timezones a Barchart account might be set to.
CANDIDATE_TZ = ["America/New_York", "America/Chicago", "UTC",
                "America/Denver", "America/Los_Angeles"]

# Barchart's close column is named inconsistently across export types: "Last" on some,
# "Latest" on the intraday historical download, "Close" elsewhere. Map them all.
COLUMN_ALIASES = {
    "time": "timestamp", "date time": "timestamp", "datetime": "timestamp",
    "date": "timestamp", "timestamp": "timestamp",
    "open": "open", "high": "high", "low": "low",
    "close": "close", "last": "close", "latest": "close",
    "last price": "close", "settle": "close", "settlement": "close",
    "volume": "volume", "vol": "volume",
}

# Columns Barchart adds that we deliberately ignore rather than treat as a failure.
IGNORED_COLUMNS = {"change", "%change", "pct change", "open interest", "symbol"}

# A genuine 09:30 ET opening spike scores far above baseline: real files come in near 19x.
# To accuse a file of carrying a DIFFERENT timezone, the alternative must itself look like
# a real opening spike. If no candidate scores well, the file simply has no spike to
# measure, which is a thin-data problem and not a timezone problem.
MISMATCH_MIN_ALT_SCORE = 8.0
WEAK_SPIKE_SCORE = 5.0


def parse_symbol(symbol: str) -> tuple[str, str]:
    """'MESM26' -> ('MES', '202606'). Raises on anything unrecognised."""
    m = SYMBOL_RE.match(symbol.upper().strip())
    if not m:
        raise ValueError(
            f"cannot parse Barchart symbol {symbol!r}. Expected ROOT+MONTH+YY such as "
            "MESM26 (MES June 2026) or MNQZ25 (MNQ December 2025)."
        )
    g = m.groupdict()
    year = 2000 + int(g["year"])
    return g["root"], f"{year}{MONTH_CODES[g['month']]:02d}"


def read_csv(path: Path) -> pd.DataFrame:
    """Read one Barchart CSV, tolerating its trailing provenance line."""
    raw = pd.read_csv(path, skip_blank_lines=True)

    # Barchart appends a line such as "Downloaded from Barchart.com as of ...".
    first = raw.columns[0]
    trailing = raw[first].astype(str).str.contains("Downloaded from|barchart", case=False,
                                                   na=False)
    if trailing.any():
        raw = raw[~trailing]

    raw.columns = [COLUMN_ALIASES.get(str(c).strip().lower(), str(c).strip().lower())
                   for c in raw.columns]

    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"{path.name}: missing columns {sorted(missing)}. "
                         f"Found: {list(raw.columns)}")

    df = raw[[c for c in ("timestamp", "open", "high", "low", "close", "volume")
              if c in raw.columns]].copy()
    if "volume" not in df.columns:
        df["volume"] = np.nan

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(",", "", regex=False), errors="coerce")

    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"])
    return df.sort_values("timestamp").reset_index(drop=True)


def infer_timezone(df: pd.DataFrame) -> tuple[str, dict[str, float]]:
    """
    Work out which timezone the naive timestamps are in, from the volume profile.

    The US cash equity open at 09:30 Eastern produces the largest, sharpest volume
    spike of the index-futures day. For each candidate timezone we localise, convert to
    Eastern, and measure how much volume lands in the five minutes from 09:30 relative
    to a typical five-minute block. The correct timezone scores far higher than the rest.

    Returns the best candidate and every candidate's score, so the margin is visible
    rather than hidden behind a single answer.
    """
    if "volume" not in df.columns or df["volume"].isna().all():
        raise ValueError(
            "cannot infer timezone without volume: the method relies on locating the "
            "09:30 ET opening volume spike. Re-download including a Volume column, or "
            "pass --assume-tz and accept the risk."
        )

    scores: dict[str, float] = {}
    for tz in CANDIDATE_TZ:
        try:
            localised = df["timestamp"].dt.tz_localize(
                ZoneInfo(tz), ambiguous="NaT", nonexistent="NaT")
        except Exception:                                # noqa: BLE001
            continue
        et = localised.dt.tz_convert(ET)
        ok = et.notna()
        if ok.sum() < 100:
            continue

        minute_of_day = (et.dt.hour * 60 + et.dt.minute)[ok]
        vol = df.loc[ok, "volume"].fillna(0.0)

        by_minute = pd.DataFrame({"m": minute_of_day.values, "v": vol.values}) \
            .groupby("m")["v"].sum()
        if by_minute.empty or by_minute.sum() <= 0:
            continue

        open_block = by_minute.reindex(range(9 * 60 + 30, 9 * 60 + 35)).fillna(0).sum()
        # Baseline: a typical 5-minute block over the whole day.
        baseline = by_minute.sum() / (len(by_minute) / 5.0)
        scores[tz] = float(open_block / baseline) if baseline > 0 else 0.0

    if not scores:
        raise ValueError("timezone inference failed: no candidate produced usable data")

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best, best_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0

    # Demand a decisive win. A narrow margin means the spike is not distinctive here,
    # and guessing would be exactly the silent failure this function exists to prevent.
    if best_score < 2.0 or best_score < 1.3 * max(runner_up, 1e-9):
        detail = ", ".join(f"{tz}={s:.2f}x" for tz, s in ranked)
        raise ValueError(
            "timezone inference was not decisive. Opening-spike scores: " + detail +
            ".\nThe importer refuses to guess, because a one-hour shift would corrupt "
            "every opening range silently. Check your Barchart account timezone setting "
            "and pass --assume-tz explicitly."
        )
    return best, scores


def opening_spike_score(df: pd.DataFrame, tz: str) -> float:
    """How decisively this file's volume spikes at 09:30 ET under the given timezone."""
    localised = df["timestamp"].dt.tz_localize(
        ZoneInfo(tz), ambiguous="NaT", nonexistent="NaT")
    et = localised.dt.tz_convert(ET)
    ok = et.notna()
    if ok.sum() < 100 or "volume" not in df.columns or df["volume"].isna().all():
        return float("nan")
    by_minute = pd.DataFrame({
        "m": (et.dt.hour * 60 + et.dt.minute)[ok].values,
        "v": df.loc[ok, "volume"].fillna(0.0).values,
    }).groupby("m")["v"].sum()
    if by_minute.empty or by_minute.sum() <= 0:
        return float("nan")
    open_block = by_minute.reindex(range(9 * 60 + 30, 9 * 60 + 35)).fillna(0).sum()
    baseline = by_minute.sum() / (len(by_minute) / 5.0)
    return float(open_block / baseline) if baseline > 0 else 0.0


def to_parquet_schema(df: pd.DataFrame, tz: str, symbol: str,
                      contract_month: str) -> pd.DataFrame:
    """Localise, convert to UTC, and emit the project's schema."""
    localised = df["timestamp"].dt.tz_localize(
        ZoneInfo(tz), ambiguous="NaT", nonexistent="NaT")
    out = pd.DataFrame({
        "timestamp_utc": localised.dt.tz_convert("UTC"),
        "open": df["open"].astype(float),
        "high": df["high"].astype(float),
        "low": df["low"].astype(float),
        "close": df["close"].astype(float),
        "volume": df["volume"].astype(float),
        "symbol": symbol,
        "contract_month": contract_month,
    })
    dropped = out["timestamp_utc"].isna().sum()
    if dropped:
        log.warning("dropped %d rows with ambiguous or nonexistent local times "
                    "(DST transitions)", dropped)
    return (out.dropna(subset=["timestamp_utc"])
            .drop_duplicates(subset=["timestamp_utc"], keep="last")
            .sort_values("timestamp_utc")
            .reset_index(drop=True))


def symbol_from_filename(path: Path) -> str | None:
    """Find a Barchart contract symbol in a filename, however it was saved."""
    for token in re.split(r"[^A-Za-z0-9]+", path.stem):
        if SYMBOL_RE.match(token.upper()):
            return token.upper()
    return None


def symbol_from_content(path: Path) -> str | None:
    """
    Fall back to a Symbol column inside the CSV.

    Barchart's default export filenames do not always carry the contract, and users
    reasonably leave files named however the browser saved them. Reading the symbol from
    the data is more reliable than insisting on a naming convention.
    """
    try:
        head = pd.read_csv(path, nrows=5)
    except Exception:                                     # noqa: BLE001
        return None
    for col in head.columns:
        if str(col).strip().lower() in ("symbol", "contract", "ticker"):
            for value in head[col].astype(str):
                token = value.strip().upper()
                if SYMBOL_RE.match(token):
                    return token
    return None


def resolve_symbol(path: Path, override: str | None) -> str | None:
    if override and SYMBOL_RE.match(override.upper()):
        return override.upper()
    return symbol_from_filename(path) or symbol_from_content(path)


def cmd_check(paths: list[Path]) -> int:
    for path in paths:
        print(f"\n=== {path.name} ===")
        try:
            df = read_csv(path)
        except Exception as exc:                          # noqa: BLE001
            print(f"  UNREADABLE: {exc}")
            continue
        print(f"  rows           {len(df):,}")
        print(f"  first          {df['timestamp'].iloc[0]}")
        print(f"  last           {df['timestamp'].iloc[-1]}")
        sym = symbol_from_filename(path)
        if sym:
            root, cm = parse_symbol(sym)
            print(f"  symbol         {sym} -> {root} {cm}")
        try:
            tz, scores = infer_timezone(df)
            print(f"  timezone       {tz}   (opening-spike scores: "
                  + ", ".join(f"{k.split('/')[-1]}={v:.2f}x" for k, v in
                              sorted(scores.items(), key=lambda kv: -kv[1])) + ")")
        except ValueError as exc:
            print(f"  timezone       UNRESOLVED\n    {exc}")
    return 0


def cmd_import(src: Path, out: Path, symbol_override: str | None,
               assume_tz: str | None, bar_size: str) -> int:
    files = sorted(p for p in src.rglob("*.csv"))
    if not files:
        log.error("no CSV files under %s", src)
        return 1

    groups: dict[tuple[str, str], list[pd.DataFrame]] = defaultdict(list)
    resolved_tz: str | None = assume_tz
    tz_source = "user override" if assume_tz else None
    skipped: dict[str, int] = defaultdict(int)

    # Files that ARE Barchart contract exports, so a folder full of unrelated CSVs (a
    # browser Downloads directory, typically) does not abort the run. Anything skipped
    # is counted and reported rather than passing unnoticed.
    usable: list[tuple[Path, str]] = []
    for path in files:
        sym = resolve_symbol(path, symbol_override)
        if not sym:
            skipped["no contract symbol in filename or contents"] += 1
            continue
        usable.append((path, sym))

    if not usable:
        log.error("no Barchart contract exports found under %s", src)
        log.error("Files must carry a contract symbol such as MESM26, either in the "
                  "filename or in a Symbol column. Checked %d CSV file(s).", len(files))
        return 1

    log.info("%d of %d CSV files look like Barchart contract exports",
             len(usable), len(files))

    for path, sym in usable:
        try:
            df = read_csv(path)
        except Exception as exc:                          # noqa: BLE001
            log.warning("%s: unreadable, skipping (%s)", path.name, exc)
            skipped["unreadable"] += 1
            continue
        if df.empty:
            skipped["no usable rows"] += 1
            continue

        root, contract_month = parse_symbol(sym)

        # Infer the timezone ONCE, from the largest file, then apply it everywhere.
        if resolved_tz is None:
            biggest = max((p for p, _ in usable), key=lambda p: p.stat().st_size)
            try:
                resolved_tz, _ = infer_timezone(read_csv(biggest))
                tz_source = f"inferred from {biggest.name}"
                log.info("timezone %s (%s)", resolved_tz, tz_source)
            except ValueError as exc:
                log.error("%s", exc)
                return 2

        # Verify EVERY file against the resolved timezone rather than assuming the
        # account setting never changed mid-download. One file exported under a
        # different setting would shift only that contract, which is precisely the kind
        # of partial corruption that survives every other check.
        # The test must be RELATIVE, not absolute. A one-hour shift still lands the
        # "09:30" window inside elevated RTH volume and scores around 2.5x, which sails
        # past any fixed threshold. What gives it away is that some OTHER timezone scores
        # far better on the same file.
        score = opening_spike_score(df, resolved_tz)
        best_alt_tz, best_alt_score = max(
            ((tz, opening_spike_score(df, tz)) for tz in CANDIDATE_TZ),
            key=lambda kv: (kv[1] if kv[1] == kv[1] else -1.0))

        scored = score == score and best_alt_score == best_alt_score   # NaN-safe
        looks_shifted = (scored and best_alt_tz != resolved_tz
                         and best_alt_score > 1.5 * score)

        if looks_shifted and best_alt_score >= MISMATCH_MIN_ALT_SCORE:
            # Another timezone produces a CONVINCING opening spike on this file. That is
            # a real export-setting mismatch and must not be imported alongside the rest.
            log.error(
                "%s: scores only %.2fx at 09:30 ET under %s, but %.2fx under %s. This "
                "file was exported in a DIFFERENT timezone from the others. Import "
                "aborted rather than shift one contract by an hour, which would corrupt "
                "its opening ranges while every other check still passed. Re-export with "
                "a consistent Barchart account timezone, or import this file separately "
                "with --assume-tz %s.",
                path.name, score, resolved_tz, best_alt_score, best_alt_tz, best_alt_tz)
            return 2

        if scored and score < WEAK_SPIKE_SCORE:
            # NO timezone produces a convincing spike, so there is no spike here to
            # measure. Almost always a window where this contract was not the front
            # month, so RTH volume never dominated. Not a timezone fault: import it and
            # let the front-month and session-completeness gates judge it downstream.
            log.warning(
                "%s: weak opening spike (%.2fx under %s, best alternative %.2fx under "
                "%s). No timezone produces a convincing 09:30 ET spike, which normally "
                "means this window predates the contract becoming front month. Importing "
                "with the resolved timezone; validate_data.py will flag it if the data is "
                "too thin to use.",
                path.name, score, resolved_tz, best_alt_score, best_alt_tz)
            skipped["weak opening spike (imported, flagged)"] += 1

        groups[(root, contract_month)].append(
            to_parquet_schema(df, resolved_tz, root, contract_month))

    written = 0
    for (root, contract_month), frames in sorted(groups.items()):
        merged = (pd.concat(frames, ignore_index=True)
                  .drop_duplicates(subset=["timestamp_utc"], keep="last")
                  .sort_values("timestamp_utc")
                  .reset_index(drop=True))
        dest_dir = out / root
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{root}_{contract_month}_{bar_size}_TRADES.parquet"
        merged.to_parquet(dest, index=False)

        import json
        dest.with_suffix(".meta.json").write_text(json.dumps({
            "symbol": root, "contract_month": contract_month, "bar_size": bar_size,
            "what_to_show": "TRADES", "rows": int(len(merged)),
            "first_bar": str(merged["timestamp_utc"].iloc[0]),
            "last_bar": str(merged["timestamp_utc"].iloc[-1]),
            "source": "Barchart CSV export",
            "source_timezone": resolved_tz,
            "timezone_determination": tz_source,
            "adjustment": "unadjusted",
            "files_merged": len(frames),
        }, indent=2))
        log.info("%-34s %8d bars  %s -> %s", dest.name, len(merged),
                 str(merged['timestamp_utc'].iloc[0])[:10],
                 str(merged['timestamp_utc'].iloc[-1])[:10])
        written += 1

    if skipped:
        print("\nskipped:")
        for reason, count in sorted(skipped.items(), key=lambda kv: -kv[1]):
            print(f"  {count:>5}  {reason}")

    print(f"\n{written} contract files written to {out}")
    print(f"timezone used: {resolved_tz} ({tz_source})")
    print(f"\nNow validate:  python tools/validate_data.py {out}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", nargs="+", type=Path,
                    help="Inspect CSVs and report the inferred timezone, without importing")
    ap.add_argument("--src", type=Path, help="Directory of Barchart CSV downloads")
    ap.add_argument("--out", type=Path, default=Path("data"))
    ap.add_argument("--symbol", help="Contract symbol when filenames do not carry it")
    ap.add_argument("--assume-tz", help="Skip inference and assert this timezone. "
                                        "Use only when inference fails and you are sure.")
    ap.add_argument("--bar-size", default="1min")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)-7s %(message)s")

    if args.check:
        return cmd_check(args.check)
    if not args.src:
        ap.error("one of --check or --src is required")
    return cmd_import(args.src, args.out, args.symbol, args.assume_tz, args.bar_size)


if __name__ == "__main__":
    sys.exit(main())
