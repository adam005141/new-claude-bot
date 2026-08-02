"""
Leg B: opening range breakout.

Economic thesis: overnight information accumulates and is repriced in the opening
auction; the first range establishes a reference that triggers stop and momentum flow.

The competing explanation that must be ruled out before believing any of it: volatility
clustering alone produces apparent breakout profits in a trending sample, and the result
is highly sensitive to `or_minutes`, which is a free parameter. Ruling that out is the
job of the null tests, not of this module.

Every condition below is computable from named inputs. There are no judgement terms.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import CostModel, Instrument, RiskParams, StrategyParams
from .execution import Side
from .sizing import expected_move_floor, stop_distance


@dataclass(frozen=True)
class Signal:
    side: Side
    trigger_price: float
    stop_price: float
    target_price: float
    stop_distance_points: float
    target_distance_points: float
    reason: str


@dataclass(frozen=True)
class Rejection:
    """A setup that was eligible but not taken. Counted so opportunity is not overstated."""
    reason: str


@dataclass
class SessionState:
    """
    Per-session trade state. Reset at every session boundary.

    Exists so re-entry can be fenced properly. Without the last-entry prices, a whipsaw
    around the opening-range edge would let the strategy buy the same failed breakout
    repeatedly and book each attempt as an independent trade, which inflates the sample
    with correlated losses and flatters nothing except the trade count.
    """
    entries: int = 0
    last_exit_bar: int | None = None
    last_entry_long: float | None = None
    last_entry_short: float | None = None

    def record_entry(self, side: Side, price: float) -> None:
        self.entries += 1
        if side is Side.LONG:
            self.last_entry_long = price
        else:
            self.last_entry_short = price

    def record_exit(self, bar_index: int) -> None:
        self.last_exit_bar = bar_index


class OpeningRangeBreakout:
    """
    Stateless evaluator. All session state arrives in the feature row, so the same object
    serves backtest and paper without carrying hidden history between them.
    """

    name = "ORB"

    def __init__(self, params: StrategyParams, inst: Instrument,
                 risk: RiskParams, costs: CostModel):
        self.p = params
        self.inst = inst
        self.risk = risk
        self.costs = costs

    def evaluate(self, row, state: SessionState,
                 bar_index: int = 0) -> Signal | Rejection | None:
        """
        Evaluate one COMPLETED bar. Returns a Signal to act on at the next bar, a
        Rejection worth counting, or None when the setup simply is not present.

        The distinction matters: None means "no setup", Rejection means "setup existed but
        was filtered". Collapsing them would make the strategy look more selective than
        it is and would hide how much the filters are actually doing.
        """
        if state.entries >= self.p.max_entries_per_session:
            return None
        if not bool(row.get("or_ready", False)):
            return None
        if bool(row.get("entries_blocked", False)):
            return Rejection("ROLL_OR_EXPIRY")

        or_high, or_low = row.get("or_high"), row.get("or_low")
        or_width, atr_ = row.get("or_width"), row.get("atr")
        width_norm = row.get("or_width_norm")
        if any(v is None or v != v for v in (or_high, or_low, or_width, atr_, width_norm)):
            return None
        if atr_ <= 0 or or_width <= 0:
            return None

        # An already-exhausted range has spent the move the breakout is trying to catch.
        # Compared against the random-walk baseline so the threshold means the same thing
        # at every combination of or_minutes and decision timeframe.
        if width_norm > self.p.or_max_width_norm:
            return Rejection("OR_TOO_WIDE")

        buffer_ = self.p.b_buffer_atr * atr_
        close = row["close"]

        if close > or_high + buffer_ and self.p.allow_long:
            side = Side.LONG
        elif close < or_low - buffer_ and self.p.allow_short:
            side = Side.SHORT
        else:
            return None

        rvol = row.get("rvol")
        if rvol is None or rvol != rvol or rvol < self.p.rvol_breakout:
            return Rejection("RVOL_TOO_LOW")

        # Re-entry guards. Both exist to stop a whipsaw around the range edge being
        # recorded as a series of independent trades.
        if state.entries > 0:
            if state.last_exit_bar is not None:
                if bar_index - state.last_exit_bar < self.p.reentry_cooldown_bars:
                    return Rejection("REENTRY_COOLDOWN")
            prior = state.last_entry_long if side is Side.LONG else state.last_entry_short
            if prior is not None:
                needed = self.p.reentry_new_extreme_atr * atr_
                extended = ((close - prior) if side is Side.LONG else (prior - close))
                if extended < needed:
                    return Rejection("NO_NEW_EXTREME")

        stop_pts = stop_distance(atr_, self.inst, self.p.m_stop_atr, self.p.min_stop_ticks)
        target_pts = self.p.r_target * or_width

        # Cost gate, applied BEFORE sizing. A move that cannot clear its own round trip
        # under the adverse scenario is not a trade regardless of how good it looks.
        floor = expected_move_floor(self.inst, self.costs, self.risk.mu_min)
        if target_pts < floor:
            return Rejection("MOVE_FLOOR")

        entry = close
        stop = entry - side.sign * stop_pts
        target = entry + side.sign * target_pts

        return Signal(
            side=side,
            trigger_price=entry,
            stop_price=self.inst.round_to_tick(stop),
            target_price=self.inst.round_to_tick(target),
            stop_distance_points=stop_pts,
            target_distance_points=target_pts,
            reason=f"ORB_{side.value}",
        )
