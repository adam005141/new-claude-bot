"""
Deterministic event loop. Shared by backtest and paper modes.

The processing order in `_step` is authoritative and is the reason results can be trusted:

    exits BEFORE entries        so a position always closes before a new one can open
    risk evaluation BEFORE entries   so a halt can never be overridden by a signal
    features from COMPLETED bars only, acted on at the NEXT bar

A signal computed on bar t is executed at bar t+1. Nothing in this loop can read a bar it
has not already processed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import date

import pandas as pd

from .config import EngineConfig
from .execution import (
    Bar, ExitReason, Position, Side, exit_at_market, fill_market, realise_pnl, resolve_exit,
)
from .risk import RiskEngine, RiskState
from .sessions import ET, classify_index, is_tradable, SessionCalendar
from .sizing import size_position
from .strategy import (
    OpeningRangeBreakout, Rejection, SessionState, Signal, VWAPBandReversion,
)

LEGS = {"A": VWAPBandReversion, "B": OpeningRangeBreakout}

log = logging.getLogger(__name__)


@dataclass
class Trade:
    symbol: str
    contract_month: str
    side: str
    quantity: int
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    session_date: date
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    exit_reason: str
    bars_held: int
    gross_usd: float
    commission_usd: float
    net_usd: float
    risk_usd: float
    target_risk_usd: float
    risk_deviation: float
    stop_distance_points: float
    r_multiple: float
    session_name: str


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    rejections: dict[str, int] = field(default_factory=dict)
    equity_curve: pd.DataFrame = field(default_factory=pd.DataFrame)
    session_log: list[dict] = field(default_factory=list)
    config_fingerprint: dict = field(default_factory=dict)
    provenance: list[dict] = field(default_factory=list)
    bars_processed: int = 0
    sessions_processed: int = 0
    terminated_early: bool = False
    final_state: str = RiskState.ACTIVE.value

    def trades_frame(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame(columns=[f.name for f in Trade.__dataclass_fields__.values()])
        return pd.DataFrame([asdict(t) for t in self.trades])


class Backtester:
    """
    Single-instrument backtest over a prepared feature frame.

    Portfolio coordination across MES and MNQ is applied at a higher level; this class
    deliberately knows about one instrument so that per-instrument results can never be
    contaminated by the other.
    """

    def __init__(self, config: EngineConfig, symbol: str,
                 calendar: SessionCalendar | None = None):
        self.cfg = config
        self.symbol = symbol
        self.inst = config.instrument(symbol)
        self.params = config.strategy_for(symbol)
        self.costs = config.costs_for(symbol)
        self.calendar = calendar or SessionCalendar()
        self.strategy = LEGS[config.leg](self.params, self.inst, config.risk, self.costs)
        self.risk = RiskEngine(rules=config.prop, risk=config.risk)

    # ------------------------------------------------------------------

    def run(self, features: pd.DataFrame) -> BacktestResult:
        result = BacktestResult(config_fingerprint=self.cfg.fingerprint())
        if features.empty:
            return result

        df = features.reset_index(drop=True)
        sessions = classify_index(pd.DatetimeIndex(df["timestamp_utc"]))
        et_times = pd.DatetimeIndex(df["timestamp_utc"]).tz_convert(ET)
        flat_time = self.cfg.risk.flat_time_et

        position: Position | None = None
        pending: Signal | None = None
        state = SessionState()
        current_session: date | None = None
        equity_rows: list[dict] = []

        rows = df.to_dict("records")

        for i, row in enumerate(rows):
            sd = row["session_date"]
            if sd != current_session:
                # Flush any position before the session boundary; never carry overnight.
                if position is not None:
                    position, trade = self._close(position, row["open"], i,
                                                  row["timestamp_utc"], ExitReason.SESSION,
                                                  sessions.iloc[i - 1] if i else "")
                    result.trades.append(trade)
                self.risk.start_session(sd)
                current_session = sd
                state = SessionState()          # re-entry state never crosses sessions
                pending = None

            bar = Bar(row["open"], row["high"], row["low"], row["close"])
            next_open = rows[i + 1]["open"] if i + 1 < len(rows) else None
            at_flat = et_times[i].time() >= flat_time

            # ---- 1. exits, before anything else -------------------------
            if position is not None:
                position.bars_held += 1
                outcome = resolve_exit(bar, position, next_open,
                                       self.cfg.execution, self.inst, self.costs)
                if outcome is not None:
                    reason, price = outcome
                    position, trade = self._close(position, price, i,
                                                  row["timestamp_utc"], reason,
                                                  str(sessions.iloc[i]), raw_price=True)
                    result.trades.append(trade)
                    state.record_exit(i)
                elif position.bars_held >= self.params.max_bars_in_trade:
                    position, trade = self._close(position, row["close"], i,
                                                  row["timestamp_utc"], ExitReason.TIME,
                                                  str(sessions.iloc[i]))
                    result.trades.append(trade)
                    state.record_exit(i)

            # ---- 2. risk gate, before entries ---------------------------
            open_pnl = position.open_pnl_usd(row["close"], self.inst) if position else 0.0
            decision = self.risk.evaluate(open_pnl=open_pnl, at_or_after_flat_time=at_flat)

            if decision.must_flatten and position is not None:
                reason = (ExitReason.RISK_HALT if decision.state != RiskState.FLATTEN_ONLY
                          else ExitReason.SESSION)
                position, trade = self._close(position, row["close"], i,
                                              row["timestamp_utc"], reason,
                                              str(sessions.iloc[i]))
                result.trades.append(trade)
                state.record_exit(i)

            equity_rows.append({
                "timestamp_utc": row["timestamp_utc"],
                "session_date": sd,
                "balance": self.risk.balance,
                "equity": self.risk.equity(open_pnl),
                "mll_floor": self.risk.mll_floor,
                "state": decision.state.value,
            })

            if self.risk.state in (RiskState.HALTED_PERMANENT, RiskState.HALTED_TARGET):
                # A breached or completed account cannot keep trading, so the replay
                # stops here. Everything after this point is UNOBSERVED, which makes the
                # trade list a path-truncated sample rather than a sample of the split.
                result.bars_processed = i + 1
                result.terminated_early = i + 1 < len(rows)
                break

            # ---- 3. execute a signal raised on the PREVIOUS bar ---------
            if pending is not None and position is None and decision.can_enter:
                position = self._open(pending, bar, i, row, result)
                if position is not None:
                    state.record_entry(position.side, position.entry_price)
                pending = None
            elif pending is not None:
                pending = None            # stale by one bar; never carried further

            # ---- 4. raise a new signal from this COMPLETED bar ----------
            if position is None and decision.can_enter and pending is None:
                if is_tradable(row["timestamp_utc"], self.calendar,
                               self.cfg.enabled_sessions):
                    out = self.strategy.evaluate(row, state, bar_index=i)
                    if isinstance(out, Signal):
                        pending = out
                    elif isinstance(out, Rejection):
                        result.rejections[out.reason] = result.rejections.get(out.reason, 0) + 1

            result.bars_processed = i + 1

        # Close anything still open at the end of the data.
        if position is not None:
            last = rows[result.bars_processed - 1]
            position, trade = self._close(position, last["close"], len(rows) - 1,
                                          last["timestamp_utc"], ExitReason.END_OF_DATA, "")
            result.trades.append(trade)

        self.risk.finish()
        result.sessions_processed = int(
            df["session_date"].iloc[:max(result.bars_processed, 1)].nunique())
        result.session_log = self.risk.session_log
        result.equity_curve = pd.DataFrame(equity_rows)
        result.final_state = self.risk.state.value
        return result

    # ------------------------------------------------------------------

    def _open(self, sig: Signal, bar: Bar, i: int, row: dict,
              result: BacktestResult) -> Position | None:
        """Enter at the next bar's open, paying the spread. Sizing may still refuse."""
        sizing = size_position(sig.stop_distance_points, self.inst, self.cfg.risk)
        if not sizing.ok:
            reason = sizing.rejected_reason or "SIZE_ZERO"
            result.rejections[reason] = result.rejections.get(reason, 0) + 1
            return None

        entry = fill_market(bar, sig.side, self.inst, self.costs)
        stop = entry - sig.side.sign * sig.stop_distance_points
        target = entry + sig.side.sign * sig.target_distance_points

        return Position(
            symbol=self.symbol,
            side=sig.side,
            quantity=sizing.quantity,
            entry_price=entry,
            stop_price=self.inst.round_to_tick(stop),
            target_price=self.inst.round_to_tick(target),
            entry_index=i,
            entry_time=row["timestamp_utc"],
            entry_session=row["session_date"],
            contract_month=row["contract_month"],
            stop_distance_points=sig.stop_distance_points,
            target_distance_points=sig.target_distance_points,
            risk_usd=sizing.total_risk_usd,
        )

    def _close(self, pos: Position, price: float, i: int, ts, reason: ExitReason,
               session_name: str, raw_price: bool = False) -> tuple[None, Trade]:
        """
        Close a position and book the P&L.

        `raw_price` marks fills whose cost is already embedded by the execution model
        (stop and target). Anything else is a discretionary market exit and pays spread
        here, so costs are charged exactly once.
        """
        exit_price = price if raw_price else exit_at_market(price, pos, self.inst, self.costs)
        gross, commission, net = realise_pnl(pos, exit_price, self.inst, self.costs)
        self.risk.record_trade(net)

        risk_usd = pos.risk_usd if pos.risk_usd > 0 else 1e-9
        target_risk = self.cfg.risk.r_target_usd

        trade = Trade(
            symbol=pos.symbol, contract_month=pos.contract_month, side=pos.side.value,
            quantity=pos.quantity, entry_time=pos.entry_time, exit_time=ts,
            session_date=pos.entry_session, entry_price=pos.entry_price,
            exit_price=exit_price, stop_price=pos.stop_price, target_price=pos.target_price,
            exit_reason=reason.value, bars_held=pos.bars_held,
            gross_usd=gross, commission_usd=commission, net_usd=net,
            risk_usd=pos.risk_usd, target_risk_usd=target_risk,
            risk_deviation=(pos.risk_usd - target_risk) / target_risk if target_risk else 0.0,
            stop_distance_points=pos.stop_distance_points,
            r_multiple=net / risk_usd,
            session_name=session_name,
        )
        return None, trade
