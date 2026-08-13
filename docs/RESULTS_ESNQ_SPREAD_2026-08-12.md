# Results: the ES/NQ spread is an execution artifact

Run 2026-08-12 against `docs/PREREGISTRATION_2026-08-12_ESNQ_SPREAD.md`. 94,805 aligned
30-minute bars, 2,051 sessions, 2009-2016. 1 MES against 1.32 MNQ, causal dollar-neutral.

**All nine cells FAIL.** The relative-value family, which was the last one open, is closed.

## The table

| window | q | min | trades | raw $ | t | p | delay-1 $ | t | keep | net $ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ALL | 1 | 30 | 45,599 | +0.265 | 12.10 | 0.0000 | -0.016 | -0.61 | **-6%** | -6.33 |
| ALL | 2 | 60 | 22,172 | +0.193 | 3.58 | 0.0000 | +0.007 | 0.14 | **4%** | -6.40 |
| ALL | 4 | 120 | 10,108 | +0.141 | 1.27 | 0.0970 | +0.104 | 1.13 | 74% | -6.46 |
| **ASIA** | 1 | 30 | 15,945 | **+0.430** | **25.09** | 0.0000 | +0.025 | 1.14 | **6%** | -6.17 |
| ASIA | 2 | 60 | 8,052 | +0.389 | 11.96 | 0.0000 | +0.060 | 1.70 | **16%** | -6.21 |
| ASIA | 4 | 120 | 4,040 | +0.382 | 6.85 | 0.0000 | +0.062 | 0.81 | **16%** | -6.22 |
| NY | 1 | 30 | 11,975 | +0.072 | 1.26 | 0.1040 | +0.076 | 1.10 | 106% | -6.53 |
| NY | 2 | 60 | 5,980 | +0.001 | 0.01 | 0.4880 | -0.209 | -1.67 | n/a | -6.60 |
| NY | 4 | 120 | 1,984 | -0.448 | -1.85 | 0.9550 | -0.116 | -0.49 | n/a | -7.05 |

NY/q2 printed a "keep" of -17225%, which is a display artifact of dividing by a raw edge of
$0.001 rather than a finding. Ignore that cell's ratio; its edge is zero to three decimals.

## The one number that closes the family

**Edge size and delay survival are almost perfectly anticorrelated.**

| cell | t | keep |
|---|---:|---:|
| ASIA/q1 | **25.09** | **6%** |
| ALL/q1 | 12.10 | -6% |
| ASIA/q2 | 11.96 | 16% |
| ASIA/q4 | 6.85 | 16% |
| ALL/q2 | 3.58 | 4% |
| ALL/q4 | 1.27 | 74% |
| NY/q1 | 1.26 | 106% |

Every cell with a large t-statistic loses essentially all of it to one bar of delay. The two
cells that survive delay are the two with no edge to survive with. **There is no cell where
a real edge and delay-robustness coexist**, and that is the whole result.

ASIA/q1's **t = 25.09 is the largest t-statistic in this project**, on 15,945 trades. Stepping
over a single 30-minute bar takes it to t = 1.14. Nothing that survives a five-year sample
at t = 25 and dies from a 30-minute delay is a forecast of anything.

## The mechanism was pre-registered and it held

The registration named two causes and predicted the numbers. Both mechanisms are visible in
the result:

**Bounce adds under differencing.** The common index move cancels in the spread while each
leg's bid-ask bounce is idiosyncratic, so bounce variance adds on a smaller base. Spread
sigma is 7.11 bp against 15.63 for ES and 17.13 for NQ.

**Stale, non-synchronous closes.** NQ trades 229 contracts per 30-minute bar in Asia against
ES's 2,125. A bar's close is its last print, so the legs are priced minutes apart when it is
thin. The signature is the scaling: ASIA/q1's raw edge is **six times** NY/q1's (+$0.430
against +$0.072) on a fraction of the volume, and it is Asia that collapses under delay
while NY, which has nothing to collapse, keeps 106%.

## Prediction scorecard

Eleventh registered prediction, and the second in a row that staked the mechanism rather
than only the verdict.

| claim | outcome |
|---|---|
| every cell fails, specifically on criterion 3 | **correct** |
| ASIA/q1 raw t "in the tens" | **correct**, 25.09 |
| Asia keeps under 25% under delay | **correct**, 6% |
| the delayed Asia number is negative | **wrong** — it is +$0.025, statistically zero but positive |
| NY shows the least of everything | **correct** |
| under 2% chance any cell passes | none did |

Five of six, and the miss is that I said "negative" where the honest answer was "zero." That
is the right kind of miss but it is still a miss: I overstated a direction I had no basis to
sign.

## Where this leaves the project

**Eighty-four cells closed. Zero strategy passes. One measurement pass** (silver, Asian
session, 2-hour fade: +$7.22 a trade at t 3.09, delay-robust at 112%, positive in 7 of 7
years, and 4 to 8 times too small for its own spread).

The families are now closed in a way that is mechanistic rather than merely empirical:

| family | status | why |
|---|---|---|
| ES directional intraday, 5 min to 4 h | **closed** | the only significant signal is the spread (Roll 1.30 ticks; 76% of it dies on a 1-bar delay) |
| ES/NQ relative value | **closed** | lag-1 only; t 25 dies to t 1.1 on a 1-bar delay |
| metals directional | **closed** | random walks; the two VR>1 cells evaporated at t 0.82 and 0.96 |
| momentum / breakout, all variants | **closed** | 43 cells, and the series is not trending at any horizon |
| silver Asian reversion | **open, uneconomic** | real and delay-robust, 4-8x under cost |

**The honest summary is that this data has been searched thoroughly and the answer is
consistent.** Where markets are liquid there is no edge; where an edge exists the market is
thin enough that the spread exceeds it. Silver made that explicit: 2.2% of ES's volume, the
only surviving signal, and a $31.20 round turn against a $7.22 edge.

What is genuinely untested is one input class, not another instrument or another horizon:
**order flow.** Every one of the 84 cells is a transformation of OHLCV. Signed volume and
trade imbalance are different information, and the Barchart export does not carry them.

2017-2023 remains undownloaded and untouched.
