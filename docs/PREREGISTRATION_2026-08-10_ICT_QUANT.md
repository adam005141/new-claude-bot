# Pre-registration: ICT structures and quant filters

Written **2026-08-10, before any of these five was run**. Nothing below may be revised after
seeing a result.

## Position

Thirty-three cells closed. This adds **five**, taking the count to thirty-eight. Bonferroni
gives nominal **p < 0.010**. Costs are excluded per the standing scope change — results are
raw entry-to-exit, `(exit - entry) x $5 x 1 contract` — with a cost-inclusive column shown
alongside so the gap stays visible.

**Expected take rate is stated for every arm and checked before the result is read.** Two of
the last three filters were near-degenerate against their own signal (VOLUME compared a
London break bar to an Asian median; the reversion HTF filter required a quiet 60 minutes at
the moment of a 2-sigma extension). Both would have been caught by this check.

## Three ICT structures, defined mechanically

ICT concepts are testable only once stated as arithmetic. These are the three that convert
cleanly; anything requiring discretionary chart reading is not testable and is excluded.

**FVG — fair value gap.** On 5-minute NY bars, a bullish imbalance forms at bar `i` when
`low[i] > high[i-2]`, leaving an untraded zone `[high[i-2], low[i]]`. Enter long if price
retraces into the zone within **12 bars**. Entry at the zone top, stop one tick below the
zone bottom, exit at session end. Bearish is the mirror: `high[i] < low[i-2]`.
*Expected take rate: 30-50% of sessions.*

**SWEEP — liquidity sweep and reclaim.** Price trades below the prior session's low, then
closes back above it within **6 bars**. Enter long at that close, stop at the sweep extreme,
exit at session end. Short is the mirror on the prior session's high.
*Expected take rate: 15-25% of sessions.*

**SILVER — the 10:00-11:00 ET window.** The best structure found so far, L2N/STRONG,
restricted to signals occurring inside that hour.
*Expected take rate: 10-20% of L2N/STRONG's signals.*

## Two quant filters

**TREND4H.** The L2N breakout, taken only when the direction agrees with the 4-hour trend:
the sign of `close[i] - close[i-48]` on 5-minute bars. This is a genuinely new bias
definition — the two already tested were the prior session's midpoint and the 60-minute move.
*Expected take rate: 45-60%.*

**VOLLOW.** The L2N breakout, taken only on sessions whose reference-window range falls in
the **lowest tercile** of the trailing 60 sessions. Causal, uses completed sessions only.
*Expected take rate: ~33%.*

## Decision rule

An arm passes if all three hold:

1. mean **> $0 per trade**, raw
2. rotation-null one-sided **p < 0.010**
3. **|t| would still exceed 2.0 after removing the best 5% of trades** — a concentration
   check, because a single good month is not an edge

Skipped signals are recorded with zero and their counterfactuals computed, as before.

## Registered prediction

> **None of the five passes.** The base rate across thirty-three cells is zero, and the best
> raw result anywhere is 0.78 points a trade at t = 2.32, which does not survive its own
> correction.
>
> **FVG is the most likely of the ICT three to look positive**, because a retracement entry
> into an imbalance is mechanically a mean-reversion trade at a level, and reversion showed
> a 56-60% win rate throughout — but win rate has been consistently uninformative here, and
> gross was negative every time.
>
> **SWEEP is the one I would least like to bet against.** A stop run followed by a reclaim is
> the single ICT idea with a plausible microstructure mechanism: forced liquidation creates a
> temporary price dislocation that a non-forced participant can absorb. If anything in this
> set works, it is this.
>
> **SILVER will fail on sample size.** Restricting to one hour cuts ~914 trades to roughly
> 100-150, and at that count the standard error triples.
>
> **TREND4H and VOLLOW behave like every prior filter**: they cut trade count and move the
> mean toward zero without crossing it.
>
> Probability at least one arm passes all three: **roughly 15%.**

Seventh prediction recorded. Prior six: Block A (wrong on sign and significance), overnight
arms (gross inside range), cross-session (correct throughout), entry timing (right on
conclusion, wrong on fill rate and filled-trade direction), entry variants (wrong that
filters would only trade less), reversion (wrong on gross sign and take rate).

## What I will not do

- Not tune the 12-bar FVG window, the 6-bar reclaim, the tercile, or the 48-bar lookback
- Not add a sixth arm after seeing these five
- Not report a pass as a result: cumulative count is thirty-eight and 2017-2023 remains the
  confirmation set
