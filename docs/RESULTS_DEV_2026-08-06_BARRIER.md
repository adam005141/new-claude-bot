# Barrier Screen: the path result, and what it settles

**Run date:** 2026-08-06
**Tool:** `tools/barrier_screen.py` (corrected version, see the calibration section)
**Data:** development split, 28,492 tradable bars over 387 sessions, ES prices, MES economics
**Ledger:** run 14, registered before the tool was written
**Trial count: unchanged at 3.** No strategy, no entry rule, no sizing, no P&L.

---

## What was measured

Expectancy in R under fixed barriers, gross of cost, for a trade opened at every single
bar and split into the part that is a real path property and the part that is just the
market going up:

```
path  = (excess_long + excess_short) / 2      moves both sides together, real
drift = (excess_long - excess_short) / 2      mirrors, and is the bull market
```

A driftless random walk scores zero at every geometry, so anything non-zero is real. This
is the statistic that decides the **sign** of an edge, which no choice of stop, target,
reward-to-risk, instrument or position size can change.

---

## Result: nothing, and not marginally

| | value |
|---|---|
| Cells screened | 270 (18 features x 3 symmetric geometries x 5 bins) |
| Best positive PATH | **+0.0047R**, z = **+0.37** |
| Cells clearing the round trip | **0 of 270** |
| Unconditional PATH, all geometries | -0.0057R to -0.0006R, i.e. zero |

The cost bar, for context:

| geometry | stop | cost in R | best PATH as a fraction |
|---|---:|---:|---:|
| 1.0x ATR | 2.31 pts | 0.429R | **1.1%** |
| 1.5x ATR | 3.46 pts | 0.286R | **1.6%** |
| 3.0x ATR | 6.93 pts | 0.143R | **3.3%** |

**The largest conditional path effect in the entire feature set is between 30 and 91 times
too small to pay its own round trip.** This is not a near miss that better execution or a
cheaper instrument could close. It is three orders of magnitude of margin in the wrong
direction, on the one quantity that determines whether anything can work.

---

## About that family-wise p of 0.000

It is real and it is useless, and reading it as a success would be a mistake.

The observed best **|z|** is 0.74 against a null median of 0.30, which is why the p is
0.000. But the best **positive** z is only +0.37. The significant cell is therefore a
**negative** one: a bin where both longs and shorts lose more than average.

That is a genuine property, and it is worth exactly nothing. A negative symmetric path
means directional trades of either sign do badly on those bars. It is a "do not trade
here" signal, not an edge. Avoiding bad bars can only reduce a loss toward zero; it cannot
create a gain, because there is no positive cell to move the capital into. The best
positive cell is 1.6% of the cost hurdle.

---

## Calibration: two biases were caught, and both invented signal

The first version of this tool would have reported a discovery. It is worth recording
exactly what it got wrong, because both errors are the kind that survive code review and
only show up when you test against an answer you already know.

**1. A binary touch rate manufactured significance out of censoring.**
Measuring "did the target come first" discards unresolved paths. Barriers are ATR-scaled,
so a high-ATR bar gets wider barriers, resolves less often within 24 bars, and its
survivors are drawn disproportionately from whichever barrier sits nearer. The bias
travels **with the feature**, so subtracting the unconditional baseline does not remove
it, and rotation cannot absorb it either, because the null hands a high-ATR bin outcomes
borrowed from ordinary bars.

On a synthetic random walk with a true edge of exactly zero, that version returned a
**family-wise p of 0.000**. Replaced by marking unresolved trades to market exactly as the
engine's time stop does, which removes the censoring rather than correcting for it. The
same walk now returns p = 0.240.

**2. A long-only measurement could not tell a signal from a bull market.**
The development split is 2023-08 to 2025-01, a strong equity bull run. On a synthetic
uptrend, a long-only read reports **+0.1013R** as a discovery while the correct PATH is
**-0.0089R**. Both sides are now measured and decomposed.

**2b.** That decomposition is only exact when stop equals target. With a payoff of 2, a
winning long pays +2R while a losing short loses 1R, so drift does not cancel and leaks
into PATH, measured at **+0.05R** on a pure uptrend, the same order as anything worth
finding. Symmetric geometries now carry the headline; asymmetric ones are shown and
excluded.

The uncorrected run reported family-wise p = 0.120 with its top cells on
`minutes_since_open` and `bar_of_session`, which are also the same quantity inside RTH and
were therefore one finding, not two. **None of that output should be read.**

---

## The one thing in this output that points somewhere

**Intraday drift is zero.** Across every geometry the unconditional drift term sits
between -0.0061R and +0.0006R, over 387 sessions in which the index rose roughly a third.

If intraday drift is zero and the index rose substantially, the returns happened while the
market was closed. That is the documented overnight-versus-intraday decomposition, and
this data is consistent with it, though the overnight leg has not been measured here and
should not be asserted until it is.

It is also the one lead this project has not exhausted. Two things have to be said about
it plainly:

- It is **not intraday**, which is the mandate, and holding overnight conflicts with a
  15:50 flat rule.
- Topstep's rules on overnight positions in the Combine are one of the six unresolved
  semantics in `config/topstep_50k_combine.v1.yaml` and would need verifying before any
  of it mattered.

---

## What this settles

Three strategies have now failed, in both polarities:

| | n | expectancy |
|---|---:|---:|
| Leg B, momentum continuation | 264 | -0.127R |
| Leg A, mean reversion to VWAP | 177 | -0.266R |
| Leg C, mean reversion to prior close | 236 | -0.432R |

Two mechanism-free screens have now found nothing:

| | what it measured | result |
|---|---|---|
| `forward_returns.py` | conditional mean forward move | family-wise p 0.375 to 0.965 |
| `barrier_screen.py` | conditional path expectancy in R | best positive 1.6% of the cost bar |

The second matters more than the first, because the mean is not what decides a sign and
the path is. `gap_vs_on_range` had the largest mean effect in the project, at 2.41x the
round trip, and Leg C lost 0.432R trading it. The path screen says why, and it says the
same thing about every other feature available.

**On this data, at this resolution, with these features, there is nothing to find.** Not
"we could not detect it": the quantity that would have to be positive is measured at
roughly 1% of the size it would need to be.

Validation and lockbox remain **UNTOUCHED**, and there is still nothing worth spending
them on.
