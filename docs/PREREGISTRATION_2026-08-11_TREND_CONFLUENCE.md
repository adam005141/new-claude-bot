# Pre-registration: the 4-hour trend filter, corrected, and four confluence structures

Written **2026-08-11, before any of these five was run**. Nothing below may be revised after
seeing a result.

## Position

Thirty-eight cells closed, zero passes. This adds **five**, taking the count to
**forty-three**. Bonferroni gives nominal **p < 0.010**. Costs remain excluded per the
standing scope change: results are raw entry-to-exit, `(exit - entry) x $5 x 1 contract`,
with a cost-inclusive column shown alongside.

Expected take rate is stated for every arm and checked before the result is read. That check
caught three of five arms in the previous run and is now standing procedure.

## Disclosure: TREND4H is contaminated and I am running it anyway

The previous run's TREND4H indexed its 48-bar lookback inside the NY window. The L2N break
fires at median bar 2, and 96.7% of breaks occur before bar 48, so the lookback ran off the
front of the array and the arm skipped 97% of signals. The 63 trades that survived returned
**+$9.70 a trade at p < 0.001**. Those 63 are the sessions where the London range held for
four hours and then broke.

**I have seen that number. It cannot be unseen.** Those 63 sessions are a subset of the
sessions TREND4H-FIX will trade. So the fix carries a known positive contaminant.

The decontamination is pre-specified here, before the run: **TREND4H-FIX is reported twice,
once on all qualifying sessions and once with those 63 late-break sessions removed.** The
second number is the one that decides the arm. If they disagree, the arm fails, because a
result that depends on trades I already looked at is not evidence.

## Arm 1: TREND4H-FIX

The L2N breakout, taken only when the trade direction agrees with the sign of
`close[i] - close[i-48]` on 5-minute bars, where **`i` indexes the full session series
sorted by `mso`, not the NY subset**. At `mso` 0 the 48-bar lookback reaches back to
`mso -240`, which is inside the London window, so the lookback is available for every break.

*Expected take rate: 45-60%.* If it is not near half, the filter is broken again.

## Arms 2 to 5: confluence

The request is to stack conditions. The arithmetic of stacking is worth stating first,
because it governs what these arms can possibly show.

**Confluence multiplies conditions and divides sample.** If two conditions are each
uninformative about the forward return, their conjunction is also uninformative, and the
only thing stacking has achieved is to raise the standard error. A confluence helps only if
the conditions **interact**: if the forward edge given both is larger than either alone
implies. Interaction is a strictly stronger claim than a main effect, and both of these main
effects have been measured at approximately zero (FVG +$0.88 at t 1.40, SWEEP -$0.11 at
t -0.11). For a confluence to pass, the interaction has to carry the entire result.

That is not impossible. It is what "confluence" means as a claim, and it has never been
measured here. But the prior is low and the sample loss is certain.

**iFVG, defined mechanically.** A bearish gap forms at bar `i` when `high[i] < low[i-2]`,
leaving the zone `[high[i], low[i-2]]`. The gap is **inverted** when a later bar closes
**above** the top of that zone, `low[i-2]`. Once inverted the zone is treated as support:
enter long on the first subsequent trade back down into the zone, stop one tick below
`high[i]`. Bullish gaps invert on a close below the zone bottom and are mirrored.

| arm | definition | expected take rate |
|---|---|---|
| **TREND4H-FVG** | the FVG retracement entry, taken only when the gap direction agrees with the same corrected 4-hour trend sign | 45-55% of FVG signals |
| **IFVG** | the inversion entry alone. Run to establish the base rate, because a combination is uninterpretable without the base rates of its parts | 35-60% of sessions |
| **SWEEP-FVG** | sweep the prior session extreme and reclaim it, then require a gap in the reclaim direction to form within 12 bars of the reclaim; enter on the retracement into that gap rather than at the reclaim close | 25-45% of sweep-reclaim events |
| **SWEEP-IFVG** | sweep and reclaim, then an inversion in the reclaim direction later in the same session; enter on the inversion retest | 15-35% of sweep-reclaim events |

One trade per session per arm, first qualifying sequence only, flat at the NY close.

## Exits are carried verbatim, and this is a stated limitation

Entry at the zone or reclaim, stop one tick beyond the structure, exit at the session close.
That is the previous registration's exit and it is **not** being changed, because changing it
after seeing that it produced 13% and 21% win rates would be tuning.

But it is a real limitation and I am not going to pretend otherwise. A tight stop against a
hold-to-close exit produces a lottery payoff, and the concentration criterion is close to
unpassable for any zone-entry arm under it. **Testing five entries against one exit tells you
about the exit as much as the entries.**

So one **diagnostic**, declared now: every arm is additionally reported under a fixed
alternative exit, **no stop at all, flat at the session close**, which is the pure
directional test of the signal. This separates "the signal has no edge" from "the exit
destroys the edge."

**The diagnostic cannot produce a PASS.** It is attribution of failure only. If a no-stop
variant looks materially better, that is a hypothesis for the untouched 2017-2023 set, and
it would carry its own trial count. It is not a result.

## Decision rule

An arm passes if all three hold:

1. mean **> $0 per trade**, raw
2. rotation-null one-sided **p < 0.010**
3. **|t| > 2.0 after removing the best 5% of trades**, and positive

Plus a floor: **fewer than 100 trades is NOT SCORED**, not failed. SILVER's 202 was already
thin and anything under 100 cannot distinguish a real effect from nothing.

For TREND4H-FIX, criteria are evaluated on the decontaminated series.

## Registered prediction

> **None of the five passes.** Base rate is zero across thirty-eight.
>
> **TREND4H-FIX comes back near zero, between -$1.50 and +$1.50 a trade with |t| < 1.5.**
> The L2N breakout's gross was measured at +/-$0.01 on ~1,900 trades, which is as close to
> "no signal" as a measurement gets. Splitting a null by trend direction produces two nulls.
> I expect the contaminated and decontaminated numbers to differ by **less than $1**, because
> 63 sessions out of an expected ~900 taken cannot move a mean far, and I expect the
> late-break subpopulation's +$9.70 to be sampling noise rather than structure.
>
> **The confluence arms lose sample faster than they gain selectivity.** I expect
> SWEEP-IFVG to land near or below the 100-trade floor and be NOT SCORED, and I would rather
> report that than score 60 trades.
>
> **IFVG is the arm I am least able to predict**, because it has no base rate here and it is
> the one ICT structure whose logic is not purely a level touch: it requires the level to
> have first failed, which is a genuine state change rather than a line on a chart. If any
> confluence works, I expect it to be the one containing IFVG.
>
> **The no-stop diagnostic will improve every zone-entry arm's t-statistic and will not turn
> any of them positive-and-significant.** The stop is destroying win rate, not edge. My
> reasoning: FVG's mean is already positive under the tight stop; the problem is
> concentration, not direction, and removing the stop widens the left tail as much as it
> preserves the right.
>
> Probability at least one arm passes all three: **roughly 10%**, lower than the 15% I
> registered last time, because stacking conditions with measured-null main effects is the
> weakest prior I have run so far.

Eighth prediction recorded. Prior seven: Block A (wrong on sign and significance), overnight
arms (gross inside range), cross-session (correct throughout), entry timing (right on
conclusion, wrong on fill rate and filled-trade direction), entry variants (wrong that
filters would only trade less), reversion (wrong on gross sign and take rate), ICT/quant
(correct that none passed, wrong on SWEEP's mechanism and on VOLLOW's direction).

## What I will not do

- Not tune the 12-bar retracement window, the 6-bar reclaim, the 48-bar lookback, the
  one-tick stop offset, or the session-close exit
- Not add a sixth arm after seeing these five
- Not promote the no-stop diagnostic to a decision cell
- Not report a pass as a result: cumulative count is forty-three and 2017-2023 remains the
  confirmation set
