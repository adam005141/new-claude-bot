# Pre-registration: does 5-minute entry timing rescue a structure with no signal?

Written **2026-08-10, before any 5-minute ES data was run**. The 5-minute set has been
imported and cross-validated against the 30-minute download, and nothing else has been
computed from it. Nothing below may be revised after seeing a result.

## The question

The three cross-session breakouts returned -$3.69 to -$5.09 per trade, and the informative
part was the gross: **L2N -$0.01 and NYOR +$0.01, which is no signal at all**, and A2L
-$1.39, which is signal pointing the wrong way.

Separately, a foresight calculation showed **10-18 ticks of favourable excursion sitting
inside the 30-minute entry bar**, distributed almost evenly between winners and losers
(ratios 1.02x, 1.16x, 1.09x). That is not the winner/loser trap that usually kills entry
refinement.

But 30-minute bars cannot say whether that excursion occurred **before** the break, where
it is unreachable, or **after** it, where a resting limit could take it. That is the only
question this test exists to answer.

## Why it could matter

If a limit at the breakout level fills even 4-5 ticks better, that is $5.00-$6.25 against a
cost of $3.70. **A zero-signal structure could become positive** — not from prediction, but
from providing liquidity at the level instead of taking it.

The counter-evidence, from this project's own history: passive entry was measured once on
MES 2024-26 for a different structure and **adverse selection cost 5-8x the spread it
saved**. Limit orders fill when the market is coming at you and do not fill when it runs
away. That is the specific mechanism this test must survive.

## Design: three structures x three entry modes

Structures are unchanged from `PREREGISTRATION_2026-08-10_CROSS_SESSION.md` — same
reference windows, same two-sided break of range +/- 1 tick, same stop at the opposite
side, same exit at the end of the trade window, same 1.00-point minimum range, 1 contract.
**A2L is kept despite being the worst.** Dropping it now would be selection.

| mode | entry |
|---|---|
| **IMMEDIATE** | market at the level, on the 5-minute bar that breaks it. Control, and a validity check that 5-minute reproduces the 30-minute result |
| **PULLBACK** | resting limit AT the level. Fills only if price trades back **through** it within **6 five-minute bars** (30 minutes). No fill, no trade |
| **BIAS** | as PULLBACK, but the break direction must agree with the higher-timeframe bias |

**Six bars is one 30-minute bar**, the resolution of the setup that generated the signal.
Chosen for that reason and not tuned. It is not a range to be searched.

**The bias is parameter-free**, deliberately, because "which moving average" is where
overfitting lives: bias is UP when the breakout level sits above the midpoint of the prior
full session's range, DOWN when below. Longs only under UP, shorts only under DOWN,
otherwise no trade. Causal, uses only completed sessions.

## Costs, and how adverse selection is handled

| mode | entry | exit | round trip |
|---|---|---|---|
| IMMEDIATE | 1.0 tick (cross) | 1.0 tick | 0.50 pt + $1.20 |
| PULLBACK / BIAS | 0.5 tick (rest, no spread crossed) | 1.0 tick | 0.375 pt + $1.20 |

Adverse selection is **modelled, not assumed away**, by requiring price to trade **strictly
through** the level by a tick before the limit is considered filled. A touch that reverses
does not fill. That is the conservative convention: when you do fill, price is already
moving against you.

## THE LOAD-BEARING RULE

**A skipped trade is not free and is not dropped.** Every signal that produces no fill is
recorded, and its counterfactual outcome under IMMEDIATE entry is computed and reported.

All statistics are computed over **every session in the window**, with zero on sessions that
signalled but did not fill. That is the series an account actually experiences, and it is
what makes a missed winner cost exactly what it should.

Any version of this test that reports only the filled trades will look excellent and be
wrong. That is the entire reason this rule is written down before the run.

## Decision rule

Six non-control cells, so Bonferroni gives nominal **p < 0.0083**. A cell passes only if all
five hold:

1. mean net **> $0 per trade**
2. rotation-null one-sided **p < 0.0083**
3. **Sharpe_all > 0.10** over all sessions, zero on non-fills
4. sign survives **2x spread**
5. **beats its own IMMEDIATE control** on Sharpe_all. An entry rule that does not beat
   entering immediately has demonstrated nothing

## Registered prediction

> **IMMEDIATE reproduces the 30-minute result**, -$3 to -$5 per trade. If it does not, the
> two datasets disagree about something and the whole test is suspect.
>
> **PULLBACK fills on 50-75% of signals**, and the filled trades look BETTER per trade —
> perhaps -$1 to +$2 — because the fill is genuinely cheaper. **But over all sessions it
> lands at or below IMMEDIATE**, because the signals that never pull back are
> disproportionately the ones that ran, and those are the winners.
>
> **BIAS makes it worse.** Short-horizon ES is mildly mean-reverting, which the A2L gross
> already showed, and a prior-session-midpoint bias is momentum-flavoured.
>
> Probability any of the six cells passes all five criteria: **roughly 12%.**

Recorded next to Block A (prediction wrong on sign and significance), the overnight arms
(gross inside the registered range), and the cross-session arms (correct on range, ordering
and mechanism).

## What I will not do

- Not tune the 6-bar fill window, the pullback depth, or the bias definition
- Not report filled-only statistics as the headline
- Not drop A2L
- Not re-run a failed cell with a fix

## Held back

**2017-2023 stays undownloaded.** If a cell passes, the confirmation set is specified now:
same code, same parameters, 2017-2023, single run.
