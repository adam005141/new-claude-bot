# Results: the 4-hour trend filter corrected, and four confluence structures

Run 2026-08-11 against `docs/PREREGISTRATION_2026-08-11_TREND_CONFLUENCE.md`, committed at
`8aab831` before the code, and the code committed at `53a839d` before the run. 2,015
sessions of ES 5-minute, 2009-2016.

**All five arms FAIL.** Two findings matter beyond that: the corrected 4-hour filter turns
out to be collinear with the thing it was supposed to filter, and the no-stop diagnostic
reversed my prediction in a way that changes what I think the exits were doing.

## Take rates, checked before the P&L

| arm | expected | observed | verdict |
|---|---:|---:|---|
| TREND4H-FIX | 45-60% | **97%** | miss. Third degenerate filter, see below |
| TREND4H-FVG | 45-55% | 57% | near-hit, slightly high |
| IFVG | 35-60% | **92%** | miss. Non-selective, exactly like plain FVG |
| SWEEP-FVG | 25-45% | 27% | hit |
| SWEEP-IFVG | 15-35% | **42%** | miss, high |

One clean hit, one near-hit, three misses.

## The numbers

Raw entry-to-exit, `(exit - entry) x $5 x 1 contract`. `net $` subtracts the measured $3.70
round turn and is shown only so the gap stays visible.

| arm | signals | taken | take% | $/trade | net $ | total $ | WR | t | t-5% | p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| TREND4H-FIX | 1,928 | 1,875 | 97% | +0.29 | -3.41 | +548 | 46% | 0.26 | -6.30 | 0.381 |
| TREND4H-FVG | 2,006 | 1,142 | 57% | +1.34 | -2.36 | +1,532 | 14% | 1.75 | -9.87 | 0.016 |
| IFVG | 1,970 | 1,820 | 92% | -0.32 | -4.02 | -584 | 13% | -0.71 | -21.24 | 0.769 |
| SWEEP-FVG | 1,636 | 446 | 27% | +1.63 | -2.07 | +729 | 13% | 1.35 | -6.13 | 0.053 \* |
| SWEEP-IFVG | 1,636 | 695 | 42% | -0.96 | -4.66 | -669 | 13% | -1.71 | -16.53 | 0.957 \* |

\* bootstrap p is not reliable below 700 trades. See the statistics correction at the end.

## The 4-hour trend filter is collinear with the breakout it filters

Take rate **97%**. The filter declines 53 of 1,928 signals. It is not filtering.

The reason is arithmetic and I should have seen it when writing the registration. The L2N
break fires at median bar 2 of the NY window. A 48-bar lookback from there reaches back to
`mso -240`, which lands **inside the London window that defines the range being broken**. If
price breaks above the London high, then by construction price at the break is at the top of
that same four-hour window, so `close[i] - close[i-48]` is positive. **The sign of the
4-hour change and the side of the range you broke are the same measurement taken twice.**

The confirmation is direct: decontaminated TREND4H-FIX returns **-$0.04 a trade on 1,812
trades**, against the unfiltered L2N breakout's previously measured gross of **plus or minus
$0.01**. Within a nickel. It is the same strategy.

So the 4-hour trend filter, as I defined it, is answered: **it cannot be tested against a
range breakout, because on that setup it carries no information the breakout does not
already carry.** Testing it would require a setup whose direction is not mechanically
determined by recent price position. TREND4H-FVG is that test, and it also failed.

This is the third degenerate filter in four registrations. The take-rate check caught all
three. The pattern in every case is the same: **the filter and the signal are computed from
overlapping windows of the same price series.**

## The decontamination worked, and it was the whole result

Pre-registered before the run: report TREND4H-FIX twice, and let the version without the 63
already-seen late-break sessions decide it.

| | trades | $/trade | t |
|---|---:|---:|---:|
| all qualifying sessions | 1,875 | **+0.29** | 0.26 |
| 63 seen sessions removed | 1,812 | **-0.04** | -0.03 |

Sixty-three sessions out of 1,875 carried the entire positive mean of the arm. That is what
looking at data before deciding how to use it costs, made visible. The registered prediction
was that the two would differ by less than $1 and that the earlier +$9.70 was sampling
noise. Both correct: the gap is $0.33, and the clean series is flat on 1,812 trades.

## Confluence: the arithmetic held

The registration stated up front that stacking multiplies conditions and divides sample, so
a confluence of two measured-null main effects can only pass on interaction. That is what
happened.

**SWEEP-FVG is the best cell in the run and it is still nothing.** +$1.63 a trade on 446
trades, t 1.35. It does beat both its parents (SWEEP -$0.11, FVG +$0.88), which is a real if
small interaction, but the sample cost is severe: 446 trades against FVG's 1,581, so the
standard error is nearly double and a mean twice as large produces a *smaller* t-statistic
than FVG's own. That is the sample-loss trade in one line.

**SWEEP-IFVG went the other way**: -$0.96 a trade, t -1.71.

## The iFVG loses money directionally, and that is the one solid finding here

Two independent arms containing the inversion, on 1,820 and 695 trades, are negative. Under
the no-stop diagnostic, where the signal is tested as a pure directional call, both are
**significantly** negative:

| | trades | $/trade, no stop | t |
|---|---:|---:|---:|
| IFVG | 1,820 | **-3.04** | **-2.86** |
| SWEEP-IFVG | 695 | **-4.83** | **-3.18** |

This joins VWAP reversion (t -2.80) and the Asia-to-London breakout (t -2.09 gross) as the
third structure in this project that is significantly negative rather than merely absent.

The plain gap and the inverted gap are the comparison that matters, because the inversion is
sold as the stronger signal: a level that failed and flipped. Measured, **plain FVG is
+$0.88 and IFVG is -$0.32, and without a stop the inverted version is -$3.04.** The
inversion does not strengthen the gap. It is worse than the gap, and worse than nothing.

## The no-stop diagnostic reversed my prediction

I registered that removing the stop would improve every zone-entry arm's t-statistic, on the
reasoning that a tight stop against a hold-to-close exit was destroying win rate rather than
edge, and that the concentration criterion was close to unpassable under it. I also wrote
that testing five entries against one exit "tells you about the exit as much as the entries."

Four of five got **worse**:

| arm | t with stop | t without |
|---|---:|---:|
| TREND4H-FIX | 0.26 | -0.11 |
| TREND4H-FVG | 1.75 | 0.70 |
| IFVG | -0.71 | **-2.86** |
| SWEEP-FVG | 1.35 | 1.47 |
| SWEEP-IFVG | -1.71 | **-3.18** |

Win rate rose from 13-14% to 44-52% when the stop was removed, and P&L got worse. Win rate
remains uninformative here, for the seventh time.

**The tight stop was load-bearing in the right direction.** It was not masking an edge; it
was capping the loss on entries that continue against you. Removing it exposes how bad the
directional call actually is. My concern that the exit was doing the damage was wrong, and
the entries carry the failure on their own.

## Prediction scorecard

Eighth registered prediction.

| claim | outcome |
|---|---|
| none of the five passes | **correct** |
| TREND4H-FIX between -$1.50 and +$1.50 with abs(t) < 1.5 | **correct**, -$0.04 at t -0.03 |
| contaminated and clean differ by less than $1 | **correct**, $0.33 |
| the earlier +$9.70 was sampling noise | **correct** |
| SWEEP-IFVG lands near or below the 100-trade floor | **wrong**, 695 trades |
| IFVG is the most likely confluence to work | **wrong, and badly** — it was the worst arm in the set and significantly negative |
| no-stop improves every zone-entry t, turns none positive | **wrong on the first half**, right on the second |

Running record across eight: consistently right that things fail, consistently wrong about
mechanism. That asymmetry is itself worth noting. Predicting failure from a base rate of
zero is cheap. Predicting why requires a model of the market I evidently do not have.

## Statistics correction, applying to the previous run as well

The bootstrap p in `ict_quant.py` and `trend_confluence.py` compared each resample's
**t-statistic** against the observed **mean in dollars**. Those are different units, and the
comparison is only equivalent when the standard error happens to be 1.0. Corrected to the
studentised form already used in `intraday_reversion.py` and the other seven tools: compare
each resample's own t to the observed t.

Both runs were re-run. **Every trade-level number is byte-identical and no verdict changed**,
because the p criterion was never the binding one. The corrected p-values for the previous
run are FVG 0.045 (was 0.161), SWEEP 0.550, SILVER 0.702 (was 0.935), VOLLOW 0.926 (was
0.974). The ICT results document has been updated.

Separately, `entry_variants.py` drew two independent resamples, one for the numerator and one
for the denominator, which decorrelates them and **over**-disperses the null, erring
conservative. Fixed and re-run: all twelve cells still fail.

**And a calibration limit worth recording.** Measured on demeaned iid input with
`mean_block=10`, 4,000 draws, the studentised stationary bootstrap reaches nominal
calibration only around **n >= 700**:

| n | 6 | 20 | 45 | 70 | 114 | 158 |
|---|---|---|---|---|---|---|
| trades | 63 | 202 | 446 | 701 | 1,142 | 1,581 |
| null t 99th pct | 1.62 | 1.67 | 1.85 | 2.23 | 2.30 | 2.32 |

Nominal is 2.326. Skewed input is worse: 1.32 at n = 63. So a bootstrap p from a small arm is
anti-conservative and is now flagged rather than printed bare. **This is what produced the
previous run's TREND4H `p < 0.001` at t = 2.38 on 63 trades**, which should have been roughly
0.01-0.02 and is not readable as a probability at all. It failed the concentration check
regardless, and every arm below 700 trades in both runs failed on a criterion that does not
use the bootstrap.

## Where this leaves the count

**Forty-three cells closed, zero passes.**

The three most reliable measurements in the project are all negative: VWAP reversion
t -2.80, the inverted fair value gap t -2.86, and the Asia-to-London breakout t -2.09 gross.
Nothing has produced a positive result that survives its own correction, at any cost
assumption including zero.

2017-2023 remains undownloaded. There is still nothing to confirm.
