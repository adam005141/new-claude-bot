"""
Feature computation.

The single invariant here: a feature attached to bar `t` uses ONLY bars up to and
including `t`. The backtest then acts on it at bar `t+1`. Any feature that needs the
future is either shifted or not computed at all.

Rolling statistics that describe "normal" behaviour (relative volume, volatility
percentile) use PRIOR sessions only, never the session being traded. Including the
current session would leak the day's own character into the decision to trade it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import regime
from .sessions import ET, minutes_since_rth_open, session_dates


def typical_price(df: pd.DataFrame) -> pd.Series:
    return (df["high"] + df["low"] + df["close"]) / 3.0


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """Volume-weighted average price, anchored at each session's first bar."""
    tp = typical_price(df)
    vol = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    g = df.groupby("session_date", sort=False)
    cum_pv = (tp * vol).groupby(df["session_date"], sort=False).cumsum()
    cum_v = vol.groupby(df["session_date"], sort=False).cumsum()
    return (cum_pv / cum_v.replace(0.0, np.nan)).ffill()


def vwap_sigma(df: pd.DataFrame, vwap: pd.Series) -> pd.Series:
    """
    Volume-weighted POPULATION standard deviation about the running VWAP.

    Two choices worth stating because implementations differ silently: this is the
    population form (divide by total weight, not weight minus one), and deviations are
    measured against the CURRENT vwap rather than a per-bar historical one.
    """
    tp = typical_price(df)
    vol = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    sd = df["session_date"]

    cum_v = vol.groupby(sd, sort=False).cumsum()
    cum_pv2 = (tp.pow(2) * vol).groupby(sd, sort=False).cumsum()
    mean_sq = cum_pv2 / cum_v.replace(0.0, np.nan)
    var = (mean_sq - vwap.pow(2)).clip(lower=0.0)
    return np.sqrt(var)


def vwap_bands(df: pd.DataFrame, vwap: pd.Series, k: float) -> tuple[pd.Series, pd.Series]:
    """Bands at +/- k sigma. Kept as a convenience over `vwap_sigma`."""
    sigma = vwap_sigma(df, vwap)
    return vwap - k * sigma, vwap + k * sigma


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    return pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Wilder-smoothed ATR on the decision timeframe."""
    tr = true_range(df)
    return tr.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()


def realized_vol(df: pd.DataFrame, window: int = 30) -> pd.Series:
    logret = np.log(df["close"] / df["close"].shift(1))
    return logret.rolling(window, min_periods=window).std()


def opening_range(df: pd.DataFrame, or_minutes: int, bar_minutes: int = 5) -> pd.DataFrame:
    """
    High and low of the first `or_minutes` after 09:30 ET, per session.

    Values become available only AFTER the window closes. Before that the columns are
    NaN, which is what stops the leg firing on a range that has not finished forming.
    `or_ready` is the explicit gate the strategy checks.
    """
    ts = pd.DatetimeIndex(df["timestamp_utc"])
    et = ts.tz_convert(ET)
    open_min = pd.Series(
        (et.hour * 60 + et.minute) - (9 * 60 + 30), index=df.index, dtype="float64"
    )
    # Bars from the prior evening belong to this session but precede its RTH open.
    open_min[open_min < -600] += 1440

    in_window = (open_min >= 0) & (open_min < or_minutes)
    sd = df["session_date"]

    hi = df["high"].where(in_window).groupby(sd, sort=False).cummax()
    lo = df["low"].where(in_window).groupby(sd, sort=False).cummin()

    out = pd.DataFrame(index=df.index)
    # Freeze the range at the window's close, then carry it forward for the session.
    out["or_high"] = hi.groupby(sd, sort=False).ffill()
    out["or_low"] = lo.groupby(sd, sort=False).ffill()
    out["or_width"] = out["or_high"] - out["or_low"]
    out["minutes_since_open"] = open_min
    out["or_ready"] = (open_min >= or_minutes) & out["or_high"].notna() & out["or_low"].notna()
    # Inside the forming window the range is not yet knowable, so blank it entirely.
    out.loc[in_window, ["or_high", "or_low", "or_width"]] = np.nan
    out["or_bars"] = max(1.0, or_minutes / max(bar_minutes, 1))
    return out


def normalise_or_width(or_width: pd.Series, atr_: pd.Series,
                       or_bars: float) -> pd.Series:
    """
    Opening-range width relative to what a driftless random walk would already produce.

    Raw or_width/ATR is NOT scale free. For a random walk the expected range over n bars
    grows as sqrt(n), so the raw ratio is ~sqrt(or_minutes / bar_minutes) before the
    market has done anything unusual: about 2.45 at 30-minute range on 5-minute bars,
    and 5.48 on 1-minute bars. A fixed threshold on the raw ratio therefore encodes the
    timeframe rather than the market, and silently changes meaning whenever either
    parameter moves.

    Dividing by sqrt(n) makes 1.0 mean "an ordinary range for this timeframe", so the
    threshold expresses how much wider than ordinary is too wide.
    """
    baseline = atr_ * np.sqrt(max(or_bars, 1.0))
    return or_width / baseline.replace(0.0, np.nan)


def relative_volume(df: pd.DataFrame, lookback: int = 20) -> pd.Series:
    """
    Session-to-date volume against the median of PRIOR sessions at the same elapsed point.

    Causal by construction: the comparison set is shifted so the current session never
    contributes to its own baseline.
    """
    sd = df["session_date"]
    vol = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
    cum = vol.groupby(sd, sort=False).cumsum()
    bar_of_session = df.groupby(sd, sort=False).cumcount()

    frame = pd.DataFrame({"sd": sd.values, "bar": bar_of_session.values, "cum": cum.values})
    wide = frame.pivot_table(index="sd", columns="bar", values="cum", aggfunc="last")
    baseline = wide.shift(1).rolling(lookback, min_periods=3).median()

    stacked = baseline.stack(future_stack=True).rename("baseline").reset_index()
    merged = frame.merge(stacked, on=["sd", "bar"], how="left")
    rvol = (merged["cum"] / merged["baseline"].replace(0.0, np.nan)).values
    return pd.Series(rvol, index=df.index)


def vwap_slope(vwap: pd.Series, atr_: pd.Series, sd: pd.Series, k: int = 10) -> pd.Series:
    """ATR-normalised VWAP slope, computed within a session so it never spans a roll."""
    diff = vwap.groupby(sd, sort=False).diff(k)
    return diff / (k * atr_.replace(0.0, np.nan))


def compute(df: pd.DataFrame, *, or_minutes: int, atr_window: int,
            rvol_lookback: int, rv_window: int = 30,
            vwap_k: float = 2.0, bar_minutes: int = 5,
            theta_trend: float = 0.35, theta_range: float = 0.15,
            theta_rvol: float = 1.10, rv_lo: float = 0.20,
            rv_hi: float = 0.80) -> pd.DataFrame:
    """Attach every feature. Input must be sorted, single-symbol, decision-timeframe bars."""
    if df.empty:
        return df.copy()

    out = df.copy().reset_index(drop=True)
    sd = out["session_date"]

    out["vwap"] = session_vwap(out)
    out["vwap_sigma"] = vwap_sigma(out, out["vwap"])
    out["vwap_lower"] = out["vwap"] - vwap_k * out["vwap_sigma"]
    out["vwap_upper"] = out["vwap"] + vwap_k * out["vwap_sigma"]
    # Deviation in sigma units. Leg A's two-bar test is a statement about this quantity at
    # t-1 and t, so expressing it once here keeps the strategy from re-deriving it and
    # keeps the prior-bar value from being taken across a session boundary.
    out["vwap_dev"] = ((out["close"] - out["vwap"])
                       / out["vwap_sigma"].replace(0.0, np.nan))
    out["prev_vwap_dev"] = out.groupby(sd, sort=False)["vwap_dev"].shift(1)
    out["atr"] = atr(out, atr_window)
    out["realized_vol"] = realized_vol(out, rv_window)
    out["rvol"] = relative_volume(out, rvol_lookback)
    out["vwap_slope"] = vwap_slope(out["vwap"], out["atr"], sd)
    out["bar_of_session"] = out.groupby(sd, sort=False).cumcount()

    out = pd.concat([out, opening_range(out, or_minutes, bar_minutes)], axis=1)
    out["or_width_norm"] = normalise_or_width(out["or_width"], out["atr"],
                                              out["or_bars"].iloc[0])

    # Volatility percentile against a trailing distribution of PRIOR sessions only.
    per_session_rv = out.groupby(sd)["realized_vol"].mean()
    trailing = per_session_rv.shift(1).rolling(60, min_periods=10)
    pct = (per_session_rv.shift(1).rolling(60, min_periods=10)
           .rank(pct=True))
    out["rv_pct"] = out["session_date"].map(pct)

    # Regime last: it consumes vwap_slope, rvol, and rv_pct, all of which are already
    # causal by construction above.
    out["regime"] = regime.attach(out, theta_trend=theta_trend, theta_range=theta_range,
                                  theta_rvol=theta_rvol, rv_lo=rv_lo, rv_hi=rv_hi)

    return out
