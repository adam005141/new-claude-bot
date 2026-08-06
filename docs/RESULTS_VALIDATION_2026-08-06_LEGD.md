# Validation Result: Leg D is closed

**Run date:** 2026-08-06
**Split:** validation, 232 sessions (2025-02-03 to 2025-12-24). **Now spent.**
**Ledger:** run 17, criteria registered before execution
**Lockbox:** **UNTOUCHED**, and there is nothing to spend it on.

---

## All three pre-registered criteria failed

The criteria were fixed in the ledger before this ran, precisely so they could not be
adjusted after seeing the result.

| # | Criterion | Outcome |
|---|---|---|
| 1 | Shape replicates: overnight positive, RTH flat or negative | **FAIL. It inverted.** |
| 2 | Survival: no MLL breach at one contract | **FAIL. Account died at session 25 of 232.** |
| 3 | Expectancy positive | **FAIL. -$49.05, profit factor 0.37.** |

The rule was all three or the leg closes. **Leg D is closed.**

---

## The shape did not just weaken. It inverted.

Backing validation out of the two cumulative decomposition runs:

| window | dev (387) | **validation (232)** | validation net $/session |
|---|---:|---:|---:|
| GLOBEX_TO_OPEN | +2.683 pts | **+0.869 pts** | **-$0.61** |
| RTH | -0.333 pts | **+1.665 pts** | +$3.37 |
| POST_CLOSE | +0.028 pts | +0.756 pts | -$1.17 |
| FULL_SESSION | +2.383 pts | +3.298 pts | +$11.54 |

**On validation the cash session beat the overnight, and the overnight did not clear its
own round trip.** The entire premise of Leg D was that returns accrue outside RTH. Over the
following eleven months they accrued inside it.

That is not a smaller edge. It is the opposite arrangement.

---

## The account died in five weeks

**HALTED_PERMANENT after 25 of 232 sessions, 11% of the split.**

| | dev | validation |
|---|---:|---:|
| Win rate | 58.9% | 44.0% |
| Payoff ratio | 0.90 | 0.48 |
| Avg loss | -$89 | **-$140** |
| Expectancy | +$10.18 | **-$49.05** |
| Profit factor | 1.26 | **0.37** |
| Max drawdown | $1,082 | **$1,510** |

The average loss grew by 57% while the average win shrank. That is the signature the
design document predicted in advance and I still failed to price: *"a premium pays until
it does not."* Leg D was written down as compensation for bearing overnight risk. In
validation the risk arrived and collected.

My Monte Carlo put P(breach) at 23% over 387 sessions at one contract. The real path
breached in 25. The model assumed normal returns; the caveat that "the real fat left tail
makes this optimistic" turned out to be doing more work than the estimate.

---

## My prediction: 0 for 3

Registered before the run: *"The shape replicates (overnight positive, RTH negative), the
account survives, and validation expectancy is positive but smaller than development's
$10.18."*

Every part wrong. Across six registered predictions in this project the record is now
roughly half right on direction and consistently wrong on magnitude, in both directions.
That is the argument for pre-committing to decision rules rather than to forecasts: the
rules held here, and they closed a leg that a discretionary reading would have kept alive
on a 1.42 Sharpe and a Combine pass.

---

## The thing I am not going to do

`FULL_SESSION` returned **+$11.54 net per session on validation**, better than anything Leg
D produced on development. It is in the table above because leaving it out would be
selective reporting.

It is not a lead, for three reasons, and they are worth stating because chasing it is the
obvious temptation:

1. **It would be fitted to validation.** That split is now spent. Building a leg because a
   number in it looked good is exactly the failure mode the split structure exists to
   prevent, and it would leave only the lockbox to test it, which is a single-use resource
   that cannot carry a hypothesis derived from the data next door.
2. **Its gap risk is unsurvivable.** Worst single session -$1,606 at one contract, **80% of
   the entire MLL buffer**, against -$851 for the overnight window. One session at 80% of
   the buffer plus any ordinary drawdown is an account.
3. **It is the same bet with a longer leash.** A 23-hour hold is more equity beta, not
   different evidence. Dev and validation disagree about which slice of the day carries
   the return, which is what "no stable structure" looks like.

---

## Where the project stands

| leg | thesis | n | result |
|---|---|---:|---|
| B | opening range breakout | 264 | -0.127R, closed |
| A | VWAP band reversion | 177 | -0.266R, closed |
| C | opening gap fade | 236 | -0.432R, closed |
| **D** | **overnight risk premium** | **299 dev / 25 val** | **passed dev, died in validation, closed** |

Two mechanism-free screens found nothing: conditional mean forward returns (family-wise p
0.375 to 0.965) and conditional path expectancy, where the best positive cell of 270 was
1.6% of the cost hurdle.

**Splits:**

| split | status |
|---|---|
| development | used, runs 1-16 and 18 |
| validation | **SPENT** on run 17 |
| lockbox | **UNTOUCHED**, single-use |

The lockbox remains unopened and there is no candidate that has earned it. Opening it now
would not be a test of anything; it would be a fourth look at a question this dataset has
already answered four times.

---

## What Leg D actually demonstrated

Not that the overnight effect is fake. The literature on it is older and broader than these
774 sessions, and this project never had the power to overturn it: the net t-statistic was
1.35 on development and would have been 1.92 using every session we own, including the
lockbox. Significance was never available.

What it demonstrated is narrower and more useful:

**A documented risk premium, harvested at the only size a $50,000 evaluation account can
carry, does not survive that account's trailing drawdown rule.** The premium is real
enough. The $2,000 buffer is too small to sit through the risk you are being paid to bear.
Those two facts are compatible, and together they close the strategy without needing the
effect to be false.

---

## Reproduction

```bash
python run_backtest.py --data data --split validation --leg D --symbols MES \
    --price-source ES --measured-costs config/measured_costs.json --cost-session ALL \
    --fixed-contracts 1 --report out
python tools/session_decomposition.py --data data --symbols MES --price-source ES \
    --measured-costs config/measured_costs.json --dev-fraction 0.80
```

Engine 0.1.0, commit `c0c56c3`. Parameters were frozen after the development run and were
not touched before validation.
