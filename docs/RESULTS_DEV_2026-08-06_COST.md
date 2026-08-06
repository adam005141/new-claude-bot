# Cost Hurdle Measurement

**Run date:** 2026-08-06
**Tool:** `tools/cost_hurdle.py`
**Data:** development split only. Two datasets: 3-year ES (proxy for MES) and the
11-month MES/MNQ history.
**Costs:** measured MES and MNQ BID/ASK quotes, adverse (p75) scenario, all-day.
**Trial count: unchanged.** This evaluates no signal, books no P&L, and consumes no
split. It is not a ledger entry.

---

## The identity

```
cost_in_R = cost_usd / risk_usd
          = (qty * round_trip_usd) / (qty * stop_points * point_value)
          = round_trip_points / stop_points
```

Quantity cancels exactly. Integer rounding, the 4-contract cap, and portfolio heat all
drop out, which is verified against `engine.sizing.size_position` in a test rather than
asserted. **The cost hurdle is set by two numbers only: the round trip in index points,
and the stop in index points.**

---

## Result 1: the hurdle at current settings is twice what I told you

I estimated 0.141R from Leg A's realised average risk. Measured against the median ATR it
is **0.286R** on the 3-year ES data.

Both numbers are correct and they measure different things. 0.141R is what the trades Leg A
*actually took* paid, and those clustered in unusually high-volatility conditions: the
implied stop was about 7 points against a median-ATR stop of 3.47. **0.286R is what a
median bar faces**, and that is the right number for designing a new strategy, because a
new strategy does not get to assume it will only fire on volatile bars.

The error came from using a realised average as if it were a population parameter. The
median 5-minute ES ATR is **2.31 points**, not the 6.0 I used as a placeholder.

---

## Result 2: the stop lever is far larger than I estimated

I said roughly 50%. Measured on 3-year ES data:

| stop | contracts | risk | **hurdle** |
|---|---:|---:|---:|
| 1.0xATR | 4 | $46 | 0.428R |
| **1.5xATR (both legs used this)** | 4 | $69 | **0.286R** |
| 2.0xATR | 4 | $92 | 0.214R |
| 3.0xATR | 2 | $69 | 0.143R |
| 4.0xATR | 2 | $92 | 0.107R |
| 6.0xATR | 1 | $69 | 0.071R |
| **8.0xATR** | 1 | $92 | **0.054R** |

**A 5.3x reduction, not 2x.** Dollar risk per trade is unchanged throughout; the position
shrinks as the stop widens. This is geometry, not risk-taking.

On the 11-month MES data the median ATR is higher (3.28 points) and the ceiling arrives
sooner: 1.5xATR gives 0.201R, the best tradable is 6.0xATR at 0.050R, and 8.0xATR is
refused because one contract would risk $131 against a $100 budget.

---

## Result 3: MNQ halves the hurdle, and the reason survives scrutiny

| | $/RT | pts/RT | median ATR | hurdle @1.5xATR | best tradable |
|---|---:|---:|---:|---:|---:|
| MES | 4.95 | 0.990 | 3.28 | 0.201R | 0.050R |
| MNQ | 4.70 | 2.350 | 16.42 | **0.095R** | 0.048R |

MNQ's round trip is 2.35 points against a 16.42-point ATR, a ratio of 0.143. MES's is 0.99
against 3.28, a ratio of 0.302. **NQ's tick is finer relative to its own volatility.** That
is a property of the contract specifications, not of any assumption we made.

### The part of that comparison that is NOT safe

The tool prints `MNQ is cheaper on both measures`. **The dollar half of that is an
artefact and should not be used.**

The spread in these models is measured. The slippage allowance is a prior, and it is
denominated in **ticks**: 0.5 ticks per side on everything. A tick is $1.25 on MES and
$0.50 on MNQ, so an identical nominal allowance charges MES **two and a half times more in
dollars** for no reason grounded in observation.

That assumption decides the dollar ranking:

| slippage denomination | MES $/RT | MNQ $/RT | cheaper |
|---|---:|---:|---|
| 0.5 ticks/side (current prior) | 4.95 | 4.70 | MNQ |
| $0.625/side on both | 4.95 | 5.45 | **MES** |

**The ranking flips.** On measured components alone MNQ's spread is $1.50/side against
MES's $1.25/side, so MNQ is the wider quote in dollars as well as in ticks; it only looks
cheaper overall because we hand it a smaller slippage allowance by accident of
denomination.

The R comparison does survive:

| slippage denomination | MES @1.5xATR | MNQ @1.5xATR |
|---|---:|---:|
| 0.5 ticks/side | 0.171R | 0.095R |
| $0.625/side on both | 0.201R | 0.111R |

MNQ is roughly half MES's hurdle under either. `tools/cost_hurdle.py` now runs this
sensitivity automatically and prints a warning when a ranking flips, so this class of
error is caught by the tool instead of by rereading its output.

---

## Result 4: the two goals fight each other

Widening the stop cuts the hurdle. It also lengthens holding time: for a random walk, time
to travel a distance scales as the square of that distance, so 1.5xATR to 3.0xATR is
roughly 4x the expected time to resolution. With `max_bars_in_trade` at 24, most of those
trades would exit on the time stop instead of at a stop or target, and a time-stop exit is
close to a coin flip.

Raising the bar cap fixes that and reduces trades per session, which lowers n, which raises
the detection floor. **Cutting the cost hurdle costs sample size.** How much is measurable
and has not been measured.

---

## Where this leaves the project

| | before | after |
|---|---:|---:|
| Cost hurdle | 0.286R (MES, 1.5xATR) | **~0.048R** (MNQ, 3xATR) |
| Detection floor, all 774 sessions | ~0.12R | **~0.12R, unchanged** |

The hurdle moved by roughly 6x. The detection floor did not move at all, because 774
sessions is 774 sessions regardless of how trades are sized.

The practical meaning: a strategy with a true gross edge of 0.10R was guaranteed to lose
money before and would now clear costs with 0.05R to spare. That is a real change in what
is *tradable*. It is not a change in what is *provable* on this data, and those two must
not be confused. Getting the detection floor down needs more history or more trades per
session, and that is a different problem.

**Nothing here rescues Leg A or Leg B.** Both were negative before costs. A lower hurdle
multiplies a negative number by a smaller constant.
