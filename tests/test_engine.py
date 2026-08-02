"""
Engine tests.

These run on SYNTHETIC data. They prove the machinery is correct: no lookahead, adverse
fill resolution, session and DST handling, roll selection, risk state transitions, and
sizing arithmetic. They say nothing whatsoever about whether the strategy is profitable.
"""

from __future__ import annotations

import sys
from datetime import date, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.config import (  # noqa: E402
    COST_ADVERSE, COST_BASE, EngineConfig, MES, MNQ, ES, RiskParams, StrategyParams,
)
from engine.data import choose_active_contract, resample  # noqa: E402
from engine.execution import (  # noqa: E402
    Bar, ExitReason, Position, Side, resolve_exit, realise_pnl,
)
from engine.features import compute, opening_range, session_vwap  # noqa: E402
from engine.risk import RiskEngine, RiskState  # noqa: E402
from engine.sessions import (  # noqa: E402
    ET, Session, classify, classify_index, minutes_since_rth_open, session_date,
)
from engine.sizing import expected_move_floor, size_position, stop_distance  # noqa: E402
from engine.backtest import Backtester  # noqa: E402
from engine.reporting import block_bootstrap_ci, compute_metrics  # noqa: E402
from engine.config import PropRules  # noqa: E402


# ---------------------------------------------------------------------------
# Sessions and the clock
# ---------------------------------------------------------------------------

def test_session_date_rolls_at_1800_et():
    """A bar at 18:00 ET belongs to the NEXT session, matching CME."""
    assert session_date(pd.Timestamp("2026-03-02 22:00", tz="UTC")) == date(2026, 3, 2)
    evening = pd.Timestamp("2026-03-02 23:00", tz="UTC")     # 18:00 EST
    assert session_date(evening) == date(2026, 3, 3)


def test_session_date_survives_dst_transition():
    """
    The sample spans two DST changes. A fixed UTC offset would shift every opening range
    by an hour across the boundary, which is why ET is always resolved via zoneinfo.
    """
    before = pd.Timestamp("2026-03-06 14:30", tz="UTC")      # 09:30 EST
    after = pd.Timestamp("2026-03-13 13:30", tz="UTC")       # 09:30 EDT
    assert before.tz_convert(ET).time() == time(9, 30)
    assert after.tz_convert(ET).time() == time(9, 30)
    assert classify(before) == Session.RTH_OPEN
    assert classify(after) == Session.RTH_OPEN


def test_minutes_since_open_is_zero_at_the_open_in_both_dst_regimes():
    for ts in (pd.Timestamp("2026-03-06 14:30", tz="UTC"),
               pd.Timestamp("2026-03-13 13:30", tz="UTC")):
        assert minutes_since_rth_open(ts) == pytest.approx(0.0)


def test_maintenance_break_is_never_tradable():
    assert classify(pd.Timestamp("2026-03-03 22:30", tz="UTC")) == Session.MAINTENANCE


def test_naive_timestamps_are_rejected():
    with pytest.raises(ValueError, match="tz-aware"):
        session_date(pd.Timestamp("2026-03-02 12:00"))


def test_classify_index_matches_scalar():
    idx = pd.date_range("2026-03-02", periods=300, freq="7min", tz="UTC")
    vec = classify_index(idx)
    for ts in idx[::37]:
        assert vec[ts] == classify(ts)


# ---------------------------------------------------------------------------
# Roll selection
# ---------------------------------------------------------------------------

def test_roll_uses_prior_session_volume_only():
    """
    The active contract must be chosen from already-closed information. Front volume
    crosses on day 3; the engine must not switch until day 4.
    """
    days = [date(2026, 3, d) for d in range(2, 7)]
    front = pd.DataFrame({"session_date": days, "contract_month": "202603",
                          "volume": [900, 900, 100, 100, 100]})
    back = pd.DataFrame({"session_date": days, "contract_month": "202606",
                         "volume": [100, 100, 900, 900, 900]})
    per = {"202603": front.rename(columns={"session_date": "s"}).assign(
               timestamp_utc=pd.to_datetime(front["session_date"]).dt.tz_localize("UTC")),
           "202606": back.assign(
               timestamp_utc=pd.to_datetime(back["session_date"]).dt.tz_localize("UTC"))}
    # choose_active_contract works off session_date + volume directly
    per = {k: v[["timestamp_utc", "volume"]] for k, v in per.items()}
    for k in per:
        per[k] = per[k].assign(volume=per[k]["volume"].astype(float))

    active = choose_active_contract(per)
    mapping = dict(zip(active["session_date"], active["contract_month"]))
    assert mapping[days[2]] == "202603", "must not roll on the day volume crosses"
    assert mapping[days[3]] == "202606", "rolls the session AFTER the crossover"


def test_roll_never_flips_back():
    days = [date(2026, 3, d) for d in range(2, 8)]
    vols_front = [900, 900, 100, 900, 100, 100]     # one noisy day after the roll
    vols_back = [100, 100, 900, 100, 900, 900]
    per = {}
    for name, vols in (("202603", vols_front), ("202606", vols_back)):
        per[name] = pd.DataFrame({
            "timestamp_utc": pd.to_datetime(pd.Series(days)).dt.tz_localize("UTC"),
            "volume": np.array(vols, dtype=float)})
    active = choose_active_contract(per)
    seq = list(active["contract_month"])
    assert seq == sorted(seq), f"roll went backwards: {seq}"


# ---------------------------------------------------------------------------
# Features and lookahead
# ---------------------------------------------------------------------------

def _session_bars(day: str, n: int = 120, freq: str = "5min",
                  start_et: str = "09:30", base: float = 5800.0) -> pd.DataFrame:
    start = pd.Timestamp(f"{day} {start_et}", tz=ET).tz_convert("UTC")
    ts = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    close = base + np.arange(n) * 0.25
    return pd.DataFrame({
        "timestamp_utc": ts, "open": close, "high": close + 1.0,
        "low": close - 1.0, "close": close, "volume": 1000.0,
        "session_date": pd.Timestamp(day).date(), "contract_month": "202603",
        "symbol": "MES", "entries_blocked": False,
    })


def test_opening_range_is_nan_until_the_window_closes():
    df = _session_bars("2026-03-03", n=24)
    orr = opening_range(df, or_minutes=30)
    # First 30 minutes = 6 five-minute bars; range is unknowable inside its own window.
    assert orr["or_high"].iloc[:6].isna().all()
    assert not orr["or_ready"].iloc[:6].any()
    assert orr["or_ready"].iloc[6:].all()
    assert orr["or_high"].iloc[6:].notna().all()


def test_opening_range_freezes_after_the_window():
    df = _session_bars("2026-03-03", n=48)
    orr = opening_range(df, or_minutes=30)
    frozen = orr["or_high"].iloc[6:].unique()
    assert len(frozen) == 1, "range must not update after its window closes"


def test_session_vwap_resets_each_session():
    a = _session_bars("2026-03-03", n=12, base=5800.0)
    b = _session_bars("2026-03-04", n=12, base=6000.0)
    df = pd.concat([a, b], ignore_index=True)
    v = session_vwap(df)
    assert v.iloc[0] == pytest.approx(5800.0, abs=1.0)
    assert v.iloc[12] == pytest.approx(6000.0, abs=1.0), "VWAP must restart, not carry over"


def test_or_width_normalisation_is_scale_free():
    """
    Raw or_width/ATR encodes the timeframe, not the market. For a random walk it grows as
    sqrt(or_minutes / bar_minutes), so a fixed raw threshold means something different at
    every timeframe. The normalised quantity must sit near 1.0 regardless.
    """
    from engine.features import normalise_or_width
    atr_ = pd.Series([2.0] * 10)
    for or_bars, raw_width in ((6, 2.45 * 2.0), (30, 5.48 * 2.0), (3, 1.73 * 2.0)):
        norm = normalise_or_width(pd.Series([raw_width] * 10), atr_, or_bars)
        assert norm.iloc[0] == pytest.approx(1.0, abs=0.02), (
            f"normalised width should be ~1.0 at or_bars={or_bars}, got {norm.iloc[0]:.2f}")


def test_or_width_filter_no_longer_rejects_ordinary_ranges():
    """The old raw-ATR default of 2.5 sat right on the median day and rejected half of it."""
    cfg = EngineConfig()
    assert cfg.strategy.or_max_width_norm == 1.5
    # An ordinary range (norm 1.0) must pass; a genuinely extended one must not.
    assert 1.0 < cfg.strategy.or_max_width_norm < 2.5


def test_features_never_reference_future_bars():
    """
    Truncating the input must not change any feature on the bars that remain. If it does,
    something is reading forward.
    """
    df = _session_bars("2026-03-03", n=60)
    full = compute(df, or_minutes=30, atr_window=14, rvol_lookback=20)
    truncated = compute(df.iloc[:40].copy(), or_minutes=30, atr_window=14, rvol_lookback=20)
    for col in ("vwap", "atr", "or_high", "or_low", "or_width"):
        a = full[col].iloc[:40].to_numpy(dtype=float)
        b = truncated[col].to_numpy(dtype=float)
        assert np.allclose(a, b, equal_nan=True), f"{col} depends on future bars"


# ---------------------------------------------------------------------------
# Execution: every ambiguity resolves against the position
# ---------------------------------------------------------------------------

def _pos(side=Side.LONG, entry=5800.0, stop=5790.0, target=5820.0) -> Position:
    return Position("MES", side, 1, entry, stop, target, 0, None, None, "202603",
                    abs(entry - stop), abs(target - entry), 50.0)


def test_same_bar_stop_and_target_resolves_to_the_stop():
    """The single most important honesty control in the engine."""
    pos = _pos()
    bar = Bar(open=5800, high=5825, low=5785, close=5810)     # spans both
    reason, price = resolve_exit(bar, pos, None, EngineConfig().execution, MES, COST_BASE)
    assert reason is ExitReason.STOP
    assert price <= pos.stop_price


def test_same_bar_resolution_holds_for_shorts():
    pos = _pos(side=Side.SHORT, entry=5800.0, stop=5810.0, target=5780.0)
    bar = Bar(open=5800, high=5815, low=5775, close=5790)
    reason, _ = resolve_exit(bar, pos, None, EngineConfig().execution, MES, COST_BASE)
    assert reason is ExitReason.STOP


def test_stop_fills_at_worse_of_stop_and_next_open():
    """Models a gap through the level rather than a courteous fill at the stop."""
    pos = _pos()
    bar = Bar(open=5795, high=5798, low=5788, close=5789)
    reason, price = resolve_exit(bar, pos, next_open=5770.0,
                                 params=EngineConfig().execution, inst=MES, costs=COST_BASE)
    assert reason is ExitReason.STOP
    assert price <= 5770.0, "must fill at the gapped open, not the stop price"


def test_target_never_gets_favourable_slippage():
    pos = _pos()
    bar = Bar(open=5810, high=5830, low=5805, close=5825)
    reason, price = resolve_exit(bar, pos, None, EngineConfig().execution, MES, COST_BASE)
    assert reason is ExitReason.TARGET
    assert price == pos.target_price


def test_no_exit_when_bar_touches_neither():
    pos = _pos()
    assert resolve_exit(Bar(5800, 5805, 5795, 5802), pos, None,
                        EngineConfig().execution, MES, COST_BASE) is None


def test_pnl_charges_commission_both_sides():
    pos = _pos()
    gross, commission, net = realise_pnl(pos, 5810.0, MES, COST_BASE)
    assert gross == pytest.approx(10.0 * 5.0)
    assert commission == pytest.approx(2 * COST_BASE.commission_per_side)
    assert net == pytest.approx(gross - commission)


# ---------------------------------------------------------------------------
# Sizing
# ---------------------------------------------------------------------------

def test_sizing_always_rounds_down():
    risk = RiskParams(r_target_usd=100.0)
    # 8-point MES stop = $40/contract. 100/40 = 2.5 -> 2, never 3.
    r = size_position(8.0, MES, risk)
    assert r.quantity == 2
    assert r.total_risk_usd == pytest.approx(80.0)
    assert r.risk_deviation == pytest.approx(-0.20)


def test_wide_stop_rounds_to_zero_and_is_reported():
    """One contract already exceeding the budget must be no trade, with a reason."""
    r = size_position(30.0, MES, RiskParams(r_target_usd=100.0))    # $150/contract
    assert r.quantity == 0
    assert not r.ok
    assert r.rejected_reason == "SIZE_ZERO_STOP_TOO_WIDE"


def test_sizing_respects_portfolio_heat():
    risk = RiskParams(r_target_usd=100.0, max_portfolio_heat_usd=150.0)
    r = size_position(8.0, MES, risk, open_heat_usd=120.0)
    assert r.quantity == 0 or r.total_risk_usd <= 30.0


def test_mnq_needs_a_wider_tick_floor():
    cfg = EngineConfig()
    assert cfg.strategy_for("MNQ").min_stop_ticks > cfg.strategy_for("MES").min_stop_ticks


def test_stop_distance_honours_the_tick_floor():
    # Tiny ATR must not produce a stop tighter than the floor.
    assert stop_distance(0.1, MES, m_stop_atr=1.5, min_stop_ticks=8) == pytest.approx(2.0)


def test_move_floor_is_higher_under_worse_costs():
    base = expected_move_floor(MES, COST_BASE, mu_min=0.25)
    adverse = expected_move_floor(MES, COST_ADVERSE, mu_min=0.25)
    assert adverse > base > 0


def test_mnq_costs_less_per_round_trip_than_mes():
    """Smaller tick value, so the same tick spread costs fewer dollars."""
    assert COST_ADVERSE.round_trip_usd(MNQ) < COST_ADVERSE.round_trip_usd(MES)


# ---------------------------------------------------------------------------
# Risk state machine
# ---------------------------------------------------------------------------

def test_mll_ratchets_on_end_of_day_balance_and_never_falls():
    """Reproduces Topstep's own worked example exactly."""
    r = RiskEngine(rules=PropRules(), risk=RiskParams())
    assert r.mll_floor == 48_000.0

    r.start_session(date(2026, 3, 2))
    r.record_trade(500.0)                       # balance 50,500
    r.start_session(date(2026, 3, 3))           # end-of-day ratchet fires
    assert r.mll_floor == pytest.approx(48_500.0)

    r.record_trade(-500.0)                      # back to 50,000
    r.start_session(date(2026, 3, 4))
    assert r.mll_floor == pytest.approx(48_500.0), "floor must never move down"


def test_mll_locks_permanently_at_starting_balance():
    r = RiskEngine(rules=PropRules(), risk=RiskParams())
    r.start_session(date(2026, 3, 2))
    r.record_trade(5_000.0)                     # far above the lock point
    r.start_session(date(2026, 3, 3))
    assert r.mll_floor == pytest.approx(50_000.0)
    r.record_trade(5_000.0)
    r.start_session(date(2026, 3, 4))
    assert r.mll_floor == pytest.approx(50_000.0), "floor must stop at the start balance"


def test_breach_halts_permanently_with_safety_margin():
    r = RiskEngine(rules=PropRules(), risk=RiskParams())
    r.start_session(date(2026, 3, 2))
    r.record_trade(-1_600.0)                    # equity 48,400, below floor 48,000 + 500 margin
    d = r.evaluate()
    assert d.state is RiskState.HALTED_PERMANENT
    assert d.must_flatten and not d.can_enter


def test_open_loss_can_breach_before_it_is_realised():
    """Equity-based evaluation, the conservative reading of an unresolved rule."""
    r = RiskEngine(rules=PropRules(), risk=RiskParams())
    r.start_session(date(2026, 3, 2))
    assert r.evaluate(open_pnl=-1_600.0).state is RiskState.HALTED_PERMANENT
    # And the usable buffer is exactly 1,500, so a smaller open loss must NOT halt.
    fresh = RiskEngine(rules=PropRules(), risk=RiskParams())
    fresh.start_session(date(2026, 3, 2))
    assert fresh.evaluate(open_pnl=-1_400.0).can_enter


def test_topstepx_has_no_firm_daily_loss_limit():
    rules = PropRules()
    assert rules.daily_loss_limit_usd is None
    r = RiskEngine(rules=rules, risk=RiskParams())
    r.start_session(date(2026, 3, 2))
    r.record_trade(-250.0)
    assert r.evaluate().can_enter, "no firm DLL on TopstepX below the self-imposed stop"


def test_self_imposed_stop_halts_the_day_only():
    r = RiskEngine(rules=PropRules(self_imposed_daily_stop_usd=300.0), risk=RiskParams())
    r.start_session(date(2026, 3, 2))
    r.record_trade(-300.0)
    assert r.evaluate().state is RiskState.HALTED_DAY
    r.start_session(date(2026, 3, 3))
    assert r.evaluate().can_enter, "a daily halt must clear at the next session"


def test_profit_target_halts_trading():
    r = RiskEngine(rules=PropRules(), risk=RiskParams())
    r.start_session(date(2026, 3, 2))
    r.record_trade(3_000.0)
    assert r.evaluate().state is RiskState.HALTED_TARGET


def test_consistency_cap_flattens_without_ending_the_evaluation():
    r = RiskEngine(rules=PropRules(consistency_day_cap_usd=1_400.0), risk=RiskParams())
    r.start_session(date(2026, 3, 2))
    r.record_trade(1_400.0)
    d = r.evaluate()
    assert d.state is RiskState.FLATTEN_ONLY and not d.can_enter


def test_flat_time_blocks_new_entries():
    r = RiskEngine(rules=PropRules(), risk=RiskParams())
    r.start_session(date(2026, 3, 2))
    assert not r.evaluate(at_or_after_flat_time=True).can_enter


def test_data_fault_fails_closed():
    r = RiskEngine(rules=PropRules(), risk=RiskParams())
    r.start_session(date(2026, 3, 2))
    d = r.evaluate(data_fault=True)
    assert d.state is RiskState.HALTED_DAY and d.must_flatten


def test_personal_mode_ignores_prop_limits():
    r = RiskEngine(rules=PropRules(enabled=False), risk=RiskParams())
    r.start_session(date(2026, 3, 2))
    r.record_trade(-5_000.0)
    assert r.evaluate().can_enter, "personal mode must not apply the prop layer"


# ---------------------------------------------------------------------------
# Config guards
# ---------------------------------------------------------------------------

def test_reference_instruments_cannot_be_traded():
    assert not ES.orderable
    with pytest.raises(ValueError, match="reference instrument"):
        EngineConfig(symbols=("ES",))


def test_parameters_outside_the_registered_range_are_rejected():
    with pytest.raises(ValueError, match="pre-registered range"):
        StrategyParams(or_minutes=240).validate()
    with pytest.raises(ValueError, match="pre-registered range"):
        StrategyParams(m_stop_atr=99.0).validate()


def test_default_cost_scenario_is_adverse_not_base():
    assert EngineConfig().cost_scenario == "adverse"


# ---------------------------------------------------------------------------
# End-to-end determinism
# ---------------------------------------------------------------------------

def _synthetic_market(days: int = 30, seed: int = 3) -> pd.DataFrame:
    """Random-walk sessions with a genuine opening range. Not a profitable market."""
    rng = np.random.default_rng(seed)
    frames = []
    d = pd.Timestamp("2026-03-02")
    made = 0
    while made < days:
        if d.weekday() >= 5:
            d += timedelta(days=1)
            continue
        start = pd.Timestamp(f"{d.date()} 09:30", tz=ET).tz_convert("UTC")
        n = 78                                   # 6.5h of 5-minute bars
        steps = rng.normal(0, 1.5, n)
        close = 5800 + np.cumsum(steps)
        frames.append(pd.DataFrame({
            "timestamp_utc": pd.date_range(start, periods=n, freq="5min", tz="UTC"),
            "open": close - steps, "high": close + abs(rng.normal(0, 1, n)),
            "low": close - abs(rng.normal(0, 1, n)), "close": close,
            "volume": rng.integers(500, 2000, n).astype(float),
            "session_date": d.date(), "contract_month": "202603",
            "symbol": "MES", "entries_blocked": False,
        }))
        made += 1
        d += timedelta(days=1)
    return pd.concat(frames, ignore_index=True)


def test_backtest_runs_and_is_deterministic():
    cfg = EngineConfig(symbols=("MES",))
    feats = compute(_synthetic_market(), or_minutes=30, atr_window=14, rvol_lookback=20)
    a = Backtester(cfg, "MES").run(feats)
    b = Backtester(cfg, "MES").run(feats)
    assert a.bars_processed == b.bars_processed
    pd.testing.assert_frame_equal(a.trades_frame(), b.trades_frame())


def test_backtest_never_holds_a_position_overnight():
    cfg = EngineConfig(symbols=("MES",))
    feats = compute(_synthetic_market(), or_minutes=30, atr_window=14, rvol_lookback=20)
    trades = Backtester(cfg, "MES").run(feats).trades_frame()
    if trades.empty:
        pytest.skip("no trades generated on this synthetic sample")
    entry_sessions = pd.to_datetime(trades["entry_time"]).dt.tz_convert(ET).dt.date
    exit_sessions = pd.to_datetime(trades["exit_time"]).dt.tz_convert(ET).dt.date
    assert (entry_sessions == exit_sessions).all(), "position survived a session boundary"


def test_worse_costs_never_improve_results():
    feats = compute(_synthetic_market(), or_minutes=30, atr_window=14, rvol_lookback=20)
    nets = {}
    for scenario in ("base", "adverse", "severe"):
        cfg = EngineConfig(symbols=("MES",), cost_scenario=scenario)
        t = Backtester(cfg, "MES").run(feats).trades_frame()
        nets[scenario] = 0.0 if t.empty else t["net_usd"].sum()
    assert nets["severe"] <= nets["adverse"] <= nets["base"] + 1e-6


def test_prop_mode_cannot_outperform_personal_mode():
    """The prop layer only ever removes permission, so it can never add profit."""
    from dataclasses import replace
    feats = compute(_synthetic_market(60), or_minutes=30, atr_window=14, rvol_lookback=20)

    personal = EngineConfig(symbols=("MES",))
    personal.prop = replace(personal.prop, enabled=False)
    p_trades = Backtester(personal, "MES").run(feats).trades_frame()
    c_trades = Backtester(EngineConfig(symbols=("MES",)), "MES").run(feats).trades_frame()
    assert len(c_trades) <= len(p_trades)


def test_metrics_and_bootstrap_handle_empty_input():
    m = compute_metrics(pd.DataFrame())
    assert m.trades == 0 and m.net_usd == 0.0
    assert block_bootstrap_ci(pd.DataFrame()) == {}


def test_resample_never_spans_sessions():
    a = _session_bars("2026-03-03", n=12, freq="1min")
    b = _session_bars("2026-03-04", n=12, freq="1min")
    out = resample(pd.concat([a, b], ignore_index=True), minutes=5)
    assert out["session_date"].nunique() == 2
    for _, g in out.groupby("session_date"):
        assert g["contract_month"].nunique() == 1
