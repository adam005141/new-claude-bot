# Results: volume-conditioned reversion, and the contrast that confirms the bounce model

Run 2026-08-12 against `docs/PREREGISTRATION_2026-08-12_VOLUME_CONDITIONED.md`. ES 5-minute,
2,053 sessions, 2009-2016. Tercile cuts 0.74 / 1.34 on time-of-day-normalised volume.

**All twelve cells fail as strategies. Two pass as measurements**, and the pre-registered
contrast came in almost exactly as stated.

## The table

| band | q | min | trades | raw $ | t | p | delay-1 $ | t | keep | net $ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| THIN | 1 | 5 | 91,962 | +0.256 | **22.08** | 0.0000 | -0.006 | -0.49 | **-3%** | -3.44 |
| THIN | 2 | 10 | 65,158 | +0.211 | 11.15 | 0.0000 | +0.020 | 0.98 | **10%** | -3.49 |
| THIN | 4 | 20 | 41,329 | +0.106 | 3.12 | 0.0000 | +0.032 | 0.88 | 30% | -3.59 |
| THIN | 8 | 40 | 23,612 | +0.188 | 2.82 | 0.0100 | +0.141 | 2.06 | 75% | -3.51 |
| MID | 1 | 5 | 109,438 | +0.207 | 15.01 | 0.0000 | +0.016 | 1.02 | 8% | -3.49 |
| MID | 2 | 10 | 76,363 | +0.193 | 8.66 | 0.0000 | -0.003 | -0.13 | -2% | -3.51 |
| MID | 4 | 20 | 47,357 | +0.074 | 1.88 | 0.0280 | +0.040 | 0.98 | 55% | -3.63 |
| MID | 8 | 40 | 26,604 | +0.131 | 1.81 | 0.0340 | +0.184 | 2.39 | 140% | -3.57 |
| **HEAVY** | **1** | 5 | 106,648 | +0.120 | 7.10 | 0.0000 | **+0.069** | **3.68** | **57%** | -3.58 |
| **HEAVY** | **2** | 10 | 70,020 | +0.143 | 5.26 | 0.0000 | **+0.097** | **3.35** | **67%** | -3.56 |
| HEAVY | 4 | 20 | 43,023 | +0.067 | 1.46 | 0.0480 | +0.071 | 1.45 | 105% | -3.63 |
| HEAVY | 8 | 40 | 24,524 | +0.123 | 1.47 | 0.0540 | +0.169 | 2.00 | 138% | -3.58 |

## The contrast, which is the actual deliverable

Registered in advance: THIN keeps under 30%, HEAVY keeps 60-100%.

| band | median keep across horizons |
|---|---:|
| **THIN** | **20%** |
| **HEAVY** | **86%** |

Both inside the registered range. This is the cleanest confirmation the bounce model has
received:

**THIN/q1 has t = 22.08 and keeps -3%.** A t-statistic of 22 on 91,962 trades, and stepping
over one five-minute bar leaves nothing. That is Roll's model in a single line: bounce lives
entirely in the adjacent print.

**HEAVY/q1 keeps 57% and its DELAYED t is 3.68.** HEAVY/q2 keeps 67% at a delayed t of 3.35.
These are real signals that survive being stepped over, which is exactly what the lag-2 term
in the diagnostic predicted and what bounce cannot produce.

## Only the third delay-robust signal ever found here

Across ninety-six cells, three structures have now shown a significant edge that survives
delayed execution:

| | trades | edge | cost | edge as % of cost |
|---|---:|---:|---:|---:|
| SI/ASIA/q4 | 2,998 | +$7.22 | $31.20 | 23% |
| **HEAVY/q2** | 70,020 | +$0.097 delayed | $3.70 | **2.6%** |
| **HEAVY/q1** | 106,648 | +$0.069 delayed | $3.70 | **1.9%** |

Everything else in the project either failed outright or turned out to be the spread. These
three are real. None is within a factor of four of paying for itself, and the two new ones
are off by a factor of forty.

## The edge does not scale with holding time, and that is informative

My registered magnitude was **$0.10 at q = 1** scaling as `sqrt(q)` to **$0.28 at q = 8**.
The first number was nearly exact (observed $0.120). The scaling was wrong:

| q | 1 | 2 | 4 | 8 |
|---|---:|---:|---:|---:|
| HEAVY raw $ | 0.120 | 0.143 | 0.067 | 0.123 |

**Flat, not rising.** This is the second time I have predicted `sqrt(q)` scaling and been
wrong (run 33 was the first), and the repetition is the useful part.

A drift scales with time, because it is an expected return per unit time. **A fixed dollar
amount that does not scale is a one-off correction**: something gets mispriced by a roughly
constant amount and resolves once, regardless of how long you then wait. That is the
signature of a transient liquidity event being absorbed, not of an ongoing mispricing. It
also means holding longer cannot rescue it, which closes the escape route that motivated the
run-33 horizon sweep.

## Prediction scorecard

Twelfth registered prediction.

| claim | outcome |
|---|---|
| no cell passes as a strategy | **correct** |
| HEAVY passes the delay test, THIN fails it | **correct**, 86% against 20% |
| THIN keeps under 30% | **correct**, 20% |
| HEAVY keeps 60-100% | **correct**, 86% |
| about $0.10 a trade at q = 1 | **correct**, $0.120 |
| rising as sqrt(q) to about $0.28 at q = 8 | **wrong**, flat at $0.123 |
| under 3% chance any cell passes as a strategy | none did |

Six of seven. The miss is the same one as run 33, which now looks less like an error of
estimation and more like a wrong model of what these signals are.

## Where this leaves things

**Ninety-six cells closed. Zero strategy passes. Three measurement passes.**

The BVC order-flow proxy is dead: forward IC of -0.0057 delayed against a 2-sigma band of
0.0027, under a cent per trade. Recorded precisely, because the distinction matters:
**BVC-OFI is a volume-weighted transformation of the same bar's price change, not a
substitute for true signed order flow.** This closes the proxy. True order flow against the
prevailing quote is still untested and still absent from the Barchart export.

What volume conditioning bought is not a strategy. It is a clean separation of the two things
that were previously mixed together in one number: **the bounce component, which is large,
fake, and dies instantly under delay; and a small real component in heavy bars, which
survives delay at t 3.68 and is worth two cents on the dollar of its own cost.**

2017-2023 remains undownloaded and untouched.
