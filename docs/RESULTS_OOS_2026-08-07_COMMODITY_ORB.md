# Commodity ORB: measured costs, the depth constraint, and the first unseen data

Date: 2026-08-07. Runs 21, 22, 23.

Three things were checked, in the order they had to be checked. All dollar figures below
depend on the contract specifications, so those went first.

---

## 1. Contract specifications (run 20 correction)

Verified against CME product pages. Four were right, one was wrong.

| | size | tick | tick value | per point | |
|---|---|---|---|---|---|
| MGC | 10 troy oz | 0.10 | $1.00 | $10 | confirmed |
| MCL | 100 barrels | 0.01 | $1.00 | $100 | confirmed |
| SIL | 1,000 troy oz | 0.005 | $5.00 | $1,000 | confirmed |
| MHG | 2,500 lb | 0.0005 | $1.25 | $2,500 | confirmed |
| MNG | 1,000 MMBtu | 0.001 | $1.00 | $1,000 | **was carried at 2,500 / $2,500** |

MNG was wrong by 2.5x. The error came from assuming the micro gas contract mirrored micro
copper's 2,500-unit size; it is 1/10th of the 10,000 MMBtu parent.

The results barely moved (basket PF 1.41 to 1.39) because position size is derived from a
dollar risk budget, `qty = budget // (stop_distance * point_value)`, so halving the point
value roughly doubles the quantity. It was re-run rather than adjusted arithmetically,
because what does change is integer rounding and which sessions the risk guard rejects.

---

## 2. Measured bid/ask (run 21)

The flat 1.5 ticks per side in `orb_commodity.py` came from the MES adverse model and had
been applied to gold, silver, copper, crude and gas without anyone checking it fit.

Three rounds of top-of-book snapshots, 2026-08-06 22:08-22:12 ET, Globex evening.

| | spread | assumed $/side | measured $/side | |
|---|---|---|---|---|
| MGC | 2 ticks | 1.50 | 1.50 | matched |
| SI | 3 ticks | 7.50 | 10.00 | **assumed was LOW** |
| HG | 3 ticks | 1.88 | 2.50 | **assumed was LOW** |
| MCL | 1 tick | 1.50 | 1.00 | assumed was high |
| NG | 1 tick | 1.50 | 1.00 | assumed was high |

The errors offset. Basket net $42,769 to $43,426; PF 1.39 either way.

**This is a null result and it is the one that mattered.** The headline was not produced by
a flattering cost constant. Had it gone the other way the whole result would have been
finished here.

### Limits, stated because they bound everything above

- **N=3 per symbol on one evening.** A spot check that can catch a constant wrong by a
  factor of two. It is not a spread distribution and cannot estimate a mean.
- **These are 2026-08 spreads applied to a 2024-26 backtest.** Nothing here reconstructs the
  spread at the moment of any historical trade, and no amount of live sampling can.
- **The sample is evening**, the wide end of the day, while the ORB trades within 180
  minutes of the open. Conservative in the right direction.
- **NG is the FULL-SIZE contract.** Micro Henry Hub is not listed in the expiry ladder
  through this feed. Same price grid and tick, so the tick count carries, but a micro is
  normally wider than its parent. NG's figure is a lower bound and its net is optimistic.
- **Silver's contract is ambiguous.** COMEX lists several silver futures against one
  underlying and the feed's symbol field is identical across every expiry. Both September
  candidates quoted 2-4 ticks, so the number is right either way; which contract produced it
  is not established.

---

## 3. Depth (run 22) — this is where it bites

A flat per-side cost assumes the whole order fills at the touch. Observed top-of-book sizes
run 1 to 6 contracts. The strategy is permitted 20.

Modelled as a uniform book, `depth` contracts per level one tick apart, so filling `qty`
costs an average `(qty/depth - 1)/2` extra ticks. A real book thickens away from the touch,
so this overstates the penalty and is used as an upper bound.

| | assumed | measured | +depth | capped at the touch |
|---|---|---|---|---|
| MGC | 10,275 (1.87) | 10,275 (1.87) | 10,237 (1.87) | 9,870 (1.87) |
| SI | 12,323 (2.03) | 11,483 (1.93) | 11,263 (1.90) | 7,159 (1.58) |
| HG | 17,098 (1.76) | 15,801 (1.69) | 14,256 (1.60) | 6,973 (1.39) |
| MCL | 515 (1.02) | 1,680 (1.06) | **-2,714 (0.91)** | 237 (1.02) |
| NG | 2,557 (1.07) | 4,187 (1.12) | 3,461 (1.10) | 3,628 (1.13) |
| **ALL** | 42,769 (1.39) | 43,426 (1.39) | 36,503 (1.32) | 27,867 (1.35) |

**MCL turns negative.** Median order 4 contracts against a 1-contract touch; 87% of its
trades exceed available depth. Crude was already the weakest symbol at PF 1.02 and 90% cost
drag; measured depth finishes it.

**Capping size beats paying the walk.** Fewer dollars ($27,867 vs $36,503) but a better
per-session Sharpe (0.130 vs 0.117) and a stronger rotation t (+2.96 vs +2.67). This is the
size-invariance result from earlier in the project working in reverse: size scales edge and
noise together and cannot change Sharpe, but the book walk is pure cost, so refusing to
trade past the touch removes a cost without removing a proportionate amount of edge.

Under CAPPED, P(pass) improves across every account: 50k at 0.5x goes 72% to 85%, 100k at
0.5x goes 85% to 95%.

Nothing here was refit. Slippage is a pure deduction in that engine and never moves a fill
or triggers a stop, so `run_orb` is called once at zero cost and the arithmetic applied on
top. **The trade list is identical in all four columns.**

---

## 4. Out of sample (run 23)

Every number above came from data the strategy was developed on by the sibling project. The
in-sample/out-of-sample split there splits that same sample in half, which controls for luck
but not for hindsight.

Bars fetched 2026-08-07, covering the period after each symbol's sample ends.

### Pre-registered before running

> If the edge is real, out-of-sample dollars per trade land near in-sample (~$37) with a
> wide interval. If it is a fit to the metals bull, they land at or below zero.
>
> Power, computed in advance: ~40 tradeable sessions, the ORB trades a minority of them,
> so expect ~15 trades. At an in-sample per-trade sd near $200 that is a standard error near
> $50 against a $37 edge. **A t near 0.7 is the EXPECTED result if the edge is entirely
> real.** Therefore a positive CANNOT confirm anything and will not be reported as
> confirmation. Only a clearly negative result is informative.

### Result

| | sessions | trades | rate | net | PF | $/trade |
|---|---|---|---|---|---|---|
| MGC in | 502 | 202 | 40% | 9,870 | 1.87 | 49 |
| MGC out | 6 | 2 | 33% | 164 | 8.72 | 82 |
| SI in | 566 | 155 | 27% | 7,159 | 1.58 | 46 |
| SI out | 17 | **1** | **6%** | 374 | inf | 374 |
| HG in | 567 | 298 | 53% | 6,973 | 1.39 | 23 |
| HG out | 17 | 8 | 47% | 506 | 2.26 | 63 |
| **ALL out** | | **11** | | **1,043** | 3.47 | **95** |

t +1.43, 95% CI **-$36 to +$225**.

**Verdict: this distinguishes nothing, exactly as predicted.** The interval spans zero and
was always going to on 11 trades. The result is equally consistent with a real edge and with
no edge. The only supportable claim is that the strategy did not collapse: same sign, same
order of magnitude. That claim is not upgraded to anything stronger.

### Two things the small sample did surface

**SI traded once in 17 sessions, against 27% in-sample.** Not noise, and mechanical: silver's
median opening range went from 0.380 to 0.690 points, so median risk per contract went from
$380 to $690 and the share of sessions above the $500 max-risk guard went from 36% to 76%.
The guard is denominated in dollars against a fixed budget, so **rising volatility silently
switches the strategy off**. Whether that is prudence or a failure mode depends on whether
the edge survives in high-volatility sessions, which this sample cannot answer.

**MGC lost most of its window to a liquidity gate.** The Dec-2026 expiry printed tens of
lots per 30-minute bar until 2026-07-30, then stepped to 13,000+. Sessions where the
contract was not the one carrying volume produce opening ranges that could not have been
traded, so they were cut rather than used. Fetching the August expiry as well would recover
them; it was not done.

---

## Where this leaves the candidate

Still the only thing in this project that has cleared every gate. What changed today:

- The cost constant is checked and was not doing the work. **Confirmed.**
- Depth is a real constraint that the original result ignored, and it kills MCL outright.
  **The basket should be four symbols, not five, and size should be capped at the touch.**
- NG's contribution rests on a spread figure that is a lower bound. **Treat NG as unproven.**
- The unseen data did not contradict the edge and could not have confirmed it.

What has still never been tested: any period outside the 2024-26 metals bull the source
project itself flags. That remains the largest unaddressed risk, and no data available here
can address it.
