"""
Risk state machine.

The prop layer sits strictly ABOVE the signal logic and can only ever remove permission.
It never alters a threshold, an entry, or an exit. That separation is what makes it
possible to report clamped and unclamped performance as genuinely the same strategy.

Everything fails closed. There is no degraded-but-trading state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .config import PropRules, RiskParams

log = logging.getLogger(__name__)


class RiskState(str, Enum):
    ACTIVE = "ACTIVE"
    FLATTEN_ONLY = "FLATTEN_ONLY"      # close existing, open nothing new
    HALTED_DAY = "HALTED_DAY"          # done for the session, resumes next reset
    HALTED_TARGET = "HALTED_TARGET"    # evaluation objective met, stop trading
    HALTED_PERMANENT = "HALTED_PERMANENT"   # loss limit breached, terminal


TERMINAL = {RiskState.HALTED_PERMANENT, RiskState.HALTED_TARGET}


@dataclass
class RiskDecision:
    state: RiskState
    reason: str
    must_flatten: bool = False

    @property
    def can_enter(self) -> bool:
        return self.state == RiskState.ACTIVE


@dataclass
class RiskEngine:
    """
    Tracks account state and gates entries.

    `mll_floor` ratchets on END-OF-DAY balance only, never intraday and never downward,
    and locks permanently once it reaches the starting balance. Breach is evaluated on
    EQUITY including open P&L, the conservative reading of an unresolved rule: if the
    firm in fact evaluates on closed balance this costs a little opportunity, whereas the
    opposite default would risk a real breach.
    """
    rules: PropRules
    risk: RiskParams
    balance: float = 0.0
    mll_floor: float = 0.0
    session_pnl: float = 0.0
    peak_balance: float = 0.0
    state: RiskState = RiskState.ACTIVE
    current_session: date | None = None
    halt_reason: str = ""
    session_log: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.balance == 0.0:
            self.balance = self.rules.starting_balance
        if self.mll_floor == 0.0:
            self.mll_floor = self.rules.initial_floor
        self.peak_balance = self.balance

    # -- session lifecycle -------------------------------------------------

    def start_session(self, sd: date) -> None:
        """Roll into a new session: ratchet the floor, then reset the daily counter."""
        if self.current_session is not None and sd != self.current_session:
            self._end_of_day_ratchet()
        self.current_session = sd
        self.session_pnl = 0.0
        if self.state == RiskState.HALTED_DAY:
            self.state = RiskState.ACTIVE
            self.halt_reason = ""

    def _end_of_day_ratchet(self) -> None:
        """
        Trail the floor up to the end-of-day balance, never down, and lock at the start
        balance. Uses the CLOSING balance, not the intraday peak.
        """
        if not self.rules.enabled:
            return
        self.session_log.append({
            "session_date": self.current_session,
            "close_balance": self.balance,
            "mll_floor": self.mll_floor,
            "session_pnl": self.session_pnl,
        })
        if self.mll_floor >= self.rules.mll_locks_at:
            return
        candidate = self.balance - self.rules.mll_buffer
        new_floor = min(max(self.mll_floor, candidate), self.rules.mll_locks_at)
        if new_floor > self.mll_floor:
            log.debug("MLL ratchet %.2f -> %.2f (balance %.2f)",
                      self.mll_floor, new_floor, self.balance)
            self.mll_floor = new_floor

    # -- accounting --------------------------------------------------------

    def record_trade(self, net_pnl: float) -> None:
        self.balance += net_pnl
        self.session_pnl += net_pnl
        self.peak_balance = max(self.peak_balance, self.balance)

    def equity(self, open_pnl: float = 0.0) -> float:
        return self.balance + open_pnl

    # -- gating ------------------------------------------------------------

    def evaluate(self, open_pnl: float = 0.0, at_or_after_flat_time: bool = False,
                 data_fault: bool = False) -> RiskDecision:
        """
        Called once per bar, BEFORE any entry logic. Order matters: terminal states first,
        then hard limits, then softer session limits.
        """
        if self.state in TERMINAL:
            return RiskDecision(self.state, self.halt_reason, must_flatten=True)

        if data_fault:
            return self._halt(RiskState.HALTED_DAY, "DATA_FAULT", flatten=True)

        if not self.rules.enabled:
            if at_or_after_flat_time:
                return RiskDecision(RiskState.FLATTEN_ONLY, "FLAT_TIME", must_flatten=True)
            return RiskDecision(RiskState.ACTIVE, "")

        eq = self.equity(open_pnl)
        safety = self.rules.mll_buffer * self.rules.mll_reserve_fraction

        if eq <= self.mll_floor + safety:
            return self._halt(RiskState.HALTED_PERMANENT, "MLL_BREACH_WITH_MARGIN",
                              flatten=True)

        if self.balance >= self.rules.target_balance:
            return self._halt(RiskState.HALTED_TARGET, "PROFIT_TARGET_REACHED", flatten=True)

        # Firm daily limit. None on TopstepX, where the default DLL was removed in 2024.
        if self.rules.daily_loss_limit_usd is not None:
            if self.session_pnl <= -self.rules.daily_loss_limit_usd:
                return self._halt(RiskState.HALTED_DAY, "FIRM_DAILY_LOSS_LIMIT", flatten=True)

        # Self-imposed stop. DESIGN, not a firm rule; breaching it is not a violation.
        if self.rules.self_imposed_daily_stop_usd is not None:
            if self.session_pnl <= -self.rules.self_imposed_daily_stop_usd:
                return self._halt(RiskState.HALTED_DAY, "SELF_IMPOSED_DAILY_STOP",
                                  flatten=True)

        # Consistency guard: deliberately forgoes profit to protect evaluation validity.
        if self.rules.consistency_day_cap_usd is not None:
            if self.session_pnl >= self.rules.consistency_day_cap_usd:
                return RiskDecision(RiskState.FLATTEN_ONLY, "CONSISTENCY_DAY_CAP",
                                    must_flatten=True)

        if at_or_after_flat_time:
            return RiskDecision(RiskState.FLATTEN_ONLY, "FLAT_TIME", must_flatten=True)

        return RiskDecision(RiskState.ACTIVE, "")

    def _halt(self, state: RiskState, reason: str, flatten: bool) -> RiskDecision:
        if self.state != state:
            log.info("risk halt: %s (%s) balance=%.2f floor=%.2f session_pnl=%.2f",
                     state.value, reason, self.balance, self.mll_floor, self.session_pnl)
        self.state = state
        self.halt_reason = reason
        return RiskDecision(state, reason, must_flatten=flatten)

    def finish(self) -> None:
        """Flush the final session so the last day appears in the ratchet log."""
        if self.current_session is not None:
            self._end_of_day_ratchet()
            self.current_session = None
