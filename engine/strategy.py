"""
Legs A and B.

Leg A: VWAP band reversion. Economic thesis: intraday order flow around a volume-weighted
reference is mean reverting inside a range, because liquidity provision is compensated for
absorbing temporary imbalance. The competing explanation that must be ruled out: a
2-sigma excursion in a market that is actually trending is the START of a move, not an
overshoot, which is why the leg is fenced to the RANGE regime and why the regime
classifier is the load-bearing component rather than the entry rule.

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
from .regime import Regime
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


class GapFade:
    """
    Leg C. Fade the opening gap back toward the prior cash close.

    Economic thesis: an overnight gap is priced on Globex liquidity, which is a fraction
    of RTH. When US participants arrive at 09:30 the level gets tested, and a gap created
    by thin-book repositioning rather than by information tends to be given back. The
    prior cash close is the reference the whole market shares, which is what makes it a
    place where resting orders actually sit.

    The competing explanation, which the band exists to separate: a gap IS information,
    priced correctly overnight, in which case fading it is betting against news. That is
    why `gap_max_range` caps the leg. A gap wider than the entire night that produced it
    is a repricing event, and this leg explicitly does not claim to trade it.

    Structurally distinct from both dead legs, which matters because otherwise this is a
    third draw from the same urn:

      Leg B  continuation from a range formed INSIDE the session         FAILED
      Leg A  reversion to a statistical mean recomputed every bar        FAILED
      Leg C  reversion to a FIXED level set before the session opened,
             fired once, at a known time, on information neither of the
             others could see

    It also fires at a fixed clock time rather than waiting for a setup, so the trade
    count is roughly one per session and is known in advance rather than discovered.
    """

    name = "GAP_FADE"

    def __init__(self, params: StrategyParams, inst: Instrument,
                 risk: RiskParams, costs: CostModel):
        self.p = params
        self.inst = inst
        self.risk = risk
        self.costs = costs

    def evaluate(self, row, state: SessionState,
                 bar_index: int = 0) -> Signal | Rejection | None:
        # One gap per session. Unlike the other legs this is not a re-entry policy
        # choice: there is only one opening gap, so a second attempt would be a
        # different trade wearing this leg's name.
        if state.entries >= 1:
            return None

        mso = row.get("minutes_since_open")
        atr_ = row.get("atr")
        gap_ratio = row.get("gap_vs_on_range")
        prior_close = row.get("prior_rth_close")
        if any(v is None or v != v for v in (mso, atr_, gap_ratio, prior_close)):
            return None
        if atr_ <= 0:
            return None
        if not bool(row.get("on_ready", False)):
            return None

        # Only in the first few bars of the cash session. The thesis is about the open
        # being tested, not about a level that has been available for hours.
        if mso < 0 or mso >= self.p.gap_window_minutes:
            return None

        close = row["close"]
        # DIRECTION FIRST, then filters, so the rejection counters stay comparable with
        # the other two legs.
        if gap_ratio > 0 and close > prior_close and self.p.allow_short:
            side = Side.SHORT           # gapped up, fade down toward the close
        elif gap_ratio < 0 and close < prior_close and self.p.allow_long:
            side = Side.LONG            # gapped down, fade up toward the close
        else:
            # Either no gap, or price has already travelled back through the prior close,
            # in which case the move this leg exists to capture has happened without it.
            return None

        if bool(row.get("entries_blocked", False)):
            return Rejection("ROLL_OR_EXPIRY")

        size = abs(gap_ratio)
        if size < self.p.gap_min_range:
            return Rejection("GAP_TOO_SMALL")
        if size > self.p.gap_max_range:
            return Rejection("GAP_TOO_LARGE")

        # Target is the gap fill: the prior cash close, unmoved and known before the open.
        target_pts = abs(close - prior_close)
        stop_pts = stop_distance(atr_, self.inst, self.p.m_stop_atr, self.p.min_stop_ticks)

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
            reason=f"GAPFADE_{side.value}",
        )


class VWAPBandReversion:
    """
    Leg A. Stateless evaluator, same contract as Leg B.

    The two-bar structure is the whole design. A touch rule enters into continuing
    momentum; requiring the excursion at t-1 and the reclaim at t makes the market
    demonstrate rejection before any risk is committed. That costs entry price, and is
    expected to lower the win rate while improving payoff. Which effect dominates is
    AWAITING-VALIDATION and is what the run is for.
    """

    name = "VWAP_REVERSION"

    def __init__(self, params: StrategyParams, inst: Instrument,
                 risk: RiskParams, costs: CostModel):
        self.p = params
        self.inst = inst
        self.risk = risk
        self.costs = costs

    def evaluate(self, row, state: SessionState,
                 bar_index: int = 0) -> Signal | Rejection | None:
        if state.entries >= self.p.max_entries_per_session:
            return None

        dev, prev_dev = row.get("vwap_dev"), row.get("prev_vwap_dev")
        vwap, sigma, atr_ = row.get("vwap"), row.get("vwap_sigma"), row.get("atr")
        if any(v is None or v != v for v in (dev, prev_dev, vwap, sigma, atr_)):
            return None
        if sigma <= 0 or atr_ <= 0:
            return None

        # VWAP sigma computed off a handful of bars describes those bars, not the session.
        # Arming before it has settled would fire on an artefact of the anchor.
        if row.get("bar_of_session", 0) < self.p.min_vwap_bars:
            return None

        # DIRECTION FIRST, then filters, for the same reason as Leg B: rejection counters
        # are only comparable when every one of them is answering "of the setups that
        # actually triggered, why was each refused?"
        k = self.p.k_entry
        if prev_dev < -k and dev >= -k and self.p.allow_long:
            side = Side.LONG
        elif prev_dev > k and dev <= k and self.p.allow_short:
            side = Side.SHORT
        else:
            return None

        # The regime gate is what stops this fading a real trend. It is checked as a
        # rejection rather than silently, so the run reports how much of the raw setup
        # population the classifier removed.
        if row.get("regime", Regime.NEUTRAL) != Regime.RANGE:
            return Rejection("NOT_RANGE_REGIME")

        if bool(row.get("entries_blocked", False)):
            return Rejection("ROLL_OR_EXPIRY")

        rvol = row.get("rvol")
        if rvol is None or rvol != rvol or rvol < self.p.rvol_min:
            return Rejection("RVOL_TOO_LOW")

        # Re-entry fences, mirrored from Leg B. For a reversion the "new extreme" is a
        # deeper excursion, not a further breakout, so the comparison is inverted: a
        # second long must be further BELOW the prior entry, otherwise a slow bleed
        # through the band books three correlated losses as three independent trades.
        close = row["close"]
        if state.entries > 0:
            if state.last_exit_bar is not None:
                if bar_index - state.last_exit_bar < self.p.reentry_cooldown_bars:
                    return Rejection("REENTRY_COOLDOWN")
            prior = state.last_entry_long if side is Side.LONG else state.last_entry_short
            if prior is not None:
                needed = self.p.reentry_new_extreme_atr * atr_
                deeper = ((prior - close) if side is Side.LONG else (close - prior))
                if deeper < needed:
                    return Rejection("NO_NEW_EXTREME")

        # Target is the mean itself (section 9). If price has already reclaimed past VWAP
        # the trade the thesis describes no longer exists, so there is nothing to take.
        target_pts = (vwap - close) if side is Side.LONG else (close - vwap)
        if target_pts <= 0:
            return None

        stop_pts = stop_distance(atr_, self.inst, self.p.m_stop_atr, self.p.min_stop_ticks)

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
            reason=f"VWAPREV_{side.value}",
        )


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

        or_high, or_low = row.get("or_high"), row.get("or_low")
        or_width, atr_ = row.get("or_width"), row.get("atr")
        width_norm = row.get("or_width_norm")
        if any(v is None or v != v for v in (or_high, or_low, or_width, atr_, width_norm)):
            return None
        if atr_ <= 0 or or_width <= 0:
            return None

        # DIRECTION FIRST, then filters.
        #
        # Ordering matters for the rejection counters, not just for speed. Filters
        # evaluated before a breakout is detected fire on every eligible bar of the
        # session, while filters evaluated after fire only on actual setups. Mixing the
        # two makes the counts incomparable and badly overstates whichever filter happens
        # to sit earliest. The first real run reported 4,503 OR_TOO_WIDE against 845
        # RVOL_TOO_LOW for exactly that reason, which reads as "width is the binding
        # filter" when the two numbers were never measuring the same population.
        #
        # Every rejection below now answers one question: of the setups that actually
        # triggered a breakout, why was each refused?
        buffer_ = self.p.b_buffer_atr * atr_
        close = row["close"]

        if close > or_high + buffer_ and self.p.allow_long:
            side = Side.LONG
        elif close < or_low - buffer_ and self.p.allow_short:
            side = Side.SHORT
        else:
            return None

        if bool(row.get("entries_blocked", False)):
            return Rejection("ROLL_OR_EXPIRY")

        # An already-exhausted range has spent the move the breakout is trying to catch.
        # Compared against the random-walk baseline so the threshold means the same thing
        # at every combination of or_minutes and decision timeframe.
        if width_norm > self.p.or_max_width_norm:
            return Rejection("OR_TOO_WIDE")

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
