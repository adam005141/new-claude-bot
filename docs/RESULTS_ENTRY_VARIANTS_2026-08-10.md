# Entry variants: filters remove losers, and still only reach zero

Run 2026-08-10, once, per `docs/PREREGISTRATION_2026-08-10_ENTRY_VARIANTS.md`.
ES 2009-2016, 2,015 sessions, 5-minute, 1 contract, all market entries, $3.70 round turn.

**All twelve cells FAIL all five criteria.**

## The structural finding

| arm | mode | take% | $/signal | skipped CF | Sharpe_all | p |
|---|---|---|---|---|---|---|
| A2L | IMMEDIATE | 100% | -5.06 | — | -0.173 | 1.000 |
| A2L | CONFIRM | 30% | -1.44 | **-6.88** | -0.081 | 1.000 |
| A2L | STRONG | 49% | -2.29 | **-5.45** | -0.111 | 1.000 |
| L2N | IMMEDIATE | 100% | -3.60 | — | -0.072 | 1.000 |
| L2N | CONFIRM | 38% | -0.67 | **-8.01** | -0.019 | 0.800 |
| L2N | **STRONG** | 47% | **+0.09** | **-7.02** | +0.003 | 0.477 |
| NYOR | IMMEDIATE | 100% | -3.58 | — | -0.084 | 1.000 |
| NYOR | CONFIRM | 38% | -1.96 | -5.51 | -0.066 | 1.000 |
| NYOR | STRONG | 45% | -0.48 | -5.61 | -0.016 | 0.812 |
| NYOR | VOLUME | 13% | -0.08 | -4.04 | -0.005 | 0.630 |

**The skipped counterfactuals are NEGATIVE**, and that is the whole story. Where the
pullback rule declined trades worth **+$9 to +$24**, these filters decline trades worth
**-$5 to -$8**. They remove losers.

That is mechanically consistent with everything measured so far: short-horizon ES is mildly
mean-reverting, so a break showing strength or continuation is less likely to revert. The
filters are selecting on the right thing.

**And it still only reaches zero.** The best cell, L2N/STRONG, is +$0.09 per signal at
p = 0.477. Adding back the cost, the trades it admits carry about **$3.90 of gross edge
against a $3.70 round trip.** Real selection, landing almost exactly on the cost line.

You can filter your way from -$5 to $0. You cannot filter your way to positive, because
there is no positive signal to concentrate — only cost to avoid.

## Two of my four filters were degenerate, which is my error

**VOLUME barely binds on A2L and L2N** (take rates 100% and 100%). It compares the break
bar's volume to the median of the *reference* window, and for A2L that reference is Asia,
where volume is a fraction of London's. Any London bar clears 1.5x an Asian median. The
comparison is between sessions with different volume levels, so it tests nothing. Only
NYOR, where reference and trade window share the NY session, is a real volume filter.

**DAYBIAS is degenerate on A2L** (take rate 100%). A break above the Asian high is almost
always above the 18:00 ET open that started that same Asian session, so the condition is
nearly implied by the signal.

So of twelve cells, roughly **nine were meaningful tests** and three tested essentially
nothing. That is a design error in the pre-registration, not a property of the market, and
it is recorded rather than quietly dropped. It does not change any verdict — the degenerate
cells simply reproduce their controls.

## Prediction scorecard

| registered | outcome |
|---|---|
| CONFIRM the only one with a real chance, -$1 to +$2/signal | **partly right**: -$0.67 to -$1.96, in range, but STRONG beat it |
| CONFIRM unlikely to clear Sharpe 0.10 | **correct** |
| STRONG and VOLUME reduce count, leave per-signal edge unchanged | **wrong**: both materially improved per-signal, by removing losers |
| DAYBIAS neutral to harmful | **correct** where it bound |
| ~10% any cell passes | none passed |

I was wrong that the filters would only trade less. They genuinely selected better trades.
The reason that still fails is not the one I predicted.

## What this closes

Thirty-one structures and cells are now closed on evidence. The multi-timeframe entry family
is tested in five forms — pullback, confirmation, strength, volume, two bias definitions —
and the shape of the answer is consistent across all of them:

- **entering later than the break** costs you the winners (pullback: skipped CF +$9 to +$24)
- **filtering the break** removes the losers (skipped CF -$5 to -$8) and reaches zero
- **nothing produces gross edge materially above the round trip**

The best subset found anywhere in this family carries $3.90 of gross against a $3.70 cost,
at p = 0.477. That is the ceiling, and it is indistinguishable from the cost line.
