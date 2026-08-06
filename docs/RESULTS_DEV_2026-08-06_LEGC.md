# Development Result: Leg C (opening gap fade), and the arithmetic that closes the framework

**Run date:** 2026-08-06
**Engine version:** 0.1.0
**Split:** development, 387 sessions, prices from ES, economics from MES
**Costs:** measured MES BID/ASK, adverse, all-day, $4.95 round trip
**Ledger:** runs 12 (screen) and 13 (Leg C), both registered before execution
**Evidence level:** development. Validation and lockbox remain **UNTOUCHED**.

---

## Verdict

**Leg C is the worst of the three, and this time the sample clears the gate.**

| | Leg B momentum | Leg A fade | **Leg C fade** |
|---|---:|---:|---:|
| Trades | 264 | 177 | **236** |
| Expectancy R | -0.127 | -0.266 | **-0.432** |
| Profit factor | 0.79 | 0.69 | **0.57** |
| Win rate | - | 34.5% | **24.6%** |
| Payoff ratio | - | 1.31 | **1.76** |
| 95% CI expectancy | [-22.75, +0.21] | [-39.57, -1.44] | **[-49.97, -15.52]** |
| Clears 200-trade gate | Yes | No | **Yes** |
| Annualised Sharpe | - | -3.23 | **-3.85** |

The interval excludes zero by a wide margin. It is negative in **all seven** contracts, in
both directions, and deepens when the best days are removed. Gross before any cost it
loses **$3,969**, which is **-$16.82 per trade** against Leg A's -$9.40 and Leg B's -$2.32.

Per the pre-commitment registered before the run: dev expectancy is negative, so **Leg C is
closed and no validation split is spent.**

---

## The finding that ends the framework, not just the leg

For a driftless random walk with stop distance `S` and target distance `T`:

```
P(target first)      = S / (S + T)
break-even win rate  = 1 / (1 + T/S)   =   S / (S + T)
```

**These are the same expression.** A random walk breaks even at *every* stop and target
geometry. Widening the stop raises the win rate and lowers the payoff by exactly
offsetting amounts.

The consequence is not a rule of thumb, it is arithmetic: **the sign of a strategy's edge
before costs depends on one number only, the gap between its realised target-first rate
and `S/(S+T)`.** Stop width, target distance, reward-to-risk, and position size cannot
change that sign. They only scale it.

Measured on both fade legs:

| | payoff | random-walk baseline | observed target-first | **shortfall** | z |
|---|---:|---:|---:|---:|---:|
| Leg A, fade VWAP excursion | 1.31 | 43.4% | 29.1% (43/148) | **-14.3 pp** | -3.51 |
| Leg C, fade the opening gap | 1.76 | 36.3% | 21.5% (48/223) | **-14.8 pp** | -4.58 |

Two setups with different anchors, different triggers, different payoff ratios, different
sample sizes, and different information sets. **The shortfall replicates to within half a
percentage point.**

### What this rules out

It rules out the entire remedy list this project has been working through:

- **Wider stops cannot help.** At a 4x ATR stop the baseline rises to roughly 60% and the
  break-even win rate rises to roughly 60% with it. A -14.8 pp shortfall stays -14.8 pp.
- **Better reward-to-risk cannot help.** Same identity.
- **A cheaper instrument cannot help.** Cost scales a negative number.
- **Wider or tighter targets cannot help.**

The cost-hurdle work in `RESULTS_DEV_2026-08-06_COST.md` measured a real 6x reduction
available from geometry and instrument choice. That reduction is still real, and it is
still irrelevant to every leg tested, because all three are negative *before* cost.

**This is the reason not to run a wide-stop variant of Leg C.** It would be trial 4, and
the arithmetic says in advance what it returns.

---

## The screen and the strategy disagree, and the disagreement is the point

The extended screen, 460 cells with the overnight family added, returned its **best cell on
the gap feature, pointing in the direction Leg C bets:**

| feature | horizon | bin | n | mean pts | vs cost | t |
|---|---:|---:|---:|---:|---:|---:|
| `gap_vs_on_range` | 120 min | 3 (gapped up) | 3,785 | **-2.38** | 2.41x | -7.84 |
| `gap_vs_on_range` | 120 min | 1 (gapped down) | 3,767 | **+1.69** | 1.71x | +6.30 |

Gap up is followed by a downward drift, gap down by an upward one, at more than twice the
round trip. That is the gap-fade thesis, and it is the largest effect in the whole screen.

**It is still not significant**, and this is exactly the case the family-wise null exists
for. Across all three null constructions the p-values are 0.375, 0.630 and 0.770. Nothing
here beats what permuting the target produces across 460 cells.

But suppose for a moment it were real. **Leg C still loses**, and the two facts fit
together perfectly:

> A favourable **mean** with an adverse **path**.

The screen measures where price is after 120 minutes with no stop in the way. Leg C has a
1.5x ATR stop, and price hits it first on 175 of 223 resolved trades. The occasional large
favourable move that lifts the mean is precisely the one the stop guarantees you are not
present for.

That is the "upper bound" caveat working as designed. It also says something sharper than
the caveat did: **an edge in the mean is not an edge, if the path gets there the wrong way
round.** Harvesting the screen's gap effect would require holding through unbounded
drawdown, which a $2,000 MLL forbids absolutely.

---

## My registered prediction: 1 of 3

| Claim | Outcome |
|---|---|
| The screen finds nothing at family-wise p < 0.05 | **Right** (0.375 to 0.770) |
| 150-190 trades, below the 200 gate | **Wrong.** 236 trades, 0.61/session. The gate cleared. |
| Expectancy indistinguishable from zero, CI straddling | **Wrong.** Decisively negative, CI excludes zero. |

I underestimated both the trade count and the size of the failure. Running record across
four registered predictions: right on direction three times out of four, wrong on
mechanism or magnitude most times. That record is why the pre-commitments matter more than
the predictions.

---

## Splits

| Split | Status |
|---|---|
| development | used (runs 1-13) |
| validation | **UNTOUCHED** |
| lockbox | **UNTOUCHED**, single-use |

---

## What the arithmetic says to do next

The only quantity that determines the sign of an edge is the target-first rate against
`S/(S+T)`. Every screen run so far has measured **means**, which is now demonstrably the
wrong statistic: `gap_vs_on_range` has the best mean in the project and a fatally adverse
path.

The measurement that has never been made is the direct one: **conditional on each feature,
does price touch the favourable barrier before the adverse one more often than
`S/(S+T)`?** That is mechanism-free, it needs no entry rule or parameter, and it is the
exact quantity that decides whether anything can work.

Registered as run 14 before building.

---

## Reproduction

```bash
python tools/forward_returns.py --data data --symbols MES --price-source ES \
    --measured-costs config/measured_costs.json --report out/forward_returns_v2.json
python run_backtest.py --data data --split dev --leg C --symbols MES --price-source ES \
    --measured-costs config/measured_costs.json --cost-session ALL --no-prop --report out
```

Engine 0.1.0, commit `c493142`. **Parameters were fixed from reasoning before the run and
have never been tuned against any result.**
