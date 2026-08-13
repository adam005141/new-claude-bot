# Pre-registration: volume-conditioned reversion

Written **2026-08-12, after the volume diagnostic and before any trade was simulated**.
Nothing below may be revised after seeing a result.

## What motivated this, disclosed

`tools/flow_structure.py` conditioned return structure on relative volume, ranked within
time-of-day and causally. It is the first diagnostic in this project to use volume for
anything but picking a roll contract.

| tercile | bars | 2se | ac1 | **ac2** | ac3 |
|---|---:|---:|---:|---:|---:|
| THIN | 184,829 | 0.0047 | **-0.0751** | +0.0011 | 0.0020 |
| MID | 184,834 | 0.0047 | -0.0438 | -0.0018 | 0.0026 |
| HEAVY | 184,838 | 0.0047 | -0.0211 | **-0.0250** | 0.0070 |

Two things here, and only the second is new.

**The lag-1 gradient is the bounce hypothesis confirmed.** Bounce is a fixed tick amount, so
as a share of variance it is largest where the bar is quietest. Thin bars carry 3.6x the
lag-1 reversion of heavy ones. That is a prediction from run 33 landing, not a discovery.

**The lag-2 term is new.** Thin bars are lag-1 only (ac2 = +0.0011, dead on zero), which is
the pure Roll signature. Heavy bars carry ac2 = **-0.0250**, more than ten standard errors
out and *more negative than their own lag 1*. **Roll's model predicts nothing at lag 2.**
Whatever produces that is not bid-ask bounce.

Selection is disclosed: this test exists because of that table.

## The test

Fade the preceding `q`-bar move, hold `q` bars, non-overlapping, no stop, both directions,
**conditioned on the relative-volume tercile of the signal bar**. `q` in {1, 2, 4, 8} bars
(5 to 40 minutes) x three terciles = **12 cells**, Bonferroni **p < 0.0042**.

THIN and MID are run as controls, not as candidates. Their purpose is to make the HEAVY
number interpretable.

## The delay test makes this falsifiable in advance

This is the sharpest prediction available in this project, because the two bands should
behave *oppositely* under the same operation:

- **THIN is lag-1 only.** One bar of delay steps entirely over its signal. Its edge should
  collapse, as ES's did in run 33 (76% destroyed).
- **HEAVY has a lag-2 component.** A delayed trade still sits inside that structure. Its
  edge should largely **survive**.

If both collapse, the lag-2 term is something I have mismeasured and the family is closed.
If both survive, my model of bounce is wrong. Either would be informative.

## Decision rule

1. mean **> $0** raw
2. **p < 0.0042**
3. **at least 60% of the edge survives one bar of delayed execution**
4. mean **> $3.70** to pass as a strategy

## Registered prediction

> **No cell passes as a strategy. HEAVY passes the delay test and THIN fails it.**
>
> The magnitude is the point and I am stating it before the run rather than explaining it
> after. A rho of -0.025 against a 5-minute sigma of 6.67 bp gives a per-trade ceiling of
> roughly `0.025 x 6.67bp x sqrt(2/pi)`, which at ES near 1450 is about **$0.10**. Scaling
> as `sqrt(q)` to q = 8 gives roughly **$0.28**. Against a $3.70 round turn that is **13 to
> 37 times short**.
>
> **I expect HEAVY to keep 60-100% of its edge under delay and THIN to keep under 30%.**
> That contrast is the real deliverable here, not the P&L.
>
> Probability any cell passes as a strategy: **under 3%.**

Twelfth prediction. The eleventh was 5 of 6, with the miss being that I signed a direction I
had no basis to sign; this one states magnitudes and a contrast rather than signs.

## What I will not do

- Not search other volume cuts, quantiles, or normalisation windows if these fail
- Not promote a control band to a candidate after seeing it
- Cumulative count becomes ninety-six; 2017-2023 remains the confirmation set
