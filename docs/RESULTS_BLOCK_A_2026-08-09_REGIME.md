# Block A: the commodity ORB does not survive outside the 2024-26 bull

Run 2026-08-09, once, per `docs/PREREGISTRATION_2026-08-07_REGIME.md`.

## Result

| | sessions | trades | rate | net | PF | WR | $/trade |
|---|---|---|---|---|---|---|---|
| GC | 759 | 379 | 50% | -363 | 0.98 | 40% | **-1** |
| SI | 759 | 292 | 38% | -115 | 1.00 | 45% | **-0** |
| HG | 755 | 416 | 55% | -2,026 | 0.90 | 48% | **-5** |
| **ALL** | 2,273 | 1,087 | 48% | **-2,504** | **0.97** | 44% | **-2.30** |

Pooled -$2.30/trade, sd $197, se $5.98, 95% CI **-$14 to +$9**.
Rotation null on 565 sessions: observed t **-0.31**, null 95th +1.47, one-sided **p = 0.646**.

## Pre-registered decision

| criterion | value | |
|---|---|---|
| pooled mean > $0/trade | -$2.30 | **FAIL** |
| rotation-null p < 0.05 | 0.646 | **FAIL** |
| ≥2 of 3 metals positive | 0 of 3 | **FAIL** |

### BLOCK A: FAIL

All three criteria, not one. Every metal negative.

## This is a real null, not an underpowered one

The power calculation was written down before the run: ~900 trades, se near $6.70. The
actual sample came in at 1,087 trades and se $5.98, slightly better than predicted.

At that standard error the in-sample edge of $37/trade would have produced **t ≈ 6.2**. The
observed t on the per-trade mean is **-0.38**. This test could not have missed the edge if
it were there.

Compare directly:

| | 2024-26 (developed on) | 2011-2013 (unseen) |
|---|---|---|
| $/trade | +$37 | **-$2.30** |
| PF | 1.35 | **0.97** |
| rotation p | 0.0035 | **0.646** |

## Robustness, registered in advance

| | result |
|---|---|
| 2x measured spread | -$11.60/trade, PF 0.84 |
| drop best 10 trades | -$12.10/trade, PF 0.82 |
| 2011 | -$11/trade, PF 0.86 |
| 2012 | +$2/trade, PF 1.03 |
| 2013 | +$3/trade, PF 1.06 |

No year is distinguishable from zero. 2012 and 2013 are mildly positive and 2011 mildly
negative, all well inside a per-year standard error near $10. There is no year in which
this worked and no year in which it clearly failed. It simply does nothing.

## My registered prediction was wrong

> Block A comes back positive but well below in-sample, somewhere in $5-25 per trade, with
> p < 0.05 on the pooled sample, and gold clearly the strongest of the three. 2013 alone is
> negative or near zero.

Wrong on the sign, wrong on significance, wrong on which year was worst. The stated
alternative was right: **a long-only opening-range breakout is a trend-following structure,
and it does not work when the trend is absent or against it.**

Recorded so the error rate stays visible.

## What this closes

The commodity ORB was the only candidate in this project to clear every gate. It cleared
them on 2024-26 data that the source project developed it on. Given genuinely unseen data
from a different regime, the edge is zero.

The four legs closed earlier were closed on MES and MNQ. This one is closed on gold, silver
and copper, across three years, with 1,087 trades and adequate power. **The candidate is
finished.**

Two caveats stated in the pre-registration that both cut the same way:

- 2026 spreads were applied to 2011 trades. Spreads were **wider** then, so the real result
  is worse than -$2.30.
- The session window was restricted to the same 15 bars as the in-sample data, so the
  comparison changed one thing only.

Neither rescues it.

## What was NOT invalidated

The apparatus. Over this exercise the data pipeline caught, in order:

1. an MNG contract spec wrong by 2.5x
2. a cost constant that was low for silver and copper (though offsetting at the basket level)
3. a depth constraint that turns MCL negative
4. a `cummax` roll guard that served the December contract for all of 2013
5. the same guard latching silver onto the wrong contract for 211 of 820 sessions off one
   anomalous print
6. a broken SIZ11 download that ended eight months before its front-month window

Any of those would have produced a plausible-looking wrong answer. That is the part worth
keeping.

## Blocks B and C

Block B (2014-2016) and Block C (2020-2022) remain unopened. Per the pre-registration a
failed block is not re-run with a fix, and neither block can resurrect A: a strategy that
is flat across 1,087 trades in one regime is not rescued by finding a positive stretch in
another. If B is opened it is **exploratory characterisation, not confirmation**, and must
be labelled so permanently.

Block C was never downloaded. There is no reason to spend the quota on it now.
