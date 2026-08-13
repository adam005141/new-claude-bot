# Pre-registration: the ES/NQ spread, confirmatory

Written **2026-08-12, after the spread diagnostic and before any spread trade was
simulated**. Nothing below may be revised after seeing a result.

## Why this is confirmatory rather than exploratory

The relative-value family was the last one open. The diagnostic on the log spread
`log(NQ) - log(ES)`, 94,826 aligned 30-minute bars over 2,052 sessions, says it is already
closed:

| window | 2se | lag1 | lag2 | lag3 | lag4 | lag5 |
|---|---:|---:|---:|---:|---:|---:|
| ALL | 0.0066 | **-0.0516** | -0.0055 | 0.0099 | 0.0017 | 0.0032 |
| ASIA | 0.0107 | **-0.2116** | -0.0190 | -0.0053 | 0.0040 | -0.0117 |
| LONDON | 0.0128 | **-0.0774** | -0.0139 | 0.0006 | -0.0108 | -0.0120 |
| NY | 0.0130 | **-0.0215** | -0.0039 | 0.0098 | 0.0051 | 0.0004 |

**All of it is at lag 1.** Roll's bounce model predicts lag-1 and nothing else. Genuine
multi-bar reversion would appear at lags 2 through 4. Nothing does.

Two mechanisms produce exactly this, and both are present:

1. **Bounce adds when you difference.** The common index move cancels in the spread but each
   leg's bid-ask bounce is idiosyncratic, so bounce variance adds while signal variance
   subtracts. Spread sigma is 7.11 bp against 15.63 bp for ES and 17.13 bp for NQ, so the
   same absolute bounce sits on a much smaller base.
2. **Stale, non-synchronous closes.** NQ trades **229 contracts per 30-minute bar in Asia**
   against ES's 2,125, and 12,918 against 84,871 in New York. A bar's close is its last
   print, so in thin hours the two legs are priced minutes apart.

The tell is the scaling: the apparent signal is **10x stronger in Asia than in New York**
while Asian NQ volume is **56x lower**. It tracks illiquidity, not economics.

**So I am not going to run a search over the spread.** I am running one confirmatory test to
convert that inference into a measurement, exactly as was done for the ES 5-minute reversion
in run 33. Asserting a mechanism is cheaper than measuring it and worth less.

## The test

Fade the preceding `q`-bar move in the spread, hold `q` bars, non-overlapping, no stop, no
filter, both directions. `q` in **{1, 2, 4}**. Windows **ALL, ASIA, NY**.

Position is one MES against the dollar-neutral quantity of MNQ, with the ratio computed
causally from the prior session's closes. Fractional contracts are not tradeable and real
sizing would be 3:4 or 4:5; the fraction is used so the hedge is exact and the result is not
contaminated by rounding. **This makes the reported edge slightly optimistic**, which is the
right direction for a test designed to kill an idea.

Costs are the sum of two legs, at the project's standing convention:

| | round turn |
|---|---:|
| MES | $3.70 |
| MNQ | $2.20 |
| **pair (at the median 1.32 ratio)** | **$6.60** |

The adverse measured model ($4.95 and $4.70) gives $11.15 and is reported alongside.

## Decision rule

Nine cells, so Bonferroni gives nominal **p < 0.0056**. The **delay test is primary**:

1. mean **> $0** raw
2. **p < 0.0056**
3. **at least 60% of the edge survives one bar of delayed execution**
4. mean **> the pair round turn** to pass as a strategy

**Criterion 3 is the one this test exists to evaluate.** A cell that fails it is an artifact
regardless of its t-statistic, and no combination of the other three rescues it.

## Registered prediction

> **Every cell fails, and fails specifically on criterion 3.**
>
> **Undelayed, ASIA/q1 will look enormous** — an `ac(1)` of -0.2116 is the largest
> autocorrelation measured anywhere in this project, and the raw t-statistic should be in
> the tens. **Delayed by one bar it will be at or below zero.**
>
> Quantitatively: the delayed edge should keep **under 25%** of the undelayed edge in ASIA,
> and I expect the delayed ASIA number to be **negative**, because once the stale-pricing
> component is stepped over, what remains is a spread trade paying two round turns.
>
> **NY is the cleanest window and will show the least of everything** — its `ac(1)` of
> -0.0215 is a quarter of Asia's on 56x the volume.
>
> Probability any cell passes as a strategy: **under 2%.** This is the lowest I have
> registered, and it is low because the diagnostic already answered the question. If a cell
> does pass criterion 3, my model of this data is wrong in a way I would want to understand
> before trading it.

Eleventh prediction. The tenth was the first where the mechanism was right rather than only
the verdict; this one stakes the mechanism explicitly and numerically.

## What I will not do

- Not search other hedge ratios, windows, or horizons if these fail
- Not reinterpret a lag-1-only signal as tradeable under any execution assumption
- Cumulative count becomes eighty-four; 2017-2023 remains the confirmation set
