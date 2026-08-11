# Results: the cells that survived bounce dilution

Run 2026-08-11 against `docs/PREREGISTRATION_2026-08-11_SURVIVING_CELLS.md`. 30-minute bars,
2009-2016.

**No cell passes as a strategy. One passes as a measurement:** silver, Asian session,
2-hour fade. It is the best thing found in this project and it still does not pay.

## The table

| cell | dir | q | min | trades | raw $ | t | p | net $ | delay-1 $ | keep | RT |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ES/LONDON | fade | 1 | 30 | 11,331 | +0.225 | 2.53 | 0.0060 | -3.48 | +0.326 | 145% | 3.70 |
| ES/LONDON | fade | 2 | 60 | 5,821 | +0.404 | 2.13 | 0.0090 | -3.30 | +0.121 | 30% | 3.70 |
| ES/LONDON | fade | 4 | 120 | 1,960 | +0.575 | 1.51 | 0.0950 | -3.13 | +1.059 | 184% | 3.70 |
| **SI/ASIA** | fade | 1 | 30 | 11,530 | +1.515 | 2.57 | 0.0030 | -29.68 | -0.182 | -12% | 31.20 |
| **SI/ASIA** | fade | 2 | 60 | 5,894 | +1.739 | 1.56 | 0.0790 | -29.46 | +2.628 | 151% | 31.20 |
| **SI/ASIA** | **fade** | **4** | **120** | **2,998** | **+7.218** | **3.09** | **0.0010** | **-23.98** | **+8.101** | **112%** | **31.20** |
| SI/ASIA | fade | 8 | 240 | 1,513 | +6.500 | 1.63 | 0.0330 | -24.70 | +6.426 | 99% | 31.20 |
| SI/LONDON | fade | 2 | 60 | 4,479 | +3.860 | 1.98 | 0.0210 | -27.34 | +6.587 | 171% | 31.20 |
| GC/NY | follow | 4 | 120 | 1,503 | +1.010 | 0.82 | 0.2080 | -4.19 | +0.713 | 71% | 5.20 |
| SI/NY | follow | 1 | 30 | 8,758 | +1.000 | 0.96 | 0.1610 | -30.20 | +0.705 | 71% | 31.20 |

(Ten of sixteen shown; the rest are in `docs/reports/surviving_cells.json`.)

Only **SI/ASIA/q4** clears the Bonferroni threshold of p < 0.0025.

## The GC/SI New York momentum cells evaporated, as predicted

GC/NY peaked at +$1.01 at t 0.82, SI/NY at +$1.00 at t 0.96, and both went negative at
other horizons. They were the only variance ratios above 1 in an 80-cell diagnostic where
roughly four spurious |z| > 2 are expected, sitting at adjacent nested horizons of two
heavily correlated instruments. That is what a false positive looks like from the inside,
and the registered prediction called it.

## ES LONDON: real-looking, and it does not reach

All three horizons positive, and the **delay test is passed emphatically** at q = 1 and
q = 4 (145% and 184%, meaning the edge is *larger* with delayed execution, which is the
opposite of a bounce signature). This is consistent with the pre-registered argument that
its `ac(1)` of -0.0355 is ten times larger than Roll's arithmetic can explain.

But no horizon reaches p < 0.0025, and the magnitudes are +$0.23 to +$0.58 against a **$3.70**
round turn. Even taken at face value it is 6 to 16 times too small.

## SI/ASIA/q4: the one that passed, and why it still fails

Fade the preceding two-hour move in silver during the Asian session, hold two hours.

| | |
|---|---|
| trades | 2,998 |
| raw | **+$7.218** per trade |
| t | **3.09**, p **0.0010** (passes Bonferroni at 0.0025) |
| one-bar delay | **+$8.101**, keeping **112%** |
| years positive | **7 of 7** |

Every criterion for a measurement, cleanly. The delay result is the important one: an edge
that grows under delayed execution cannot be bid-ask bounce, which is the failure mode that
killed the ES 5-minute reversion.

**It fails on cost, and not marginally.** Micro silver's measured round turn is **$31.20**.
The edge is 23% of it.

### Two things that make it weaker than the headline

**55% of the total P&L comes from 2011**, the year silver ran from $18 to $49 and crashed.

| year | trades | $/trade | t | total |
|---|---:|---:|---:|---:|
| 2010 | 70 | 18.64 | 1.07 | 1,305 |
| **2011** | 505 | **23.76** | 2.32 | **12,000** |
| 2012 | 506 | 2.57 | 0.56 | 1,300 |
| 2013 | 494 | 3.67 | 0.64 | 1,815 |
| 2014 | 481 | 5.31 | 1.77 | 2,555 |
| 2015 | 488 | 3.66 | 1.45 | 1,785 |
| 2016 | 454 | 1.94 | 0.46 | 880 |

Excluding 2011: **+$3.87 a trade over 2,493 trades, 6 of 6 remaining years positive.** So the
effect is genuinely persistent, not a single event, but its usable magnitude is roughly half
the headline. $3.87 against $31.20 is 12% of cost.

**And the cost convention does not save it.** This project models a round turn as *two* full
spreads, which is conservative: a taker pays half the spread against mid on each side, so
one full spread per round turn is the standard convention. Under that looser model silver's
round turn is about $16.20 rather than $31.20. **I am not changing the convention after
seeing a result** — but it is worth stating that the conclusion is robust to it, because
$3.87 against $16.20 is still four times short.

Scaling to the full-size SI contract (5,000 oz rather than 1,000) multiplies both the edge
and the tick value by five and changes nothing about the ratio.

**I attempted to measure the live SI and SIL spreads through IBKR to check whether the
full-size contract is materially tighter in relative terms. Both snapshots returned empty,
so that number is unmeasured and I am not going to estimate it.** It is the one concrete
thing that could move this cell, and it is a specific next step rather than a hope.

## Prediction scorecard

Tenth registered prediction, and the first where the mechanism claim was explicit.

| claim | outcome |
|---|---|
| no cell passes as a strategy | **correct** |
| one or two pass as a measurement | **correct**, exactly one |
| GC/SI NY momentum evaporates | **correct** |
| SI cells fail on cost by an order of magnitude | **correct** |
| "a real, statistically clean, economically useless edge" is the most likely outcome | **correct**, and it is precisely what SI/ASIA/q4 is |
| ES LONDON is the one that survives the delay test | **half right** — it survived the delay test emphatically, but SI/ASIA was the cell that reached significance |

First prediction in ten where the mechanism was substantially right rather than only the
verdict.

## Where this leaves things

**Seventy-five cells closed, zero strategy passes, one measurement pass.**

The measurement pass matters more than the count. Everything before it failed by a factor of
5 to 30 against cost, or turned out to be the spread itself. SI/ASIA/q4 fails by a factor of
4 to 8, survives delayed execution, and is positive in every one of seven years. That is a
different kind of negative: not "there is nothing there," but "there is something there and
it is smaller than the toll."

The families still open are unchanged and now better motivated:

1. **Cross-sectional relative value.** Still completely untested, and it is the only family
   where the noise cancels rather than accumulates.
2. **Non-price information.** Volume sits in every row and has only ever been used to pick
   a roll.
3. **Cheaper execution on the one thing that works.** SI/ASIA/q4's problem is entirely the
   denominator.

2017-2023 remains undownloaded and untouched.
