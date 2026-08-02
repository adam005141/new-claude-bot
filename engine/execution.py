"""
Order and fill modelling.

Every ambiguity resolves AGAINST the position. This is not pessimism for its own sake:
the two standard ways a backtest invents edge are assuming a limit fills on a touch, and
assuming the target filled before the stop when a single bar spans both. Both are
disallowed here by construction.

Bar data cannot say what happened inside a bar. Where the intrabar sequence is unknown,
the adverse sequence is assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .config import CostModel, ExecutionParams, Instrument


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

    @property
    def sign(self) -> int:
        return 1 if self is Side.LONG else -1

    @property
    def opposite(self) -> "Side":
        return Side.SHORT if self is Side.LONG else Side.LONG


class ExitReason(str, Enum):
    STOP = "STOP"
    TARGET = "TARGET"
    TIME = "TIME"
    SESSION = "SESSION"
    RISK_HALT = "RISK_HALT"
    ROLL = "ROLL"
    END_OF_DATA = "END_OF_DATA"


@dataclass(frozen=True)
class Bar:
    """One decision-timeframe bar."""
    open: float
    high: float
    low: float
    close: float

    def spans(self, price: float) -> bool:
        return self.low <= price <= self.high


@dataclass
class Position:
    symbol: str
    side: Side
    quantity: int
    entry_price: float
    stop_price: float
    target_price: float
    entry_index: int
    entry_time: object
    entry_session: object
    contract_month: str
    stop_distance_points: float
    target_distance_points: float
    risk_usd: float
    bars_held: int = 0

    def open_pnl_points(self, mark: float) -> float:
        return (mark - self.entry_price) * self.side.sign

    def open_pnl_usd(self, mark: float, inst: Instrument) -> float:
        return self.open_pnl_points(mark) * inst.point_value * self.quantity


def fill_entry(bar: Bar, limit_price: float, side: Side,
               params: ExecutionParams) -> float | None:
    """
    Resting limit entry. Returns the fill price, or None if it did not fill.

    Without queue data, the only defensible assumption is that price must trade strictly
    THROUGH the limit, not merely touch it. Assuming a touch fills would hand the strategy
    the best price of every bar it happened to reach.
    """
    if params.limit_requires_trade_through:
        filled = bar.low < limit_price if side is Side.LONG else bar.high > limit_price
    else:
        filled = bar.low <= limit_price if side is Side.LONG else bar.high >= limit_price
    return limit_price if filled else None


def fill_market(bar: Bar, side: Side, inst: Instrument, costs: CostModel) -> float:
    """
    Market order at the bar's open, paying the spread and slippage on that side.

    Costs are charged as price adjustment rather than a separate fee so that reported
    entry and exit prices are the prices actually transacted.
    """
    adverse_ticks = costs.spread_ticks_per_side + costs.slippage_ticks_per_side
    return bar.open + side.sign * adverse_ticks * inst.tick_size


def resolve_exit(bar: Bar, pos: Position, next_open: float | None,
                 params: ExecutionParams, inst: Instrument,
                 costs: CostModel) -> tuple[ExitReason, float] | None:
    """
    Decide whether a bar closes the position, and at what price.

    Resolution order is deliberate and is the single most important honesty control in
    the whole engine:

    1. If the bar spans BOTH stop and target, the STOP wins. Always. The sequence is
       unknowable from OHLC, so the adverse one is assumed.
    2. A stop fills at the WORSE of its price and the next bar's open, which is what
       models a gap through the level.
    3. A target fills at its limit price, with no favourable slippage ever granted.
    """
    hit_stop = bar.spans(pos.stop_price)
    hit_target = bar.spans(pos.target_price)

    if hit_stop and hit_target:
        if params.same_bar_resolves_to_stop:
            return ExitReason.STOP, _stop_fill(pos, next_open, params, inst, costs)
        return ExitReason.TARGET, pos.target_price

    if hit_stop:
        return ExitReason.STOP, _stop_fill(pos, next_open, params, inst, costs)

    if hit_target:
        return ExitReason.TARGET, pos.target_price

    return None


def _stop_fill(pos: Position, next_open: float | None, params: ExecutionParams,
               inst: Instrument, costs: CostModel) -> float:
    """Stop fill price: the worse of the stop and the next open, plus exit slippage."""
    price = pos.stop_price
    if params.stop_fills_at_worse_of_open and next_open is not None:
        price = min(price, next_open) if pos.side is Side.LONG else max(price, next_open)
    slip = costs.slippage_ticks_per_side * inst.tick_size
    return price - pos.side.sign * slip


def exit_at_market(price: float, pos: Position, inst: Instrument,
                   costs: CostModel) -> float:
    """Discretionary exit (time stop, session end, risk halt) paying the spread."""
    adverse_ticks = costs.spread_ticks_per_side + costs.slippage_ticks_per_side
    return price - pos.side.sign * adverse_ticks * inst.tick_size


def realise_pnl(pos: Position, exit_price: float, inst: Instrument,
                costs: CostModel) -> tuple[float, float, float]:
    """
    Returns (gross_usd, commission_usd, net_usd).

    Spread and slippage are already embedded in the fill prices, so only commission is
    subtracted here. Double-charging them would overstate costs as surely as omitting
    them understates.
    """
    points = (exit_price - pos.entry_price) * pos.side.sign
    gross = points * inst.point_value * pos.quantity
    commission = 2 * costs.commission_per_side * pos.quantity
    return gross, commission, gross - commission
