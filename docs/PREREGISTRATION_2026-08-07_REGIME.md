# Pre-registration: does the commodity ORB edge exist outside the 2024-26 metals bull?

Written **2026-08-07, before any pre-2024 data existed on disk**. Committed before the
download of Stage 2 onward. Nothing below may be revised after seeing a result; a revision
is a new trial and must be recorded as one in the experiment ledger.

## Why this has to be pre-registered

Six new years of intraday data is six years of opportunities to find something that is not
there. With enough passes I will find a configuration that works on 2011-2016 and it will
be worthless. The only defence is to fix the test now, run it once, and accept the answer.

## The claim under test

The commodity ORB reported PF 1.39 (1.32 with depth priced, 1.35 capped) and a rotation-null
p of 0.0035 on 2024-2026. That entire sample is a metals bull market, which the source
project itself flags. The strategy is **long only**. The obvious failure mode is that it is
a bull-market artifact.

**H0: the per-trade edge is zero outside the 2024-26 sample.**

## Frozen configuration

Taken from `OrbConfig` defaults as committed at `8a14361`. Not one value may move.

| | |
|---|---|
| opening range | 60 minutes, on 30-minute bars |
| entry | first trade above OR high + 1 tick, long only |
| entry cutoff | 180 minutes after the open |
| stop | opposite side of the opening range, filled at the **worse** of stop and open |
| exit | session close, one trade per session |
| minimum OR | 2 ticks |
| risk budget | $250/trade, max 20 contracts, skip if risk/contract > $500 |
| costs | **CAPPED** model: per-symbol half-spread + 0.5 tick, size capped at measured depth |
| roll | volume crossover via `build_continuous`, decided one session in arrears; roll sessions excluded |
| session window | **restricted to 09:30-17:00 ET**, the same 15 bars the 2024-26 sample covered |

Two deliberate choices recorded now so they cannot be presented as discoveries later:

**The session window is restricted on purpose.** Barchart supplies the full 47-bar Globex
session; the imported 2024-26 sample only ever had 15 bars. Testing the full session would
change two things at once and the comparison would mean nothing. The wider window is an
*exploratory* question listed below, not part of this test.

**2026 spreads are applied to 2011 trades, and that favours the strategy.** Spreads were
wider then. This biases the test toward passing, so a failure is decisive and a pass is
optimistic. A stressed variant at 2x the measured spread is registered below as a
robustness check, not as a separate hypothesis.

## Blocks, and what may be looked at when

| block | years | status |
|---|---|---|
| **A** | 2011-2013 | **Confirmatory.** Run once, result written to the ledger before anything else is opened. |
| **B** | 2014-2016 | **Lockbox 1.** Opened only after A's result is committed. |
| **C** | 2020-2022 | **Lockbox 2.** Different regime (vol shock). Opened only after B. |

Every prior look invalidates a lockbox. If I open B before committing A, B is no longer
evidence and must be reported as exploratory.

## Decision rule for Block A

Computed on all three metals pooled, 2011-2013, using the frozen configuration.

**PASS requires all three:**

1. Mean net **> $0 per trade**
2. Rotation-null one-sided **p < 0.05** (stationary bootstrap, mean block 10, 2,000 draws,
   mean removed for the null)
3. **At least 2 of 3 metals individually positive** — guards against one symbol carrying it

**FAIL** is any of: non-positive pooled mean, p >= 0.05, or two or more metals negative.

### What is explicitly NOT a failure

A **positive but smaller** edge than the $37/trade in-sample figure is a PASS. A long-only
breakout should earn less in a bear market. Predicted in advance: I expect Block A to come
in materially below in-sample, plausibly in the $5-$25 range, and possibly negative in 2013
alone while positive across the block.

### Power, computed before running

Three metals over three years is roughly 750 sessions each, and the ORB trades ~40% of
sessions, so expect **~900 trades**. At the in-sample per-trade sd near $200 that is a
standard error near **$6.70**.

- a $37/trade edge would show t ~ 5.5
- a $10/trade edge would show t ~ 1.5

So this test can genuinely decide, unlike the 11-trade check on 2026-07 data which was
inconclusive by construction. If Block A returns a null, that is a real null and not a
sample-size artifact.

## Robustness checks, registered now

Run alongside Block A and reported with it, whatever they show:

1. **2x measured spread.** If the sign flips under doubled costs, the edge does not survive
   period-appropriate execution and the PASS is withdrawn.
2. **Drop the best 10 trades.** Already this project's fragility gate.
3. **Per-year split within the block**, reported for information. A single bad year does not
   fail the block; the block-level rule above is the decision.

## Exploratory, and labelled as such forever

Anything found here requires fresh confirmation on unopened data and may not be reported as
a result of this test:

- Full 47-bar session versus the restricted 15-bar window
- Short side, or symmetric long/short
- Whether the **dollar-denominated risk guard** switches the strategy off as volatility
  rises. This already happened out-of-sample: silver's opening range doubled and 76% of
  sessions fell past the $500 cap, so it traded once in 17 sessions. Block C is where I
  expect this to bite hardest.
- Any opening-range length, entry cutoff, or bar size other than the frozen ones

## What I will not do

- Not tune any parameter on this data
- Not select years, symbols, or sub-periods after seeing results
- Not change the cost model after seeing results
- Not re-run a failed block with a fix. **If it fails, it fails**, and the ledger records it
  next to the four legs already closed on evidence

## Registered prediction

For the record, so the error rate stays visible:

> Block A comes back **positive but well below in-sample**, somewhere in $5-$25 per trade,
> with p < 0.05 on the pooled sample, and gold clearly the strongest of the three. 2013
> alone is negative or near zero.
>
> Confidence: moderate. The honest alternative is that a long-only opening-range breakout
> is a trend-following structure and simply does not work in a three-year downtrend, in
> which case Block A is negative and the candidate is finished.
