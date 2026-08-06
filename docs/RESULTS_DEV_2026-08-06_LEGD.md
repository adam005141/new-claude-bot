# Development Result: Leg D, the overnight hold

**Run date:** 2026-08-06
**Split:** development, 387 sessions, ES prices, MES economics, prop rules ON
**Costs:** measured MES BID/ASK, adverse, $4.95 round trip
**Ledger:** run 16, registered before the strategy was written
**Evidence level:** development. Validation and lockbox remain **UNTOUCHED**.

---

## It passed

**HALTED_TARGET after 327 of 387 sessions.** Balance $53,043.70 against a $53,000 target.
The first time anything in this project has reached the objective.

| | |
|---|---:|
| Trades | 299 |
| Win rate | 58.9% |
| Payoff ratio | 0.90 |
| Expectancy | **+$10.18** |
| Profit factor | 1.29 |
| Net | +$3,043.70 |
| Max drawdown | **$1,082.35**, 54% of the MLL buffer |
| Sharpe, annualised | **1.42** |
| Max losing streak | 6 |
| Disaster stop hits | **1 of 299** |

The profile is exactly what a risk premium looks like: win often, lose slightly bigger.
58.9% at a 0.90 payoff. Not the shape of a predictive signal, and it was not designed to be
one.

---

## Why this is not yet evidence

**The confidence interval straddles zero.**

| | 95% CI |
|---|---|
| Expectancy | **[-$2.85, +$22.72]** |
| Net | **[-$852.58, +$6,793.92]** |

A run that hits its target while its interval includes zero is a run that could have been
luck. That is the whole finding, and no amount of Sharpe makes it go away.

**And significance is not available from this dataset at all:**

| split | n | net t | one-sided p |
|---|---:|---:|---:|
| development (used) | 387 | 1.35 | 0.088 |
| validation | 232 | 1.05 | 0.147 |
| dev + validation | 619 | 1.71 | 0.043 |
| **everything, lockbox included** | 774 | **1.92** | 0.028 |

**Spending every session we own does not reach t = 2.** So the question this project can
actually answer is not "is the overnight effect real" but "does an account trading it
survive and pass, out of sample." Those are different questions, and only the second one
is available.

**The sample is a bull market.** A long-only overnight rule cannot separate the documented
overnight/intraday effect from 2023-2025 going up. That is not a caveat to be waved
through; it is the single most likely explanation for everything above.

---

## The prediction check: 2 of 3, wrong on the one that mattered

| Registered before the run | Outcome |
|---|---|
| The account survives the split | **Right** |
| Max drawdown exceeds half the MLL buffer | **Right**, $1,082 = 54% |
| It does NOT reach $3,000 inside 387 sessions | **Wrong.** Reached at session 327. |

Running record over five registered predictions: direction right most times, magnitude
wrong most times. Here I underestimated the result, which is the direction that should
make me more sceptical rather than less.

---

## What the run settled that I expected to be a problem

**The overnight spread is not wider.** `--cost-session ASIA` returned the same
0.990 points, $4.95, as the all-day figure. My stated biggest open risk was that entering
at 18:00 ET, the thinnest moment of the day, would cost materially more than the RTH-dominated
all-day number. Measured, it does not. MES quotes the minimum tick overnight.

The standing caveat still applies and matters more here than anywhere else: quoted spread
is a **lower bound**. Overnight top-of-book depth is a fraction of RTH, so a market order
for one contract is fine and the same order for five is not. This result does not scale.

**The disaster brake worked, once.** One stop in 299 trades, at -$562.45. Without it that
night was heading for the -$851 worst case in the decomposition. The brake is sized at
roughly four session standard deviations precisely so it never interferes with ordinary
variation, and it did not: 298 of 299 trades exited on the clock.

---

## Things that are structurally wrong with this result

**`expectancy R` of 0.020 is meaningless here.** R is defined as the disaster stop, $500,
which is not a risk unit. `mean risk deviation 400%` is the same artefact. Both are
correct arithmetic on a definition that does not apply to a scheduled exposure. Read
dollars, not R, for Leg D.

**The reported metrics are path-truncated**, because the run stopped when it won. Win rate,
expectancy and drawdown are all conditioned on reaching the target. The unconditioned
research number needs `--no-prop` over all 387 sessions and has not been produced yet.

**One contract is the only survivable size**, and that was established before the run:
worst night -$851 is 43% of the buffer at one contract, 85% at two, and fatal at three.
Seventeen months at one contract on the measured drift. The dev run beat that because the
sample cooperated, not because the arithmetic changed.

**162 `ROLL_OR_EXPIRY` rejections**, roughly 27 sessions where the roll guard blocked the
entry. Correct behaviour, and it costs about 7% of the opportunity.

---

## What happens next, decided before the numbers exist

Under the rule used to close Leg C, positive expectancy with a CI straddling zero means
**closed as undetectable, no validation spend.** Leg D does not automatically get an
exemption for being interesting.

But Leg D differs from A, B and C in a way that is about evidence rather than preference:
its prior comes from **outside this dataset**. The overnight/intraday decomposition is a
documented, decades-long property of equity indices, not something found by searching these
387 sessions. Legs A to C were hypotheses this project invented and then tested on the data
that suggested them. Leg D is a hypothesis the literature supplies and this data is
consistent with.

That is the only honest argument for spending validation, and it is an argument about
**mechanism**, not about the result being encouraging.

**Registered criteria for the validation run, fixed now.** Parameters frozen exactly as
they stand.

1. **Replication of the shape, not the profit.** Overnight positive and RTH flat or
   negative on the validation split, measured the same way. If the shape inverts, Leg D is
   closed regardless of P&L.
2. **Survival.** The account does not breach the MLL over the validation split at one
   contract.
3. **Expectancy positive.** Sign only. Significance is unavailable and will not be claimed.

All three, or Leg D is closed. Any one failing closes it. **The lockbox stays shut either
way**: it is single-use, and it is for a final go/no-go on a system whose rules are frozen,
not for a third look at an underpowered question.

---

## Reproduction

```bash
python run_backtest.py --data data --split dev --leg D --symbols MES --price-source ES \
    --measured-costs config/measured_costs.json --cost-session ALL \
    --fixed-contracts 1 --report out
```

Engine 0.1.0, commit `2591e3e`. Parameters were derived from the loss buffer and the clock
before the run and have never been tuned against a result.
