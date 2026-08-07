"""
Data loading, roll handling, and construction of the continuous active-contract series.

Two rules govern everything here:

1. Prices are UNADJUSTED traded prices from the active dated contract. Back-adjusted
   series are forbidden from feeding any executable level, because the adjustment shifts
   historical prices and would silently corrupt stops, targets, and fills around rolls.
2. The active contract is chosen from information available at the PRIOR session close.
   Choosing it from the current session's own volume would be lookahead: it would use
   the very activity the strategy is trying to trade ahead of.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from .sessions import session_dates

log = logging.getLogger(__name__)

# Symbols may contain DIGITS: M2K, M6E, MYM. The original `[A-Z]+` silently skipped every
# such file, so a whole instrument could be present on disk and invisible to the engine,
# reported as "no files" rather than as an error. Anchored to start with a letter so the
# six-digit contract group cannot be absorbed into the symbol.
_FILENAME = re.compile(
    r"^(?P<symbol>[A-Z][A-Z0-9]*)_(?P<contract>\d{6})_(?P<bar>\w+?)_(?P<what>[A-Z_]+)\.parquet$"
)

REQUIRED_COLUMNS = {"timestamp_utc", "open", "high", "low", "close"}


@dataclass(frozen=True)
class ContractFile:
    path: Path
    symbol: str
    contract_month: str
    bar_size: str
    what_to_show: str

    @property
    def expiry(self) -> date:
        """Third Friday of the contract month."""
        y, m = int(self.contract_month[:4]), int(self.contract_month[4:])
        fridays = [d for d in range(1, 29)
                   if date(y, m, d).weekday() == 4]
        return date(y, m, fridays[2])


def discover(data_dir: str | Path, symbol: str,
             bar_size: str = "1min", what: str = "TRADES") -> list[ContractFile]:
    """Find every dated-contract file for one symbol, sorted by contract month."""
    root = Path(data_dir)
    found: list[ContractFile] = []
    for p in sorted(root.rglob("*.parquet")):
        if "_cache" in p.parts:
            continue
        m = _FILENAME.match(p.name)
        if not m:
            continue
        g = m.groupdict()
        if g["symbol"] != symbol or g["bar"] != bar_size or g["what"] != what:
            continue
        found.append(ContractFile(p, g["symbol"], g["contract"], g["bar"], g["what"]))
    return sorted(found, key=lambda c: c.contract_month)


def load_contract(cf: ContractFile) -> pd.DataFrame:
    """Load one contract file and normalise it to the engine's schema."""
    df = pd.read_parquet(cf.path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"{cf.path.name}: missing columns {sorted(missing)}")

    df = df.copy()
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    if "volume" not in df.columns:
        df["volume"] = pd.NA
    df["contract_month"] = cf.contract_month
    df["symbol"] = cf.symbol

    df = (df[["timestamp_utc", "open", "high", "low", "close", "volume",
              "symbol", "contract_month"]]
          .drop_duplicates(subset=["timestamp_utc"], keep="last")
          .sort_values("timestamp_utc")
          .reset_index(drop=True))
    return df


def choose_active_contract(per_contract: dict[str, pd.DataFrame],
                           min_session_volume_fraction: float = 0.01,
                           confirm_sessions: int = 3) -> pd.DataFrame:
    """
    Volume-crossover roll, decided one session in arrears.

    Returns a frame indexed by session date with the contract to trade in that session.

    The lag is the whole point. Volume for session D is only known once D has closed, so
    the choice made from D's volume can only take effect from D+1. Anything else peeks.

    DORMANT SESSIONS DO NOT GET A VOTE
    ----------------------------------
    Only sessions carrying at least `min_session_volume_fraction` of the busiest session's
    volume take part in the decision. Without that filter the roll is destroyed by data
    that starts at a contract's listing date rather than near its front-month window.

    Concretely, from real 2011-2013 gold: every expiry is listed years early and dribbles
    single-lot prints long before anyone trades it, and a far-dated December routinely
    out-trades the intervening months while all of them are dormant. The anti-flip-flop
    guard below then latches onto that December on a 2-lot session in 2011, so the whole of
    2013 is served by the December contract while February, April, June and August were
    each front in turn. The raw per-session winners were correct throughout; the guard was
    being applied to noise.

    The threshold is not sensitive: dormant sessions run three to four orders of magnitude
    below front-month ones, so anything from 0.1% to 10% gives the same roll. It exists to
    separate "trading" from "not trading", not to be tuned.

    Sessions below the floor still receive an active contract, inherited from the nearest
    decided session, and are flagged `thin_session` by `build_continuous` so the caller can
    exclude them. They are not dropped here: that would silently change the span of every
    series built from data whose leading edge is thin.
    """
    frames = []
    for contract, df in per_contract.items():
        if df.empty:
            continue
        sd = session_dates(pd.DatetimeIndex(df["timestamp_utc"]))
        vol = pd.to_numeric(df["volume"], errors="coerce").fillna(0).values
        frames.append(pd.DataFrame({"session_date": sd.values,
                                    "contract_month": contract,
                                    "volume": vol}))
    if not frames:
        return pd.DataFrame(columns=["session_date", "contract_month"])

    daily = (pd.concat(frames, ignore_index=True)
             .groupby(["session_date", "contract_month"], as_index=False)["volume"].sum())

    session_total = daily.groupby("session_date")["volume"].sum()
    all_sessions = session_total.index.sort_values()
    floor = float(min_session_volume_fraction) * float(session_total.max())
    voting = session_total.index[session_total >= floor]

    # Winner by volume WITHIN each session, then shifted forward one session so the
    # decision only ever uses already-closed information.
    winner = (daily[daily["session_date"].isin(voting)]
              .sort_values(["session_date", "volume"])
              .groupby("session_date", as_index=False)
              .last()[["session_date", "contract_month"]]
              .rename(columns={"contract_month": "winner"})
              .sort_values("session_date")
              .reset_index(drop=True))
    if winner.empty:
        return pd.DataFrame(columns=["session_date", "contract_month"])

    # Rolling FORWARD to a later expiry takes effect the next session: that is an ordinary
    # volume crossover, and the one-session lag is the whole contract of this function.
    # Falling BACK to an earlier expiry has to persist for `confirm_sessions` consecutive
    # voting sessions first, because a single quiet day on which the old contract
    # out-trades the new one is noise, not a roll.
    #
    # The asymmetry replaces a `cummax` over the winner series. That guard enforced the
    # same "never flip back" intent, but by making the choice MONOTONIC FOREVER, so one
    # anomalous session corrupted every session after it.
    #
    # Real example, from silver 2011. The December 2011 contract is missing from the
    # download, so on 2011-09-26 the only contracts with any volume were dormant ones and
    # the session total of 3,021 lots squeaked over the floor. The far-dated December 2012
    # contract won that single session on 1,077 lots, cummax latched onto it, and 211 of
    # the following 820 sessions were served by the wrong contract -- right through 2012,
    # when March, May, July and September each genuinely had their turn. A local gap in one
    # contract became global corruption of the whole series.
    #
    # Under this rule the same session costs a handful of sessions rather than the rest of
    # the series: the spurious jump forward is taken, then the real front month wins
    # `confirm_sessions` in a row and the series falls back to it. Contract months are
    # zero-padded YYYYMM, so string ordering is expiry ordering.
    seq = winner["winner"].tolist()
    current = seq[0]                       # no prior session to learn from
    streak_of, streak_n = None, 0
    active_seq: list[str] = []
    for w in seq:
        active_seq.append(current)         # decided before this session is observed
        streak_of, streak_n = (w, streak_n + 1) if w == streak_of else (w, 1)
        if w > current:
            current = w                    # forward: an ordinary crossover
        elif w < current and streak_n >= confirm_sessions:
            current = w                    # backward: only once it has proved itself
    winner["active"] = active_seq

    # Dormant sessions inherit the nearest decision: forward from the last decided one,
    # and backward for any that precede the first.
    active = (winner.set_index("session_date")["active"]
              .reindex(all_sessions).ffill().bfill())
    return (active.rename("contract_month").reset_index()
            .rename(columns={"index": "session_date"})[["session_date", "contract_month"]])


def build_continuous(data_dir: str | Path, symbol: str,
                     bar_size: str = "1min", what: str = "TRADES",
                     stop_entries_days_before_expiry: int = 5,
                     min_session_volume_fraction: float = 0.01,
                     confirm_sessions: int = 3) -> pd.DataFrame:
    """
    Build the continuous active-contract series for one symbol.

    Bars are taken from whichever dated contract was active in that session, at that
    contract's own unadjusted prices. No stitching adjustment is applied, so a roll shows
    up as a price discontinuity between sessions. That is correct: the discontinuity is
    real, and hiding it would manufacture overnight P&L that nobody could have earned.

    Adds:
      session_date          the CME session each bar belongs to
      contract_month        the contract actually traded
      is_roll_session       True when the active contract differs from the prior session
      thin_session          True when the active contract barely traded that session
      entries_blocked       True within N sessions of expiry, or during a roll session
    """
    files = discover(data_dir, symbol, bar_size, what)
    if not files:
        raise FileNotFoundError(
            f"no {symbol} {bar_size} {what} files under {data_dir}. "
            "Run tools/ibkr_download.py first."
        )

    per_contract = {cf.contract_month: load_contract(cf) for cf in files}
    expiry = {cf.contract_month: cf.expiry for cf in files}

    active = choose_active_contract(per_contract, min_session_volume_fraction,
                                    confirm_sessions)
    if active.empty:
        raise ValueError(f"{symbol}: no volume anywhere, cannot determine active contract")
    active_by_date = dict(zip(active["session_date"], active["contract_month"]))

    out = []
    for contract, df in per_contract.items():
        if df.empty:
            continue
        d = df.copy()
        d["session_date"] = session_dates(pd.DatetimeIndex(d["timestamp_utc"])).values
        keep = d["session_date"].map(active_by_date) == contract
        out.append(d[keep])

    if not out:
        raise ValueError(f"{symbol}: active-contract selection produced no bars")

    cont = (pd.concat(out, ignore_index=True)
            .drop_duplicates(subset=["timestamp_utc"], keep="last")
            .sort_values("timestamp_utc")
            .reset_index(drop=True))

    prior = cont["contract_month"].groupby(cont["session_date"]).transform("first")
    session_first = cont.drop_duplicates("session_date")[["session_date", "contract_month"]]
    session_first["is_roll"] = session_first["contract_month"].ne(
        session_first["contract_month"].shift(1)).fillna(False)
    roll_map = dict(zip(session_first["session_date"], session_first["is_roll"]))
    cont["is_roll_session"] = cont["session_date"].map(roll_map).fillna(False)

    # A session where the active contract barely traded is not a session anyone could
    # have traded. Flagged rather than dropped: dropping would silently shorten every
    # series whose leading edge is thin. `tools/oos_test.py` had to gate this by hand
    # after MGC's December expiry printed tens of lots a bar for three weeks while August
    # carried the market, and the opening ranges from those sessions were untradeable.
    sess_vol = cont.groupby("session_date")["volume"].sum()
    thin = sess_vol < min_session_volume_fraction * float(sess_vol.max())
    cont["thin_session"] = cont["session_date"].map(thin).fillna(False)

    days_to_expiry = cont.apply(
        lambda r: (expiry[r["contract_month"]] - r["session_date"]).days, axis=1)
    cont["days_to_expiry"] = days_to_expiry
    cont["entries_blocked"] = (
        (days_to_expiry <= stop_entries_days_before_expiry) | cont["is_roll_session"]
    )

    log.info("%s: %d bars, %s to %s, %d sessions, %d contracts, %d blocked bars",
             symbol, len(cont), cont["session_date"].min(), cont["session_date"].max(),
             cont["session_date"].nunique(), cont["contract_month"].nunique(),
             int(cont["entries_blocked"].sum()))
    return cont


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """
    Resample 1-minute bars to the decision timeframe.

    Bars are labelled by their OPEN and closed on the left, so a bar timestamped 09:30
    covers 09:30 to 09:35 and is only COMPLETE at 09:35. The backtest never acts on a bar
    until the following one begins, which is what makes that labelling safe.

    Resampling is done per session so a bar can never span the maintenance break or two
    different contracts.
    """
    if minutes <= 1:
        return df.reset_index(drop=True)

    rule = f"{minutes}min"
    pieces = []
    for (sd, contract), grp in df.groupby(["session_date", "contract_month"], sort=True):
        g = grp.set_index("timestamp_utc")
        agg = g.resample(rule, label="left", closed="left").agg(
            open=("open", "first"), high=("high", "max"),
            low=("low", "min"), close=("close", "last"),
            volume=("volume", "sum"),
        ).dropna(subset=["open"])
        if agg.empty:
            continue
        agg["session_date"] = sd
        agg["contract_month"] = contract
        agg["symbol"] = grp["symbol"].iloc[0]
        for col in ("is_roll_session", "entries_blocked"):
            if col in grp.columns:
                agg[col] = bool(grp[col].any())
        if "days_to_expiry" in grp.columns:
            agg["days_to_expiry"] = grp["days_to_expiry"].iloc[0]
        pieces.append(agg.reset_index())

    if not pieces:
        return df.iloc[0:0].reset_index(drop=True)

    return (pd.concat(pieces, ignore_index=True)
            .sort_values("timestamp_utc")
            .reset_index(drop=True))


def provenance(data_dir: str | Path, symbol: str,
               bar_size: str = "1min", what: str = "TRADES") -> list[dict]:
    """Collect the .meta.json sidecars so every run records what it consumed."""
    out = []
    for cf in discover(data_dir, symbol, bar_size, what):
        meta = cf.path.with_suffix(".meta.json")
        if meta.exists():
            try:
                out.append(json.loads(meta.read_text()))
            except Exception as exc:                      # noqa: BLE001
                log.warning("unreadable provenance %s: %s", meta.name, exc)
    return out
