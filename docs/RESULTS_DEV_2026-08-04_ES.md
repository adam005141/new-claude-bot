# Development Result: Leg B on 3 Years (ES proxy)

**Run date:** 2026-08-04
**Engine version:** 0.1.0
**Split:** development, 387 sessions (2023-08-03 to 2025-01-31) of a 774-session sample
**Data:** Barchart 1-minute, 13 ES dated contracts, prices from ES, economics from MES
**Costs:** measured from MES BID/ASK quotes, adverse scenario, $4.95 round trip
**Ledger:** run 9, registered before execution
**Evidence level:** development / in-sample. Validation and lockbox remain **UNTOUCHED**.

---

## Verdict

**Leg B has a NEGATIVE edge. Not an undetectable one. A negative one.**

This is the first run in the project to clear the 200-trade gate, so it is evidence
rather than the absence of evidence.

| | 11-month MES (run 1) | 3-year ES proxy (run 9) |
|---|---:|---:|
| Trades | 72 | **264** |
| Expectancy | +$3.60 | **-$10.91** |
| Expectancy R | +0.043 | **-0.127** |
| Profit factor | 1.07 | **0.79** |
| 95% CI on expectancy | [-20.13, +25.93] | **[-22.75, +0.21]** |
| Clears 200-trade gate | No | **Yes** |

The earlier interval straddled zero symmetrically, which is what "we cannot tell" looks
like. This one sits almost entirely below zero, with its upper bound essentially on it.

---

## The finding that settles it

| | USD |
|---|---:|
| Net | -2,880.85 |
| Commissions | +549.60 |
| Embedded spread and slippage (458 contract round trips) | +1,717.50 |
| Total modelled cost | 2,267.10 |
| **Gross before ANY cost** | **-613.75** |

**The strategy loses money before paying a single cent of cost.**

Every previous discussion in this project treated cost as the thing standing between Leg B
and viability. That framing is now dead. Strip out commission, spread, and slippage
entirely, hand the strategy perfect free execution, and it still loses $614 over 264
trades. There is no edge for costs to eat.

---

## Why this negative is robust

**It is not one bad day.** Top-5 concentration is 9.2%, against 24.5% on the 11-month run.
Removing the best days makes it *worse*, not better:

| | Net |
|---|---:|
| All trades | -2,880.85 |
| Excluding top 1 day | -3,261.15 |
| Excluding top 3 days | -3,784.05 |
| Excluding top 5 days | -4,248.88 |

A result driven by a handful of lucky sessions collapses when they are removed. This one
deepens, which means the loss is spread across the whole sample.

**It is not one contract.** Six of seven are negative:

| Contract | Trades | Expectancy | PF |
|---|---:|---:|---:|
| 202312 | 57 | -14.02 | 0.74 |
| 202406 | 53 | -9.53 | 0.82 |
| 202409 | 52 | -0.86 | 0.98 |
| 202403 | 48 | -23.72 | 0.63 |
| 202412 | 27 | -4.92 | 0.89 |
| 202503 | 21 | -26.61 | 0.49 |
| 202309 | 6 | +49.88 | 2.71 |

The only positive bucket has six trades.

**It is not one direction.** Shorts PF 0.72, longs PF 0.90. Both lose. The earlier
long/short asymmetry that looked like captured drift does not survive a longer sample,
which supports the drift explanation over the edge explanation.

**It is not a regime.** Three years spanning 2023 to 2025 contains materially different
volatility conditions, which the original 11-month sample did not.

---

## Prop mode: the account dies

Same strategy, $2,000 buffer applied:

- **HALTED_PERMANENT after 110 of 387 sessions (28%).**
- MLL breached roughly five months in.
- Expectancy over the truncated path: -$15.96, profit factor 0.72.

Those 71 trades are path-truncated and conditioned on surviving that far, so they are
reported only to document that the account fails, not as a performance measure. The
personal-mode figures above are the research result.

---

## Proxy validity

Prices came from ES rather than MES. The substitution was measured before use, not
assumed: **1.19% trigger disagreement** on the 230-session overlap, against a 2% threshold
fixed in the tool beforehand, with **zero opposite-direction firings**.

A 1.19% signal difference cannot flip a result this broad. If anything the proxy question
is now moot: a strategy that is negative before costs across seven contracts, both
directions, and three years is not one tick of basis away from working.

---

## What this changes

**Leg B is closed.** Not "underpowered", not "needs more data". Tested at n=264 with
measured costs across three years, it has a negative gross edge.

The two remedies discussed earlier are both now irrelevant:

- **More history** would sharpen an estimate that is already decisively negative.
- **Better cost data** cannot help something that loses before costs.

The opening-range breakout thesis in SPECIFICATION.md section 2 predicted that overnight
information is repriced at the open and the first range establishes a reference that
triggers momentum flow. The competing explanation listed alongside it was that volatility
clustering alone produces apparent breakout profits in trending samples. Three years of
data support neither: the setup does not produce profits at all, apparent or otherwise.

---

## Splits

| Split | Status |
|---|---|
| development | used (runs 1-10) |
| validation | **UNTOUCHED** |
| lockbox | **UNTOUCHED**, single-use |

There is no case for spending the validation split on a strategy with a negative gross
edge on development data. Validation exists to check whether a promising result survives
out of sample. Nothing here is promising.

---

## Reproduction

```bash
python run_backtest.py --data data --split dev --symbols MES --price-source ES \
    --measured-costs config/measured_costs.json --no-prop --report out    # research
python run_backtest.py --data data --split dev --symbols MES --price-source ES \
    --measured-costs config/measured_costs.json --report out              # prop
```

Engine 0.1.0, commit `1d834ac`. Configuration fingerprint, data provenance, and the
`terminated_early` flag are recorded in `out/summary_dev_adverse.json`.

**Parameters were unchanged from runs 1-8 and frozen before this data was seen.** No
parameter has been tuned against any result at any point in this project.
