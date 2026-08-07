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
from engine.regime import Regime  # noqa: E402
from engine.strategy import SessionState  # noqa: E402


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


# ---------------------------------------------------------------------------
# Re-entry guards
# ---------------------------------------------------------------------------

def _orb_row(close: float, or_high: float = 5807.0, or_low: float = 5793.0,
             atr_: float = 4.0, rvol: float = 2.0) -> dict:
    # width 14 against a baseline of atr*sqrt(6)=9.8 gives norm 1.43, inside the 1.5 cap.
    width = or_high - or_low
    return {
        "close": close, "or_high": or_high, "or_low": or_low, "or_width": width,
        "or_width_norm": width / (atr_ * np.sqrt(6)), "atr": atr_, "rvol": rvol,
        "or_ready": True, "entries_blocked": False,
    }


def _orb(**overrides):
    from engine.strategy import OpeningRangeBreakout
    from engine.config import StrategyParams, RiskParams, COST_ADVERSE, MES
    return OpeningRangeBreakout(StrategyParams(**overrides), MES, RiskParams(), COST_ADVERSE)


def test_first_entry_is_taken():
    from engine.strategy import SessionState, Signal
    out = _orb().evaluate(_orb_row(close=5830.0), SessionState(), bar_index=10)
    assert isinstance(out, Signal) and out.side is Side.LONG


def test_reentry_blocked_during_cooldown():
    """A stop-out followed immediately by another breakout is the whipsaw case."""
    from engine.strategy import SessionState, Rejection
    st = SessionState(entries=1, last_exit_bar=10, last_entry_long=5825.0)
    out = _orb(reentry_cooldown_bars=3).evaluate(_orb_row(close=5850.0), st, bar_index=12)
    assert isinstance(out, Rejection) and out.reason == "REENTRY_COOLDOWN"


def test_reentry_requires_a_new_extreme():
    """
    After the cooldown, re-entering at or below the previous entry would be buying the
    same failed level again and booking it as an independent trade.
    """
    from engine.strategy import SessionState, Rejection, Signal
    st = SessionState(entries=1, last_exit_bar=10, last_entry_long=5825.0)
    orb = _orb(reentry_cooldown_bars=3, reentry_new_extreme_atr=0.5)

    # atr=4.0, so a new extreme needs +2.0 beyond 5825.
    too_close = orb.evaluate(_orb_row(close=5826.0), st, bar_index=20)
    assert isinstance(too_close, Rejection) and too_close.reason == "NO_NEW_EXTREME"

    far_enough = orb.evaluate(_orb_row(close=5828.0), st, bar_index=20)
    assert isinstance(far_enough, Signal)


def test_new_extreme_rule_applies_per_direction():
    """A long entry must not block a short re-entry; a regime flip is a genuine setup."""
    from engine.strategy import SessionState, Signal
    st = SessionState(entries=1, last_exit_bar=10, last_entry_long=5825.0)
    out = _orb(reentry_cooldown_bars=3).evaluate(_orb_row(close=5770.0), st, bar_index=20)
    assert isinstance(out, Signal) and out.side is Side.SHORT


def test_entry_cap_is_enforced():
    from engine.strategy import SessionState
    st = SessionState(entries=3, last_exit_bar=1)
    assert _orb(max_entries_per_session=3).evaluate(
        _orb_row(close=5900.0), st, bar_index=50) is None


def test_reentry_state_resets_each_session():
    """Yesterday's entries must not restrict today."""
    cfg = EngineConfig(symbols=("MES",))
    feats = compute(_synthetic_market(40), or_minutes=30, atr_window=14,
                    rvol_lookback=20, bar_minutes=5)
    trades = Backtester(cfg, "MES").run(feats).trades_frame()
    if trades.empty:
        pytest.skip("no trades on this synthetic sample")
    per_session = trades.groupby("session_date").size()
    assert per_session.max() <= cfg.strategy.max_entries_per_session


def test_reentry_raises_the_trade_ceiling():
    """The whole point of allowing re-entry: more independent observations."""
    feats = compute(_synthetic_market(60), or_minutes=30, atr_window=14,
                    rvol_lookback=20, bar_minutes=5)
    from dataclasses import replace
    once = EngineConfig(symbols=("MES",), strategy=StrategyParams(max_entries_per_session=1))
    many = EngineConfig(symbols=("MES",), strategy=StrategyParams(max_entries_per_session=3))
    n1 = len(Backtester(once, "MES").run(feats).trades_frame())
    n3 = len(Backtester(many, "MES").run(feats).trades_frame())
    assert n3 >= n1


def test_reentry_params_are_range_checked():
    with pytest.raises(ValueError, match="pre-registered range"):
        StrategyParams(max_entries_per_session=50).validate()
    with pytest.raises(ValueError, match="pre-registered range"):
        StrategyParams(reentry_new_extreme_atr=9.0).validate()


def test_rejections_are_only_counted_for_actual_breakouts():
    """
    Filters must be evaluated AFTER a breakout is detected, so every rejection counter
    describes the same population: setups that actually triggered. A filter evaluated
    earlier fires on every eligible bar and swamps the others in the diagnostics.
    """
    from engine.strategy import SessionState
    orb = _orb()
    # Price sitting inside the range is not a setup, so nothing should be counted at all,
    # even though the range is deliberately too wide and the contract is blocked.
    quiet = _orb_row(close=5800.0, or_high=5807.0, or_low=5793.0, atr_=1.0)
    quiet["entries_blocked"] = True
    assert orb.evaluate(quiet, SessionState(), bar_index=5) is None


def test_wide_range_is_only_reported_when_a_breakout_triggers():
    from engine.strategy import SessionState, Rejection
    orb = _orb()
    wide = _orb_row(close=5900.0, or_high=5850.0, or_low=5750.0, atr_=4.0)
    out = orb.evaluate(wide, SessionState(), bar_index=5)
    assert isinstance(out, Rejection) and out.reason == "OR_TOO_WIDE"


# ---------------------------------------------------------------------------
# Measured cost model
# ---------------------------------------------------------------------------

def _measured_file(tmp_path, open_median=2.0, mid_median=1.0):
    """Quote stats with a deliberately wider opening hour, as real markets show."""
    import json
    doc = {"instruments": {"MES": {
        "tick_size": 0.25, "tick_value_usd": 1.25, "point_value_usd": 5.0,
        "overall": {"median_ticks": 1.0, "p75_ticks": 1.0, "p95_ticks": 2.0},
        "by_session": {
            "RTH_OPEN": {"median_ticks": open_median, "p75_ticks": open_median,
                         "p95_ticks": open_median * 2},
            "RTH_MIDDAY": {"median_ticks": mid_median, "p75_ticks": mid_median,
                           "p95_ticks": mid_median},
        }}}}
    path = tmp_path / "measured.json"
    path.write_text(json.dumps(doc))
    return path


def test_measured_costs_replace_assumptions(tmp_path):
    from engine.config import measured_cost_models
    models = measured_cost_models(_measured_file(tmp_path), "MES")
    assert all(m.measured for m in models.values())
    assert models["base"].spread_ticks_per_side == 1.0
    assert models["severe"].spread_ticks_per_side == 2.0


def test_measured_costs_keep_a_slippage_allowance(tmp_path):
    """
    Quoted spread is a lower bound. Setting slippage to zero would assert that a market
    order transacts exactly at the quote, which is false.
    """
    from engine.config import measured_cost_models
    for m in measured_cost_models(_measured_file(tmp_path), "MES").values():
        assert m.slippage_ticks_per_side > 0


def test_session_costs_are_charged_where_the_strategy_trades(tmp_path):
    """
    Leg B fires in the opening hour. Charging it the all-day median would understate the
    cost of precisely the trades it takes.
    """
    from engine.config import measured_cost_models
    path = _measured_file(tmp_path, open_median=2.0, mid_median=1.0)
    allday = measured_cost_models(path, "MES")["base"]
    at_open = measured_cost_models(path, "MES", session="RTH_OPEN")["base"]
    assert at_open.spread_ticks_per_side == 2.0
    assert at_open.spread_ticks_per_side > allday.spread_ticks_per_side
    assert at_open.round_trip_usd(MES) > allday.round_trip_usd(MES)


def test_missing_symbol_raises_rather_than_silently_using_priors(tmp_path):
    """A run that believes it used measured costs but quietly used guesses is worse."""
    from engine.config import measured_cost_models
    with pytest.raises(KeyError, match="not present"):
        measured_cost_models(_measured_file(tmp_path), "MNQ")


def test_missing_session_raises(tmp_path):
    from engine.config import measured_cost_models
    with pytest.raises(KeyError, match="not measured"):
        measured_cost_models(_measured_file(tmp_path), "MES", session="ASIA")


def test_engine_uses_per_symbol_measured_costs(tmp_path):
    import json
    doc = json.loads(_measured_file(tmp_path).read_text())
    doc["instruments"]["MNQ"] = {
        "tick_size": 0.25, "tick_value_usd": 0.50, "point_value_usd": 2.0,
        "overall": {"median_ticks": 1.0, "p75_ticks": 2.0, "p95_ticks": 4.0}}
    path = tmp_path / "both.json"
    path.write_text(json.dumps(doc))

    cfg = EngineConfig(symbols=("MES", "MNQ"), measured_costs_path=str(path))
    mes, mnq = cfg.costs_for("MES"), cfg.costs_for("MNQ")
    assert mes.spread_ticks_per_side == 1.0
    assert mnq.spread_ticks_per_side == 2.0, "each instrument gets its own measured spread"


def test_assumed_costs_used_when_no_measured_file():
    cfg = EngineConfig(symbols=("MES",))
    assert not cfg.costs_for("MES").measured


# ---------------------------------------------------------------------------
# Price-source proxy
# ---------------------------------------------------------------------------

def test_reference_instrument_still_cannot_be_traded_and_says_what_to_do():
    """
    The orderable guard must stay. Researching on ES history is a price-source
    substitution, not a licence to emit ES orders.
    """
    with pytest.raises(ValueError, match="price_source instead"):
        EngineConfig(symbols=("ES",))


def test_price_source_keeps_the_traded_instrument_economics():
    """
    Prices may come from ES; point value, tick value, and costs must not. ES is worth
    ten times MES per point, so leaking its economics would inflate every P&L tenfold.
    """
    cfg = EngineConfig(symbols=("MES",), price_source="ES")
    assert cfg.instrument("MES").point_value == 5.00
    assert cfg.price_source == "ES"
    # The traded instrument is still the micro, and still orderable.
    assert cfg.instrument("MES").orderable


def test_price_source_must_be_a_known_symbol():
    with pytest.raises(ValueError, match="unknown price_source"):
        EngineConfig(symbols=("MES",), price_source="NOTREAL")


def test_price_source_is_recorded_in_the_fingerprint():
    """A proxy run must be identifiable as one from its artefacts alone."""
    assert EngineConfig(symbols=("MES",), price_source="ES").fingerprint()["price_source"] == "ES"
    assert EngineConfig(symbols=("MES",)).fingerprint()["price_source"] is None


# ---------------------------------------------------------------------------
# Early termination
# ---------------------------------------------------------------------------

def test_permanent_halt_marks_the_run_as_path_truncated():
    """
    When the account breaches the MLL the replay stops, because a dead account cannot
    keep trading. The result must SAY so: the trades are then a path-truncated sample
    that stops at the moment of death, not a sample of the period, and every statistic
    computed from them is conditioned on surviving that far.
    """
    from dataclasses import replace
    feats = compute(_synthetic_market(120, seed=11), or_minutes=30, atr_window=14,
                    rvol_lookback=20, bar_minutes=5)
    cfg = EngineConfig(symbols=("MES",))
    # A tiny buffer guarantees the breach inside the sample.
    cfg.prop = replace(cfg.prop, mll_buffer=200.0, self_imposed_daily_stop_usd=None)

    result = Backtester(cfg, "MES").run(feats)
    if result.final_state != "HALTED_PERMANENT":
        pytest.skip("synthetic sample did not breach")

    assert result.terminated_early
    assert 0 < result.sessions_processed < feats["session_date"].nunique()


def test_a_surviving_run_is_not_flagged_as_truncated():
    from dataclasses import replace
    feats = compute(_synthetic_market(40), or_minutes=30, atr_window=14,
                    rvol_lookback=20, bar_minutes=5)
    cfg = EngineConfig(symbols=("MES",))
    cfg.prop = replace(cfg.prop, enabled=False)
    result = Backtester(cfg, "MES").run(feats)
    assert not result.terminated_early
    assert result.sessions_processed == feats["session_date"].nunique()


def test_trade_rate_divides_by_sessions_actually_replayed():
    """
    Dividing by the full split understates the trade rate by exactly the fraction of the
    split that never ran. The first ES proxy run reported 0.18 trades/session against a
    true rate near 0.6 for this reason.
    """
    from engine.reporting import compute_metrics
    trades = pd.DataFrame({
        "net_usd": [10.0] * 60, "gross_usd": [11.0] * 60, "commission_usd": [1.0] * 60,
        "risk_usd": [100.0] * 60, "risk_deviation": [0.0] * 60, "bars_held": [5] * 60,
        "session_date": [date(2026, 3, 1 + i % 100) if i % 100 < 28 else date(2026, 3, 1)
                         for i in range(60)],
    })
    full_split = compute_metrics(trades, sessions_in_sample=400)
    observed = compute_metrics(trades, sessions_in_sample=100)
    assert observed.trades_per_day == pytest.approx(4 * full_split.trades_per_day)


# ---------------------------------------------------------------------------
# Leg A: regime classification and VWAP band reversion
# ---------------------------------------------------------------------------

def _regime_inputs(slope, rvol, rv_pct):
    return (pd.Series([slope]), pd.Series([rvol]), pd.Series([rv_pct]))


def _classify_one(slope, rvol, rv_pct, **kw):
    from engine.regime import classify
    p = {"theta_trend": 0.35, "theta_range": 0.15, "theta_rvol": 1.10,
         "rv_lo": 0.20, "rv_hi": 0.80, **kw}
    return classify(*_regime_inputs(slope, rvol, rv_pct), **p).iloc[0]


def test_regime_neutral_band_between_the_thresholds_never_trades():
    """
    A slope between theta_range and theta_trend belongs to neither regime. Without the
    gap every bar is forced into a regime and the classifier manufactures trades exactly
    where its own signal is weakest.
    """
    from engine.regime import Regime
    assert _classify_one(0.25, 1.5, 0.5) is Regime.NEUTRAL
    assert _classify_one(0.10, 1.5, 0.5) is Regime.RANGE
    assert _classify_one(0.50, 1.5, 0.5) is Regime.TREND


def test_regime_missing_inputs_are_never_tradable():
    from engine.regime import Regime
    assert _classify_one(np.nan, 1.5, 0.5) is Regime.NEUTRAL
    assert _classify_one(0.10, np.nan, 0.5) is Regime.NEUTRAL
    assert _classify_one(0.10, 1.5, np.nan) is Regime.NEUTRAL


def test_regime_range_requires_middling_volatility():
    """Flat slope is not enough: the quietest and wildest days are excluded by rv_pct."""
    from engine.regime import Regime
    assert _classify_one(0.10, 1.5, 0.05) is Regime.NEUTRAL
    assert _classify_one(0.10, 1.5, 0.95) is Regime.NEUTRAL


def test_regime_trend_requires_participation():
    """A steep VWAP on thin volume is drift, not a trend, so it must not classify TREND."""
    from engine.regime import Regime
    assert _classify_one(0.90, 0.40, 0.5) is Regime.NEUTRAL


def test_collapsing_the_neutral_band_is_rejected_by_config():
    with pytest.raises(ValueError, match="theta_range"):
        StrategyParams(theta_range=0.35, theta_trend=0.35).validate()


def _leg_a_row(**over):
    row = {
        "close": 5800.0, "vwap": 5810.0, "vwap_sigma": 4.0,
        "vwap_dev": -2.0, "prev_vwap_dev": -2.6, "atr": 3.0, "rvol": 1.0,
        "bar_of_session": 50, "regime": Regime.RANGE, "entries_blocked": False,
    }
    row.update(over)
    return row


def _leg_a(params: StrategyParams | None = None):
    from engine.strategy import VWAPBandReversion
    return VWAPBandReversion(params or StrategyParams(), MES, RiskParams(), COST_ADVERSE)


def test_leg_a_requires_excursion_then_reclaim_not_just_a_touch():
    """
    A touch rule enters into continuing momentum. The two-bar structure demands the prior
    bar be OUTSIDE the band and the current bar back inside it.
    """
    from engine.strategy import Signal
    leg = _leg_a()
    # Excursion at t-1, reclaim at t: this is the setup.
    assert isinstance(leg.evaluate(_leg_a_row(), SessionState()), Signal)
    # Still outside at t: the market has not demonstrated rejection yet.
    assert leg.evaluate(_leg_a_row(vwap_dev=-2.4), SessionState()) is None
    # Never outside at t-1: nothing to revert from.
    assert leg.evaluate(_leg_a_row(prev_vwap_dev=-1.5), SessionState()) is None


def test_leg_a_refuses_to_fade_a_trending_market():
    from engine.strategy import Rejection
    leg = _leg_a()
    for r in (Regime.TREND, Regime.NEUTRAL):
        out = leg.evaluate(_leg_a_row(regime=r), SessionState())
        assert isinstance(out, Rejection) and out.reason == "NOT_RANGE_REGIME"


def test_leg_a_shorts_are_the_exact_mirror_of_longs():
    from engine.strategy import Signal
    leg = _leg_a()
    long_ = leg.evaluate(_leg_a_row(), SessionState())
    short = leg.evaluate(_leg_a_row(close=5820.0, vwap_dev=2.0, prev_vwap_dev=2.6),
                         SessionState())
    assert isinstance(short, Signal) and short.side is Side.SHORT
    assert short.target_distance_points == pytest.approx(long_.target_distance_points)
    assert short.stop_distance_points == pytest.approx(long_.stop_distance_points)


def test_leg_a_targets_the_mean_and_never_beyond_it():
    """Target is VWAP itself. A move that has already reached it is not a trade."""
    leg = _leg_a()
    sig = leg.evaluate(_leg_a_row(), SessionState())
    assert sig.target_distance_points == pytest.approx(10.0)   # 5810 vwap - 5800 close
    assert leg.evaluate(_leg_a_row(close=5815.0), SessionState()) is None


def test_leg_a_rejects_a_reversion_too_small_to_pay_its_own_costs():
    from engine.strategy import Rejection
    leg = _leg_a()
    floor = expected_move_floor(MES, COST_ADVERSE, RiskParams().mu_min)
    # A VWAP a hair above the close leaves less room than the round trip needs.
    out = leg.evaluate(_leg_a_row(vwap=5800.0 + floor / 2), SessionState())
    assert isinstance(out, Rejection) and out.reason == "MOVE_FLOOR"


def test_leg_a_reentry_requires_a_deeper_excursion_not_a_further_breakout():
    """
    Leg B's new-extreme fence looks for price extending past the prior entry. For a
    reversion the analogue is inverted: a second long must be further BELOW the first,
    otherwise a slow bleed through the band books correlated losses as new trades.
    """
    from engine.strategy import Rejection, Signal
    leg = _leg_a()
    state = SessionState(entries=1, last_exit_bar=0, last_entry_long=5800.0)
    shallower = leg.evaluate(_leg_a_row(close=5801.0), state, bar_index=10)
    assert isinstance(shallower, Rejection) and shallower.reason == "NO_NEW_EXTREME"
    deeper = leg.evaluate(_leg_a_row(close=5795.0, vwap=5810.0), state, bar_index=10)
    assert isinstance(deeper, Signal)


def test_leg_a_waits_for_the_vwap_sigma_to_settle():
    leg = _leg_a()
    assert leg.evaluate(_leg_a_row(bar_of_session=2), SessionState()) is None


def test_leg_selection_actually_changes_the_strategy():
    from engine.strategy import OpeningRangeBreakout, VWAPBandReversion
    assert isinstance(Backtester(EngineConfig(symbols=("MES",), leg="A"), "MES").strategy,
                      VWAPBandReversion)
    assert isinstance(Backtester(EngineConfig(symbols=("MES",), leg="B"), "MES").strategy,
                      OpeningRangeBreakout)


def test_leg_a_features_never_reference_future_bars():
    df = _session_bars("2026-03-03", n=60)
    full = compute(df, or_minutes=30, atr_window=14, rvol_lookback=20)
    trunc = compute(df.iloc[:40].copy(), or_minutes=30, atr_window=14, rvol_lookback=20)
    for col in ("vwap_sigma", "vwap_dev", "prev_vwap_dev"):
        a = full[col].iloc[:40].to_numpy(dtype=float)
        b = trunc[col].to_numpy(dtype=float)
        assert np.allclose(a, b, equal_nan=True), f"{col} depends on future bars"


def test_prev_vwap_dev_never_crosses_a_session_boundary():
    a = _session_bars("2026-03-03", n=20, base=5800.0)
    b = _session_bars("2026-03-04", n=20, base=6000.0)
    feats = compute(pd.concat([a, b], ignore_index=True),
                    or_minutes=30, atr_window=14, rvol_lookback=20)
    first_of_second = feats.index[feats["session_date"] == date(2026, 3, 4)][0]
    assert pd.isna(feats["prev_vwap_dev"].iloc[first_of_second]), (
        "the first bar of a session must not inherit the previous session's deviation")


def test_leg_a_backtest_runs_and_is_deterministic():
    cfg = EngineConfig(symbols=("MES",), leg="A")
    feats = compute(_synthetic_market(), or_minutes=30, atr_window=14, rvol_lookback=20)
    a = Backtester(cfg, "MES").run(feats)
    b = Backtester(cfg, "MES").run(feats)
    pd.testing.assert_frame_equal(a.trades_frame(), b.trades_frame())


# ---------------------------------------------------------------------------
# Overnight, gap and prior-session structure
# ---------------------------------------------------------------------------

def _overnight_market(days: int = 25, seed: int = 3, start: str = "2026-03-02"):
    """Sessions that actually contain a Globex overnight, 18:00 ET through 16:00 ET."""
    from engine.sessions import session_dates
    rng = np.random.default_rng(seed)
    frames, d = [], pd.Timestamp(start)
    while len(frames) < days:
        if d.weekday() >= 5:
            d += timedelta(days=1)
            continue
        first = pd.Timestamp(f"{(d - timedelta(days=1)).date()} 18:00",
                             tz=ET).tz_convert("UTC")
        n = 22 * 12
        steps = rng.normal(0, 1.2, n)
        close = 5800 + np.cumsum(steps)
        frames.append(pd.DataFrame({
            "timestamp_utc": pd.date_range(first, periods=n, freq="5min", tz="UTC"),
            "open": close - steps, "high": close + abs(rng.normal(0, .8, n)),
            "low": close - abs(rng.normal(0, .8, n)), "close": close,
            "volume": rng.integers(200, 2000, n).astype(float),
            "symbol": "MES", "contract_month": "202603", "entries_blocked": False,
        }))
        d += timedelta(days=1)
    df = pd.concat(frames, ignore_index=True)
    df["session_date"] = session_dates(pd.DatetimeIndex(df["timestamp_utc"])).values
    return df


def test_minutes_since_open_is_negative_before_the_open_across_the_1800_boundary():
    """
    The bug this replaced: wall-clock arithmetic put an 18:00 ET bar at +510 minutes AFTER
    its session's open instead of -930 before it. Every overnight feature would inherit it.
    """
    from engine.overnight import minutes_since_open
    df = _overnight_market(5)
    mso = minutes_since_open(df)
    et = pd.DatetimeIndex(df["timestamp_utc"]).tz_convert(ET)
    for hhmm, expected in (("18:00", -930), ("22:00", -690), ("02:00", -450),
                           ("09:30", 0), ("15:55", 385)):
        got = mso[et.strftime("%H:%M") == hhmm]
        assert (got == expected).all(), f"{hhmm} ET gave {got.unique()}, expected {expected}"


def test_minutes_since_open_survives_a_dst_transition():
    """US DST moved on 2026-03-08. A fixed offset would shift every session by an hour."""
    from engine.overnight import minutes_since_open
    df = _overnight_market(8, start="2026-03-04")
    mso = minutes_since_open(df)
    et = pd.DatetimeIndex(df["timestamp_utc"]).tz_convert(ET)
    at_open = mso[et.strftime("%H:%M") == "09:30"]
    assert (at_open == 0).all(), "09:30 ET is minute zero in both DST regimes"


def test_overnight_levels_are_blank_until_the_open_and_frozen_after():
    df = _overnight_market(10)
    feats = compute(df, or_minutes=30, atr_window=14, rvol_lookback=20)
    for sd, g in feats.groupby("session_date"):
        pre = g[g["minutes_since_open"] < 0]
        post = g[g["minutes_since_open"] >= 0]
        if pre.empty or post.empty:
            continue
        assert pre["on_high"].isna().all(), "a forming overnight high must not be visible"
        assert not pre["on_ready"].any(), "on_ready must be False before the open"
        assert post["on_high"].nunique() == 1, "overnight high must freeze at the open"
        assert post["on_high"].iloc[0] == pytest.approx(pre["high"].max())
        assert post["on_low"].iloc[0] == pytest.approx(pre["low"].min())


def test_gap_is_measured_against_the_prior_session_cash_close():
    df = _overnight_market(10)
    feats = compute(df, or_minutes=30, atr_window=14, rvol_lookback=20)
    sessions = sorted(feats["session_date"].unique())
    prev, cur = sessions[3], sessions[4]
    p = feats[feats["session_date"] == prev]
    p_rth = p[(p["minutes_since_open"] >= 0) & (p["minutes_since_open"] < 390)]
    c = feats[(feats["session_date"] == cur) & (feats["minutes_since_open"] >= 0)]
    expected = c["open"].iloc[0] - p_rth["close"].iloc[-1]
    assert c["gap_points"].iloc[0] == pytest.approx(expected)


def test_overnight_features_never_reference_future_bars():
    df = _overnight_market(12)
    full = compute(df, or_minutes=30, atr_window=14, rvol_lookback=20)
    cut = int(len(df) * 0.7)
    trunc = compute(df.iloc[:cut].copy(), or_minutes=30, atr_window=14, rvol_lookback=20)
    # The final session of the truncated frame is genuinely incomplete, so compare only
    # sessions that are whole in both.
    whole = set(trunc["session_date"].unique()) - {trunc["session_date"].iloc[-1]}
    a = full[full["session_date"].isin(whole)].reset_index(drop=True)
    b = trunc[trunc["session_date"].isin(whole)].reset_index(drop=True)
    for col in ("on_high", "on_low", "on_range", "gap_points", "prior_rth_close",
                "dist_on_high_atr", "on_pos", "minutes_since_open"):
        assert np.allclose(a[col].to_numpy(dtype=float), b[col].to_numpy(dtype=float),
                           equal_nan=True), f"{col} depends on future bars"


# ---------------------------------------------------------------------------
# Leg C: opening gap fade
# ---------------------------------------------------------------------------

def _leg_c_row(**over):
    row = {
        "close": 5810.0, "prior_rth_close": 5800.0, "gap_vs_on_range": 0.5,
        "atr": 6.67, "minutes_since_open": 0.0, "on_ready": True,
        "entries_blocked": False,
    }
    row.update(over)
    return row


def _leg_c(params: StrategyParams | None = None):
    from engine.strategy import GapFade
    return GapFade(params or StrategyParams(), MES, RiskParams(), COST_ADVERSE)


def test_leg_c_fades_the_gap_toward_the_prior_cash_close():
    from engine.strategy import Signal
    leg = _leg_c()
    up = leg.evaluate(_leg_c_row(), SessionState())
    assert isinstance(up, Signal) and up.side is Side.SHORT
    assert up.target_distance_points == pytest.approx(10.0)   # 5810 close - 5800 prior

    down = leg.evaluate(_leg_c_row(close=5790.0, gap_vs_on_range=-0.5), SessionState())
    assert isinstance(down, Signal) and down.side is Side.LONG
    assert down.target_distance_points == pytest.approx(10.0)


def test_leg_c_will_not_chase_a_gap_that_has_already_filled():
    """If price has crossed back through the prior close the move is gone, not available."""
    leg = _leg_c()
    assert leg.evaluate(_leg_c_row(close=5795.0), SessionState()) is None
    assert leg.evaluate(_leg_c_row(close=5805.0, gap_vs_on_range=-0.5), SessionState()) is None


def test_leg_c_band_excludes_noise_below_and_news_above():
    from engine.strategy import Rejection
    leg = _leg_c()
    small = leg.evaluate(_leg_c_row(gap_vs_on_range=0.10), SessionState())
    assert isinstance(small, Rejection) and small.reason == "GAP_TOO_SMALL"
    huge = leg.evaluate(_leg_c_row(gap_vs_on_range=1.8), SessionState())
    assert isinstance(huge, Rejection) and huge.reason == "GAP_TOO_LARGE"


def test_leg_c_only_fires_near_the_open():
    leg = _leg_c()
    assert leg.evaluate(_leg_c_row(minutes_since_open=10.0), SessionState()) is not None
    assert leg.evaluate(_leg_c_row(minutes_since_open=45.0), SessionState()) is None
    assert leg.evaluate(_leg_c_row(minutes_since_open=-30.0), SessionState()) is None


def test_leg_c_takes_one_trade_per_session():
    """There is only one opening gap. A second attempt is a different trade."""
    leg = _leg_c()
    assert leg.evaluate(_leg_c_row(), SessionState(entries=1)) is None


def test_leg_c_refuses_before_the_overnight_range_is_complete():
    leg = _leg_c()
    assert leg.evaluate(_leg_c_row(on_ready=False), SessionState()) is None


def test_inverted_gap_band_is_rejected_by_config():
    with pytest.raises(ValueError, match="gap_min_range"):
        StrategyParams(gap_min_range=0.9, gap_max_range=0.6).validate()


def test_leg_c_runs_end_to_end_and_is_deterministic():
    cfg = EngineConfig(symbols=("MES",), leg="C")
    feats = compute(_overnight_market(30), or_minutes=30, atr_window=14, rvol_lookback=20)
    a = Backtester(cfg, "MES").run(feats)
    b = Backtester(cfg, "MES").run(feats)
    pd.testing.assert_frame_equal(a.trades_frame(), b.trades_frame())
    trades = a.trades_frame()
    if not trades.empty:
        assert (trades.groupby("session_date").size() <= 1).all(), "one gap trade per session"


# ---------------------------------------------------------------------------
# Overnight trading: session enablement and the flat rule
# ---------------------------------------------------------------------------

def test_the_futures_hour_after_the_cash_close_is_tradable():
    """
    16:00-17:00 ET is 15:00-16:00 CT and the contract is open. It used to classify CLOSED,
    which silently removed a tradable hour from every screen.
    """
    from engine.sessions import Session as S
    ts = pd.Timestamp("2026-03-04 16:30", tz=ET).tz_convert("UTC")
    assert classify(ts) == S.POST_CLOSE
    assert S.POST_CLOSE in __import__("engine.sessions", fromlist=["x"]).DEFAULT_ENABLED


def test_the_daily_halt_is_never_tradable():
    """17:00-18:00 ET is the CME break, which is the user's 14:00-15:00 Pacific."""
    from engine.sessions import Session as S, DEFAULT_ENABLED as EN
    assert S.MAINTENANCE not in EN
    assert S.CLOSED not in EN
    ts = pd.Timestamp("2026-03-04 17:30", tz=ET).tz_convert("UTC")
    assert classify(ts) == S.MAINTENANCE


def test_overnight_sessions_are_now_enabled():
    from engine.sessions import Session as S, DEFAULT_ENABLED as EN, RTH_ONLY
    for s in (S.ASIA, S.LONDON, S.EU_NY_OVERLAP, S.NY_PREMARKET):
        assert s in EN, f"{s} must be tradable now that overnight holds are allowed"
    assert RTH_ONLY < EN, "RTH_ONLY is kept so pre-2026-08-06 results stay reproducible"


def test_flat_time_precedes_the_halt_not_the_cash_close():
    cfg = EngineConfig()
    assert cfg.risk.flat_time_et == time(16, 50)
    assert cfg.risk.flat_time_et < time(17, 0), "must be flat BEFORE the CME break"


def test_a_position_still_never_crosses_a_session_boundary():
    """
    The invariant survives the rule change, and that is the point: the 17:00 flat
    requirement lands on the 18:00 session roll, so allowing overnight holds lengthens the
    leash inside a session without ever letting one span two.
    """
    cfg = EngineConfig(symbols=("MES",), leg="C")
    feats = compute(_overnight_market(20), or_minutes=30, atr_window=14, rvol_lookback=20)
    trades = Backtester(cfg, "MES").run(feats).trades_frame()
    if trades.empty:
        pytest.skip("no trades on this synthetic sample")
    entry_sd = pd.to_datetime(trades["entry_time"]).map(session_date)
    exit_sd = pd.to_datetime(trades["exit_time"]).map(session_date)
    assert (entry_sd == exit_sd).all()


def test_session_windows_cover_every_tradable_minute():
    """
    A gap in the window map silently deletes tradable time. Sweep the clock and assert
    that the only unclassified minutes are the halt itself.
    """
    from engine.sessions import Session as S
    idx = pd.date_range("2026-03-04 00:00", periods=24 * 60, freq="1min", tz=ET)
    named = classify_index(pd.DatetimeIndex(idx).tz_convert("UTC"))
    et = idx
    for s, t in zip(named.to_numpy(), et):
        minute = t.hour * 60 + t.minute
        if 17 * 60 <= minute < 18 * 60:
            assert s == S.MAINTENANCE, f"{t.time()} should be the halt, got {s}"
        else:
            assert s != S.CLOSED, f"{t.time()} classified CLOSED but the market is open"


# ---------------------------------------------------------------------------
# Leg D: overnight hold
# ---------------------------------------------------------------------------

def _leg_d(params: StrategyParams | None = None):
    from engine.strategy import OvernightHold
    return OvernightHold(params or StrategyParams(), MES, RiskParams(), COST_ADVERSE)


def test_leg_d_arms_only_at_the_globex_open():
    from engine.strategy import Signal
    leg = _leg_d()
    row = {"close": 5800.0, "atr": 5.0, "minutes_since_open": -930.0,
           "entries_blocked": False}
    assert isinstance(leg.evaluate(row, SessionState()), Signal)
    assert leg.evaluate({**row, "minutes_since_open": -880.0}, SessionState()) is None
    assert leg.evaluate({**row, "minutes_since_open": -100.0}, SessionState()) is None
    assert leg.evaluate({**row, "minutes_since_open": 60.0}, SessionState()) is None


def test_leg_d_exit_is_the_clock_not_a_bar_count():
    """
    An overnight hold is defined by WHEN it closes. Expressing it as a bar count would
    change meaning silently on any session missing a few bars.
    """
    leg = _leg_d()
    sig = leg.evaluate({"close": 5800.0, "atr": 5.0, "minutes_since_open": -930.0,
                        "entries_blocked": False}, SessionState())
    assert sig.exit_by_mso == 0.0, "must close at the 09:30 ET open"


def test_leg_d_stop_is_a_disaster_brake_not_a_risk_unit():
    """
    Measured overnight session sd is about 24.5 points. The stop must sit far outside
    that, or the leg becomes the same path bet that killed Legs A and C.
    """
    leg = _leg_d()
    sig = leg.evaluate({"close": 5800.0, "atr": 5.0, "minutes_since_open": -930.0,
                        "entries_blocked": False}, SessionState())
    assert sig.stop_distance_points == pytest.approx(100.0)   # $500 / $5 per point
    assert sig.stop_distance_points > 3 * 24.5


def test_leg_d_takes_one_exposure_per_session():
    leg = _leg_d()
    row = {"close": 5800.0, "atr": 5.0, "minutes_since_open": -930.0,
           "entries_blocked": False}
    assert leg.evaluate(row, SessionState(entries=1)) is None


def test_r_sizer_refuses_leg_d_and_fixed_sizing_is_why_it_exists():
    """
    A 100-point stop risks $500 a contract against a $100 R target, so the R sizer
    correctly refuses. Fixed sizing is the narrow, explicit override.
    """
    from engine.sizing import size_position
    r = RiskParams()
    assert size_position(100.0, MES, r).rejected_reason == "SIZE_ZERO_STOP_TOO_WIDE"
    fixed = size_position(100.0, MES, RiskParams(fixed_contracts=1))
    assert fixed.ok and fixed.quantity == 1
    # The deviation from target stays visible rather than being hidden by the override.
    assert fixed.total_risk_usd == pytest.approx(500.0)
    assert fixed.risk_deviation == pytest.approx(4.0)


def test_fixed_sizing_of_zero_is_refused():
    from engine.sizing import size_position
    got = size_position(100.0, MES, RiskParams(fixed_contracts=0))
    assert not got.ok and got.rejected_reason == "FIXED_SIZE_ZERO"


def test_leg_d_runs_end_to_end_and_holds_overnight():
    from dataclasses import replace
    cfg = EngineConfig(symbols=("MES",), leg="D")
    cfg.risk = replace(cfg.risk, fixed_contracts=1)
    cfg.prop = replace(cfg.prop, enabled=False)
    feats = compute(_overnight_market(30), or_minutes=30, atr_window=14, rvol_lookback=20)
    res = Backtester(cfg, "MES").run(feats)
    trades = res.trades_frame()
    assert not trades.empty, "leg D must trade every session it can"
    assert (trades["side"] == "LONG").all()
    assert (trades.groupby("session_date").size() <= 1).all()
    # Entered in the evening, exited the next morning, still inside one session date.
    entry_et = pd.to_datetime(trades["entry_time"]).dt.tz_convert(ET)
    exit_et = pd.to_datetime(trades["exit_time"]).dt.tz_convert(ET)
    assert (entry_et.dt.hour >= 18).all(), "entry must be at the Globex open"
    assert (exit_et.dt.hour < 12).all(), "exit must be at the RTH open"
    assert (exit_et.dt.date > entry_et.dt.date).all(), "the hold must span the night"


def test_flat_time_is_session_relative_not_wall_clock():
    """
    Regression. `et.time() >= flat_time` reads correctly only for a session confined to
    the afternoon. Once overnight holds were allowed it silently forbade all of them: an
    18:00 ET bar is "after 16:50" on the clock while being fifteen hours BEFORE its own
    session's flat time. Leg D raised a signal every night and the risk gate refused every
    one, producing an empty trade list rather than an error.
    """
    from dataclasses import replace
    cfg = EngineConfig(symbols=("MES",), leg="D")
    cfg.risk = replace(cfg.risk, fixed_contracts=1)
    cfg.prop = replace(cfg.prop, enabled=False)
    feats = compute(_overnight_market(20), or_minutes=30, atr_window=14, rvol_lookback=20)
    trades = Backtester(cfg, "MES").run(feats).trades_frame()
    entry_et = pd.to_datetime(trades["entry_time"]).dt.tz_convert(ET)
    assert (entry_et.dt.hour >= 18).any(), (
        "entries after the wall-clock flat time but before the session flat time "
        "must be permitted")


def test_positions_are_still_flattened_at_the_session_flat_time():
    """The other half: the fix must not disable the flat rule it generalised."""
    from dataclasses import replace
    from engine.overnight import minutes_since_open
    cfg = EngineConfig(symbols=("MES",), leg="C")
    cfg.prop = replace(cfg.prop, enabled=False)
    feats = compute(_overnight_market(25), or_minutes=30, atr_window=14, rvol_lookback=20)
    trades = Backtester(cfg, "MES").run(feats).trades_frame()
    if trades.empty:
        pytest.skip("no trades on this synthetic sample")
    exit_mso = minutes_since_open(
        pd.DataFrame({"timestamp_utc": pd.to_datetime(trades["exit_time"]),
                      "session_date": trades["session_date"]}))
    assert (exit_mso <= cfg.risk.flat_time_et.hour * 60
            + cfg.risk.flat_time_et.minute - (9 * 60 + 30)).all(), \
        "no position may survive its session's flat time"


def test_symbols_containing_digits_are_discoverable():
    """
    Regression. The discovery pattern used `[A-Z]+` for the symbol, so M2K, M6E and MYM
    were silently invisible: the file sat on disk and the engine reported "no files" rather
    than raising. Found when a commodity import produced M2K and nothing could read it.
    """
    import tempfile
    from engine.data import discover
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for name in ("M2K_202603_1min_TRADES.parquet", "MES_202603_1min_TRADES.parquet",
                     "M6E_202603_1min_TRADES.parquet"):
            (root / name).write_bytes(b"")
        for sym in ("M2K", "MES", "M6E"):
            assert len(discover(root, sym)) == 1, f"{sym} not discovered"
        # The six-digit contract must not be absorbed into a greedy symbol group.
        assert discover(root, "M2K")[0].contract_month == "202603"
