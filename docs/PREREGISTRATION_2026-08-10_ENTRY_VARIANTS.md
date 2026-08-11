# Pre-registration: four more entry rules, three structures

Written **2026-08-10, before any of these variants was run**. Nothing below may be revised
after seeing a result.

## Multiple-testing position, stated up front

Nineteen structures are already closed on evidence. This adds **twelve cells**, taking the
cumulative count to thirty-one. At a nominal 0.05, thirty-one trials give roughly an **80%
chance of at least one false positive**. That is why:

- every cell is Bonferroni-corrected at **0.05 / 12 = 0.0042**
- **any pass on 2009-2016 is EXPLORATORY, not a finding.** It becomes a finding only after a
  single confirming run on the untouched 2017-2023 set, which is not yet downloaded

## One variant is post-hoc and is labelled as such

**CONFIRM is derived from the previous result.** The entry-timing test showed that the
11-13% of breaks which never retraced would have earned +$9.06, +$23.89 and +$13.93. A rule
built to capture that, tested on the data that revealed it, is circular.

It is run anyway because it is the mechanically indicated next step, but it carries a
standing condition the other three do not: **a positive CONFIRM result on 2009-2016 means
nothing at all without 2017-2023.** The other three variants were specified without
reference to any 5-minute result.

## Structures

Unchanged: A2L, L2N, NYOR. Same reference windows, same two-sided break of range +/- 1 tick,
same stop at the opposite side, same exit at the end of the trade window, same 1.00-point
minimum, 1 contract, priced as MES. **Only the entry rule changes.**

## The four variants

Every one is a market entry, so the cost model is identical to IMMEDIATE: 1.0 tick per side
plus $1.20, i.e. $3.70 a round turn. No limit orders, so no adverse-selection modelling is
needed and none is claimed.

| variant | rule | origin |
|---|---|---|
| **CONFIRM** | enter at the OPEN of the bar after the break, only if the break bar CLOSED beyond the level | **post-hoc** |
| **STRONG** | enter at the level, only if the break bar closed in the top 25% of its own range (long) or bottom 25% (short) | a priori |
| **VOLUME** | enter at the level, only if the break bar's volume exceeds 1.5x the median 5-minute volume of that session's reference window | a priori |
| **DAYBIAS** | enter at the level, only if the break direction agrees with the sign of (level minus the session's 18:00 ET open) | a priori |

The thresholds — top quartile, 1.5x volume — are stated once and are **not a range to be
searched**. If a variant fails at its stated threshold it fails; it does not get retried at
another.

DAYBIAS is deliberately a different construct from the already-failed midpoint bias: it asks
whether price is up or down on the current session, not where it sits against yesterday.

## The load-bearing rule carries over

**A skipped signal is not free and is not dropped.** Every filtered-out signal is recorded
with zero P&L, and its counterfactual under IMMEDIATE entry is computed and reported. All
statistics run over **every session** in the window.

Three of these four variants are filters, and a filter's whole risk is that it removes
winners. Reporting only the trades a filter admits would make every one of them look good.

## Decision rule

A cell passes only if all five hold:

1. mean net **> $0 per signal** (not per filled trade)
2. rotation-null one-sided **p < 0.0042**
3. **Sharpe_all > 0.10** over all sessions
4. sign survives **2x spread**
5. **beats its own IMMEDIATE control** on Sharpe_all

## Registered prediction

> **CONFIRM is the only one with a real chance, and it is compromised by being post-hoc.**
> It should capture part of the +$9 to +$24 that non-retracing breaks earn, but it pays for
> the confirmation: entering at the next bar's open means the continuation has already
> partly happened. Net, I expect it near **-$1 to +$2 per signal** — better than IMMEDIATE's
> -$3.58 to -$5.06, possibly positive, and very unlikely to clear Sharpe 0.10.
>
> **STRONG and VOLUME reduce trade count and leave per-signal edge roughly unchanged.**
> Filters on a zero-signal structure filter noise. Expect Sharpe to move toward zero from
> below, mostly by trading less, exactly as BIAS did.
>
> **DAYBIAS behaves like the midpoint bias: neutral to harmful.** Short-horizon ES is mildly
> mean-reverting and this is another momentum-flavoured filter.
>
> Probability any of the twelve cells passes all five criteria: **roughly 10%.** Probability
> that a cell passing here also survives 2017-2023: lower still.

Recorded next to four prior predictions: Block A (wrong on sign and significance), overnight
arms (gross inside the registered range), cross-session (correct throughout), entry timing
(right on conclusion, wrong on fill rate and wrong that filled trades would improve — both
errors optimistic).

## What I will not do

- Not tune the quartile, the volume multiple, or the confirmation definition
- Not report filtered-only statistics as the headline
- Not treat a 2009-2016 pass as a result
- Not add a fifth variant after seeing these four
