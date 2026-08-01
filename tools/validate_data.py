#!/usr/bin/env python3
"""
Ingest validation gates for downloaded MES / MNQ bars.

Implements the checks in SPECIFICATION.md section 4. A failing session is
QUARANTINED, never silently repaired. The point of this file is to catch the
specific ways futures data lies to you before any of it reaches research.

The gate that matters most is `front_month_attribution`. During the environment
audit, the Sep-2026 MES contract returned a full year of daily bars, but volume was
zero or single-digit for the first ten months because it was not yet the front
month. Research run over that window would be studying a contract nobody traded.

Usage
-----
    python tools/validate_data.py data/MES/MES_202603_1min_TRADES.parquet
    python tools/validate_data.py data/            # whole tree
    python tools/validate_data.py data/ --json report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

import pandas as pd

# Thresholds. All correspond to named parameters in SPECIFICATION.md section 4.
MAX_GAP_BARS = 3
MIN_SESSION_VOLUME_PCT = 0.20
MAX_JUMP_ATR = 10.0
MIN_FRONT_MONTH_VOLUME_SHARE = 0.50


@dataclass
class Finding:
    gate: str
    severity: str              # "error" quarantines, "warning" is advisory
    message: str
    detail: dict = field(default_factory=dict)


@dataclass
class Report:
    path: str
    rows: int
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "rows": self.rows,
            "ok": self.ok,
            "findings": [asdict(f) for f in self.findings],
        }


# ---------------------------------------------------------------------------
# Individual gates. Each takes a DataFrame and appends findings.
# ---------------------------------------------------------------------------

def gate_schema(df: pd.DataFrame, out: list[Finding]) -> bool:
    required = {"timestamp_utc", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        out.append(Finding("schema", "error", f"missing required columns: {sorted(missing)}"))
        return False
    return True


def gate_timestamps(df: pd.DataFrame, out: list[Finding]) -> None:
    ts = df["timestamp_utc"]
    n_dupes = int(ts.duplicated().sum())
    if n_dupes:
        out.append(Finding("timestamps", "error",
                           f"{n_dupes} duplicate timestamps", {"count": n_dupes}))
    if not ts.is_monotonic_increasing:
        out.append(Finding("timestamps", "error", "timestamps are not monotonically increasing"))
    if getattr(ts.dtype, "tz", None) is None:
        out.append(Finding("timestamps", "error",
                           f"timestamps are not timezone aware (dtype={ts.dtype})"))


def gate_ohlc_coherence(df: pd.DataFrame, out: list[Finding]) -> None:
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    bad = (l > o) | (l > c) | (h < o) | (h < c) | (h < l)
    n = int(bad.sum())
    if n:
        out.append(Finding("ohlc_coherence", "error",
                           f"{n} bars violate low <= open,close <= high",
                           {"count": n, "first": str(df.loc[bad, 'timestamp_utc'].iloc[0])}))


def gate_gaps(df: pd.DataFrame, out: list[Finding], max_gap_bars: int = MAX_GAP_BARS) -> None:
    """Flag gaps beyond the tolerance, ignoring the daily maintenance break and weekends."""
    if len(df) < 3:
        return
    deltas = df["timestamp_utc"].diff().dropna()
    modal = deltas.mode()
    if modal.empty:
        return
    step = modal.iloc[0]
    if step <= pd.Timedelta(0):
        return

    # An hour covers the CME maintenance break; anything longer is usually a weekend.
    tolerance = max(step * (max_gap_bars + 1), pd.Timedelta(hours=1))
    gaps = deltas[deltas > tolerance]
    intraday = gaps[gaps < pd.Timedelta(days=2)]
    if len(intraday):
        out.append(Finding("gaps", "warning",
                           f"{len(intraday)} intraday gaps exceed {tolerance}",
                           {"count": int(len(intraday)),
                            "largest": str(intraday.max())}))


def gate_volume(df: pd.DataFrame, out: list[Finding]) -> None:
    if "volume" not in df.columns or df["volume"].isna().all():
        return                                   # BID/ASK bars legitimately carry no volume
    vol = pd.to_numeric(df["volume"], errors="coerce")
    if (vol < 0).any():
        out.append(Finding("volume", "error",
                           f"{int((vol < 0).sum())} bars have negative volume"))
    zero_share = float((vol == 0).mean())
    if zero_share > 0.5:
        out.append(Finding("volume", "error",
                           f"{zero_share:.0%} of bars have zero volume; "
                           "contract was likely not trading in this window",
                           {"zero_share": round(zero_share, 4)}))
    elif zero_share > 0.2:
        out.append(Finding("volume", "warning",
                           f"{zero_share:.0%} of bars have zero volume",
                           {"zero_share": round(zero_share, 4)}))


def gate_front_month_attribution(df: pd.DataFrame, out: list[Finding]) -> None:
    """
    The contract must actually have been liquid over the window it covers.

    This is the gate that catches a contract listed long before it became the front
    month. Without it, months of near-zero-volume bars enter research as if they were
    tradable.
    """
    if "volume" not in df.columns or df["volume"].isna().all():
        return
    vol = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    daily = vol.groupby(df["timestamp_utc"].dt.date).sum()
    if len(daily) < 5:
        return
    peak = daily.max()
    if peak <= 0:
        out.append(Finding("front_month_attribution", "error",
                           "no volume anywhere in this file"))
        return

    liquid_days = int((daily >= MIN_FRONT_MONTH_VOLUME_SHARE * daily.median()).sum())
    share = liquid_days / len(daily)
    thin = daily[daily < 0.01 * peak]
    if len(thin):
        out.append(Finding(
            "front_month_attribution", "warning",
            f"{len(thin)} of {len(daily)} days have under 1% of peak volume; "
            "trim to the liquid front-month window before research",
            {"thin_days": int(len(thin)), "total_days": int(len(daily)),
             "first_thin": str(thin.index[0]), "last_thin": str(thin.index[-1]),
             "liquid_share": round(share, 3)},
        ))


def gate_session_completeness(df: pd.DataFrame, out: list[Finding]) -> None:
    """
    Each trading session must contain roughly a full session's worth of bars.

    This catches TRUNCATED DOWNLOADS, which are invisible to every other gate: the bars
    present are individually valid, timestamps are monotonic, OHLC is coherent, volume is
    positive. Nothing looks wrong except that most of each session is simply absent.

    Real failure this exists to catch: IBKR's durationStr is session-relative, so an
    endDateTime landing partway through a live session returns only the elapsed part of it.
    A 2026-08-01 run produced 60, 120, and 301-bar weekday responses against a 1380-bar
    full session, roughly 26% completeness overall, and passed every other gate.

    A truncated dataset is worse than a missing one. VWAP, volume profile, opening range,
    and every session statistic would be computed over a NON-RANDOM fraction of the
    session, biased toward whichever hours the anchor happened to capture.
    """
    if len(df) < 100:
        return

    per_day = df.groupby(df["timestamp_utc"].dt.date).size()
    if len(per_day) < 5:
        return

    # Reference "full session" = the 90th percentile of observed daily counts. Using a high
    # quantile rather than the max avoids a single weekend-spanning response setting the bar.
    full = per_day.quantile(0.90)
    if full <= 0:
        return

    completeness = (per_day / full).clip(upper=1.0)
    median_completeness = float(completeness.median())
    truncated = int((completeness < 0.5).sum())

    detail = {
        "median_completeness": round(median_completeness, 3),
        "reference_full_session_bars": int(full),
        "median_bars_per_day": int(per_day.median()),
        "days": int(len(per_day)),
        "days_under_50pct": truncated,
    }

    if median_completeness < 0.80:
        out.append(Finding(
            "session_completeness", "error",
            f"sessions are truncated: median day has {int(per_day.median())} bars against a "
            f"full session of ~{int(full)} ({median_completeness:.0%} complete). "
            "Re-download before using this data.",
            detail,
        ))
    elif truncated > 0.20 * len(per_day):
        out.append(Finding(
            "session_completeness", "warning",
            f"{truncated} of {len(per_day)} days are under 50% of a full session",
            detail,
        ))


def gate_price_continuity(df: pd.DataFrame, out: list[Finding],
                          max_jump_atr: float = MAX_JUMP_ATR) -> None:
    if len(df) < 30:
        return
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=14).mean()
    jump = (df["close"] - df["close"].shift()).abs()
    flagged = jump > (max_jump_atr * atr)
    n = int(flagged.sum())
    if n:
        out.append(Finding("price_continuity", "warning",
                           f"{n} bars jump more than {max_jump_atr}x ATR",
                           {"count": n,
                            "first": str(df.loc[flagged, 'timestamp_utc'].iloc[0])}))


def validate_frame(df: pd.DataFrame, path: str = "<frame>") -> Report:
    rep = Report(path=path, rows=int(len(df)))
    if df.empty:
        rep.findings.append(Finding("schema", "error", "file is empty"))
        return rep
    if not gate_schema(df, rep.findings):
        return rep

    df = df.sort_values("timestamp_utc").reset_index(drop=True)
    gate_timestamps(df, rep.findings)
    gate_ohlc_coherence(df, rep.findings)
    gate_gaps(df, rep.findings)
    gate_volume(df, rep.findings)
    gate_front_month_attribution(df, rep.findings)
    gate_session_completeness(df, rep.findings)
    gate_price_continuity(df, rep.findings)
    return rep


def validate_path(path: Path) -> list[Report]:
    files = sorted(path.rglob("*.parquet")) if path.is_dir() else [path]
    files = [f for f in files if "_cache" not in f.parts]
    reports = []
    for f in files:
        try:
            reports.append(validate_frame(pd.read_parquet(f), str(f)))
        except Exception as exc:                     # noqa: BLE001
            r = Report(path=str(f), rows=0)
            r.findings.append(Finding("read", "error", f"could not read: {exc}"))
            reports.append(r)
    return reports


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Validate downloaded futures bar data.")
    p.add_argument("path", type=Path)
    p.add_argument("--json", type=Path, help="Write a full JSON report here")
    args = p.parse_args(argv)

    if not args.path.exists():
        print(f"no such path: {args.path}", file=sys.stderr)
        return 2

    reports = validate_path(args.path)
    if not reports:
        print("no parquet files found")
        return 1

    n_bad = 0
    for r in reports:
        status = "PASS" if r.ok else "QUARANTINE"
        if not r.ok:
            n_bad += 1
        print(f"{status:11s} {Path(r.path).name:44s} {r.rows:>8,} rows")
        for f in r.findings:
            print(f"    [{f.severity:7s}] {f.gate}: {f.message}")

    print(f"\n{len(reports) - n_bad}/{len(reports)} files passed")

    if args.json:
        args.json.write_text(json.dumps([r.to_dict() for r in reports], indent=2))
        print(f"report written to {args.json}")

    return 0 if n_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
