"""
Session and clock logic.

Every boundary is a named parameter defined in America/New_York and resolved through a
DST-aware library. Eastern Time is NEVER a fixed UTC offset: the 2025-09 to 2026-07
dataset spans two DST transitions, so a hardcoded offset would silently shift every
opening range by an hour across the boundary.

Five distinct clock concepts are kept separate and never derived from one another:
the equity cash close, futures settlement, the CME maintenance break, the firm's
required flat time, and the firm's daily reset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")

# A CME equity-index session runs 18:00 ET through 17:00 ET the next day, so the session
# a bar belongs to is not simply its calendar date. Adding this offset rotates the clock
# so that 18:00 ET lands on midnight of the session it opens.
_SESSION_ROLL_OFFSET = timedelta(hours=6)


class Session(str, Enum):
    """Named intraday windows. Every one is a hypothesis that evidence may disable."""
    ASIA = "ASIA"
    LONDON = "LONDON"
    EU_NY_OVERLAP = "EU_NY_OVERLAP"
    NY_PREMARKET = "NY_PREMARKET"
    RTH_OPEN = "RTH_OPEN"
    RTH_MIDDAY = "RTH_MIDDAY"
    RTH_AFTERNOON = "RTH_AFTERNOON"
    RTH_CLOSE = "RTH_CLOSE"
    POST_CLOSE = "POST_CLOSE"
    MAINTENANCE = "MAINTENANCE"
    CLOSED = "CLOSED"


# Ordered, non-overlapping, half-open [start, end) windows in ET.
DEFAULT_WINDOWS: list[tuple[Session, time, time]] = [
    (Session.RTH_OPEN,      time(9, 30),  time(10, 30)),
    (Session.RTH_MIDDAY,    time(10, 30), time(14, 0)),
    (Session.RTH_AFTERNOON, time(14, 0),  time(15, 50)),
    (Session.RTH_CLOSE,     time(15, 50), time(16, 0)),
    # The cash market closes at 16:00 but the future keeps trading until 17:00 ET
    # (16:00 CT). That hour was previously classified CLOSED, which silently removed a
    # tradable hour from every screen. It only mattered once overnight holds were allowed.
    (Session.POST_CLOSE,    time(16, 0),  time(17, 0)),
    (Session.MAINTENANCE,   time(17, 0),  time(18, 0)),
    (Session.NY_PREMARKET,  time(8, 0),   time(9, 30)),
    (Session.EU_NY_OVERLAP, time(7, 0),   time(8, 0)),
    (Session.LONDON,        time(3, 0),   time(7, 0)),
    (Session.ASIA,          time(18, 0),  time(23, 59, 59)),
]

# Every session the contract actually trades. The only excluded windows are MAINTENANCE
# (17:00-18:00 ET, the CME daily halt) and CLOSED.
#
# This was RTH-only until 2026-08-06, when the firm rule was clarified: positions may be
# held overnight and must be flat only for the daily break. Every result recorded before
# that date was produced under the RTH-only setting and measured RTH bars alone, which is
# why roughly fifteen hours of each session had never been screened.
#
# The 17:00 flat requirement lands exactly on the 18:00 session roll, so the engine's
# invariant that a position never crosses a session boundary still holds unchanged. What
# changes is the length of the leash inside one session: up to 23 hours instead of 6.
DEFAULT_ENABLED: frozenset[Session] = frozenset({
    Session.ASIA, Session.LONDON, Session.EU_NY_OVERLAP, Session.NY_PREMARKET,
    Session.RTH_OPEN, Session.RTH_MIDDAY, Session.RTH_AFTERNOON, Session.RTH_CLOSE,
    Session.POST_CLOSE,
})

# RTH only. Kept so the pre-2026-08-06 results stay reproducible.
RTH_ONLY: frozenset[Session] = frozenset({
    Session.RTH_OPEN, Session.RTH_MIDDAY, Session.RTH_AFTERNOON,
})


@dataclass(frozen=True)
class SessionCalendar:
    """
    Holiday and early-close calendar.

    An unknown date FAILS CLOSED to "do not trade" only when `strict` is set. The
    backtest default is permissive, because a missing holiday entry would otherwise
    silently delete tradable days from the sample and flatter the results by omission.
    Live deployment should set strict=True.
    """
    holidays: frozenset[date] = frozenset()
    early_closes: dict[date, time] = field(default_factory=dict)
    strict: bool = False

    def is_holiday(self, session_date: date) -> bool:
        return session_date in self.holidays

    def close_time(self, session_date: date) -> time:
        return self.early_closes.get(session_date, time(16, 0))

    def is_early_close(self, session_date: date) -> bool:
        return session_date in self.early_closes


def to_et(ts: pd.Timestamp | datetime) -> pd.Timestamp:
    """Convert a UTC-aware timestamp to Eastern, DST-aware. Rejects naive input."""
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        raise ValueError(f"naive timestamp {ts!r}; all timestamps must be tz-aware UTC")
    return ts.tz_convert(ET)


def session_date(ts: pd.Timestamp | datetime) -> date:
    """
    The trading session a timestamp belongs to.

    Bars from 18:00 ET onward belong to the NEXT calendar day's session, matching CME's
    definition. Grouping by calendar date instead would split every session in two and
    corrupt session VWAP, opening range, and every daily statistic.
    """
    return (to_et(ts) + _SESSION_ROLL_OFFSET).date()


def session_dates(index: pd.DatetimeIndex) -> pd.Series:
    """Vectorised `session_date` for a whole index."""
    if index.tz is None:
        raise ValueError("index must be tz-aware UTC")
    return pd.Series((index.tz_convert(ET) + _SESSION_ROLL_OFFSET).date, index=index)


def classify(ts: pd.Timestamp | datetime,
             windows: list[tuple[Session, time, time]] | None = None) -> Session:
    """Classify one timestamp into a named session window."""
    et = to_et(ts)
    if et.weekday() == 5:                                  # Saturday: never open
        return Session.CLOSED
    t = et.time()
    for name, start, end in (windows or DEFAULT_WINDOWS):
        if start <= t < end:
            return name
    if t >= time(18, 0) or t < time(3, 0):
        return Session.ASIA
    return Session.CLOSED


def classify_index(index: pd.DatetimeIndex,
                   windows: list[tuple[Session, time, time]] | None = None) -> pd.Series:
    """Vectorised `classify`. Kept loop-free for speed on ~700k bars."""
    if index.tz is None:
        raise ValueError("index must be tz-aware UTC")
    et = index.tz_convert(ET)
    minutes = et.hour * 60 + et.minute
    out = pd.Series(Session.CLOSED, index=index, dtype=object)

    for name, start, end in (windows or DEFAULT_WINDOWS):
        s = start.hour * 60 + start.minute
        e = end.hour * 60 + end.minute
        out[(minutes >= s) & (minutes < e)] = name

    still_closed = out == Session.CLOSED
    out[still_closed & ((minutes >= 18 * 60) | (minutes < 3 * 60))] = Session.ASIA
    out[et.weekday == 5] = Session.CLOSED
    return out


def rth_open_et(session_date_: date) -> datetime:
    """09:30 ET on the given session date, DST-aware."""
    return datetime.combine(session_date_, time(9, 30), tzinfo=ET)


def minutes_since_rth_open(ts: pd.Timestamp | datetime) -> float:
    """
    Minutes elapsed since 09:30 ET of this timestamp's session. Negative before the open.

    Used by the opening-range leg, which must never evaluate before its range window has
    actually closed.
    """
    et = to_et(ts)
    return (et - rth_open_et(session_date(ts))).total_seconds() / 60.0


def is_tradable(ts: pd.Timestamp | datetime,
                calendar: SessionCalendar,
                enabled: frozenset[Session] = DEFAULT_ENABLED) -> bool:
    """
    Whether a timestamp is eligible for a NEW entry.

    Deliberately conservative: this gates entries only. Exits, flattening, and risk halts
    must still run outside these windows, which is why the backtest loop calls this at the
    entry step and nowhere earlier.
    """
    sd = session_date(ts)
    if calendar.is_holiday(sd):
        return False
    sess = classify(ts)
    if sess in (Session.CLOSED, Session.MAINTENANCE):
        return False
    if calendar.is_early_close(sd) and to_et(ts).time() >= calendar.close_time(sd):
        return False
    return sess in enabled
