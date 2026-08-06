# Experiment Ledger

Every run against real data is recorded here, including failures. The ledger exists so the
multiple-testing burden is countable: the correction in SPECIFICATION.md section 18.3
assumes the number of trials is known, and it is only known if every trial is written down.

**A configuration tried and abandoned still counts.** Omitting failures is the single
easiest way to make a search look more disciplined than it was.

| # | Date | Split | Instrument | Leg | Config | Trades | Expectancy $ | Verdict |
|---|---|---|---|---|---|---:|---:|---|
| 1 | 2026-08-02 | dev | MES | B (ORB) | defaults, adverse | 72 | +3.60 | **FAILED** concentration, fragility, significance |
| 2 | 2026-08-02 | dev | MNQ | B (ORB) | defaults, adverse | 11 | +31.44 | **NO EVIDENCE**, n too small |
| 3 | 2026-08-02 | dev | MES | B (ORB) | defaults, severe | 71 | +0.04 | **FAILED**, edge vanishes under cost stress |
| 4 | 2026-08-02 | dev | MNQ | B (ORB) | defaults, severe | 10 | +41.45 | **NO EVIDENCE**, improved under worse costs |
| 5 | 2026-08-02 | dev | MES | B (ORB) | defaults, base | 72 | +4.83 | **FAILED**, same gates |
| 6 | 2026-08-02 | dev | MNQ | B (ORB) | defaults, base | 11 | +31.80 | **NO EVIDENCE**, n too small |
| 7 | 2026-08-02 | dev | MES | B (ORB) | defaults, adverse, **MEASURED** costs | 72 | +3.60 | **FAILED**, identical to run 1; verdict confirmed on measured costs |
| 8 | 2026-08-02 | dev | MNQ | B (ORB) | defaults, adverse, **MEASURED** costs | 10 | +41.55 | **NO EVIDENCE**, n too small |
| 9 | 2026-08-04 | dev | MES via ES prices | B (ORB) | defaults, adverse, measured, **prop ON** | 71 | -15.96 | **ACCOUNT DIED** at 28% of split; path-truncated |
| 10 | 2026-08-04 | dev | MES via ES prices | B (ORB) | defaults, adverse, measured, **prop OFF** | **264** | **-10.91** | **NEGATIVE EDGE.** First run to clear the 200-trade gate. Loses -613.75 BEFORE any cost. |
| 11 | 2026-08-06 | dev | MES via ES prices | **A (VWAP reversion)** | spec defaults, adverse, measured, prop OFF | 177 | **-20.70** | **FAILED**, and below the 200 gate. -0.266R, PF 0.69, loses -1,664.38 before any cost. Target-first rate 29.1% against a 43.4% coin-flip baseline: **mildly anti-predictive**. |
| 12 | 2026-08-06 | dev | MES via ES prices | screen | forward returns, 460 cells, overnight family added | n/a | n/a | **NOT SIGNIFICANT**, family-wise p 0.375 to 0.770 across three null constructions. Best cell was `gap_vs_on_range` at 120 min, 2.41x cost, in the gap-fade direction. |
| 13 | 2026-08-06 | dev | MES via ES prices | **C (gap fade)** | registered defaults, adverse, measured, prop OFF | **236** | **-33.03** | **FAILED, worst of the three.** -0.432R, PF 0.57, CI [-49.97, -15.52] excludes zero. Negative in **all seven** contracts and both directions. Clears the 200 gate. |
| 15 | 2026-08-06 | dev | MES via ES prices | session decomposition | 4 windows, buy-and-hold, 1 contract | 387 | **+8.47/sess** | **FIRST POSITIVE.** Overnight (18:00-09:30) +2.68 pts/session, RTH -0.33. But **t NET = 1.35**, not the 2.15 on the gross mean. Worst night -$851 = 43% of the MLL at ONE contract. |
| 14 | 2026-08-06 | dev | MES via ES prices | barrier screen | path expectancy in R, 270 cells, 3 symmetric geometries | n/a | n/a | **NOTHING.** Best positive PATH +0.0047R, **0 of 270 cells clear the round trip**, best positive is 1.6% of the cost bar. The p=0.000 is a NEGATIVE cell and is not tradeable. |

**Distinct configurations tried: 2.** Runs 1 to 10 are the same frozen parameter set
evaluated under three predeclared cost scenarios, a measured-cost re-run, and a three-year
re-run on validated proxy data. That is robustness checking, not a search. Run 11 is the
second and only other configuration. **No parameter has been tuned against any result at
any point.**

**RUN 14 SETTLES THE QUESTION THE LEGS WERE ASKING.** The path expectancy is the only
statistic that decides the sign of an edge, and conditional on every feature available it
is measured at between 30 and 91 times too small to pay a round trip. The best positive
cell in 270 is +0.0047R against a cost bar of 0.286R. That is not an undetected edge, it
is a measured absence. See `RESULTS_DEV_2026-08-06_BARRIER.md`.

Two biases were caught in that tool during calibration, both of which invented signal, and
both of which had already produced a real-data result before being found. A binary touch
rate returned family-wise p=0.000 on a synthetic random walk with a true edge of exactly
zero, because censoring travels with an ATR-scaled feature and no baseline or rotation
removes it. A long-only measurement reported +0.1013R on a synthetic pure uptrend where
the correct path answer was -0.0089R. **The earlier real-data output of p=0.120 came from
that version and must not be read.**

**ALL THREE LEGS ARE CLOSED**, and run 13 produced the arithmetic that closes the
framework rather than just the leg. For a driftless random walk `P(target first)` and the
break-even win rate are the SAME expression, `S/(S+T)`, so a random walk breaks even at
every geometry and **the sign of an edge before costs is decided solely by the gap between
the realised target-first rate and `S/(S+T)`.** Stop width, target distance,
reward-to-risk and instrument choice cannot change that sign. Measured: Leg A -14.3pp
(z=-3.51), Leg C -14.8pp (z=-4.58). Replicated to within half a point across different
anchors, triggers and sample sizes. See `RESULTS_DEV_2026-08-06_LEGC.md`.

This is why **no wide-stop variant will be run**: the arithmetic states its result in
advance.

**BOTH EARLIER LEGS ARE CLOSED.** Leg B is momentum continuation, Leg A is mean reversion. They
are opposite bets on the same series and both lose before costs on the same three years,
in both directions, in six of seven contracts, and more heavily once the best days are
removed. See `RESULTS_DEV_2026-08-06_LEGA.md`.

**The binding constraint is now measured, and it is not either signal.** The cost hurdle
is 0.141R per trade. The minimum detectable edge across the *entire* 774-session sample,
lockbox included, is about 0.12R. Those two numbers are the same size, so this dataset
cannot certify a realistic winner; it can only reject clear losers, which it has now done
twice. Any proposal for a third leg must state how it changes one of those two numbers
before it is registered, not merely how it changes the entry rule.

**LEG B IS CLOSED, and not for want of evidence.** Run 10 cleared the 200-trade gate at
n=264 across three years with measured costs and returned an expectancy of -0.127R. Gross
of every cost it still loses $613.75, so the cost question that dominated runs 1 to 8 is
moot: there is no edge for costs to consume. The negative survives removing the best days,
holds in six of seven contracts, and holds in both directions.

See `RESULTS_DEV_2026-08-04_ES.md`. Further work on Leg B is not justified. A different
leg must be registered here before it is run.

**Prediction check.** Before run 10 the ledger recorded: "Leg B fails again. The
concentration failure is a property of what was measured, not of how much." The direction
was right, the reasoning was half wrong. Concentration was not the mechanism; on the larger
sample concentration improved (9.2% versus 24.5%) while the result got worse. The 11-month
sample was not hiding a fragile edge, it was hiding a negative one.

---

## Registered BEFORE execution: run 16 (Leg D, overnight hold)

Registered before the strategy was written.

| Field | Value |
|---|---|
| Instrument | MES, prices from ES, same dataset as runs 9-15 |
| Entry | first bar of the Globex session, within 30 minutes of 18:00 ET. **Long only.** |
| Exit | the 09:30 ET open, by CLOCK not by bar count |
| Stop | $500/contract disaster brake, about 4 measured session sd. Not a signal parameter. |
| Size | **fixed at 1 contract.** The R sizer correctly refuses a 100-point stop. |
| Split | development. Validation and lockbox remain **UNTOUCHED**. |

**Run 15 prediction check: 4 for 4, the first clean sweep.** Registered beforehand:
GLOBEX_TO_OPEN positive (+2.68 pts, right), RTH flat or negative (-0.33, right), overnight
t between 1 and 3 (2.15 gross, right), and at least one session above 25% of the MLL
buffer (worst was 43%, right).

**The correction that matters more than the prediction.** The tool printed t = 2.15 on the
GROSS mean. Cost is a constant per session, so it moves the mean without touching the
standard deviation, and the **net t is 1.35**, one-sided p about 0.09 with the direction
pre-registered, about 0.35 once the four windows are Bonferroni-corrected. **The overnight
effect is NOT statistically significant after costs on this sample.** The tool now prints
both and says to read the net one.

**Economics, computed before the backtest.**

| size | worst night | as % of MLL | months to $3,000 | P(breach) | P(pass) |
|---|---:|---:|---:|---:|---:|
| 1 | -$851 | 43% | 16.9 | 23% | 63% |
| 2 | -$1,702 | 85% | 8.4 | 47% | 53% |
| 3 | -$2,553 | **128%, dies in one night** | 5.6 | 53% | 47% |

Monte Carlo on the measured net moments (mean $8.47, sd $123 per session) under the
end-of-day trailing MLL, normal returns, so the real fat left tail makes it optimistic.
**One contract is the only survivable size, and it is a 63/23 gamble taking 17 months.**

**Session sd is $123 against $8.47 of drift.** The whole development result is 1.36 sd
from zero, and 840 sessions, three and a half years, would be needed for the drift to
clear two standard deviations of noise. This sample cannot settle it either way.

**The largest open risk is the overnight SPREAD.** The $4.95 round trip is the all-day
measured figure, dominated by RTH. Leg D enters at 18:00 ET, the thinnest moment of the
day. If the true overnight round trip is $8 rather than $4.95, net expectancy falls from
$8.47 to about $5.40 and everything above gets worse. `--cost-session ASIA` now exists to
measure it, and that check comes before the backtest is believed.

**Prediction.** With prop rules on and one contract, the account survives the development
split but the maximum drawdown exceeds half the MLL buffer, and the run does not reach the
$3,000 target inside 387 sessions.

---

## Registered BEFORE execution: run 15 (session decomposition)

Measurement only. No entry rule, no sizing, no P&L, development split only. Trial count
stays at 3.

**The rule changed, and it invalidates the SCOPE of every prior result.** On 2026-08-06
the firm rule was clarified: positions may be held overnight, and must be flat only for
the CME daily halt at 17:00-18:00 ET (14:00-15:00 Pacific). Everything in runs 1-14 was
produced with RTH-only bars, so roughly fifteen and a half hours of every session had
never been screened, backtested, or looked at.

Two engine corrections follow from it, both recorded because they change what past runs
measured:

- `DEFAULT_ENABLED` now covers every session the contract trades. `RTH_ONLY` is kept so
  runs 1-14 stay reproducible.
- 16:00-17:00 ET classified as `CLOSED` and now classifies as `POST_CLOSE`. The cash
  market shuts at 16:00 but the future trades to 17:00, so a full tradable hour was being
  silently discarded. A test now sweeps the clock and asserts the only unclassified
  minutes are the halt itself.
- `flat_time_et` moves from 15:50 to 16:50, ten minutes before the halt rather than ten
  minutes before the cash close.

**The engine invariant survives.** The 17:00 flat requirement lands exactly on the 18:00
session roll, so a position still never crosses a session boundary. What changes is the
leash inside one session: up to 23 hours instead of 6.

**What run 15 measures.** Each session split into windows a compliant trade could hold:
GLOBEX_TO_OPEN (18:00-09:30), RTH (09:30-16:00), POST_CLOSE (16:00-16:50), and
FULL_SESSION (18:00-16:50). Each reported as a standalone buy-and-hold with one round trip
charged.

**Motivation, and it is a measured one.** Run 14 put intraday drift between -0.0061R and
+0.0006R across every geometry over 387 sessions in which the index rose roughly a third.
Zero intraday drift and a large index gain cannot both hold unless the gain happened
outside RTH.

**Stated in advance, because it decides how to read a positive result.** An overnight long
is **not alpha**. It is the equity risk premium plus the documented overnight/intraday
effect, harvested with a timing rule. Two consequences: it should persist out of sample in
a way none of Legs A to C would have, and it should hurt precisely when risk arrives. The
development split is a bull market, so a positive overnight number is exactly what this
sample produces and is a reason to test out of sample, not a reason to believe it.

**The binding constraint is gap risk, not expectancy.** An overnight position cannot be
stopped during the halt or through a gap, so the account is exposed to the entire move
rather than to a stop distance. The run reports the worst and 1st-percentile overnight
moves against the $2,000 MLL. If one night in the sample would have ended the account at
one contract, expectancy is irrelevant.

**Prediction:** GLOBEX_TO_OPEN carries a positive mean and RTH is flat or negative, with
the overnight t-statistic between 1 and 3, and at least one session in the sample whose
overnight move exceeds 25% of the MLL buffer at one contract.

---

## Registered BEFORE execution: run 14 (barrier touch screen)

Registered before the tool was written. Measurement only: no entry rule, no sizing, no
P&L, no split beyond development. Not a strategy trial, so the trial count stays at 3.

Every screen so far measured **means**. Run 13 proved that is the wrong statistic:
`gap_vs_on_range` produced the largest mean effect in the project, 2.41x the round trip
and pointing the way Leg C bets, while Leg C lost 0.432R trading exactly that. A
favourable mean with an adverse path is not an edge.

Run 14 measures the quantity that actually decides the sign: conditional on each feature,
does price touch the favourable barrier before the adverse one more often than an average
bar does at the same geometry? Five geometries from 1.5x/1.5x to 4.0x/2.0x, so no result
can be an artefact of one arrangement.

**Design correction made during construction, before any real-data output.** The first
version compared each bin to the theoretical `S/(S+T)`. Calibration on a synthetic random
walk showed the unconditional rate at **76.1% against a theoretical 66.7%** for a 4.0x
stop and 2.0x target, and **29.2% against 33.3%** for the mirror. The cause is the 24-bar
cap: it censors the FARTHER barrier, so whichever barrier sits nearer is over-represented
among resolved outcomes. Comparing to theory would have shown a large positive excess in
every bin of half the geometries for a purely mechanical reason. Cells are now compared to
the **observed** unconditional rate at the same geometry, which absorbs censoring,
tie-break drag and drift exactly. The censoring bias is reported separately rather than
hidden.

**This correction also qualifies the run 11 and 13 shortfall figures.** Both used the
theoretical baseline. Censoring biases a payoff-above-1 setup downward, so part of the
-14.3pp and -14.8pp is mechanical. On synthetic data the effect was -1.1pp at 1.5x/3.0x
and -4.2pp at 2.0x/4.0x, which is a fraction of -14.5pp but not nothing. Run 14's
unconditional row measures it on the real data, and the shortfall figures should be read
against that row rather than against theory.

**Prediction:** nothing clears the family-wise null. If that holds, no arrangement of
stops, targets, instruments or sizing applied to this feature set can be profitable, and
that is a complete answer rather than another failed leg.

---

## Registered BEFORE execution: runs 12 and 13 (Leg C)

Recorded before the strategy was written, and before the extended screen was run. Nothing
below has been executed.

### Run 12: the gate

The forward-return screen, re-run with the **overnight, gap and prior-session** feature
family added. That family is the reason a third leg is worth attempting at all: every
feature in the first screen was computed from RTH bars of the session being traded, which
ignored roughly fifteen hours per session that the engine already had bars for.

| Field | Value |
|---|---|
| Tool | `tools/forward_returns.py`, unchanged method, 8 new features |
| New features | `gap_atr`, `gap_vs_on_range`, `on_range_atr`, `on_range_norm`, `on_pos`, `dist_on_high_atr`, `dist_on_low_atr`, `prior_close_pos` |
| Cells | ~460, up from 260 |
| Split | development only |

`on_range_norm` is the **control for the competing explanation.** If an apparent overnight
level effect is really volatility clustering wearing a costume, it shows up there and not
in the distance features. That distinction is the point of including it.

### Run 13: Leg C, opening gap fade

| Field | Value |
|---|---|
| Instrument | MES, prices from ES, same dataset as runs 9-11 |
| Entry | first bar of RTH within `gap_window_minutes`, fading toward the prior cash close |
| Direction | gap up to SHORT, gap down to LONG. One trade per session. |
| Band | `0.25 <= abs(gap) / overnight_range <= 1.00` |
| Target | the prior RTH cash close, fixed before the session opened |
| Stop, time stop, floor | unchanged from Legs A and B |
| Split | development. Validation and lockbox remain **UNTOUCHED**. |

**Why this is not a third draw from the same urn.** Leg B was continuation from a range
formed inside the session. Leg A was reversion to a statistical mean recomputed every bar.
Leg C reverts to a **fixed level set before the session opened**, fires once at a known
clock time, and reads information neither of the others could see. It is a different
anchor, a different trigger mechanism, and a different information set.

**Design correction made BEFORE any Leg C result existed, recorded so it is not mistaken
for tuning.** The band was first written as `0.75 <= abs(gap_atr) <= 3.00`, in units of the
5-minute ATR. That is a units error of exactly the kind that broke `or_max_width_atr`: a
gap is an overnight move and an ATR is a 5-minute move, so their ratio scales with the
square root of the bars in a night. On the measured median ES ATR of 2.31 points an
ordinary 10-point gap scores 4.3 and would have been rejected as "news". The synthetic
check showed it: 288 `GAP_TOO_LARGE` against 15 trades. The denominator is now the
overnight range, which is daily-scale, complete before the open, and meaningful on its own
terms. **No P&L was seen at any point in making this change.**

**Trial count: 3.** A nominal p of 0.05 now corresponds to a family-wise 0.14.

**Power, stated before the result.** Expected ~0.4-0.5 trades per session, so roughly
**150-190 trades on dev, which is BELOW the 200-trade gate.** This is known in advance and
is a property of the design: there is only one opening gap per day. Run 13 therefore
**cannot** produce a decisive positive on its own.

**Pre-commitment, so the decision is not made after seeing the number.**

- If dev expectancy is negative: Leg C is closed. No validation spend.
- If dev expectancy is positive and the CI excludes zero: still not a result at n<200.
  The parameters are frozen exactly as they stand and **validation is spent once** as a
  genuine out-of-sample test. That is what validation is for.
- If dev is positive but the CI straddles zero: closed as undetectable. **No validation
  spend**, because confirming an undetectable effect is not something validation can do.

**Prediction, recorded before the run so it can be wrong.** The screen finds nothing at
family-wise p < 0.05, and Leg C returns an expectancy indistinguishable from zero with a
CI straddling it. My previous three predictions ran two right on direction and one badly
wrong on mechanism, so this is worth what that record says it is worth.

---

## Registered BEFORE execution: run 11 (Leg A)

Recorded here before the code was written, not merely before it was run. Nothing below has
been executed.

| Field | Value |
|---|---|
| Planned date | 2026-08-05 |
| Instrument | **MES**, prices from **ES** (`--price-source ES`), same dataset as runs 9-10 |
| Leg | **A (VWAP band reversion)**, RANGE regime only |
| Parameters | `k_entry` 2.0, `rvol_min` 0.80, `min_vwap_bars` 12, regime `theta_trend` 0.35, `theta_range` 0.15, `theta_rvol` 1.10, `rv_lo` 0.20, `rv_hi` 0.80. All taken verbatim from SPECIFICATION.md sections 7 and 8, written 2026-07-31, before any data existed. |
| Shared with Leg B | `m_stop_atr` 1.5, `min_stop_ticks` 8, `max_bars_in_trade` 24, re-entry fences, `mu_min` 0.25 |
| Costs | `config/measured_costs.json`, measured from MES quotes, adverse |
| Split | development only. Validation and lockbox remain **UNTOUCHED**. |

**Trial count.** This is the **second distinct configuration** in the project. Runs 1-10
were one frozen parameter set under different cost and data conditions. Leg A is a
genuinely new trial and raises the multiple-testing burden for every subsequent claim: at
two trials a nominal p of 0.05 corresponds to a family-wise 0.10, so the significance bar
for Leg A is stricter than it was for Leg B, not the same.

**Power, stated before the result so it cannot be rationalised after.** Leg B produced
0.68 trades per session on this split. Leg A trades only in RANGE, which is a strict
subset of sessions, so its trade count will be **lower**, not higher. At n in the 150-300
band the minimum detectable edge is roughly 0.15R against a plausible true edge of
0.02-0.10R. **This run can return a decisive negative. It cannot return a decisive
positive.** A positive result here means "not yet excluded", and the correct response
would be to spend the validation split, not to believe it.

**Prediction, recorded before the run so it can be wrong.** Leg A is negative or
indistinguishable from zero on a cost-adjusted basis, and the binding failure is the
expected-move floor rather than the signal: the distance from a 2-sigma excursion back to
VWAP on MES is frequently smaller than the round trip it has to clear. I expect the
`MOVE_FLOOR` rejection counter to exceed the trade count.

**What would make me wrong.** A positive gross-of-cost expectancy at n >= 200 with a
95% CI excluding zero, holding in both directions and in a majority of contracts. That is
the same bar Leg B failed.

---

## Registered BEFORE execution: run 9

Recorded here before the run, per rule 1. Nothing below has been executed.

| Field | Value |
|---|---|
| Planned date | 2026-08-04 |
| Instrument | **MES**, with prices sourced from **ES** (`--price-source ES`) |
| Leg | B (ORB) |
| Parameters | **UNCHANGED** from runs 1-8. Frozen before the new data was seen. |
| Data | Barchart 1-minute, 13 dated contracts, 2023-08-03 to 2026-08-03 |
| Costs | `config/measured_costs.json`, measured from **MES** quotes |
| Economics | MES point value $5.00 and MES tick value $1.25. ES economics are never used. |
| Split | development only. Validation and lockbox remain untouched. |
| Expected dev n | ~236 trades at the measured 0.63 trades/session |
| Expected detection floor | ~0.15R, against ~0.28R on the 11-month sample |

**Proxy justification.** `tools/compare_es_mes.py` on the 230-session overlap:
triggers disagree on **1.19%** of firing bars (89 ES-only, 52 MES-only, **0 opposite
directions**), against a threshold of 2% fixed in the tool before the measurement. Price
basis is 0.000 ticks median with 90.4% of bars inside one tick.

The large basis tail (p05 -218 ticks, max 287) is **roll misalignment, not basis**: ES and
MES pick their active contract from their own volume crossovers and do not always roll on
the same session, so those bars measure the quarterly calendar spread of roughly 50 index
points. An intraday ES/MES basis is arbitraged to well under a tick; a 54-point gap is two
different contracts, not two different books. It does not affect the trigger because the
opening range and the close shift together.

**Prediction, recorded before the run so it can be wrong.** Leg B fails again. The
concentration failure is a property of what was measured, not of how much, and more data
does not repair it. What the larger sample buys is a fairer test, not a better result.

---

**Prediction check, run 11.** Registered: negative or indistinguishable from zero, fewer
trades than Leg B, and the binding failure would be the expected-move floor with
`MOVE_FLOOR` rejections exceeding the trade count. The first two were right. The third was
badly wrong: `MOVE_FLOOR` fired **4** times against **177** trades. The reversions were
comfortably large enough to pay for themselves. The failure was the signal, not the cost
floor. **Third prediction falsified by measurement in this project.**

---

**Splits consumed:**

| Split | Status |
|---|---|
| development | used (runs 1-14) |
| validation | **UNTOUCHED** |
| lockbox | **UNTOUCHED**, single-use |

---

## Rules for future entries

1. Register the intended configuration **before** running it, not after seeing the result.
2. Record failures with the same detail as successes.
3. A parameter changed after seeing a result is a **new trial**, and increases the
   correction burden for every subsequent claim.
4. Re-running the same configuration on the same split is not a new trial; re-running it
   with any parameter changed is.
5. The lockbox is opened once, ever, after the rules and code are frozen. Every prior look
   invalidates it.

## Cost model

| Date | Change |
|---|---|
| 2026-08-02 | Costs were ASSUMED priors for runs 1-6. |
| 2026-08-02 | BID/ASK downloaded (348,857 MES and 348,741 MNQ quote-bars). Cost scenarios replaced with measured percentiles. MES adverse matched the prior exactly; MNQ was understated by 57-122%. |

Two predictions falsified by the measurement, recorded so the error rate is visible:
the opening hour is NOT wider than midday (1.00x for both instruments), and MNQ's quoted
spread is wider in TICKS than MES's (3 against 1 at p75).

**Correction, 2026-08-06.** The second bullet originally read "MNQ is NOT the cheaper
instrument in dollars per contract." That conflated ticks with dollars and was wrong as
stated. An MNQ tick is $0.50 against MES's $1.25, so MNQ's 3-tick spread is $1.50/side
against MES's $1.25/side: wider in ticks, and only 20% dearer in dollars rather than
triple. Which instrument is cheaper per round trip then depends entirely on the ASSUMED
slippage allowance, and the ranking flips with its denomination. See
`RESULTS_DEV_2026-08-06_COST.md`. The instrument comparison in dollars is not a usable
finding; the comparison in R is.

## Notes

- Runs 1-6 used engine 0.1.0 at commit `0670cb2`.
- Rejection counters from runs before `0670cb2` are not comparable across reasons; filters
  were evaluated at different points in the chain. Trade results are unaffected.
- Runs 1-6 used **assumed** costs. Runs 7-8 used **measured** spreads from 348,857 MES and
  348,741 MNQ quote-bars. The MES adverse prior matched measurement exactly, so the verdict
  is unchanged and the fragility gate is now properly evaluated rather than merely
  demonstrated.
