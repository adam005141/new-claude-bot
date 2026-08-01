"""
Offline tests for the data tooling.

These cover the pure logic only: request planning, chunk merging, and the ingest
validation gates. The IB-connected path in ibkr_download.py is NOT covered, because
this environment has no IB Gateway. That path is unverified until it is run live.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.ibkr_download import (  # noqa: E402
    ContractSpec, Request, plan_requests, merge_cache, DURATION_FOR_BAR_SIZE,
    estimate_runtime_seconds, format_duration, _synthetic_contracts,
)
from tools.validate_data import validate_frame  # noqa: E402

UTC = timezone.utc


def mkspec(month: str, ltd: str, symbol: str = "MES") -> ContractSpec:
    return ContractSpec(symbol=symbol, contract_month=month, last_trade_date=ltd)


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

def test_active_window_ends_at_expiry():
    spec = mkspec("202603", "20260320")
    start, end = spec.active_window(days=100)
    assert end == datetime(2026, 3, 20, tzinfo=UTC)
    assert (end - start).days == 100


def test_plan_walks_backward_within_the_window():
    spec = mkspec("202603", "20260320")
    reqs = plan_requests([spec], "1 min", ["TRADES"],
                         start=datetime(2025, 1, 1, tzinfo=UTC),
                         end=datetime(2026, 12, 31, tzinfo=UTC),
                         active_window_days=10)
    assert len(reqs) == 10                       # 10 days, stepping 1 day at a time
    ends = [r.end_dt for r in reqs]
    assert ends == sorted(ends, reverse=True)    # newest first
    assert max(ends) == datetime(2026, 3, 20, tzinfo=UTC)


def test_plan_clips_to_caller_date_range():
    """A contract whose window predates the requested range must not be fetched."""
    old = mkspec("202409", "20240920")
    reqs = plan_requests([old], "1 min", ["TRADES"],
                         start=datetime(2026, 1, 1, tzinfo=UTC),
                         end=datetime(2026, 12, 31, tzinfo=UTC))
    assert reqs == []


def test_plan_multiplies_by_what_to_show():
    spec = mkspec("202603", "20260320")
    one = plan_requests([spec], "1 min", ["TRADES"],
                        datetime(2025, 1, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC),
                        active_window_days=5)
    three = plan_requests([spec], "1 min", ["TRADES", "BID", "ASK"],
                          datetime(2025, 1, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC),
                          active_window_days=5)
    assert len(three) == 3 * len(one)
    assert {r.what_to_show for r in three} == {"TRADES", "BID", "ASK"}


def test_larger_bar_sizes_use_bigger_chunks():
    spec = mkspec("202603", "20260320")
    kw = dict(start=datetime(2025, 1, 1, tzinfo=UTC),
              end=datetime(2026, 12, 31, tzinfo=UTC), active_window_days=90)
    minute = plan_requests([spec], "1 min", ["TRADES"], **kw)
    hourly = plan_requests([spec], "1 hour", ["TRADES"], **kw)
    assert len(minute) == 90          # 1-day step
    assert len(hourly) == 4           # 25-day step
    assert len(hourly) < len(minute)


def test_requests_overlap_so_no_session_is_caught_midway():
    """
    Regression test for the truncation bug.

    IBKR's durationStr is session-relative: an endDateTime landing partway through a live
    session returns only the elapsed part of it. Stepping by exactly the duration meant
    weekday anchors produced 60-bar responses against a 1380-bar session (~26% complete).

    The duration must therefore cover strictly more ground than the step, so every session
    falls entirely inside at least one request.
    """
    for bar_size, (_dur, duration_days, step_days) in DURATION_FOR_BAR_SIZE.items():
        assert step_days < duration_days, (
            f"{bar_size}: step {step_days}d must be smaller than duration {duration_days}d, "
            "otherwise a session anchored mid-way is silently truncated"
        )


def test_one_minute_steps_daily_with_two_day_duration():
    spec = mkspec("202603", "20260320")
    reqs = plan_requests([spec], "1 min", ["TRADES"],
                         start=datetime(2025, 1, 1, tzinfo=UTC),
                         end=datetime(2026, 12, 31, tzinfo=UTC),
                         active_window_days=10)
    assert len(reqs) == 10                        # unchanged request count
    assert all(r.duration == "2 D" for r in reqs)  # but each covers two days
    ends = sorted({r.end_dt for r in reqs}, reverse=True)
    assert (ends[0] - ends[1]).days == 1           # stepping one day at a time


def test_rejects_unsupported_arguments():
    spec = mkspec("202603", "20260320")
    kw = dict(start=datetime(2025, 1, 1, tzinfo=UTC), end=datetime(2026, 12, 31, tzinfo=UTC))
    with pytest.raises(ValueError, match="unsupported bar size"):
        plan_requests([spec], "3 secs", ["TRADES"], **kw)
    with pytest.raises(ValueError, match="unsupported whatToShow"):
        plan_requests([spec], "1 min", ["NONSENSE"], **kw)


def test_cache_names_are_unique_per_request():
    spec = mkspec("202603", "20260320")
    reqs = plan_requests([spec], "1 min", ["TRADES", "BID"],
                         datetime(2025, 1, 1, tzinfo=UTC), datetime(2026, 12, 31, tzinfo=UTC),
                         active_window_days=20)
    names = [r.cache_name() for r in reqs]
    assert len(names) == len(set(names))


def test_synthetic_contracts_are_third_fridays():
    specs = _synthetic_contracts("MES",
                                 datetime(2025, 1, 1, tzinfo=UTC),
                                 datetime(2026, 6, 30, tzinfo=UTC))
    assert specs
    for s in specs:
        d = datetime.strptime(s.last_trade_date, "%Y%m%d")
        assert d.weekday() == 4          # Friday
        assert 15 <= d.day <= 21         # third one
        assert d.month in (3, 6, 9, 12)


def test_runtime_estimate_and_formatting():
    assert estimate_runtime_seconds(100, 11.0) == 1100.0
    assert format_duration(3661) == "1h 1m"
    assert format_duration(61) == "1m 1s"
    assert format_duration(5) == "5s"


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------

def _chunk(start: datetime, n: int, price: float = 5000.0) -> pd.DataFrame:
    ts = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    return pd.DataFrame({
        "timestamp_utc": ts,
        "open": price, "high": price + 1, "low": price - 1, "close": price,
        "volume": 100,
        "symbol": "MES", "contract_month": "202603",
        "contract_id": "MES202603", "bar_size": "1 min", "what_to_show": "TRADES",
    })


def test_merge_dedupes_sorts_and_writes_metadata(tmp_path):
    cache = tmp_path / "_cache"
    cache.mkdir()
    a = _chunk(datetime(2026, 3, 2, tzinfo=UTC), 60)
    b = _chunk(datetime(2026, 3, 1, tzinfo=UTC), 60)
    overlap = _chunk(datetime(2026, 3, 2, tzinfo=UTC), 10)     # duplicate timestamps
    a.to_parquet(cache / "MES_202603_1min_TRADES_20260302T000000.parquet", index=False)
    b.to_parquet(cache / "MES_202603_1min_TRADES_20260301T000000.parquet", index=False)
    overlap.to_parquet(cache / "MES_202603_1min_TRADES_20260302T001000.parquet", index=False)

    written = merge_cache(cache, tmp_path, "1 min")
    assert len(written) == 1

    df = pd.read_parquet(written[0])
    assert len(df) == 120                                    # overlap removed
    assert df["timestamp_utc"].is_monotonic_increasing
    assert not df["timestamp_utc"].duplicated().any()

    meta = written[0].with_suffix(".meta.json")
    assert meta.exists()
    import json
    m = json.loads(meta.read_text())
    assert m["rows"] == 120
    assert m["adjustment"] == "unadjusted"
    assert m["chunks_merged"] == 3


def test_merge_separates_trades_from_quotes(tmp_path):
    cache = tmp_path / "_cache"
    cache.mkdir()
    t = _chunk(datetime(2026, 3, 1, tzinfo=UTC), 30)
    q = _chunk(datetime(2026, 3, 1, tzinfo=UTC), 30)
    q["what_to_show"] = "BID"
    t.to_parquet(cache / "MES_202603_1min_TRADES_20260301T000000.parquet", index=False)
    q.to_parquet(cache / "MES_202603_1min_BID_20260301T000000.parquet", index=False)

    written = merge_cache(cache, tmp_path, "1 min")
    assert len(written) == 2
    assert {p.name.split("_")[3].replace(".parquet", "") for p in written} == {"TRADES", "BID"}


def test_merge_tolerates_empty_and_corrupt_chunks(tmp_path):
    cache = tmp_path / "_cache"
    cache.mkdir()
    good = _chunk(datetime(2026, 3, 1, tzinfo=UTC), 30)
    good.to_parquet(cache / "MES_202603_1min_TRADES_20260301T000000.parquet", index=False)
    pd.DataFrame().to_parquet(cache / "MES_202603_1min_TRADES_20260302T000000.parquet")
    (cache / "MES_202603_1min_TRADES_20260303T000000.parquet").write_text("not parquet")

    written = merge_cache(cache, tmp_path, "1 min")
    assert len(written) == 1
    assert len(pd.read_parquet(written[0])) == 30


# ---------------------------------------------------------------------------
# Validation gates
# ---------------------------------------------------------------------------

def _clean(n: int = 400) -> pd.DataFrame:
    ts = pd.date_range("2026-03-01", periods=n, freq="1min", tz="UTC")
    close = pd.Series(range(n), dtype="float64") * 0.25 + 5000.0
    return pd.DataFrame({
        "timestamp_utc": ts,
        "open": close, "high": close + 0.5, "low": close - 0.5, "close": close,
        "volume": 100,
    })


def test_clean_data_passes():
    assert validate_frame(_clean()).ok


def test_empty_and_missing_columns_fail():
    assert not validate_frame(pd.DataFrame()).ok
    bad = _clean().drop(columns=["high"])
    rep = validate_frame(bad)
    assert not rep.ok
    assert any("missing required columns" in f.message for f in rep.errors)


def test_duplicate_timestamps_quarantine():
    df = pd.concat([_clean(50), _clean(50)], ignore_index=True)
    rep = validate_frame(df)
    assert not rep.ok
    assert any(f.gate == "timestamps" for f in rep.errors)


def test_incoherent_ohlc_quarantines():
    df = _clean()
    df.loc[10, "low"] = df.loc[10, "high"] + 5      # low above high
    rep = validate_frame(df)
    assert not rep.ok
    assert any(f.gate == "ohlc_coherence" for f in rep.errors)


def test_naive_timestamps_quarantine():
    df = _clean()
    df["timestamp_utc"] = df["timestamp_utc"].dt.tz_localize(None)
    rep = validate_frame(df)
    assert not rep.ok
    assert any("timezone aware" in f.message for f in rep.errors)


def test_negative_volume_quarantines():
    df = _clean()
    df.loc[5, "volume"] = -1
    rep = validate_frame(df)
    assert not rep.ok
    assert any(f.gate == "volume" for f in rep.errors)


def test_mostly_zero_volume_quarantines():
    """The exact failure seen during the audit: a contract not yet the front month."""
    df = _clean()
    df.loc[: len(df) - 20, "volume"] = 0
    rep = validate_frame(df)
    assert not rep.ok
    assert any("not trading in this window" in f.message for f in rep.errors)


def test_quote_bars_without_volume_still_pass():
    """BID/ASK bars legitimately carry no volume and must not be quarantined for it."""
    df = _clean()
    df["volume"] = None
    assert validate_frame(df).ok


def test_thin_prefix_is_flagged_as_warning_not_error():
    """
    Reproduces the audited Sep-2026 MES contract: a year of daily bars whose volume was
    negligible for the first ten months, then jumped once it became the front month.
    Advisory rather than a quarantine, because trimming to the liquid window is the fix.

    Needs enough distinct days to clear the gate's 5-day minimum, so this uses daily
    bars over roughly a year rather than minute bars over two days.
    """
    n = 250
    ts = pd.date_range("2025-08-01", periods=n, freq="1D", tz="UTC")
    close = pd.Series(range(n), dtype="float64") * 2.0 + 6400.0
    df = pd.DataFrame({
        "timestamp_utc": ts,
        "open": close, "high": close + 5, "low": close - 5, "close": close,
        "volume": 5,                                  # pre-front-month dribble
    })
    df.loc[200:, "volume"] = 1_000_000                # becomes front month

    rep = validate_frame(df)
    assert rep.ok                                     # warning, not quarantine
    finding = next(f for f in rep.findings if f.gate == "front_month_attribution")
    assert finding.severity == "warning"
    assert finding.detail["thin_days"] == 200
    assert finding.detail["total_days"] == 250


def test_price_jump_flagged():
    df = _clean()
    df.loc[200:, ["open", "high", "low", "close"]] += 500.0
    rep = validate_frame(df)
    assert any(f.gate == "price_continuity" for f in rep.findings)


def test_truncated_sessions_are_quarantined():
    """
    Reproduces the real 2026-08-01 failure: most days hold a fraction of a session while a
    few weekend-anchored responses hold a full one. Every other gate passes; only
    session_completeness catches it.
    """
    frames = []
    start = pd.Timestamp("2026-03-02", tz="UTC")
    for day in range(40):
        d = start + pd.Timedelta(days=day)
        n = 1380 if day % 7 in (5, 6) else 120     # weekends full, weekdays truncated
        ts = pd.date_range(d, periods=n, freq="1min", tz="UTC")
        c = pd.Series(range(n), dtype="float64") * 0.25 + 5800.0
        frames.append(pd.DataFrame({
            "timestamp_utc": ts, "open": c, "high": c + 0.5, "low": c - 0.5,
            "close": c, "volume": 500,
        }))
    df = pd.concat(frames, ignore_index=True)

    rep = validate_frame(df)
    assert not rep.ok, "truncated sessions must quarantine, not pass"
    f = next(x for x in rep.errors if x.gate == "session_completeness")
    assert f.detail["median_bars_per_day"] == 120
    assert f.detail["reference_full_session_bars"] == 1380
    assert f.detail["median_completeness"] < 0.2


def test_complete_sessions_pass_completeness_gate():
    frames = []
    start = pd.Timestamp("2026-03-02", tz="UTC")
    for day in range(20):
        ts = pd.date_range(start + pd.Timedelta(days=day), periods=1380, freq="1min", tz="UTC")
        c = pd.Series(range(1380), dtype="float64") * 0.25 + 5800.0
        frames.append(pd.DataFrame({
            "timestamp_utc": ts, "open": c, "high": c + 0.5, "low": c - 0.5,
            "close": c, "volume": 500,
        }))
    rep = validate_frame(pd.concat(frames, ignore_index=True))
    assert not any(f.gate == "session_completeness" for f in rep.findings)


def test_hourly_bars_do_not_false_positive_on_completeness():
    """Hourly data has ~23 bars per session; the gate must not read that as truncation."""
    frames = []
    start = pd.Timestamp("2026-03-02", tz="UTC")
    for day in range(30):
        ts = pd.date_range(start + pd.Timedelta(days=day), periods=23, freq="1h", tz="UTC")
        c = pd.Series(range(23), dtype="float64") * 2.0 + 5800.0
        frames.append(pd.DataFrame({
            "timestamp_utc": ts, "open": c, "high": c + 1, "low": c - 1,
            "close": c, "volume": 5000,
        }))
    rep = validate_frame(pd.concat(frames, ignore_index=True))
    assert not any(f.gate == "session_completeness" and f.severity == "error"
                   for f in rep.findings)
