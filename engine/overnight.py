"""
Overnight, gap, and prior-session structure.

WHY THIS FILE EXISTS
--------------------
The forward-return screen found no univariate feature in the existing set that predicts
direction better than chance. That finding is real but narrow, and its most important
limitation is what was not in the set: every feature screened was computed from RTH bars
of the session being traded. Nothing described the overnight session, the gap, or the
prior day's structure.

That is roughly fifteen and a half hours of price formation per session that the engine
had bars for and never looked at. It is the largest block of genuinely new information
available without buying new data.

ECONOMIC THESIS
---------------
Globex trades through the night on a fraction of RTH liquidity, against participants who
often cannot hedge until the US opens. Positioning built in that window is tested when
real liquidity arrives at 09:30. The overnight extremes are therefore not statistical
constructs like a VWAP band; they are price levels where trading actually happened and
where resting orders accumulate.

The competing explanation, which the evidence has to rule out rather than assume: the
overnight range is simply a volatility estimate, and any apparent level effect is
volatility clustering wearing a costume. That is exactly why `on_range_norm` is computed
and screened alongside the level distances, so the two can be told apart.

CAUSALITY
---------
Every overnight quantity is complete at 09:30 and constant for the rest of the session,
so a bar at 11:00 uses only information that existed at the open. Before 09:30 the
columns are NaN rather than partially formed, because a half-built overnight high is not
the thing the thesis is about. Prior-session values come from the previous session date
and are known before this session begins.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .sessions import ET

# The RTH cash window, in minutes from the 09:30 ET open. 390 minutes is 09:30 to 16:00.
# This is the CASH CLOSE, not the firm's 15:50 flat time; prior-day levels are properties
# of the market, and must not move when a risk parameter changes.
RTH_MINUTES = 390


def minutes_since_open(df: pd.DataFrame) -> pd.Series:
    """
    Minutes from this bar to its own session's 09:30 ET open. Negative before the open.

    Correct across the 18:00 session boundary, which the clock-only arithmetic in
    `features.opening_range` was not: it read wall-clock time alone, so an 18:00 ET bar
    came out as +510 minutes after the open instead of -930 minutes before it. Nothing
    traded overnight, so the error was invisible; every overnight feature here would
    inherit it.

    The fix is to measure against the session the bar belongs to rather than against the
    clock, using the calendar offset between the bar's own ET date and its session date.
    """
    et = pd.DatetimeIndex(df["timestamp_utc"]).tz_convert(ET)
    minutes_of_day = et.hour * 60 + et.minute
    # 0 for bars on their session's own calendar date, -1 for the prior evening.
    day_offset = (pd.to_datetime(et.date) - pd.to_datetime(df["session_date"].values)).days
    return pd.Series(minutes_of_day - (9 * 60 + 30), index=df.index) + 1440 * day_offset


def overnight_levels(df: pd.DataFrame, mso: pd.Series) -> pd.DataFrame:
    """
    High, low and range of everything before 09:30 ET, per session.

    Frozen at the open. `on_ready` is the explicit gate: it is False for every overnight
    bar, so a strategy cannot fire on a range that is still forming, and True from the
    open onward.
    """
    sd = df["session_date"]
    pre = mso < 0

    hi = df["high"].where(pre).groupby(sd, sort=False).max()
    lo = df["low"].where(pre).groupby(sd, sort=False).min()

    out = pd.DataFrame(index=df.index)
    out["on_high"] = sd.map(hi)
    out["on_low"] = sd.map(lo)
    out["on_range"] = out["on_high"] - out["on_low"]
    # Blank during formation. A partially built overnight high is not the level the
    # thesis is about, and leaving it visible would let a signal read the future.
    out.loc[pre.to_numpy(), ["on_high", "on_low", "on_range"]] = np.nan
    out["on_ready"] = (~pre) & out["on_high"].notna() & (out["on_range"] > 0)
    return out


def prior_session(df: pd.DataFrame, mso: pd.Series) -> pd.DataFrame:
    """
    Prior session's RTH open, high, low and close, plus where the close sat in its range.

    Uses the CASH window only. Including the overnight portion would make "the prior day's
    high" mean something different from what every other participant means by it.
    """
    sd = df["session_date"]
    rth = (mso >= 0) & (mso < RTH_MINUTES)

    frame = pd.DataFrame({
        "sd": sd.values,
        "high": df["high"].where(rth).values,
        "low": df["low"].where(rth).values,
        "close": df["close"].where(rth).values,
        "open": df["open"].where(rth).values,
    })
    per = frame.groupby("sd", sort=True).agg(
        rth_high=("high", "max"), rth_low=("low", "min"),
        rth_close=("close", "last"), rth_open=("open", "first"))
    prior = per.shift(1)

    out = pd.DataFrame(index=df.index)
    for col in ("rth_high", "rth_low", "rth_close"):
        out[f"prior_{col}"] = sd.map(prior[col])
    span = (out["prior_rth_high"] - out["prior_rth_low"]).replace(0.0, np.nan)
    out["prior_close_pos"] = (out["prior_rth_close"] - out["prior_rth_low"]) / span
    out["this_rth_open"] = sd.map(per["rth_open"])
    return out


def compute(df: pd.DataFrame, atr_: pd.Series, *, lookback: int = 20) -> pd.DataFrame:
    """
    Attach the whole family. `df` must be sorted, single-symbol, decision-timeframe bars.

    Everything is expressed either in ATR units or as a fraction of a range, never in raw
    index points. A raw point distance means something different on MES at 5,800 than on
    MNQ at 20,000, and a feature that silently encodes the price level is not a feature.
    """
    mso = minutes_since_open(df)
    sd = df["session_date"]

    out = pd.concat([overnight_levels(df, mso), prior_session(df, mso)], axis=1)
    out["minutes_since_open"] = mso

    atr_safe = atr_.replace(0.0, np.nan)

    # --- the gap: where RTH opened relative to where it last closed ----------
    out["gap_points"] = out["this_rth_open"] - out["prior_rth_close"]
    out["gap_atr"] = out["gap_points"] / atr_safe
    out.loc[(mso < 0).to_numpy(), ["gap_points", "gap_atr"]] = np.nan

    # --- was the night wide or quiet, relative to recent nights? -------------
    # This is the control for the competing explanation. If a level effect is really
    # volatility clustering, it will show up here and not in the distance features.
    per_session_range = out.groupby(sd, sort=False)["on_range"].max()
    baseline = per_session_range.shift(1).rolling(lookback, min_periods=5).median()
    out["on_range_norm"] = sd.map(per_session_range / baseline)
    out["on_range_atr"] = out["on_range"] / atr_safe

    # --- where is price now, relative to the overnight structure? ------------
    out["dist_on_high_atr"] = (df["close"] - out["on_high"]) / atr_safe
    out["dist_on_low_atr"] = (df["close"] - out["on_low"]) / atr_safe
    span = out["on_range"].replace(0.0, np.nan)
    # 0.0 at the overnight low, 1.0 at the overnight high. Deliberately NOT clipped:
    # values outside [0, 1] are the breakouts, which is the interesting part.
    out["on_pos"] = (df["close"] - out["on_low"]) / span
    out["gap_vs_on_range"] = out["gap_points"] / span

    return out.drop(columns=["this_rth_open"])
