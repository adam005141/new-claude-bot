"""
Position sizing and the expected-move floor.

Two hard rules:

1. Quantity ALWAYS rounds down. Rounding up breaches the risk target by construction,
   and at 1-4 contracts the breach is a large fraction of the budget.
2. A setup whose expected move cannot clear its own round-trip cost under the ADVERSE
   scenario is rejected at signal time, before sizing. For micros this is the binding
   viability test, not a diagnostic: a micro pays a parent-sized spread while capturing
   one tenth the dollar move.

Rounding down means realised risk can sit well under target. That deviation is recorded
on every trade rather than smoothed away, because at these contract counts it is a real
property of the system and not a rounding detail.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import CostModel, Instrument, RiskParams


@dataclass(frozen=True)
class SizingResult:
    quantity: int
    risk_per_contract_usd: float
    total_risk_usd: float
    target_risk_usd: float
    rejected_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.quantity >= 1 and self.rejected_reason is None

    @property
    def risk_deviation(self) -> float:
        """Signed fraction by which realised risk misses target. -0.25 means 25% under."""
        if self.target_risk_usd <= 0:
            return 0.0
        return (self.total_risk_usd - self.target_risk_usd) / self.target_risk_usd


def stop_distance(atr_value: float, inst: Instrument, m_stop_atr: float,
                  min_stop_ticks: int) -> float:
    """
    Stop distance in index points.

    The tick floor stops a quiet regime producing a stop so tight that spread and noise
    dominate the outcome.
    """
    return max(m_stop_atr * atr_value, min_stop_ticks * inst.tick_size)


def expected_move_floor(inst: Instrument, costs: CostModel, mu_min: float,
                        p_target: float = 0.5) -> float:
    """
    Minimum expected favourable move, in index points, for a setup to be worth taking.

    Derived from cost and the required net-expectancy margin:

        move * point_value * P(target) >= round_trip_cost / (1 - mu_min)

    `p_target` is a prior, not a measurement. Until win rate is estimated on development
    data it stays at 0.5, and every floor computed from it inherits that assumption.
    """
    if not 0.0 < p_target <= 1.0:
        raise ValueError("p_target must be in (0, 1]")
    required_usd = costs.round_trip_usd(inst) / (1.0 - mu_min)
    return required_usd / (inst.point_value * p_target)


def passes_move_floor(expected_move_points: float, inst: Instrument,
                      costs: CostModel, mu_min: float, p_target: float = 0.5) -> bool:
    return expected_move_points >= expected_move_floor(inst, costs, mu_min, p_target)


def size_position(stop_points: float, inst: Instrument, risk: RiskParams,
                  open_heat_usd: float = 0.0) -> SizingResult:
    """
    Risk-based integer sizing, rounded down, capped by portfolio heat and contract limit.

    Returns quantity 0 with a reason rather than raising, so the caller can log a rejected
    opportunity. Silently dropping these would understate the opportunity count and make
    the strategy look more selective than it is.
    """
    target = risk.r_target_usd
    if stop_points <= 0:
        return SizingResult(0, 0.0, 0.0, target, "NON_POSITIVE_STOP")

    per_contract = stop_points * inst.point_value

    if risk.fixed_contracts is not None:
        # Scheduled exposure, sized by what the account can survive rather than by a stop
        # distance. Bypassing the R sizer here is deliberate and narrow: Leg D's stop is a
        # disaster brake four standard deviations out, so per-contract risk far exceeds the
        # R target and the sizer would correctly refuse a trade that is not actually
        # risking that much in any normal night. The realised risk is still recorded on
        # every trade, so the deviation from target stays visible rather than hidden.
        q = max(0, int(risk.fixed_contracts))
        if q < 1:
            return SizingResult(0, per_contract, 0.0, target, "FIXED_SIZE_ZERO")
        return SizingResult(q, per_contract, q * per_contract, target)
    if per_contract <= 0:
        return SizingResult(0, per_contract, 0.0, target, "NON_POSITIVE_RISK")

    qty = math.floor(target / per_contract)

    if qty < 1:
        # One contract already exceeds the per-trade budget. Correct outcome is no trade.
        return SizingResult(0, per_contract, 0.0, target, "SIZE_ZERO_STOP_TOO_WIDE")

    qty = min(qty, risk.max_contracts_per_instrument)

    remaining_heat = risk.max_portfolio_heat_usd - open_heat_usd
    if remaining_heat <= 0:
        return SizingResult(0, per_contract, 0.0, target, "PORTFOLIO_HEAT_EXHAUSTED")

    qty = min(qty, math.floor(remaining_heat / per_contract))
    if qty < 1:
        return SizingResult(0, per_contract, 0.0, target, "PORTFOLIO_HEAT")

    return SizingResult(qty, per_contract, qty * per_contract, target)
