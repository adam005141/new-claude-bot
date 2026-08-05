"""
Causal regime classification.

Leg A only trades RANGE and Leg B only trades TREND or NEUTRAL, so the classifier is
what keeps a mean-reversion setup out of a trending market. Getting it wrong in the
optimistic direction would let the strategy fade exactly the moves that run.

Everything here uses information available at the decision bar. The volatility
percentile in particular is built from a trailing distribution that ends at the PRIOR
session close: including the current session would let the day's own character decide
whether the day was tradable.

The NEUTRAL band between `theta_range` and `theta_trend` is deliberate. Without it every
bar would be forced into one regime or the other, and the classifier would manufacture
trades at the boundary where its own signal is weakest.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd


class Regime(str, Enum):
    TREND = "TREND"
    RANGE = "RANGE"
    NEUTRAL = "NEUTRAL"


def classify(slope_abs: pd.Series, rvol: pd.Series, rv_pct: pd.Series, *,
             theta_trend: float, theta_range: float, theta_rvol: float,
             rv_lo: float, rv_hi: float) -> pd.Series:
    """
    Vectorised regime classification.

    TREND   directional VWAP slope with participation to back it
    RANGE   flat VWAP slope and volatility in the middle of its own distribution
    NEUTRAL everything else, which never trades

    Anything with a missing input is NEUTRAL, so a warm-up bar or a gap can never be
    mistaken for a tradable regime.
    """
    out = pd.Series(Regime.NEUTRAL, index=slope_abs.index, dtype=object)

    known = slope_abs.notna() & rvol.notna() & rv_pct.notna()

    is_trend = known & (slope_abs >= theta_trend) & (rvol >= theta_rvol)
    is_range = (known & (slope_abs < theta_range)
                & (rv_pct >= rv_lo) & (rv_pct <= rv_hi))

    # TREND is applied second so that a bar satisfying both, which the NEUTRAL gap makes
    # impossible under sane thresholds, resolves to the more dangerous reading.
    out[is_range] = Regime.RANGE
    out[is_trend] = Regime.TREND
    return out


def attach(df: pd.DataFrame, *, theta_trend: float, theta_range: float,
           theta_rvol: float, rv_lo: float, rv_hi: float) -> pd.Series:
    """Classify a feature frame produced by engine.features.compute."""
    return classify(
        df["vwap_slope"].abs(), df["rvol"], df["rv_pct"],
        theta_trend=theta_trend, theta_range=theta_range,
        theta_rvol=theta_rvol, rv_lo=rv_lo, rv_hi=rv_hi,
    )
