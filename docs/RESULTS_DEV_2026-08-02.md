# Development Result: Leg B (Opening Range Breakout)

**Run date:** 2026-08-02
**Engine version:** 0.1.0
**Split:** development (first 50% of sessions, 2025-09-10 to 2026-02-19, 115 sessions)
**Data:** IBKR TWS API, MES and MNQ dated contracts, 1-minute TRADES, resampled to 5-minute
**Evidence level:** development / in-sample. **Not validation. Not untouched test.**

---

## Verdict

| Instrument | Verdict |
|---|---|
| **MES** | **FAILED.** Three predeclared gates. Does not proceed. |
| **MNQ** | **NO EVIDENCE.** n = 10 to 11. Not a sample. Does not proceed. |

Per SPECIFICATION.md section 1, "neither instrument has sufficient evidence" is an
explicitly valid outcome of this design. That is the outcome.

**The validation split has NOT been touched. The lockbox has NOT been touched.**

---

## MES results across all three cost scenarios

| Scenario | Trades | Expectancy $ | Net $ | PF | 95% CI on expectancy |
|---|---:|---:|---:|---:|---|
| base | 72 | 4.83 | 347.60 | 1.10 | [-18.47, +26.98] |
| adverse | 72 | 3.60 | 259.48 | 1.07 | [-20.13, +25.93] |
| severe | 71 | 0.04 | 2.50 | 1.00 | [-24.40, +22.43] |

Win rate 45.8%, payoff ratio 1.27, max drawdown $795.82 (adverse).

---

## Gate 1: profit concentration. FAILED

SPECIFICATION.md section 18.4 requires survival after removing a small number of top days.

| | base | adverse | severe |
|---|---:|---:|---:|
| All trades | +347.60 | +259.48 | +2.50 |
| Excluding top 1 day | +32.45 | **-55.05** | **-313.28** |
| Excluding top 3 days | **-461.55** | **-547.18** | **-809.15** |
| Excluding top 5 days | **-849.30** | **-932.43** | **-1,188.78** |

**A single day carries the entire result.** Under the default adverse scenario, removing
one day out of 115 turns the strategy negative. This alone is disqualifying: it is the
signature of a lucky day, not of a repeatable process.

---

## Gate 2: cost fragility. FAILED

SPECIFICATION.md section 13.4: an edge that disappears under a small realistic cost
increase is labelled **fragile** and does not proceed.

Costs consume **66% of gross-before-cost**. Each additional half-tick of spread per side
costs $127.50 across the sample:

| Assumption | Net $ |
|---|---:|
| adverse (default) | +259.48 |
| +0.5 tick/side | +131.98 |
| severe (+1.0 tick/side) | **+2.50** |
| +1.5 tick/side | **-123.02** |

The measured severe run landed at +$2.50 against a +$4.48 prediction from this arithmetic,
confirming the model.

**The entire result lives inside one tick of an assumption that was never measured.** No
BID/ASK data has been downloaded, so the spread is a prior, not an observation. This gate
cannot even be evaluated properly until quote data exists.

---

## Gate 3: statistical significance. FAILED

Every confidence interval contains zero, in every cost scenario. The point estimate moves
by a factor of roughly 120 (from $4.83 to $0.04) while the evidence never changes: there
is none.

This was predicted before the run. At n = 72 the minimum detectable edge is ~0.28R; the
measured 0.043R sits well inside the noise band. The run did not fail because the strategy
is bad. It failed because **this sample cannot answer the question**, and the point
estimate landed where noise would put it.

---

## Additional evidence against

**Long/short asymmetry.** Shorts 52 trades, +$738, PF 1.34. Longs 20 trades, -$478,
PF 0.64. Over Sep 2025 to Feb 2026 this is far more consistent with capturing a directional
drift in one regime than with a breakout mechanism, which should be broadly indifferent to
direction. A regime-dependent directional bias is exactly what an 11-month single-regime
sample cannot distinguish from edge.

**Contract-level instability.** 202512 gave +$556.67 (PF 1.27); 202603 gave -$297.20
(PF 0.79). The sign flips between adjacent contracts.

---

## MNQ: not a sample

| Scenario | Trades | Expectancy $ | Net $ | PF |
|---|---:|---:|---:|---:|
| base | 11 | 31.80 | 349.80 | 1.92 |
| adverse | 11 | 31.44 | 345.80 | 1.90 |
| severe | 10 | 41.45 | 414.50 | 2.32 |

**MNQ improves as costs get worse.** That is impossible for a real edge and is the
clearest single diagnostic in this report. The cause is mechanical: the severe scenario
dropped one trade (11 to 10), and at n = 10 a single trade moves every statistic. The
reported Sharpe of 5.51 to 7.39 is an artifact of a tiny denominator, not a finding.

Top-5 concentration is 86.9%; excluding the top 3 days the result is negative in every
scenario. **Every MNQ number in this report should be disregarded.**

**Why so few trades:** 558 `SIZE_ZERO_STOP_TOO_WIDE` rejections. MNQ stop distances
frequently exceed the $100 per-trade risk budget at one contract, so the trade cannot be
taken at all. This is the micro-sizing constraint from SPECIFICATION.md section 10.3
appearing exactly as anticipated, not a defect.

---

## What was NOT done, deliberately

- **No parameter tuning.** `or_minutes`, `rvol_breakout`, `m_stop_atr`, `r_target` and the
  rest were left at their pre-registered values. With 115 development sessions and 13
  tunable parameters, a search would certainly find a configuration that looks profitable
  and would mean nothing. Tuning to rescue a result that fails on one day's profit is the
  precise failure mode this project exists to avoid.
- **The validation split was not examined.** Looking at it to "check" would spend it.
- **The lockbox was not opened.**
- **No result was re-run after seeing an unfavourable outcome.**

---

## Honest reading

The engine is working correctly. It processed 316,425 bars per instrument, handled four
dated contracts with volume-crossover rolls, applied adverse fill assumptions throughout,
and returned a negative verdict. A backtest that only ever returns encouraging answers is
broken; this one is not.

The strategy shows no detectable edge on this data. Two distinct reasons, and they matter
because they point to different remedies:

1. **The sample cannot resolve an edge of realistic size.** 72 trades, one volatility
   regime, minimum detectable edge ~0.28R against a plausible 0.02 to 0.10R. More data
   would fix this.
2. **The result fails concentration and fragility on its own terms.** One day carries it,
   and it evaporates within one tick of spread. More data would *not* fix that; it is a
   property of what was measured, not of how much was measured.

Point 2 is the more serious of the two. A strategy that depends on a single session and on
an unmeasured spread assumption has no demonstrated mechanism behind it.

---

## Measured costs, 2026-08-02 (added after BID/ASK download)

348,857 MES and 348,741 MNQ quote-bars measured. Crossed, zero, and stale quotes were
0.01% and 0.04% respectively, so the distributions are clean.

### Two predictions I made that the data falsified

**1. "The opening hour quotes wider than midday."** WRONG. Measured ratio is **1.00x** for
both instruments. Spread is essentially flat across every session window for MES, and for
MNQ the RTH windows are actually the TIGHTEST (2 ticks) while London and the EU/NY overlap
are widest (3 ticks). The reasoning was plausible and the data does not support it. The
`--cost-session` mechanism is retained because it is correct in principle and cost-free
when the ratio is 1.0, but for this dataset it changes nothing.

**2. "MNQ may be the more cost-efficient instrument."** WRONG in the units that matter.
That claim assumed both instruments quote near 1 tick. Measured:

| | MES | MNQ |
|---|---:|---:|
| Median spread | 1.0 tick | 2.0 ticks |
| 75th percentile | 1.0 tick | 3.0 ticks |
| 95th percentile | 2.0 ticks | 6.0 ticks |
| 99th percentile | 3.0 ticks | **19.0 ticks** |
| Share at 1 tick | 84.9% | **11.6%** |

MNQ quotes 2 to 3 times wider than MES in ticks. In dollars per contract at the 75th
percentile, MNQ round-trips at $3.00 of spread against MES at $2.50, so **MNQ is the more
expensive instrument**, not the cheaper one. The original claim survives only when
normalised by index level (MNQ 0.0036% vs MES 0.0043%), and the $2,000 loss buffer is
denominated in dollars, not in percent of index.

### Measured versus assumed round-trip cost per contract

| Scenario | Assumed | Measured | Change |
|---|---:|---:|---:|
| MES base | $3.70 | $4.33 | +17% |
| MES adverse | $4.95 | $4.95 | 0% |
| MES severe | $7.45 | $8.70 | +17% |
| MNQ base | $2.20 | $3.45 | +57% |
| MNQ adverse | $2.70 | $4.70 | +74% |
| MNQ severe | $3.70 | $8.20 | +122% |

**The MES cost model was right.** The adverse scenario, which is the default and the one
the verdict rests on, matches the measurement exactly. The MES conclusion in this document
therefore stands unchanged and is now resting on measured rather than assumed costs.

**The MNQ cost model was materially wrong**, understating cost by 57% to 122%. MNQ produced
only 10 to 11 trades so no conclusion depended on it, but any future MNQ work must use the
measured figures.

### MNQ tail risk

MNQ's 99th-percentile spread is 19 ticks, a $19.00 round trip. That is 19% of the $100
per-trade risk budget spent entirely on crossing the spread before the trade does anything.
Combined with the 558 `SIZE_ZERO_STOP_TOO_WIDE` rejections already noted, MNQ is a
materially harder instrument to trade profitably at this account size than MES.

### Backtest re-run on measured costs: verdict CONFIRMED

Run: `--measured-costs config/measured_costs.json --cost-session RTH_OPEN`

MES charged $4.95/contract round trip, identical to the assumed adverse prior. Every
statistic is therefore unchanged:

| Metric | Assumed | Measured |
|---|---:|---:|
| Round trip / contract | $4.95 | $4.95 |
| Trades | 72 | 72 |
| Expectancy | $3.60 | $3.60 |
| Net | $259.48 | $259.48 |
| Profit factor | 1.07 | 1.07 |
| Excluding top 1 day | -$55.05 | -$55.05 |

**The cost question is now closed.** It was the one open item capable of changing the
verdict, and measurement confirmed rather than overturned it. MES fails concentration,
fragility, and significance on measured costs.

**A note on where the session mechanism mattered.** It did no work for MES, whose spread is
flat everywhere. For MNQ it did: the blended p75 of 3 ticks is inflated by London and
overnight sessions, while the RTH_OPEN p75 where Leg B actually fires is 2 ticks. Charging
the blended figure would have overstated MNQ cost by 27% ($4.70 versus $3.70). So
attributing cost to the traded session was the right design; the specific prediction about
WHICH session is widest was wrong in both direction and instrument. MNQ is widest in
London and the EU/NY overlap, not at the New York open.

### What this does not resolve

Quoted spread remains a **lower bound**. Queue position, partial fills, and widening in the
instant an order arrives are not observable in bar data. Real execution cost is at least
these figures and usually worse.

---

## Options

1. **Stop.** Leg B on 11 months of data shows nothing. This is a legitimate and complete
   answer, and it cost a few hours rather than an evaluation fee.
2. **Acquire deeper history**, freeze these exact rules, and re-run. FirstRate Data carries
   ~7 years of MNQ 1-minute for a one-off per-symbol fee. That takes development n from 72
   toward ~800, drops the detection threshold from 0.28R to ~0.06R, and supplies genuine
   regime diversity. **The rules must be frozen before that data is seen**, otherwise the
   new sample is contaminated the same way this one would be by tuning.
3. **Download BID/ASK first** so the cost model is measured rather than assumed. Roughly
   4.5 hours. This does not rescue the result, but it converts the fragility gate from
   unevaluable into testable, and it is a prerequisite for trusting any future run.
4. **Test a different leg** (Leg A, VWAP band reversion) on the same data. Honest only if
   registered in the experiment ledger first and counted against the multiple-testing
   budget. Note that the sample-size problem applies identically.

**Recommendation: 3 then 2.** Measure costs, acquire deeper history, freeze the rules
before looking, then re-run. Option 1 remains entirely defensible.

---

## Reproduction

```bash
python run_backtest.py --data data --split dev --cost-scenario base    --report out
python run_backtest.py --data data --split dev --cost-scenario adverse --report out
python run_backtest.py --data data --split dev --cost-scenario severe  --report out
```

Engine 0.1.0, commit `0670cb2`. Full configuration fingerprint and data provenance are
recorded in `out/summary_dev_*.json`.

**Note on the rejection counters in the runs before commit `0670cb2`:** filters were
evaluated at different points in the chain, so the counts were not comparable. The counts
above and in the current code are post-fix. Trade results are unaffected, since no trading
decision depended on the ordering.
