# Pre-registration: intraday mean reversion, with a higher-timeframe filter

Written **2026-08-10, before any reversion code was run against the 5-minute ES set**.
Nothing below may be revised after seeing a result.

## Scope change, agreed and recorded

The funded-account feasibility bars are **dropped**: no Sharpe > 0.10 requirement, no
pass-rate simulation, no three-month timeline. The question is now simply whether the
strategy makes money.

**Transaction costs are NOT dropped.** A strategy that loses to the spread is not profitable
on any account. Costs stay at the measured $3.70 round turn, and the 2x-spread robustness
check stays.

Trades stay intraday and flat by the end of the NY session, which was the only restriction
retained.

## Why reversion, and why now

Every structure closed in this project has been momentum-shaped: opening-range breakout,
cross-session breakout, gap fade in the continuation direction, overnight drift, and five
entry variants on top of those. All failed.

Three measurements point the same way:

1. **A2L's gross was significantly NEGATIVE**, -$1.39 a trade at t = -2.13. Breaking the
   Asian range predicts reversal, not continuation.
2. **Filters that demand strength removed losers** (skipped counterfactuals -$5 to -$8),
   which is what you would see if weak breaks revert.
3. **Waiting for a pullback removed winners** (+$9 to +$24), the other face of the same
   thing: breaks that do not come back are the real moves, and most breaks come back.

The only reversion structure ever tested here is Leg A, VWAP band reversion, which returned
-0.266R on **177 trades** of MES 2024-26. That is underpowered, not disproven. This re-tests
it on **~2,000 sessions of ES across eight years**, roughly eleven times the sample.

**This re-opens a closed leg.** Disclosed, and it counts toward the multiple-testing burden,
which now stands at thirty-one closed cells.

## The structure

Session VWAP as the anchor, computed causally from the session open, on 5-minute ES bars.

    z = (close - session_vwap) / running_sd(close - session_vwap)

The running standard deviation uses only completed bars in the current session, with a
**12-bar minimum** before any signal is allowed. That 12-bar warm-up is carried over
verbatim from Leg A's registered config; it is not a new choice.

| | |
|---|---|
| trade window | NY only, mso 0 to 390 |
| entry | first bar with abs(z) >= **2.0** — short if z positive, long if z negative |
| target | z crosses 0, i.e. price returns to VWAP |
| stop | abs(z) >= **4.0** |
| time stop | end of the NY session, flat by mso 390 |
| trades | one per session, first signal only |
| size | 1 contract, priced as MES |
| cost | $3.70 round turn |

**k_entry = 2.0 is carried over verbatim from Leg A's registered config.** The stop at 4.0
is twice the entry, which is the one obvious symmetric choice. Neither is a range to search.

NY only, because the terrain table put a round trip at 3.4% of the median NY range against
5.7% for London and 8.3% for Asia. That choice was made before this test and for a stated
reason.

## The two arms

| arm | rule |
|---|---|
| **REV** | fade every qualifying extension |
| **REV-HTF** | fade only when the higher timeframe is not trending: the 60-minute price change at signal time (12 five-minute bars) is under **1.0** session sigma |

REV-HTF is the higher-timeframe filter you asked for, in its most defensible form: fade
extensions only when the larger picture is range-bound rather than directional. One
threshold, stated once.

## Decision rule

Two arms, so Bonferroni gives nominal **p < 0.025**. An arm passes if all three hold:

1. mean net **> $0 per trade** after the $3.70 round turn
2. rotation-null one-sided **p < 0.025**
3. **sign survives 2x spread**

The Sharpe and pass-rate criteria are deliberately absent, per the scope change above.

## The load-bearing rule carries over

REV-HTF is a filter, and a filter's risk is that it removes winners. Every signal it
declines is recorded with zero P&L and its counterfactual under unfiltered REV is computed
and reported. Statistics run over every session.

## Registered prediction

> **REV comes back slightly positive in GROSS and negative in NET.** The reversion is real —
> three independent measurements above imply it — but I expect gross of roughly **+$2 to
> +$5 a trade against a $3.70 cost**, which straddles break-even. The most likely single
> outcome is a small negative net that fails criterion 1.
>
> **REV-HTF trades perhaps 40-60% as often and improves gross per trade**, because trending
> sessions are exactly where fading loses. Whether that is enough to clear cost is the real
> question, and it is close.
>
> This is the **first structure in the project where I would not be surprised by a positive
> result.** Probability at least one arm passes all three: **roughly 30%**, materially higher
> than the 10-15% I have registered for recent tests, because for once the direction is
> indicated by measurement rather than hoped for.

Recorded next to five prior predictions: Block A (wrong on sign and significance), overnight
arms (gross inside the range), cross-session (correct throughout), entry timing (right on
conclusion, wrong on fill rate and on filled-trade direction), entry variants (wrong that
filters would only trade less).

## What I will not do

- Not tune k_entry, the stop, the warm-up, or the HTF threshold
- Not switch to London or Asia if NY fails
- Not report filtered-only statistics as the headline
- Not re-run a failed arm with a fix

## Held back

**2017-2023 remains undownloaded.** If an arm passes, the confirmation set is specified now:
same code, same parameters, 2017-2023, single run. Given this is a re-opened leg and the
cumulative trial count is thirty-three, that confirmation is not optional.
