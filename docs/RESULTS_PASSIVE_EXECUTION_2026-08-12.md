# Results: passive execution fails, and the search is over

Run 2026-08-12 against `docs/PREREGISTRATION_2026-08-12_PASSIVE_EXECUTION.md`. Micro silver,
Asian session, 3,109 signals, 2009-2016.

**All seven cells FAIL.** The pre-registration contained a stopping rule and this result
triggers it.

## A void first run, disclosed

The first execution of this tool had the limit resting on the **wrong side** of the market:
a short offered below rather than above. The bug was caught by the pre-registered
expected-fill-rate check, not by inspection — fill rates came back **84%, 95%, 99%, rising
with `m`**, when resting further from the market must fill *less* often.

That run is void and its numbers are not reported. This is the third implementation defect
the fill-rate/take-rate check has caught (after TREND4H's truncated lookback and two
collinear filters). It has now earned its place three times over.

## The table

| arm | m | signals | fill% | expected | $/signal | $/fill | **unfilled CF** | t | p | RT | net |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| TAKE | 0 | 3,109 | 100% | - | +7.29 | +7.29 | - | 3.20 | 0.0000 | 31.20 | -23.91 |
| PASSIVE-ENTRY | 0 | 3,109 | 84% | 85-95% | +1.11 | +1.32 | **+38.43** | 0.52 | 0.275 | 16.20 | -15.09 |
| PASSIVE-ENTRY | 1 | 3,109 | 73% | 70-85% | +2.21 | +3.01 | **+32.68** | 1.05 | 0.138 | 16.20 | -13.99 |
| PASSIVE-ENTRY | 3 | 3,109 | 52% | 40-65% | +2.72 | +5.27 | **+25.44** | 1.40 | 0.109 | 16.20 | -13.48 |
| PASSIVE-BOTH | 0 | 3,109 | 84% | 85-95% | -3.01 | -3.58 | **+38.43** | -1.38 | 0.924 | 1.20 | -4.21 |
| PASSIVE-BOTH | 1 | 3,109 | 73% | 70-85% | -0.31 | -0.42 | **+32.68** | -0.14 | 0.515 | 1.20 | -1.51 |
| PASSIVE-BOTH | 3 | 3,109 | 52% | 40-65% | +1.73 | +3.34 | **+25.44** | 0.87 | 0.190 | 1.20 | **+0.53** |

TAKE reproduces run 34 at +$7.29 against +$7.22, which validates that the signal was not
disturbed.

## The counterfactual column is the entire result

**At every value of `m`, the signals you fail to fill are worth several times the ones you
catch.**

| m | fill rate | filled mean | unfilled counterfactual | ratio |
|---:|---:|---:|---:|---:|
| 0 | 84% | +$1.32 | **+$38.43** | **29x** |
| 1 | 73% | +$3.01 | **+$32.68** | **11x** |
| 3 | 52% | +$5.27 | **+$25.44** | **4.8x** |

This is adverse selection in its purest measured form, and the mechanism is exact. The trade
is a fade: price overshot up, so you offer. **Your offer fills only if price keeps going
up** — that is, only on the occasions when the overshoot extended and the reversion was
slow or absent. When price reverses immediately, which is the winning case, it never comes
to your limit at all.

You are not choosing which trades to take. The market is choosing for you, and it hands you
the failures.

## PASSIVE-BOTH/m3 beat its cost and is still worthless

One cell cleared criterion 3: +$1.73 a signal against a $1.20 round turn, net **+$0.53**.

It fails on p (0.190 against a required 0.0071) and it fails criterion 4 decisively: the
signals it misses are worth **+$25.44** against the +$3.34 it captures. A strategy whose
foregone trades are worth 7.6 times its realised ones is not a strategy, it is a selection
artifact with a positive sign.

At the conservative $2.50 commission it is **-$0.77** and does not even clear that bar.

## Prediction scorecard

Thirteenth registered prediction.

| claim | outcome |
|---|---|
| no arm passes | **correct** |
| criterion 4 is what kills it | **correct, and decisively** |
| filled trades land at +$2 to +$5 | **correct**, $1.32 / $3.01 / $5.27 |
| PASSIVE-BOTH at m=0 comes closest | **wrong** — m=0 was the *worst* PASSIVE-BOTH at -$3.01; m=3 came closest |
| at m=3 filled trades go negative | **wrong, and backwards** — m=3 gave the *best* filled trades at +$5.27 |
| about 15% chance any arm passes | none did |

The two misses are the same mistake. I assumed resting further from the market would select
harder for continuation. It does the opposite: filling only on a *larger* overshoot selects
for a larger subsequent reversion, so filled trades improve monotonically with `m`. What
does not improve is the trade-off, because the missed trades stay worth more at every
distance.

Four of six. Right on outcome and mechanism, wrong on the direction of the one parameter.

## The stopping rule, honoured

The pre-registration stated: *"If this fails, I will say the search is over rather than
propose a 106th cell."*

**It failed. The search is over.**

### What was established

| family | status |
|---|---|
| ES directional intraday, 5 min to 4 h | closed — the only significant signal is the spread (Roll 1.30 ticks; 76% dies on a one-bar delay) |
| ES/NQ relative value | closed — lag-1 only; t 25.09 falls to t 1.14 on a one-bar delay |
| metals directional | closed — random walks; the two VR>1 cells died at t 0.82 and 0.96 |
| momentum and breakout, all variants | closed — 43 cells; the series does not trend at any horizon |
| volume-conditioned reversion | real, delay-robust, **1.9-2.6% of cost** |
| silver Asian reversion, taking | real, delay-robust, **23% of cost** |
| silver Asian reversion, passive | **closed here** — adverse selection costs 4.8x to 29x more than the spread it saves |

**One hundred and five cells. Zero strategy passes. Three real signals, none tradeable.**

### The finding, stated plainly

This is not "nothing was found." Three structures are genuinely there: they survive delayed
execution, they hold across eight years, and two of them are significant at t 3.68 and t 3.20.

**Every one of them is smaller than the cost of accessing it**, and the two facts are not
independent. Silver is the thinnest instrument in the set at 2.2% of ES's volume, it is the
only place a substantial edge survived, and its spread is three ticks wide precisely because
it is thin. The edge exists because the market is illiquid, and the illiquidity is priced at
more than the edge is worth. When we tried to stop paying that price by supplying liquidity
instead of taking it, the market simply stopped giving us the good trades.

That is what an efficient market looks like from the inside. Not an absence of structure —
structure that costs more to reach than it pays.

### What would change this

Not another variant on this data. Two things, in order of honesty:

1. **Tick-level data** would let queue position be modelled rather than assumed. But note
   the direction of the error: this simulation was **optimistic** — it assumed a fill
   whenever price traded through, ignoring the queue entirely — and it still failed by 4.8x.
   Real queue effects make it worse, not better.
2. **True signed order flow**, which remains the one input class never tested. All 105 cells
   are transformations of OHLCV. I would not fund this on the evidence above, and I want
   that recorded as my recommendation rather than left as an open door.

2017-2023 remains undownloaded and untouched. There was never anything to confirm.
