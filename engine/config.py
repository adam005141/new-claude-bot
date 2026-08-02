"""
Typed configuration.

Every value carries a classification from SPECIFICATION.md section 14:
FIXED-MARKET, FIXED-FIRM, DESIGN, or AWAITING-VALIDATION. Signal parameters and firm
rules live in separate objects and are never merged, so that changing a Topstep rule
can never alter a trading signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import time
from pathlib import Path
from typing import Any

import yaml

from .sessions import Session, DEFAULT_ENABLED


@dataclass(frozen=True)
class Instrument:
    """FIXED-MARKET. Verified contract specification."""
    symbol: str
    point_value: float           # USD per index point
    tick_size: float             # index points
    tick_value: float            # USD per tick
    orderable: bool = True
    exchange: str = "CME"

    def ticks_to_dollars(self, ticks: float) -> float:
        return ticks * self.tick_value

    def points_to_dollars(self, points: float) -> float:
        return points * self.point_value

    def round_to_tick(self, price: float) -> float:
        return round(price / self.tick_size) * self.tick_size


MES = Instrument("MES", point_value=5.00, tick_size=0.25, tick_value=1.25)
MNQ = Instrument("MNQ", point_value=2.00, tick_size=0.25, tick_value=0.50)
# Reference only. Orderable=False is enforced structurally by the router.
ES = Instrument("ES", point_value=50.00, tick_size=0.25, tick_value=12.50, orderable=False)
NQ = Instrument("NQ", point_value=20.00, tick_size=0.25, tick_value=5.00, orderable=False)

INSTRUMENTS: dict[str, Instrument] = {i.symbol: i for i in (MES, MNQ, ES, NQ)}


@dataclass(frozen=True)
class CostModel:
    """
    DESIGN + PRIOR ESTIMATE. Not measured.

    These are assumptions, not observations. The account holds TRADES bars only, with no
    bid/ask, so spread is asserted rather than measured. Break-even on MES is roughly
    three ticks, so an error here of one tick is enough to flip a marginal result. Every
    number produced downstream inherits that uncertainty and is labelled accordingly.

    Replace with measured spreads once BID/ASK bars are downloaded.
    """
    name: str
    commission_per_side: float        # USD per contract per side
    spread_ticks_per_side: float      # ticks crossed on entry and again on exit
    slippage_ticks_per_side: float    # additional adverse ticks beyond the spread
    measured: bool = False            # True only when derived from real quote data

    def round_trip_usd(self, inst: Instrument) -> float:
        commission = 2 * self.commission_per_side
        ticks = 2 * (self.spread_ticks_per_side + self.slippage_ticks_per_side)
        return commission + inst.ticks_to_dollars(ticks)

    def round_trip_points(self, inst: Instrument) -> float:
        return self.round_trip_usd(inst) / inst.point_value


COST_BASE = CostModel("base", 0.60, 1.0, 0.0)
COST_ADVERSE = CostModel("adverse", 0.60, 1.0, 0.5)
COST_SEVERE = CostModel("severe", 0.60, 1.5, 1.0)
COST_SCENARIOS: dict[str, CostModel] = {c.name: c for c in (COST_BASE, COST_ADVERSE, COST_SEVERE)}


@dataclass(frozen=True)
class StrategyParams:
    """
    Leg B, opening range breakout. All DESIGN and AWAITING-VALIDATION.

    Ranges mirror SPECIFICATION.md section 14 and are enforced by `validate()`, so a
    sweep cannot silently wander outside the pre-registered search space.
    """
    or_minutes: int = 30                  # range 5-60      HIGH OVERFIT RISK
    b_buffer_atr: float = 0.25            # range 0.0-1.0
    # Multiples of the RANDOM-WALK BASELINE, not of raw ATR. 1.0 means an ordinary
    # range for this timeframe. See features.normalise_or_width for why raw ATR
    # multiples are not scale free.
    or_max_width_norm: float = 1.5        # range 0.5-4.0
    rvol_breakout: float = 1.20           # range 1.0-2.0
    m_stop_atr: float = 1.5               # range 0.75-3.0
    min_stop_ticks: int = 8               # MES 8, MNQ 12
    r_target: float = 1.0                 # multiples of OR width
    max_bars_in_trade: int = 24
    atr_window: int = 14
    rvol_lookback: int = 20
    max_entries_per_session: int = 1      # ORB does not re-enter by default
    allow_long: bool = True
    allow_short: bool = True

    def validate(self) -> None:
        checks = [
            ("or_minutes", self.or_minutes, 5, 60),
            ("b_buffer_atr", self.b_buffer_atr, 0.0, 1.0),
            ("or_max_width_norm", self.or_max_width_norm, 0.5, 4.0),
            ("rvol_breakout", self.rvol_breakout, 1.0, 2.0),
            ("m_stop_atr", self.m_stop_atr, 0.75, 3.0),
            ("min_stop_ticks", self.min_stop_ticks, 1, 40),
            ("r_target", self.r_target, 0.5, 3.0),
            ("max_bars_in_trade", self.max_bars_in_trade, 1, 200),
        ]
        for name, value, lo, hi in checks:
            if not lo <= value <= hi:
                raise ValueError(
                    f"{name}={value} outside pre-registered range [{lo}, {hi}]. "
                    "Widening a range mid-search invalidates the multiple-testing correction."
                )


@dataclass(frozen=True)
class RiskParams:
    """DESIGN. Derived from the usable loss buffer, never the headline balance."""
    r_target_usd: float = 100.0
    max_portfolio_heat_usd: float = 150.0
    corr_threshold: float = 0.75
    corr_lookback_sessions: int = 20
    mu_min: float = 0.25                  # required net-expectancy margin
    max_contracts_per_instrument: int = 4
    flat_time_et: time = time(15, 50)


@dataclass(frozen=True)
class PropRules:
    """
    FIXED-FIRM. Topstep $50,000 Trading Combine, config v1.1.0.

    Platform is TopstepX, where the default daily loss limit was removed in Aug 2024, so
    `daily_loss_limit_usd` is None and the MLL is the only firm loss constraint. On
    Tradovate/NinjaTrader/Quantower/TradingView a firm DLL is reported to still apply;
    setting the field is then the entire change required.
    """
    enabled: bool = True
    starting_balance: float = 50_000.0
    profit_target: float = 3_000.0
    mll_buffer: float = 2_000.0
    mll_locks_at: float = 50_000.0
    daily_loss_limit_usd: float | None = None          # TopstepX: none
    self_imposed_daily_stop_usd: float | None = 300.0  # DESIGN, not a firm rule
    mll_reserve_fraction: float = 0.25
    consistency_day_cap_usd: float | None = 1_400.0

    @property
    def usable_mll(self) -> float:
        return self.mll_buffer * (1.0 - self.mll_reserve_fraction)

    @property
    def target_balance(self) -> float:
        return self.starting_balance + self.profit_target

    @property
    def initial_floor(self) -> float:
        return self.starting_balance - self.mll_buffer


@dataclass(frozen=True)
class ExecutionParams:
    """DESIGN. Every ambiguity resolves against the position. See SPECIFICATION.md 13.2."""
    entry_timeout_bars: int = 2
    latency_ms: int = 250
    # When a bar spans both stop and target, assume the stop filled first. Always.
    same_bar_resolves_to_stop: bool = True
    # A limit fills only if price trades strictly THROUGH it, never merely touching.
    limit_requires_trade_through: bool = True
    # A stop fills at the worse of its price and the next bar's open, modelling gaps.
    stop_fills_at_worse_of_open: bool = True


@dataclass
class EngineConfig:
    """Top-level configuration. One object drives backtest and paper identically."""
    symbols: tuple[str, ...] = ("MES", "MNQ")
    decision_bar_minutes: int = 5
    enabled_sessions: frozenset[Session] = DEFAULT_ENABLED
    strategy: StrategyParams = field(default_factory=StrategyParams)
    risk: RiskParams = field(default_factory=RiskParams)
    prop: PropRules = field(default_factory=PropRules)
    execution: ExecutionParams = field(default_factory=ExecutionParams)
    cost_scenario: str = "adverse"        # adverse is the default, not base
    roll_stop_entries_days: int = 5
    seed: int = 7

    def __post_init__(self) -> None:
        self.strategy.validate()
        if self.cost_scenario not in COST_SCENARIOS:
            raise ValueError(f"unknown cost scenario {self.cost_scenario!r}")
        for s in self.symbols:
            if s not in INSTRUMENTS:
                raise ValueError(f"unknown symbol {s!r}")
            if not INSTRUMENTS[s].orderable:
                raise ValueError(
                    f"{s} is a reference instrument and cannot be traded. "
                    "Reference feeds may inform features but never produce orders."
                )

    @property
    def costs(self) -> CostModel:
        return COST_SCENARIOS[self.cost_scenario]

    def instrument(self, symbol: str) -> Instrument:
        return INSTRUMENTS[symbol]

    def strategy_for(self, symbol: str) -> StrategyParams:
        """
        MES and MNQ get independent parameters. MNQ's larger point moves mean an identical
        tick floor would be a materially tighter stop, so the floor differs by instrument.
        """
        if symbol == "MNQ":
            return StrategyParams(**{**asdict(self.strategy), "min_stop_ticks": 12})
        return self.strategy

    def fingerprint(self) -> dict[str, Any]:
        """Full parameter snapshot recorded with every run for reproducibility."""
        return {
            "symbols": list(self.symbols),
            "decision_bar_minutes": self.decision_bar_minutes,
            "enabled_sessions": sorted(s.value for s in self.enabled_sessions),
            "strategy": asdict(self.strategy),
            "risk": {**asdict(self.risk), "flat_time_et": self.risk.flat_time_et.isoformat()},
            "prop": asdict(self.prop),
            "execution": asdict(self.execution),
            "cost_scenario": self.cost_scenario,
            "costs": asdict(self.costs),
            "seed": self.seed,
        }


def load_yaml(path: str | Path) -> dict[str, Any]:
    with open(path) as fh:
        return yaml.safe_load(fh) or {}
