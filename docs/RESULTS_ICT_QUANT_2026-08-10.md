# Results: ICT structures and quant filters, ES 5-minute, 2009-2016

Run 2026-08-10 against `docs/PREREGISTRATION_2026-08-10_ICT_QUANT.md`, committed at `c84065f`
before the code, and the code committed at `c0e83c2` before the run. 2,015 sessions.

**All five arms FAIL.** Two of them fail as tests of the thing they were supposed to test,
not as tests of the market. That distinction is the main finding here and it is recorded
below rather than buried.

## Take rates, checked before the P&L

This check was added to this registration specifically because two of the previous three
filters were near-degenerate against their own signal. It earned its place immediately.

| arm | expected | observed | verdict |
|---|---:|---:|---|
| FVG | 30-50% | **79%** | miss, and the signal itself fires in **99% of sessions** |
| SWEEP | 15-25% | **54%** | miss, 1,636 of 2,015 sessions sweep a prior extreme |
| SILVER | 10-20% | 10% | hit, bottom edge |
| TREND4H | 45-60% | **3%** | miss by an order of magnitude — implementation defect, see below |
| VOLLOW | ~33% | 36% | hit |

Two hits, three misses. Had I read the P&L first I would have read TREND4H's `p < 0.0001`
as a result.

## The numbers

Raw entry-to-exit, `(exit - entry) x $5 x 1 contract`. `net $` subtracts the measured $3.70
round turn and is shown only so the gap stays visible. `t-5%` is the t-statistic after
deleting the best 5% of trades.

| arm | signals | taken | take% | pts | $/trade | net $ | total $ | WR | t | t-5% | p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FVG | 2,004 | 1,581 | 79% | 0.176 | +0.88 | -2.82 | +1,389 | 13% | 1.40 | **-13.75** | 0.161 |
| SWEEP | 1,636 | 887 | 54% | -0.023 | -0.11 | -3.81 | -101 | 21% | -0.11 | -8.61 | 0.548 |
| SILVER | 1,928 | 202 | 10% | -0.343 | -1.71 | -5.41 | -346 | 45% | -0.52 | -2.78 | 0.935 |
| TREND4H | 1,928 | 63 | 3% | 1.940 | +9.70 | +6.00 | +611 | 65% | 2.38 | 1.74 | <0.001 |
| VOLLOW | 1,928 | 701 | 36% | -0.397 | -1.98 | -5.68 | -1,391 | 40% | -1.57 | -6.29 | 0.974 |

Decision rule was mean > $0 raw, rotation-null `p < 0.010` (Bonferroni across five), and
`|t| > 2.0` after trimming the best 5%. No arm clears all three.

## TREND4H is void, not failed

The arm reports +$9.70 a trade at `p < 0.0001` and it is worth nothing. The 4-hour lookback
was indexed inside the NY window: `j = i - 48` where `i` counts 5-minute bars from the NY
open. Measured directly — the L2N breakout fires at **median bar 2**, and **96.7% of
breakouts occur before bar 48**, so the lookback ran off the front of the array and the arm
skipped. What survived is not "breakouts aligned with the 4-hour trend." It is the 3% of
sessions where the London range held for four hours and then broke, which is a different
population with a different mechanism and n = 63.

It failed the concentration check anyway (`t-5%` 1.74), so the pre-registered rule voided it
without needing the diagnosis. But it would have failed for the wrong reason.

**The 4-hour trend filter has not been tested.** Testing it requires the lookback to reach
back through the London and Asian sessions, which the continuous series supports. That is a
new cell, it counts toward the trial burden, and it is contaminated: I have now seen that
the late-breakout subpopulation pays +$9.70. Any re-run has to be interpreted with that
known.

## FVG is not a filter

The imbalance condition `low[i] > high[i-2]` fires in **99% of sessions**. A structure that
selects almost everything is not selecting. Whatever ICT material claims about fair value
gaps marking significant levels, on 5-minute ES the pattern is ordinary bar noise: two bars
apart, a 3-bar range that does not overlap is the common case, not the exception.

The P&L profile is a lottery ticket. Win rate 13%, mean +$0.88, and trimming the best 5% of
trades takes t from +1.40 to **-13.75**. That is what a tight stop plus a hold-to-close exit
produces: the zone is a few ticks wide, so nearly everything stops out small, and the rare
survivor runs. Positive expectancy concentrated in 5% of trades is not something you can
trade through a $2,000 drawdown limit even if it were real, and at t 1.40 it is not.

## SWEEP was the one I said I would least like to bet against

It came in at **-$0.11 a trade, t -0.11, on 887 trades**. Not negative, not positive —
nothing. The registered argument was that forced liquidation creates a dislocation a
non-forced participant can absorb. If that mechanism operates on ES it does not survive to
the 5-minute close-back-above formulation, and 887 trades is enough sample to say the effect
is smaller than about $1.30 a trade at 2 standard errors.

The take rate also undercuts the premise: 81% of sessions trade through a prior session
extreme. There is no scarce liquidity pool being raided. It is just where price goes.

## SILVER: sample size, as predicted

202 trades, -$1.71, t -0.52. The registered prediction said it would fail on sample size and
it did, though it also went the wrong direction. The 10:00-11:00 ET hour is not special.

## VOLLOW: the clean negative

The only arm whose take rate matched, whose filter was causal and non-collinear, and which
had enough trades to say something. Low-volatility sessions produce **-$1.98 a trade** on
701 trades. Breaking out of a quiet London range is worse than breaking out of a normal one.
That is consistent with everything measured since the cross-session run: breaks revert, and
they revert hardest when the range that was broken was narrow.

## Prediction scorecard

Seventh registered prediction.

| claim | outcome |
|---|---|
| none of the five passes | **correct** |
| FVG most likely of the ICT three to look positive | **correct** — it was the only positive mean |
| SWEEP the one I would least like to bet against | **wrong, and instructively** — it was the deadest arm in the set |
| SILVER fails on sample size, 100-150 trades | **correct**, 202 trades |
| TREND4H and VOLLOW cut count and move the mean toward zero without crossing | **wrong for VOLLOW** — it moved further negative, not toward zero. TREND4H unanswerable |
| ~15% chance any arm passes | no pass |

Running record: 2 of 7 predictions substantially correct, 3 partially, 2 wrong on mechanism.
I am better at predicting failure than at predicting why.

## Where this leaves the count

**Thirty-eight cells closed, zero passes.** Excluding costs entirely did not change the
answer: at raw entry-to-exit prices the best structure in this run is +$0.88 a trade at
t 1.40, and the two most reliable numbers in the whole project remain **negative** — VWAP
reversion at t -2.80 and the Asia-to-London breakout at t -2.09 gross.

2017-2023 remains undownloaded. There is nothing to confirm.
