# Pre-registration: the gold/silver spread, actually traded

Written **2026-08-13, before any GC/SI trade was simulated**. Nothing below may be revised
after seeing a result.

## Why

The metals diagnostic found GC/SI carries autocorrelation at lags 2, 3 and 5 outside the
Bartlett band, with variance ratios deepening monotonically (0.970/-2.5, 0.931/-3.2,
0.888/-3.5). It is the first spread in this project with structure past lag 1, which is
where Roll's bounce model stops. The two controls behaved as bounce predicts: SI/HG lag-1
only, GC/HG nothing anywhere.

**No trade has been simulated. The $3.30 per-trade figure in the ledger entry is a PRIOR
ESTIMATE derived algebraically from the variance ratio, not a measurement.** This test
replaces it with a measurement.

## Structure

Fade the preceding `q`-bar move in `log(GC) - log(SI)`, hold `q` bars, non-overlapping, both
directions, no stop, no filter. `q` in **{2, 4, 8}** on 30-minute bars, so 1, 2 and 4 hours.
Windows **ALL** and **NY**. Six cells, Bonferroni **p < 0.0083**.

One MGC against the dollar-neutral quantity of SIL, ratio computed causally from the prior
session's closes. Take rate is 100% by construction; there is no filter, so the degeneracy
failure mode cannot occur.

| | micro | point value | measured spread | round turn |
|---|---|---:|---:|---:|
| GC | MGC (10 oz) | $10 | 2 ticks | **$5.20** |
| SI | SIL (1,000 oz) | $1,000 | 3 ticks | **$31.20** |

Pair round turn is `5.20 + ratio x 31.20`, roughly **$25** at the median ratio.

## What must be reported, because a mean hides it

The decision rule is not the whole deliverable. Every cell reports:

- **mean win and mean loss separately**, and their ratio
- **win rate**, alongside them, never alone
- a full trade ledger with entry and exit prices for the best cell

VWAP reversion won 59.8% of the time and lost money because its losses were twice the size
of its wins. Win rate has been uninformative in every run of this project. Reporting the
win/loss size asymmetry is how that gets caught rather than repeated.

## Decision rule

1. mean **> $0** raw
2. **p < 0.0083**
3. **at least 60% of the edge survives one bar of delayed execution**
4. mean **> the pair round turn** to pass as a strategy

## Registered prediction

> **No cell passes as a strategy.** The algebraic estimate was $3.30 against a ~$25 round
> turn. I expect the measured mean to land between **$1 and $6** and to fail criterion 4 by
> **4x to 20x**.
>
> **I expect it to pass the delay test**, unlike ES/NQ, because the structure sits at lags 2
> and 3 rather than lag 1. If it fails the delay test, the diagnostic's lag profile is
> telling me something I have mismeasured.
>
> **On wins versus losses: I expect them to be close to symmetric in size**, within 20% of
> each other, with the edge coming from frequency rather than magnitude. This is a
> fixed-horizon trade with no stop, so it has none of the machinery that made VWAP
> reversion's losses twice its wins. If losses come back much larger than wins, that is a
> real finding and not something I predicted.
>
> Probability any cell passes as a strategy: **under 5%.**

Fourteenth prediction.

## What I will not do

- Not tune q, the windows, or the hedge ratio
- Not report a mean without the win/loss decomposition beside it
- Cumulative count becomes one hundred and eleven; 2017-2023 remains the confirmation set
