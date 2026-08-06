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

import numpy as np
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


# ---------------------------------------------------------------------------
# Barchart import
# ---------------------------------------------------------------------------

def _barchart_csv(tmp_path, tz_name: str, name: str, days: int = 12) -> Path:
    """A Barchart-style export with a realistic 09:30 ET volume spike, written in tz."""
    import numpy as np
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    rng = np.random.default_rng(3)
    rows, d, made = [], pd.Timestamp("2024-01-02"), 0
    while made < days:
        if d.weekday() < 5:
            start = pd.Timestamp(f"{(d - pd.Timedelta(days=1)).date()} 18:00", tz=et)
            ts = pd.date_range(start, periods=1380, freq="1min", tz=et)
            mod = ts.hour * 60 + ts.minute
            vol = np.where((mod >= 570) & (mod < 575), 9000,
                  np.where((mod >= 570) & (mod < 960), 1200, 150)).astype(float)
            px = 4750 + np.cumsum(rng.normal(0, 0.5, len(ts)))
            local = ts.tz_convert(ZoneInfo(tz_name)).tz_localize(None)
            rows.append(pd.DataFrame({
                "Time": local.strftime("%m/%d/%Y %H:%M"),
                "Open": px.round(2), "High": (px + .5).round(2),
                "Low": (px - .5).round(2), "Last": px.round(2),
                "Volume": vol.astype(int)}))
            made += 1
        d += pd.Timedelta(days=1)
    path = tmp_path / name
    with open(path, "w", newline="") as fh:
        pd.concat(rows, ignore_index=True).to_csv(fh, index=False)
        fh.write("Downloaded from Barchart.com as of 08/02/2026\n")
    return path


def test_barchart_symbol_parsing():
    from tools.import_barchart import parse_symbol
    assert parse_symbol("MESM26") == ("MES", "202606")
    assert parse_symbol("MNQZ25") == ("MNQ", "202512")
    assert parse_symbol("ESH24") == ("ES", "202403")
    with pytest.raises(ValueError, match="cannot parse"):
        parse_symbol("NOTASYMBOL")


def test_barchart_reader_strips_the_provenance_footer(tmp_path):
    from tools.import_barchart import read_csv
    df = read_csv(_barchart_csv(tmp_path, "America/New_York", "MESH24.csv", days=2))
    assert len(df) == 2 * 1380
    assert {"timestamp", "open", "high", "low", "close", "volume"} <= set(df.columns)
    assert df["close"].notna().all()


def test_timezone_is_inferred_from_the_opening_volume_spike(tmp_path):
    """
    The CSV carries no timezone marker. Reading a Central export as Eastern shifts every
    bar by an hour, builds the opening range from 08:30 data, and still produces a
    plausible-looking backtest. Inference exists so that cannot happen silently.
    """
    from tools.import_barchart import infer_timezone, read_csv
    for tz in ("America/New_York", "America/Chicago"):
        df = read_csv(_barchart_csv(tmp_path, tz, f"MESH24_{tz[-5:]}.csv"))
        best, scores = infer_timezone(df)
        assert best == tz, f"inferred {best}, expected {tz}"
        assert scores[tz] > 5.0, "the correct timezone should win decisively"


def test_inference_refuses_without_volume(tmp_path):
    from tools.import_barchart import infer_timezone, read_csv
    df = read_csv(_barchart_csv(tmp_path, "America/New_York", "MESH24.csv", days=2))
    df["volume"] = np.nan
    with pytest.raises(ValueError, match="cannot infer timezone without volume"):
        infer_timezone(df)


def test_mismatched_timezone_across_files_aborts(tmp_path):
    """
    A relative test, not an absolute one. A one-hour shift still lands the "09:30" window
    inside elevated RTH volume and scores ~2.5x, which passes any fixed threshold. What
    exposes it is another timezone scoring far better on the same file.
    """
    from tools.import_barchart import cmd_import
    src = tmp_path / "src"; src.mkdir()
    _barchart_csv(src, "America/New_York", "MESH24.csv")
    _barchart_csv(src, "America/Chicago", "MESM24.csv")
    assert cmd_import(src, tmp_path / "out", None, None, "1min") == 2


def test_consistent_timezone_imports_and_round_trips(tmp_path):
    """After import, the volume spike must still land at 09:30 Eastern."""
    from tools.import_barchart import cmd_import
    from zoneinfo import ZoneInfo
    src = tmp_path / "src"; src.mkdir()
    _barchart_csv(src, "America/Chicago", "MESH24.csv")
    out = tmp_path / "out"
    assert cmd_import(src, out, None, None, "1min") == 0

    written = out / "MES" / "MES_202403_1min_TRADES.parquet"
    assert written.exists()
    df = pd.read_parquet(written)
    et = pd.DatetimeIndex(df["timestamp_utc"]).tz_convert(ZoneInfo("America/New_York"))
    peak = df.assign(m=et.strftime("%H:%M")).groupby("m")["volume"].sum().idxmax()
    assert peak.startswith("09:3"), f"spike landed at {peak}, not the 09:30 ET open"


def test_import_records_timezone_provenance(tmp_path):
    """How the timezone was determined must be recorded, not just what it was."""
    import json
    from tools.import_barchart import cmd_import
    src = tmp_path / "src"; src.mkdir()
    _barchart_csv(src, "America/Chicago", "MESH24.csv")
    out = tmp_path / "out"
    cmd_import(src, out, None, None, "1min")
    meta = json.loads((out / "MES" / "MES_202403_1min_TRADES.meta.json").read_text())
    assert meta["source_timezone"] == "America/Chicago"
    assert "inferred" in meta["timezone_determination"]
    assert meta["adjustment"] == "unadjusted"


def _junk_csv(d: Path, name: str, text: str) -> Path:
    path = d / name
    path.write_text(text)
    return path


def test_import_skips_unrelated_csvs_instead_of_aborting(tmp_path):
    """
    A real Downloads folder is full of bank statements and invoices. Aborting on the
    first unrecognised file would make --src point at it useless.
    """
    from tools.import_barchart import cmd_import
    src = tmp_path / "Downloads"; src.mkdir()
    _barchart_csv(src, "America/Chicago", "MESH24_2024-01-02.csv")
    _junk_csv(src, "bank_statement.csv", "Date,Description,Amount\n2024-01-01,COFFEE,-4.50\n")
    _junk_csv(src, "invoice.csv", "a,b,c\n1,2,3\n")

    assert cmd_import(src, tmp_path / "out", None, None, "1min") == 0
    assert (tmp_path / "out" / "MES" / "MES_202403_1min_TRADES.parquet").exists()


def test_symbol_is_read_from_a_symbol_column_when_the_filename_lacks_it(tmp_path):
    """Browsers save Barchart exports under names like 'barchart_export (3).csv'."""
    from tools.import_barchart import cmd_import, symbol_from_content
    src = tmp_path / "Downloads"; src.mkdir()
    made = _barchart_csv(src, "America/Chicago", "MESM24_tmp.csv", days=12)

    # Rewrite it with a Symbol column and a filename carrying no contract.
    df = pd.read_csv(made, nrows=12 * 1380)
    df.insert(0, "Symbol", "MESM24")
    renamed = src / "barchart_export (3).csv"
    df.to_csv(renamed, index=False)
    made.unlink()

    assert symbol_from_content(renamed) == "MESM24"
    assert cmd_import(src, tmp_path / "out", None, None, "1min") == 0
    assert (tmp_path / "out" / "MES" / "MES_202406_1min_TRADES.parquet").exists()


def test_import_errors_only_when_nothing_is_usable(tmp_path):
    from tools.import_barchart import cmd_import
    src = tmp_path / "Downloads"; src.mkdir()
    _junk_csv(src, "bank_statement.csv", "Date,Description,Amount\n2024-01-01,X,-1\n")
    assert cmd_import(src, tmp_path / "out", None, None, "1min") == 1


def test_latest_column_is_recognised_as_close(tmp_path):
    """
    Barchart's intraday historical download names the close column "Latest", not "Last".
    The first real download of 124 files was rejected entirely because of this.
    """
    from tools.import_barchart import read_csv
    src = tmp_path / "esh24_intraday-1min.csv"
    pd.DataFrame({
        "timestamp": ["01/02/2024 09:30", "01/02/2024 09:31"],
        "open": [4750.0, 4751.0], "high": [4751.0, 4752.0], "low": [4749.0, 4750.0],
        "latest": [4750.5, 4751.5], "change": [0.25, 0.25], "%change": ["0.01%", "0.01%"],
        "volume": [1000, 1200],
    }).to_csv(src, index=False)

    df = read_csv(src)
    assert "close" in df.columns
    assert df["close"].tolist() == [4750.5, 4751.5]


def test_all_close_column_spellings_map(tmp_path):
    from tools.import_barchart import read_csv
    for spelling in ("Close", "Last", "Latest", "Settle"):
        src = tmp_path / f"esh24_{spelling}.csv"
        pd.DataFrame({
            "Time": ["01/02/2024 09:30"], "Open": [4750.0], "High": [4751.0],
            "Low": [4749.0], spelling: [4750.5], "Volume": [1000],
        }).to_csv(src, index=False)
        assert read_csv(src)["close"].iloc[0] == 4750.5, f"{spelling} not mapped"


def test_es_symbols_parse_to_the_es_root():
    """The importer must label ES data as ES, not silently treat it as MES."""
    from tools.import_barchart import parse_symbol
    assert parse_symbol("ESH24") == ("ES", "202403")
    assert parse_symbol("ESU23") == ("ES", "202309")
    assert parse_symbol("MESH24") == ("MES", "202403")


def _flat_volume_csv(tmp_path, tz_name: str, name: str, days: int = 10) -> Path:
    """
    A contract window with NO opening spike, which is what a pre-front-month period
    looks like: thin, flat volume with no RTH dominance.
    """
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    rng = np.random.default_rng(9)
    rows, d, made = [], pd.Timestamp("2024-01-02"), 0
    while made < days:
        if d.weekday() < 5:
            start = pd.Timestamp(f"{(d - pd.Timedelta(days=1)).date()} 18:00", tz=et)
            ts = pd.date_range(start, periods=1380, freq="1min", tz=et)
            px = 4750 + np.cumsum(rng.normal(0, 0.5, len(ts)))
            local = ts.tz_convert(ZoneInfo(tz_name)).tz_localize(None)
            rows.append(pd.DataFrame({
                "Time": local.strftime("%m/%d/%Y %H:%M"),
                "Open": px.round(2), "High": (px + .5).round(2),
                "Low": (px - .5).round(2), "Latest": px.round(2),
                "Volume": rng.integers(1, 5, len(ts))}))     # flat, no spike
            made += 1
        d += pd.Timedelta(days=1)
    path = tmp_path / name
    with open(path, "w", newline="") as fh:
        pd.concat(rows, ignore_index=True).to_csv(fh, index=False)
    return path


def test_spikeless_file_is_imported_not_treated_as_a_timezone_mismatch(tmp_path):
    """
    A file with no opening spike is a THIN-DATA problem, not a timezone problem.

    The first version aborted the whole import when a pre-front-month window scored
    1.14x against a 3.09x alternative, claiming a timezone mismatch. Both numbers are
    weak; real files score near 19x. Accusing a file requires the alternative to look
    like a genuine spike, not merely a better bad one.
    """
    from tools.import_barchart import cmd_import
    src = tmp_path / "src"; src.mkdir()
    _barchart_csv(src, "America/Chicago", "ESH24_good.csv")
    _flat_volume_csv(src, "America/Chicago", "ESM25_thin.csv")

    assert cmd_import(src, tmp_path / "out", None, None, "1min") == 0
    assert (tmp_path / "out" / "ES" / "ES_202403_1min_TRADES.parquet").exists()
    assert (tmp_path / "out" / "ES" / "ES_202506_1min_TRADES.parquet").exists()


def test_genuine_timezone_shift_still_aborts(tmp_path):
    """The relaxation must not disarm the guard against a real one-hour shift."""
    from tools.import_barchart import cmd_import
    src = tmp_path / "src"; src.mkdir()
    _barchart_csv(src, "America/New_York", "ESH24_eastern.csv")
    _barchart_csv(src, "America/Chicago", "ESM24_central.csv")
    assert cmd_import(src, tmp_path / "out", None, None, "1min") == 2


# ---------------------------------------------------------------------------
# Cost hurdle: the identity that quantity cancels
# ---------------------------------------------------------------------------

def test_cost_hurdle_identity_matches_the_engines_own_sizing():
    """
    cost_in_R = round_trip_points / stop_points is claimed to be EXACT, not approximate.
    If integer rounding or the contract cap leaked into it the whole analysis would be
    wrong, so it is checked against size_position rather than asserted.
    """
    from engine.config import MES, MNQ, COST_ADVERSE, RiskParams
    from engine.sizing import size_position
    from tools.cost_hurdle import cost_in_r

    risk = RiskParams()
    checked = 0
    for inst in (MES, MNQ):
        rt_points = COST_ADVERSE.round_trip_points(inst)
        for stop_pts in (2.0, 4.0, 6.5, 8.8, 13.0, 20.0, 26.0):
            s = size_position(stop_pts, inst, risk)
            if not s.ok:
                continue
            empirical = (s.quantity * COST_ADVERSE.round_trip_usd(inst)) / s.total_risk_usd
            assert empirical == pytest.approx(cost_in_r(rt_points, stop_pts), abs=1e-12), (
                f"{inst.symbol} at {stop_pts} points: identity broke")
            checked += 1
    assert checked >= 10, "the sweep must actually exercise several sizes"


def test_wider_stops_lower_the_hurdle_proportionally():
    from tools.cost_hurdle import cost_in_r
    assert cost_in_r(0.99, 20.0) == pytest.approx(cost_in_r(0.99, 10.0) / 2)


def test_hurdle_table_refuses_geometries_the_engine_would_refuse():
    """
    A table that recommends a stop size_position rejects would be worse than useless. The
    refusal point is where one contract exceeds the R budget.
    """
    from engine.config import MES, COST_ADVERSE, RiskParams
    from engine.sizing import size_position
    from tools.cost_hurdle import report

    risk = RiskParams()
    # Median ATR of 10 points puts the wider multiples past the MES refusal point of
    # r_target / point_value = 100 / 5 = 20 points.
    rows = report(MES, COST_ADVERSE, pd.Series([10.0] * 50), risk)
    assert any(not r["tradable"] for r in rows), "sweep must reach the refusal point"
    for r in rows:
        engine_says_ok = size_position(r["stop_points"], MES, risk).ok
        assert r["tradable"] == engine_says_ok, (
            f"table and engine disagree at {r['stop_points']:.1f} points")


def test_cheapest_instrument_in_dollars_need_not_be_cheapest_in_R():
    """
    The measured finding was that MNQ costs MORE per contract in dollars. In R it can
    still be cheaper, because its point moves are larger relative to its tick. This is the
    claim the tool exists to make checkable, so it is pinned here.
    """
    from engine.config import MES, MNQ, COST_ADVERSE
    from tools.cost_hurdle import cost_in_r

    # Same stop expressed in each instrument's own ATR units: ES 5-min ATR near 6 points,
    # NQ near 3.4x that. Illustrative multiples, not measurements.
    mes = cost_in_r(COST_ADVERSE.round_trip_points(MES), 1.5 * 6.0)
    mnq = cost_in_r(COST_ADVERSE.round_trip_points(MNQ), 1.5 * 20.4)
    assert COST_ADVERSE.round_trip_usd(MNQ) < COST_ADVERSE.round_trip_usd(MES)
    assert mnq < mes, "MNQ should be cheaper in R at comparable ATR multiples"


def test_redenominating_slippage_charges_equal_dollars_across_instruments():
    """
    The 0.5-tick slippage prior charges MES $0.625/side and MNQ $0.250/side for the same
    nominal allowance, purely because a tick is worth different amounts. This helper is
    how that assumption gets tested rather than inherited.
    """
    from engine.config import MES, MNQ, COST_ADVERSE
    from tools.cost_hurdle import redenominate_slippage

    for inst in (MES, MNQ):
        alt = redenominate_slippage(COST_ADVERSE, inst, 0.625)
        assert alt.slippage_ticks_per_side * inst.tick_value == pytest.approx(0.625)
        # Spread and commission must pass through untouched; only slippage is restated.
        assert alt.spread_ticks_per_side == COST_ADVERSE.spread_ticks_per_side
        assert alt.commission_per_side == COST_ADVERSE.commission_per_side


def test_the_dollar_instrument_ranking_is_an_artefact_but_the_R_ranking_is_not():
    """
    Pinned because it changed a conclusion. With measured spreads (MES 1 tick, MNQ 3
    ticks) MNQ looks cheaper per round trip under the tick-denominated slippage prior and
    MORE expensive under a dollar-denominated one. The R ranking does not flip, so the
    R conclusion is safe and the dollar one is not.
    """
    from engine.config import MES, MNQ, CostModel
    from tools.cost_hurdle import cost_in_r, redenominate_slippage

    mes_c = CostModel("m", 0.60, 1.0, 0.5)      # measured MES p75 spread
    mnq_c = CostModel("m", 0.60, 3.0, 0.5)      # measured MNQ p75 spread
    med_atr = {"MES": 3.28, "MNQ": 16.42}       # measured dev medians, 5-min bars

    ticks = {i.symbol: c.round_trip_usd(i) for i, c in ((MES, mes_c), (MNQ, mnq_c))}
    usd = {i.symbol: redenominate_slippage(c, i, 0.625).round_trip_usd(i)
           for i, c in ((MES, mes_c), (MNQ, mnq_c))}
    assert ticks["MNQ"] < ticks["MES"], "tick-denominated: MNQ looks cheaper"
    assert usd["MNQ"] > usd["MES"], "dollar-denominated: MNQ looks dearer. Ranking flips."

    for costs in (lambda i, c: c, lambda i, c: redenominate_slippage(c, i, 0.625)):
        r = {i.symbol: cost_in_r(costs(i, c).round_trip_points(i), 1.5 * med_atr[i.symbol])
             for i, c in ((MES, mes_c), (MNQ, mnq_c))}
        assert r["MNQ"] < r["MES"], "the R ranking must NOT flip"
