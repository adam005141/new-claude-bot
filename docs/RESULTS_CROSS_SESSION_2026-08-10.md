# Cross-session breakouts: all three fail, and the prediction held

Run 2026-08-10, once, per `docs/PREREGISTRATION_2026-08-10_CROSS_SESSION.md`.
ES 2009-2016, 2,018 sessions, priced as MES, 1 contract, two-sided, $3.70/round trip.

## Result

| arm | trades | f | net | $/trade | WR | long | stop | Sharpe_all | t | p |
|---|---|---|---|---|---|---|---|---|---|---|
| A2L | 1,870 | 0.93 | -9,526 | **-5.09** | 39% | 55% | 27% | -0.173 | -7.78 | 1.000 |
| L2N | 1,918 | 0.95 | -7,125 | **-3.71** | 44% | 51% | 31% | -0.074 | -3.34 | 0.999 |
| NYOR | 1,927 | 0.95 | -7,110 | **-3.69** | 44% | 54% | 28% | -0.086 | -3.84 | 1.000 |

All three **FAIL** all four criteria. Under a doubled spread they go to -$6.34, -$4.96 and
-$4.94. Every one of the eight years is negative for every arm — there is no regime in this
sample where a range breakout worked.

## Gross versus cost, which is the informative part

| arm | gross $/trade | t(gross) | net | reading |
|---|---|---|---|---|
| A2L | **-1.39** | **-2.13** | -5.09 | **negative before cost** |
| L2N | -0.01 | -0.01 | -3.71 | zero before cost |
| NYOR | +0.01 | +0.01 | -3.69 | zero before cost |

**L2N and NYOR have no signal at all.** Gross is one cent per trade on ~1,900 trades. A
breakout of the London range into NY, and of the NY opening range into the rest of NY, is a
coin flip. They lose exactly the commission and spread, nothing more and nothing less.

**A2L is worse than nothing.** The Asian-range breakout is negative *before* any cost, at
-$1.39 a trade with t = -2.13. Breaking the Asian range predicts reversal, not continuation,
and it does so in the thinnest and most mean-reverting session of the day.

## The registered prediction was correct

> All three arms come back negative after cost, between -$2 and -$8 per trade. NYOR is the
> least bad... A2L is the worst... short-horizon ES returns are mildly mean-reverting, not
> trending, so a breakout should be slightly negative once it pays the spread.

Every part held. Range -$5.09 to -$3.69, inside the predicted -$2 to -$8. Ordering exact:
A2L worst, NYOR least bad. And the stated mechanism is confirmed rather than merely
consistent: A2L's gross is significantly negative, which is what mean reversion predicts and
what a pure cost story would not.

Recorded next to Block A, where the prediction was wrong on sign and significance, and the
overnight arms, where the gross figure landed inside the registered range.

## What this closes

Thirteen structures are now closed on evidence. The two-sided fix mattered and was not
enough: making the breakout symmetric removed the long-only bias that Block A's post-mortem
blamed, and the arms still returned zero gross. Long share came out 51-55%, so the design
worked as intended; there was simply nothing to capture.

Taken with the terrain table, the picture across the whole 24-hour day is now consistent:

- **Directional drift** exists in Asia (t 2.68) and is 0.70x its own round trip
- **The overnight premium** is real, +0.376 pts, and is 0.75x its round trip
- **Breakouts** have zero gross edge in London and NY, and negative gross in Asia

Every measurable effect found in ES over eight years is either smaller than the spread or
pointing the wrong way.

## Not tested, and not claimed

Mean reversion is the mirror of what was tested here and A2L's negative gross is a hint
toward it. That is **not** a finding and must not be traded on: it is the same data, it
would be a fourth arm added after seeing three, and the pre-registration forbids exactly
that. If it is ever tested it needs its own registration and the untouched 2017-2023 set.
