# Development Result: Leg A (VWAP band reversion) on 3 years, ES proxy

**Run date:** 2026-08-06
**Engine version:** 0.1.0
**Split:** development, 387 sessions (2023-08-03 to 2025-01-31) of a 774-session sample
**Data:** Barchart 1-minute, 13 ES dated contracts, prices from ES, economics from MES
**Costs:** measured from MES BID/ASK quotes, adverse, all-day session, $4.95 round trip
**Ledger:** run 11, registered before the code was written
**Evidence level:** development / in-sample. Validation and lockbox remain **UNTOUCHED**.

---

## Verdict

**Leg A fails. It is worse than Leg B, and it fails at n=177, below our own 200-trade gate.**

| | Leg B (run 10) | Leg A (run 11) |
|---|---:|---:|
| Trades | 264 | 177 |
| Trades per session | 0.68 | 0.46 |
| Win rate | - | 34.5% |
| Payoff ratio | - | 1.31 |
| Expectancy | -$10.91 | **-$20.70** |
| Expectancy R | -0.127 | **-0.266** |
| Profit factor | 0.79 | **0.69** |
| 95% CI on expectancy | [-22.75, +0.21] | **[-39.57, -1.44]** |
| Annualised Sharpe | - | **-3.23** |
| Clears the 200-trade gate | Yes | **No** |

---

## What the sample size does and does not permit

The engine printed `SAMPLE BELOW GATE: 177 < 200 trades. Not evidence.` That gate is
ours, it was set before any of this, and it applies here.

**It constrains the statistical claim.** The nominal 95% CI on expectancy is
[-39.57, -1.44], which excludes zero, but this is the **second distinct configuration** in
the project. Under the multiple-testing correction registered in SPECIFICATION.md section
18.3, two trials at a family-wise 0.05 requires roughly a 97.5% interval, and the upper
bound of -1.44 does not survive that widening. **Leg A's negative is not statistically
decisive.**

**It does not constrain the accounting.** The cost decomposition below is arithmetic on
the 177 observed trades, not an inference about a population.

---

## The cost decomposition

| | USD |
|---|---:|
| Net | -3,664.17 |
| Commissions (404 contract round trips) | +484.80 |
| Embedded spread and slippage | +1,515.00 |
| Total modelled cost | 1,999.80 |
| **Gross before ANY cost** | **-1,664.38** |

**Leg A loses $9.40 per trade before paying anything.** Leg B lost $2.32 per trade before
costs. On the same data, the same risk framework, and the same three years, the reversion
setup is four times worse per trade than the breakout it replaced.

**Caveat, stated because it also applies retroactively to Leg B.** Shifting the bootstrap
CI by the modelled cost puts the 95% interval on the gross figure at roughly
[-5,167, +1,744], which straddles zero. The same is true of Leg B's -$613.75. The
gross-before-cost number is a fact about the observed trades and is the right thing to
look at, but neither leg's gross figure is on its own statistically distinguishable from
zero. `RESULTS_DEV_2026-08-04_ES.md` called that figure "the finding that settles it" for
Leg B; that was the right conclusion resting partly on the wrong sentence. What settles
both legs is the total weight of the evidence below, not that single number.

---

## The finding that is actually decisive

The strategy resolved 148 trades at either its stop or its target: **43 targets against
105 stops, a 29.1% target-first rate.**

The observed payoff ratio is 1.31, so break-even requires a 43.4% hit rate. For a
driftless random walk on the same stop and target geometry, the probability of touching
the target first is also about 43%. **Leg A hit its target 29.1% of the time against a
coin-flip baseline of 43.4%**, a gap of 14 percentage points, z = -3.51.

This is not "no edge". It says that after a 2-sigma excursion followed by a reclaim, price
continued in the direction of the excursion **more often than chance**. The setup is
mildly anti-predictive.

**Confound, stated rather than buried.** Our execution model is deliberately pessimistic
in ways that push in exactly this direction: a bar spanning both stop and target always
resolves to the stop, and a stop fills at the worse of its price and the next bar's open.
Both bias the target-first rate downward. I cannot separate the mechanical component from
the signal component without per-trade path data, so I will not claim the whole 14 points
is signal. The direction of the finding is safe; its magnitude is not.

---

## Why this negative is robust

**It is not one lucky or unlucky stretch.** Removing the best days makes it worse, exactly
as Leg B did:

| | Net |
|---|---:|
| All trades | -3,664.17 |
| Excluding top 1 day | -4,247.45 |
| Excluding top 3 days | -4,909.00 |
| Excluding top 5 days | -5,454.88 |

**It is not one contract.** Six of seven are negative. The only positive bucket, 202403,
has 33 trades and +$510.

**It is not one direction.** Longs PF 0.66, shorts PF 0.71. Both lose, and by similar
amounts. This is the same pattern as Leg B, and it is the pattern you get when there is no
edge rather than when a filter is mistuned.

**The regime filter was doing its job, and it was not enough.** `NOT_RANGE_REGIME`
rejected 448 setups against 177 taken, so the classifier removed roughly 57% of the
directional setups it saw. The leg still lost. Removing the filter would produce more
trades of the same negative quality, not a better result.

---

## My registered prediction was half wrong

Recorded before the run: *"Leg A is negative or indistinguishable from zero on a
cost-adjusted basis, and the binding failure is the expected-move floor rather than the
signal. I expect the `MOVE_FLOOR` rejection counter to exceed the trade count."*

| Claim | Outcome |
|---|---|
| Negative or indistinguishable from zero | **Right** |
| Fewer trades than Leg B | **Right** (0.46/session vs 0.68) |
| `MOVE_FLOOR` exceeds the trade count | **Badly wrong: 4 against 177** |
| The binding failure is the cost floor | **Wrong. The binding failure is the signal.** |

I expected the distance from a 2-sigma excursion back to VWAP to be too small to clear a
$4.95 round trip. It was almost never too small: the floor rejected 4 setups out of
roughly 785 evaluated. The reversions were plenty large enough to pay for themselves. They
simply did not happen often enough, and the market continued more often than it reverted.

That is the third prediction this project has falsified by measurement. The running record
is in the ledger.

---

## The constraint that no new strategy fixes

This is the most useful number in the document.

**Cost hurdle:** $11.30 per trade at the observed 2.28 contracts, against a mean risk unit
of $80.20. **Every strategy in this framework must produce 0.141R of gross edge per trade
before it breaks even.**

**Detection floor:** the full sample is 774 sessions. At the 0.5 trades/session both legs
produced, using *every* split including the lockbox yields roughly 390 trades, where the
minimum detectable edge is about **0.12R**.

Those two numbers are the same size. The smallest edge this dataset can confirm is
approximately the same as the smallest edge worth trading. There is no room between them.

The consequence is concrete: a strategy with a true gross edge of 0.20R, which would be
genuinely excellent for 5-minute index futures, nets 0.06R after costs and would need
several thousand trades to be distinguished from zero. **This dataset cannot certify a
realistic winner.** It can only reject clear losers, which is exactly what it has now done
twice.

---

## What two failures mean together

Leg B is momentum continuation. Leg A is mean reversion. They are opposite bets on the
same price series, and both lost before costs on the same three years. That is not two
unlucky strategies. What has actually been tested and found wanting is the framework they
share:

- 5-minute decision bars
- next-bar market entry, so the signal bar's move is always given away
- an ATR-scaled stop with a fixed target and a 24-bar cap
- a directional bet resolved within the session

A third signal inside that framework is a third draw from the same urn, and the power
analysis above says we could not confirm a win even if we drew one.

---

## Splits

| Split | Status |
|---|---|
| development | used (runs 1-11) |
| validation | **UNTOUCHED** |
| lockbox | **UNTOUCHED**, single-use |

Neither leg comes close to justifying the validation split.

---

## Reproduction

```bash
python run_backtest.py --data data --split dev --leg A --symbols MES --price-source ES \
    --measured-costs config/measured_costs.json --cost-session ALL --no-prop --report out
```

Engine 0.1.0, commit `9dd9900`. Configuration fingerprint and data provenance are in
`out/summary_legA_dev_adverse.json`.

**Parameters were taken verbatim from SPECIFICATION.md sections 7 and 8, dated
2026-07-31, before any data existed in this project. Nothing has been tuned against any
result at any point.**
