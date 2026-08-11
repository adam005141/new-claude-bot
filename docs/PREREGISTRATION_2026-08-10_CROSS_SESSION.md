# Pre-registration: cross-session range breakouts, NY / London / Asia

Written **2026-08-10, before any breakout code was run against ES**. The only ES numbers
seen so far are the exploratory terrain table (drift, range, volume share, cost/range per
window), which contains no breakout result. Nothing below may be revised after seeing one.

## Why this, and what is different from Leg B

Leg B was an opening-range breakout and it failed. Three things about that test were weak,
and all three are fixed here rather than argued away:

1. **It ran on 72 trades of MES.** This runs on ~2,000 sessions of ES per arm across eight
   years and several regimes.
2. **It was long only.** So was the commodity ORB, and Block A's post-mortem named that as
   the likely cause: a long-only breakout is a trend-following structure that cannot work
   when the trend is absent or against it. **Every arm here is two-sided.**
3. **It only ever looked at the NY open.** Asia and London have never been tested.

This is still a price pattern on a liquid future, and that class is **0 for 10** in this
project. The prior is poor and is not being dressed up.

## The three arms

| arm | reference range | traded in | mso |
|---|---|---|---|
| **A2L** | Asia 18:00-03:00 ET | London 03:00-09:30 | ref -930..-390, trade -390..0 |
| **L2N** | London 03:00-09:30 ET | NY 09:30-16:00 | ref -390..0, trade 0..390 |
| **NYOR** | NY first 60 min 09:30-10:30 | rest of NY 10:30-16:00 | ref 0..60, trade 60..390 |

Windows are minutes-since-open, so they are DST-correct by construction. The post-close
hour is excluded: the terrain table put a round trip at 16.7% of its median range, which is
not tradeable, and that exclusion is made now rather than after seeing a result.

## Rules, fixed

- **Entry**: first touch of `reference_high + 1 tick` goes long, or `reference_low - 1 tick`
  goes short. **Two-sided.** First break only; one trade per session per arm.
- **Stop**: the opposite side of the reference range. Filled at the **worse** of the stop
  and the bar open, so a gap through it is not filled at a price nobody offered.
- **Exit**: end of the trade window, or the stop, whichever comes first.
- **Minimum range**: skip the session if the reference range is under **4 ticks (1.00
  point)**. Principled, not tuned: the stop distance has to at least cover the 0.5-point
  round trip, and a range under 1 point cannot.
- **Size**: exactly **1 contract**, priced as MES at $5/point. No sizing rule is introduced,
  because size scales edge and noise identically and cannot move any criterion below except
  the dollar columns.
- **Cost**: $3.70 per round trip — one tick of spread plus half a tick of slippage per side,
  plus $1.20 commission. Same model as the overnight arms.
- **Exclusions**: roll sessions and near-expiry sessions (`entries_blocked`), and dormant
  sessions (`thin_session`).

## Decision rule

An arm **passes** only if all four hold:

1. mean net **> $0 per trade**
2. rotation-null one-sided **p < 0.0167** (Bonferroni across the three arms; stationary
   bootstrap, mean block 10, 2,000 draws, mean removed under the null)
3. **Sharpe_all > 0.10**, computed over every session in the window with zero on sessions
   that did not trade — the level that reaches ~59% pass on a 50k account
4. **sign survives 2x spread.** If doubling the spread flips it, it was never a result

## Registered prediction

> All three arms come back **negative after cost**, between -$2 and -$8 per trade.
>
> NYOR is the least bad, because the terrain table puts a round trip at 3.4% of the NY
> range against 8.3% of Asia's.
>
> A2L is the worst: the Asian range is 6 points, so a stop at the opposite side is a
> 6-point risk taken to chase a London range of 8.75, and the cost is 8.3% of it.
>
> Mechanism, stated so the prediction is falsifiable rather than vague: **short-horizon ES
> returns are mildly mean-reverting, not trending**, so a breakout should be slightly
> negative once it pays the spread. If instead the arms come back positive, that
> mean-reversion premise is wrong and I want that on the record.
>
> Probability I put on any arm passing all four criteria: **roughly 15%.**

Recorded next to Block A, where my prediction was wrong on sign and significance, and the
overnight arms, where the gross figure landed inside my registered range.

## What I will not do

- Not add a fourth arm after seeing these three
- Not tune the buffer, the minimum range, the stop, or the exit
- Not switch to one-sided after seeing that one side did better
- Not re-run a failed arm with a fix

## Held back

**2017-2023 remains undownloaded and must stay that way.** If an arm passes, the
confirmation set is specified now: same code, same parameters, 2017-2023, single run.
