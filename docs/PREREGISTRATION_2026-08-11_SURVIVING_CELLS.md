# Pre-registration: the four cells that survived bounce dilution

Written **2026-08-11, after the 30-minute return-structure diagnostic across four
instruments and before this test was run**. Nothing below may be revised after seeing a
result.

## What motivated this, disclosed

Run 33 established that ES's 5-minute mean reversion is bid-ask bounce. The 30-minute
diagnostic confirms it decisively: at 30-minute bars, where the artifact is diluted roughly
sixfold relative to the bar's move, **ES ALL has `ac(1) = 0.0000` and VR(2) = 0.999 at
z = -0.1.** A perfect random walk. The z = -7.8 at 5 minutes was the spread.

The same diagnostic ran on GC, SI and HG. Across 4 instruments x 4 windows x 5 horizons,
almost everything is a random walk. **Four cells are not**, and this tests those four.

**Selection is disclosed:** these cells were chosen after seeing the diagnostic. The
effective number of independent looks is roughly 16 (instrument x window; the five horizons
within a window are nested and highly correlated, not independent). At 16 looks, 0.7 cells
with |z| > 2 are expected by chance.

## The four cells

**ES LONDON, mean-reverting.** The strongest survivor and the only one I would have bet on
in advance. `ac(1) = -0.0355` against a Bartlett 2se of 0.0128, so 5.5 standard errors, and
the variance ratios are coherently below 1 at **every** horizon: 0.962, 0.922, 0.901, 0.904,
0.859 at z = -3.3, -3.6, -2.9, -2.0, -2.1. A single anomalous cell is noise; a monotone
profile across five nested horizons is a property.

**Critically, this one is not bounce.** Roll's arithmetic predicts a bounce contribution to
`ac(1)` of `-(s^2/4)/var`. With ES's 0.25 pt tick at roughly 1500 index (1.67 bp) and a
London 30-minute sigma of 14.35 bp, that is **-0.0034**. The measured -0.0355 is **ten times
larger** than bounce can account for.

**SI ASIA and SI LONDON, mean-reverting.** VR at z = -2.1 to -2.3 across four horizons each.

**GC NY and SI NY, trending.** The only variance ratios above 1 anywhere in the table:
GC 1.078 and 1.115 at z = +2.2 and +2.3; SI 1.093 and 1.117 at z = +2.2 and +2.0, both at
q = 8 and 16. Two instruments agreeing is weaker evidence than it looks, because gold and
silver are heavily correlated and this is closer to one observation than two.

## The test

The same direct, assumption-free measurement used in run 33. At the close of bar `t`,
having observed the return over the preceding `q` bars, take a position and hold `q` bars.
Non-overlapping, no stop, no filter, both directions.

- **Reverting cells** take the opposite side. **Trending cells** take the same side.
- Restricted to the window named in the cell, on 30-minute bars.
- `q` in **{1, 2, 4, 8}** bars, which is 30 minutes to 4 hours.

**The 1-bar-delay column is a headline, not a footnote.** Run 33 established that delaying
execution one bar is the discriminator between a real forecast and a microstructure
artifact, and it destroyed 76% of the apparent 5-minute edge. Every cell here reports its
delayed number next to its immediate one, and **a cell whose edge does not survive a one-bar
delay is reported as an artifact regardless of its t-statistic.**

## Costs, measured

Both bars are reported, per the standing scope: raw first, then against the measured round
turn for that instrument.

| | micro | tick $ | measured spread | round turn |
|---|---|---:|---:|---:|
| ES | MES | 1.25 | 1 tick | **$3.70** |
| GC | MGC | 1.00 | 2 ticks | **$5.20** |
| SI | SIL | 5.00 | 3 ticks | **$31.20** |

**Silver's round turn is $31.20.** At 3 ticks on a $5.00 tick, SIL is the most expensive
instrument in this project by a factor of six. The two SI cells are being run for
completeness and because the measurement is cheap, but a silver intraday strategy would need
an edge larger than any structure measured anywhere in this project to clear its own spread.
I am stating that before the run, not after.

## Decision rule

Cells x horizons is 6 x 4 = 24, so Bonferroni gives nominal **p < 0.0021**. A cell passes as
a **measurement** on:

1. mean **> $0** raw, in the predicted direction
2. **p < 0.0021**
3. **at least 60% of the edge survives a one-bar execution delay**

It passes as a **strategy** only with:

4. mean **> the instrument's measured round turn**

The concentration criterion is **dropped**, and the reason is recorded in
`RESULTS_REVERSION_HORIZON_2026-08-11.md`: at large trade counts, deleting the top 5% of a
fat-tailed near-zero-mean distribution is negative by construction, so the criterion stops
measuring concentration and starts measuring kurtosis. It did no work in run 33 and I am not
going to keep quoting a number that cannot discriminate. Criterion 3 replaces it and is a
sharper test of the same worry.

## Registered prediction

> **No cell passes as a strategy. I expect one or two to pass as measurements.**
>
> **ES LONDON is the one I expect to survive the delay test**, because its `ac(1)` is ten
> times larger than bounce can explain, which is a quantitative argument rather than a
> hopeful one. But the diagnostic already put its 1-bar ceiling at **$0.30 against a $3.70
> round turn**, and even scaling as `sqrt(q)` to q = 8 that reaches only about $0.85. I
> expect a real, statistically clean, economically useless edge. **That is the single most
> likely outcome of this entire run** and it is worth naming in advance because it is the
> shape of an honest negative: the signal exists and does not pay.
>
> **The SI cells fail on cost by an order of magnitude** even if their edge is real. $31.20.
>
> **GC NY and SI NY trending are the ones I expect to evaporate.** They are the only
> positive VRs in an 80-cell table where roughly 4 spurious |z| > 2 are expected, they sit
> at adjacent nested horizons of two correlated instruments, and momentum has failed in
> every one of the 43 directional cells already closed.
>
> Probability any cell passes as a strategy: **under 5%**, the lowest I have registered.
> Probability ES LONDON passes as a measurement: **about 60%**.

Tenth prediction. The running pattern across nine is correct on outcome, wrong on mechanism.
This time the mechanism claim is explicit and falsifiable: ES LONDON survives the delay,
the GC/SI NY momentum cells do not.

## What I will not do

- Not add a fifth cell or a fifth horizon after seeing these
- Not rescue a cell that fails the delay test by reinterpreting it
- Not report a measurement pass as a tradeable strategy
- Cumulative count becomes seventy-five; 2017-2023 remains the confirmation set
