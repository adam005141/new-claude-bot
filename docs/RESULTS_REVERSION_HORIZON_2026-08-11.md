# Results: the reversion edge versus holding horizon, and what it actually is

Run 2026-08-11 against `docs/PREREGISTRATION_2026-08-11_REVERSION_HORIZON.md`, committed at
`8529f66` before the code. ES 5-minute, 2,053 sessions, 2009-2016.

**All eight horizons FAIL.** More usefully, the mechanism is now identified, and it closes
an entire family rather than adding a forty-fourth body to the pile.

## The sweep

Fade the preceding `q`-bar move, hold `q` bars, non-overlapping, no stop, no filter. Raw
`(exit - entry) x $5`.

| q | minutes | trades | raw $/trade | net $/trade | WR | t | t-5% | p |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 219,867 | **+0.205** | -3.495 | 44.8% | **19.36** | -44.83 | 0.0000 |
| 2 | 10 | 116,346 | +0.161 | -3.539 | 45.7% | 8.15 | -39.88 | 0.0000 |
| 3 | 15 | 79,245 | +0.181 | -3.519 | 46.5% | 6.30 | -34.24 | 0.0000 |
| 6 | 30 | 40,699 | +0.049 | -3.651 | 47.4% | 0.87 | -28.34 | 0.195 |
| 12 | 60 | 20,836 | +0.019 | -3.681 | 48.4% | 0.16 | -21.11 | 0.427 |
| 24 | 120 | 9,654 | -0.004 | -3.704 | 48.7% | -0.02 | -14.68 | 0.513 |
| 48 | 240 | 3,937 | -0.296 | -3.996 | 48.4% | -0.68 | -9.48 | 0.733 |
| 78 | 390 | 1,980 | +1.513 | -2.187 | 50.5% | 2.24 | -4.07 | 0.017 |

**My registered prediction was wrong in the most informative way available.** I predicted
the edge would rise monotonically with `q`, roughly as `sqrt(q)`, peaking near $1.50 at the
session horizon. It does the opposite: it is largest at `q = 1` and **decays to zero by 60
minutes**, going negative at two and four hours.

That decay is the finding. An edge that scales as `sqrt(q)` is a real forecast of price. An
edge that lives entirely in the first bar and vanishes within an hour is microstructure.

## What it is: bid-ask bounce

Transaction prices alternate between the bid and the ask. That alternation manufactures
negative first-order autocorrelation in a series with no forecastable structure whatsoever.
Roll (1984) gives the arithmetic: bounce implies `cov(r_t, r_{t-1}) = -s^2 / 4`, so the
effective spread can be recovered from the autocovariance.

Measured on this data:

| | |
|---|---|
| lag-1 autocovariance of price changes | **-0.02634 pt²** |
| Roll implied effective spread | **0.3246 pt = 1.30 ticks** |
| ES tick size | 0.25 pt |
| implied spread in dollars, 1 MES | **$1.62** |

**1.30 ticks is exactly what ES's effective spread should be**: one tick quoted, plus a
little impact. The estimator recovers the real number from the "signal."

The `q = 1` edge is **$0.205 a trade. The spread generating it is $1.62.** The apparent
opportunity is eight times smaller than the cost of the mechanism producing it. You would be
paying the spread to harvest a statistic *made of* the spread.

### The decisive test: delay execution by one bar

A genuine price inefficiency does not evaporate in five minutes. Bounce lives entirely in
the immediately adjacent print, so delaying execution by a single bar should destroy it and
leave any real forecast intact.

| q | no delay | t | 1-bar delay | t | 2-bar delay | t |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | +0.205 | 19.36 | **+0.049** | 3.61 | **+0.011** | 0.72 |
| 2 | +0.161 | 8.15 | +0.056 | 2.56 | -0.024 | -0.96 |
| 3 | +0.181 | 6.30 | +0.011 | 0.35 | -0.049 | -1.43 |
| 6 | +0.049 | 0.87 | +0.085 | 1.47 | +0.117 | 1.94 |
| 12 | +0.019 | 0.16 | +0.053 | 0.47 | +0.193 | 1.74 |

**76% of the edge is gone after one bar of delay. 95% after two.** t collapses from 19.36 to
0.72. Nothing survives that is distinguishable from zero.

Two independent lines of evidence, Roll's estimator and the delay test, give the same
answer. **The z = -7.8 mean reversion measured in the diagnostic is the bid-ask spread.
There is no tradeable short-horizon reversion in ES.**

## The q = 78 exception is noise

The session-length fade shows +$1.513 at t 2.24, breaking the decay pattern. It fails on
p (0.017 against a required 0.00625) and it is the most concentrated result in the table
after trimming: `t-5%` of **-4.07**. On 1,980 trades, following seven horizons that decay
smoothly toward zero, a single out-of-pattern positive is what noise looks like. I am not
going to build on it, and the pre-registration forbids adding a ninth horizon to chase it.

## A criterion that stopped meaning what it meant

Every `t-5%` in the table is heavily negative, down to -44.83. That is not eight independent
condemnations. **The concentration criterion does not transfer to samples this large.** It
was designed to catch "one good month" in a few-hundred-trade arm. At 219,867 trades,
deleting the top 5% removes 11,000 observations from a fat-tailed, near-zero-mean
distribution, and the result is guaranteed negative regardless of whether an edge exists.

Recording this as a limitation of my own decision rule rather than quietly leaning on it.
The criterion did no work here. **The binding facts are the raw magnitudes and the delay
test**, neither of which needs it.

## What this closes

The arithmetic that motivated the sweep still holds: edge scales as `sqrt(time)`, cost does
not scale, so `edge / cost` is monotone increasing in holding period. The sweep was built to
find the horizon where that crossover happens.

**There is no crossover, because there is no edge to scale.** The only statistically
overwhelming signal in the series is an artifact of the spread, and it is the one thing that
does *not* grow with holding time. Everything at a horizon long enough to matter measures
zero: `q = 6` through `q = 48` span $+0.049 to $-0.296 on 75,000 trades combined.

This closes **ES-only, price-only, directional intraday strategies at 5-minute to 4-hour
horizons** with a mechanism rather than a body count. That is the family containing all
forty-three prior cells. They did not fail through bad luck or bad parameter choices. They
failed because the thing they were all trying to time is not there.

## Prediction scorecard

Ninth registered prediction.

| claim | outcome |
|---|---|
| every horizon positive raw | **wrong**, q = 24 and 48 are negative |
| no horizon clears $3.70 | **correct** |
| mean rises monotonically with q, peaking $0.50-$2.50 at q = 48-78 | **wrong, and this was the point** — it decays from the first bar |
| t-statistics enormous at small q and misleading | **correct**, t = 19.36 on a $0.205 edge |
| probability any horizon clears cost under 10% | none did |

I predicted the right verdict from the wrong model. I assumed a real forecast that was
merely too small; it is not a forecast at all. Across nine predictions the pattern is now
unmistakable: **correct on outcome, wrong on mechanism, nearly every time.**

## Where this leaves the count

**Fifty-one cells closed, zero passes.**

Three structures are significantly negative (VWAP reversion t -2.80, inverted fair value gap
t -2.86, Asia-to-London breakout t -2.09 gross) and the one significantly positive structure
turns out to be the spread.

## What is genuinely still open

Stated precisely, because "keep trying things" is not a plan and the closed family is now
large.

1. **Cross-sectional relative value.** Every cell so far is a single-instrument directional
   bet. A spread between two correlated instruments is a different object: much of the
   common noise cancels, and bid-ask bounce is idiosyncratic to each leg rather than shared.
   Untested here. GC, SI and HG 30-minute data covering 2008-2016 is already on disk and has
   never been used for anything but an opening-range breakout.
2. **Longer horizons, where the cost arithmetic is least hostile.** At 5 minutes a round
   turn is a large fraction of the bar's whole move. Over a session it is a few percent of
   the range. The session-level variance ratio was 0.926 at z = -2.1, which is weak but is
   the only place the geometry favours us.
3. **Information other than price.** Volume is in every row of this dataset and has been
   used only as a roll-selection input. Order-flow imbalance is a different input class from
   everything tested so far, all of which was a transformation of OHLC.

2017-2023 remains undownloaded and untouched.
