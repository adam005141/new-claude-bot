# Pre-registration: passive execution on the one signal that could afford it

Written **2026-08-12, before any passive-fill simulation was run**. Nothing below may be
revised after seeing a result.

## Why this test and not a 97th signal

Ninety-six cells. Three structures survive delayed execution and are real. All three fail on
the same term:

| | edge | taking cost | shortfall |
|---|---:|---:|---:|
| **SI/ASIA/q4** | +$7.22 | $31.20 | **4.3x** |
| HEAVY/q2 | +$0.097 | $3.70 | 38x |
| HEAVY/q1 | +$0.069 | $3.70 | 54x |

The two ES cells are unreachable at any cost: commission alone is $1.20, so a free spread
still leaves HEAVY/q2 twelve times short. **Silver is the only case where execution could
close the gap**, because $7.22 against a commission-only floor of $1.20 is positive.

So this attacks cost rather than searching for more signal. **The project has never tested
that**, and the binding constraint has been the same in all ninety-six cells.

## Why run 27 does not already answer this

Run 27 tested limit entries and found adverse selection did double damage: filled trades got
worse (L2N -3.60 to -6.60) and the 11-13% that never filled would have earned +$9.06,
+$23.89 and +$13.93. Passive execution is already on this project's record as a failure.

**That measured momentum entries, and the logic inverts for reversion.** A breakout that
comes back to your limit is a breakout that is failing, so you are selected against by
construction. A reversion entry is the other side of that trade: you are supplying liquidity,
and being filled at the overshoot is precisely the event the signal calls mispriced.

Which effect dominates here is unmeasured. **I do not expect it to work** — resting a bid
under a falling market still fills you preferentially when the fall continues — but there is
a real mechanism on both sides rather than only on one.

## The structure

SI/ASIA/q4 exactly as it passed as a measurement in run 34: fade the preceding 4-bar
(2-hour) move in Asian-session silver on 30-minute bars, hold 4 bars, non-overlapping, both
directions, one SIL contract. **Not re-derived and not re-tuned.**

Only execution changes.

| arm | entry | exit | spread paid |
|---|---|---|---:|
| **TAKE** (control) | market | market | 6 ticks |
| **PASSIVE-ENTRY** | limit | market | 3 ticks |
| **PASSIVE-BOTH** | limit | limit, market if unfilled | 0 to 3 ticks |

The limit rests at `close(signal bar) + m ticks` in the favourable direction, `m` in
**{0, 1, 3}**. A fill requires the next bar to trade **strictly through** the limit, which is
the conservative convention run 27 used.

`m` is a queue-position stress test, not a tuned parameter. `m = 0` rests at the last trade;
`m = 3` rests a full spread away, so the market must come to you before filling. Larger `m`
buys a better entry and should suffer worse selection. **All three are reported. None is
selected after the fact.**

## Costs

Project convention, `2 x (spread in ticks) x tick value + commission`, silver micro at a
measured 3-tick spread and a $5.00 tick:

| arm | spread | commission | round turn |
|---|---:|---:|---:|
| TAKE | $30.00 | $1.20 | **$31.20** |
| PASSIVE-ENTRY | $15.00 | $1.20 | **$16.20** |
| PASSIVE-BOTH | $0.00 | $1.20 | **$1.20** |

**The $1.20 commission is carried from the MES model and is not a measured SIL number.** A
$2.50 round turn is reported alongside so the conclusion does not rest on it.

## The load-bearing rule

**Every unfilled signal is recorded with zero P&L and its TAKE-execution counterfactual is
computed.** Statistics run over all signals, not over fills. This is the rule that produced
run 27's real finding, and without it a passive test is pure survivorship.

## Expected fill rates, stated before the result is read

| m | expected fill rate |
|---:|---|
| 0 | 85-95% |
| 1 | 70-85% |
| 3 | 40-65% |

Asian silver moves about 23 bp per 30-minute bar and one tick is 2.4 bp, so price crosses
the last trade almost every bar. **A very high fill rate at `m = 0` is a symptom of the
model's optimism, not a finding**, and I am saying so in advance.

## The honesty constraint this test cannot escape

**Thirty-minute OHLC bars cannot model queue position.** I can test whether price traded
through a level; I cannot test whether I was at the front of the queue when it did. In a
market whose spread is three ticks wide, queue position is most of the answer.

**A pass here is therefore weaker evidence than a pass on a taking strategy**, and it would
be a hypothesis requiring tick data to confirm, not a tradeable result. A failure here is
strong evidence, because the simulation is optimistic in the direction of passing.

## Decision rule

Nine cells (3 arms x 3 values of `m`, with TAKE invariant to `m`), Bonferroni **p < 0.0056**.

1. mean **> $0** per signal, counting unfilled signals as zero
2. **p < 0.0056**
3. mean **> the arm's round turn**
4. **the unfilled counterfactual must not exceed the filled mean** — if the signals you miss
   were the good ones, the strategy is an artifact of selection

## Registered prediction

> **No arm passes. PASSIVE-BOTH at `m = 0` comes closest and fails on criterion 4.**
>
> I expect fill rates near the top of the stated ranges and **filled trades to be materially
> worse than the $7.22 taking figure** — my estimate is **+$2 to +$5 per filled trade**,
> because being filled means price kept moving against the fade for at least one more bar.
> At `m = 3` I expect filled trades to be **negative**, since a three-tick adverse extension
> before fill selects hard for continuation.
>
> Against a $1.20 floor, +$2 to +$5 would clear criterion 3. **Criterion 4 is what I expect
> to kill it**: the unfilled signals should carry the larger part of the edge, exactly as in
> run 27.
>
> Probability any arm passes all four: **about 15%.** Higher than my recent registrations
> because the cost side has never been attacked and the arithmetic genuinely permits it, not
> because the evidence is encouraging.

Thirteenth prediction. The last was six of seven, missing only the `sqrt(q)` scaling.

## What I will not do

- Not tune `m`, the signal, the horizon, or the session
- Not report filled-only statistics as the headline
- Not treat a pass as tradeable without tick-level confirmation
- Cumulative count becomes one hundred and five; 2017-2023 remains the confirmation set

## And the stopping rule

**If this fails, I will say the search is over rather than propose a 106th cell.** Every
family is closed with a mechanism, the three real signals are 2% to 23% of their own costs,
and the one case where execution could have closed the gap will have been tested. That is a
conclusion, not a plateau.
