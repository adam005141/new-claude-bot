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


def measured_cost_models(path: str | Path, symbol: str,
                         commission_per_side: float = 0.60,
                         session: str | None = None) -> dict[str, "CostModel"]:
    """
    Build cost scenarios from MEASURED quoted spreads instead of priors.

    The three scenarios become percentiles of the observed per-minute spread
    distribution rather than round numbers someone chose:

        base     median   typical conditions
        adverse  p75      the worse half of minutes
        severe   p95      stressed conditions

    Slippage stays as an explicit ADDITIONAL allowance on top of the quoted spread,
    because quoted spread is a lower bound: it cannot see queue position, partial
    fills, or the widening that happens as an order arrives. Setting it to zero would
    assert that a market order transacts exactly at the quote, which is false.

    Raises if the file does not describe the requested symbol, rather than silently
    falling back to the assumed model. A run that believes it used measured costs but
    quietly used priors is worse than one that fails.
    """
    import json
    data = json.loads(Path(path).read_text())
    instruments = data.get("instruments", {})
    if symbol not in instruments:
        raise KeyError(
            f"{symbol} not present in {path}. Measured symbols: {sorted(instruments)}. "
            "Run tools/measure_costs.py for this symbol before using measured costs."
        )
    stats = instruments[symbol]["overall"]
    if session:
        # Spread is not constant through the day. A strategy that only fires in the
        # opening hour pays the OPENING spread; charging it the all-day median would
        # understate the cost of precisely the trades it takes. Measured data shows the
        # opening hour running materially wider than midday, so this is not a rounding
        # difference, it is the difference between one tick and two.
        by_session = instruments[symbol].get("by_session", {})
        found = None
        for key in (session, f"Session.{session}"):
            if key in by_session:
                found = by_session[key]
                break
        if found is None:
            raise KeyError(
                f"session {session!r} not measured for {symbol}. "
                f"Available: {sorted(by_session)}. Re-run tools/measure_costs.py "
                "with --by-session, or omit the session to use all-day figures."
            )
        stats = found
    overall = stats
    return {
        "base": CostModel("base(measured)", commission_per_side,
                          overall["median_ticks"], 0.25, measured=True),
        "adverse": CostModel("adverse(measured)", commission_per_side,
                             overall["p75_ticks"], 0.50, measured=True),
        "severe": CostModel("severe(measured)", commission_per_side,
                            overall["p95_ticks"], 1.00, measured=True),
    }


COST_BASE = CostModel("base", 0.60, 1.0, 0.0)
COST_ADVERSE = CostModel("adverse", 0.60, 1.0, 0.5)
COST_SEVERE = CostModel("severe", 0.60, 1.5, 1.0)
COST_SCENARIOS: dict[str, CostModel] = {c.name: c for c in (COST_BASE, COST_ADVERSE, COST_SEVERE)}


@dataclass(frozen=True)
class StrategyParams:
    """
    Signal parameters for both legs. All DESIGN and AWAITING-VALIDATION.

    Ranges mirror SPECIFICATION.md section 14 and are enforced by `validate()`, so a
    sweep cannot silently wander outside the pre-registered search space.

    Leg A and Leg B share one object deliberately. The stop rule, the time stop, the
    re-entry fences, and the regime thresholds are properties of the system rather than of
    a leg, and duplicating them would let the two legs drift apart silently.
    """
    # --- Leg A: VWAP band reversion (SPECIFICATION.md section 8) ---------------
    k_entry: float = 2.0                  # range 1.0-3.0   sigma from VWAP to arm
    rvol_min: float = 0.80                # range 0.5-1.5
    min_vwap_bars: int = 12               # range 1-100     VWAP sigma is noise before this
    # --- Regime classification (SPECIFICATION.md section 7) -------------------
    theta_trend: float = 0.35             # range 0.1-1.0
    theta_range: float = 0.15             # range 0.0-0.5   must stay below theta_trend
    theta_rvol: float = 1.10              # range 0.8-2.0
    rv_lo: float = 0.20                   # range 0.0-0.5
    rv_hi: float = 0.80                   # range 0.5-1.0
    # --- Leg C: gap fade toward the prior cash close --------------------------
    # Measured in units of the OVERNIGHT RANGE, not of the 5-minute ATR.
    #
    # The first draft used ATR and was a units error of the same kind as the old
    # or_width/ATR filter. A gap is an overnight move; a 5-minute ATR is a 5-minute move.
    # Their ratio grows with the square root of the number of bars in a night, so a fixed
    # ATR threshold encodes the decision timeframe rather than the market. On the measured
    # median ES ATR of 2.31 points an ordinary 10-point gap scores 4.3, which the intended
    # 3.0 cap would have rejected as "news" for no reason connected to news.
    #
    # The overnight range is the natural denominator: it is a daily-scale quantity, it is
    # complete before the open, and the comparison it expresses is meaningful on its own
    # terms. Did the gap consume a fraction of the night's range, or all of it?
    #
    # Below gap_min the move cannot pay its own round trip. Above gap_max the gap is
    # larger than the entire night that produced it, which is a repricing event, and this
    # leg explicitly does not claim to trade those.
    gap_min_range: float = 0.25           # range 0.05-1.0
    gap_max_range: float = 1.00           # range 0.5-3.0
    # Minutes, not bars, so the window means the same thing at any decision timeframe.
    gap_window_minutes: int = 15          # range 5-60   how long after the open it may fire
    # --- Leg B: opening range breakout ----------------------------------------
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
    # Re-entry. A once-daily ORB caps the sample at one trade per session, which on an
    # 11-month dataset is too few to detect any plausible edge. Re-entry raises the
    # ceiling, but naively it just re-buys the same failed level, so it is fenced by a
    # cooldown and a new-extreme requirement rather than by the cap alone.
    max_entries_per_session: int = 3       # range 1-6
    reentry_cooldown_bars: int = 3         # bars after an exit before re-arming
    reentry_new_extreme_atr: float = 0.5   # how far beyond the prior entry to re-enter
    allow_long: bool = True
    allow_short: bool = True

    def validate(self) -> None:
        checks = [
            ("k_entry", self.k_entry, 1.0, 3.0),
            ("rvol_min", self.rvol_min, 0.5, 1.5),
            ("min_vwap_bars", self.min_vwap_bars, 1, 100),
            ("theta_trend", self.theta_trend, 0.1, 1.0),
            ("theta_range", self.theta_range, 0.0, 0.5),
            ("theta_rvol", self.theta_rvol, 0.8, 2.0),
            ("rv_lo", self.rv_lo, 0.0, 0.5),
            ("rv_hi", self.rv_hi, 0.5, 1.0),
            ("gap_min_range", self.gap_min_range, 0.05, 1.0),
            ("gap_max_range", self.gap_max_range, 0.5, 3.0),
            ("gap_window_minutes", self.gap_window_minutes, 5, 60),
            ("or_minutes", self.or_minutes, 5, 60),
            ("b_buffer_atr", self.b_buffer_atr, 0.0, 1.0),
            ("or_max_width_norm", self.or_max_width_norm, 0.5, 4.0),
            ("rvol_breakout", self.rvol_breakout, 1.0, 2.0),
            ("m_stop_atr", self.m_stop_atr, 0.75, 3.0),
            ("min_stop_ticks", self.min_stop_ticks, 1, 40),
            ("r_target", self.r_target, 0.5, 3.0),
            ("max_bars_in_trade", self.max_bars_in_trade, 1, 200),
            ("max_entries_per_session", self.max_entries_per_session, 1, 6),
            ("reentry_cooldown_bars", self.reentry_cooldown_bars, 0, 20),
            ("reentry_new_extreme_atr", self.reentry_new_extreme_atr, 0.0, 3.0),
        ]
        for name, value, lo, hi in checks:
            if not lo <= value <= hi:
                raise ValueError(
                    f"{name}={value} outside pre-registered range [{lo}, {hi}]. "
                    "Widening a range mid-search invalidates the multiple-testing correction."
                )
        if self.theta_range >= self.theta_trend:
            raise ValueError(
                f"theta_range={self.theta_range} must stay strictly below "
                f"theta_trend={self.theta_trend}. Closing the gap removes the NEUTRAL "
                "no-trade band and forces every bar into a regime, which is exactly the "
                "behaviour section 7 was written to prevent."
            )
        if self.rv_lo >= self.rv_hi:
            raise ValueError(f"rv_lo={self.rv_lo} must be below rv_hi={self.rv_hi}")
        if self.gap_min_range >= self.gap_max_range:
            raise ValueError(
                f"gap_min_range={self.gap_min_range} must be below "
                f"gap_max_range={self.gap_max_range}. Leg C trades the band between them; "
                "inverting the bounds would make it trade nothing while appearing valid."
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
    # Flat before the CME daily halt at 17:00 ET (14:00 Pacific), NOT at the cash close.
    # 16:50 leaves ten minutes to exit into a book that is still liquid rather than
    # market-ordering into the last print before a halt.
    flat_time_et: time = time(16, 50)


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
    # Which entry leg is live. One leg per run: SPECIFICATION.md section 7 requires each
    # regime route to report its own sample size and uncertainty, and a blended run cannot
    # do that. A losing leg is never allowed to hide inside a combined statistic.
    leg: str = "B"
    decision_bar_minutes: int = 5
    enabled_sessions: frozenset[Session] = DEFAULT_ENABLED
    strategy: StrategyParams = field(default_factory=StrategyParams)
    risk: RiskParams = field(default_factory=RiskParams)
    prop: PropRules = field(default_factory=PropRules)
    execution: ExecutionParams = field(default_factory=ExecutionParams)
    cost_scenario: str = "adverse"        # adverse is the default, not base
    # Load PRICE DATA from a different symbol while keeping this instrument's economics.
    # Set only after the substitution has been validated: tools/compare_es_mes.py measures
    # whether the proxy's entry triggers actually match the traded instrument's.
    #
    # This is NOT a way around the orderable guard. Orders, sizing, costs, and P&L stay on
    # the traded micro; only the price history comes from elsewhere.
    price_source: str | None = None
    measured_costs_path: str | None = None   # when set, spreads come from real quotes
    measured_costs_session: str | None = None  # charge one session's spread, not all-day
    roll_stop_entries_days: int = 5
    seed: int = 7

    def __post_init__(self) -> None:
        self.strategy.validate()
        if self.leg not in ("A", "B", "C"):
            raise ValueError(f"unknown leg {self.leg!r}; expected 'A', 'B' or 'C'.")
        if self.cost_scenario not in COST_SCENARIOS:
            raise ValueError(f"unknown cost scenario {self.cost_scenario!r}")
        for s in self.symbols:
            if s not in INSTRUMENTS:
                raise ValueError(f"unknown symbol {s!r}")
            if not INSTRUMENTS[s].orderable:
                raise ValueError(
                    f"{s} is a reference instrument and cannot be traded. "
                    "Reference feeds may inform features but never produce orders. "
                    "To research on its price history while trading a micro, set "
                    "price_source instead: symbols=('MES',), price_source='ES'."
                )
        if self.price_source is not None and self.price_source not in INSTRUMENTS:
            raise ValueError(f"unknown price_source {self.price_source!r}")

    @property
    def costs(self) -> CostModel:
        """Assumed costs. Per-symbol measured costs come from `costs_for`."""
        return COST_SCENARIOS[self.cost_scenario]

    def costs_for(self, symbol: str) -> CostModel:
        """
        Costs for one instrument, measured when a quote file is configured.

        Measured spreads are per instrument: MES and MNQ do not quote the same width,
        and applying one blended figure to both would flatter whichever is wider.
        """
        if self.measured_costs_path is None:
            return self.costs
        return measured_cost_models(
            self.measured_costs_path, symbol,
            session=self.measured_costs_session)[self.cost_scenario]

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
            "leg": self.leg,
            "decision_bar_minutes": self.decision_bar_minutes,
            "enabled_sessions": sorted(s.value for s in self.enabled_sessions),
            "strategy": asdict(self.strategy),
            "risk": {**asdict(self.risk), "flat_time_et": self.risk.flat_time_et.isoformat()},
            "prop": asdict(self.prop),
            "execution": asdict(self.execution),
            "cost_scenario": self.cost_scenario,
            "price_source": self.price_source,
            "costs": asdict(self.costs),
            "seed": self.seed,
        }


def load_yaml(path: str | Path) -> dict[str, Any]:
    """
    Load a YAML config file.

    PyYAML is imported here rather than at module scope so that a missing optional
    dependency cannot break the entire engine at import time, which is exactly what
    happened when this module hard-imported it.
    """
    import yaml
    with open(path) as fh:
        return yaml.safe_load(fh) or {}
