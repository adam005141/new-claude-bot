# Experiment Ledger

Every run against real data is recorded here, including failures. The ledger exists so the
multiple-testing burden is countable: the correction in SPECIFICATION.md section 18.3
assumes the number of trials is known, and it is only known if every trial is written down.

**A configuration tried and abandoned still counts.** Omitting failures is the single
easiest way to make a search look more disciplined than it was.

| # | Date | Split | Instrument | Leg | Config | Trades | Expectancy $ | Verdict |
|---|---|---|---|---|---|---:|---:|---|
| 30 | 2026-08-10 | **pre-registered, ES 2009-2016, 5-min** | ES as MES | ICT + quant: FVG / SWEEP / SILVER / TREND4H / VOLLOW | raw entry-to-exit, no fees or slippage, Bonferroni 0.010, concentration trim | 3,434 taken | best +0.88/trade | **ALL FIVE FAIL, AND TWO ARE VOID AS TESTS.** The pre-registered take-rate check caught three misses before the P&L was read, which is exactly why it was added. **TREND4H is VOID, not failed**: the 48-bar lookback was indexed inside the NY window, and the L2N break fires at median bar 2 with 96.7% before bar 48, so the arm skipped 97% of signals and the surviving n=63 (+$9.70, p<0.001) is the late-breakout subpopulation, not a trend filter. It failed the concentration trim anyway (t-5% 1.74). **FVG is not a filter**: the imbalance fires in 99% of sessions. Its +$0.88 at t 1.40 is a lottery ticket -- WR 13%, and trimming the best 5% takes t to **-13.75**. **SWEEP, the arm I said I would least like to bet against, was the deadest in the set**: -$0.11 at t -0.11 on 887 trades, and 81% of sessions sweep a prior extreme, so there is no scarce liquidity pool. SILVER -$1.71 on 202 trades (sample size, as predicted). **VOLLOW is the clean negative**: matched take rate, causal, non-collinear, -$1.98 on 701 trades -- quiet-range breaks are worse than normal ones. Removing costs entirely did not change the answer. |
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
| 29 | 2026-08-10 | **pre-registered, ES 2009-2016, 5-min** | ES as MES | intraday VWAP reversion, REV / REV-HTF | NY window, fade 2.0σ, stop 4.0σ, funded-account bars DROPPED, costs retained | 1,969 | -5.29/trade | **BOTH FAIL. REVERSION IS NEGATIVE BEFORE COSTS: gross -$1.59/trade.** WR 56%, so price usually returns to VWAP, but not far or often enough to pay for the runs, and the 4σ stop makes those losses large. **CONFIRMS Leg A rather than overturning it** -- Leg A died on 177 MES trades and I argued underpowered; on 11x the sample it is disproven. REV-HTF flips gross to +$1.82 and declines trades worth -$5.48, so the higher-timeframe filter does real work, but +$1.82 against $3.70 is still a loss. **SECOND DEGENERATE FILTER IN TWO REGISTRATIONS**: predicted 40-60% take rate, got 5%, because a 2σ extension almost always IS a large 60-min move -- the filter is near-collinear with its own signal. Fix recorded: state and check expected take rate before running. |
| 28 | 2026-08-10 | **pre-registered, ES 2009-2016, 5-min** | ES as MES | entry variants: CONFIRM/STRONG/VOLUME/DAYBIAS x 3 arms | market entries, $3.70 RT, Bonferroni 0.0042 | 12 cells | best +0.09/signal | **ALL TWELVE FAIL.** But the mechanism inverts the previous run: **skipped counterfactuals are NEGATIVE (-$5 to -$8), so these filters REMOVE LOSERS**, where the pullback rule removed winners (+$9 to +$24). Best cell L2N/STRONG +$0.09/signal at p 0.477 -- adding back cost, the admitted trades carry ~$3.90 gross against a $3.70 round trip. **You can filter from -$5 to $0; you cannot filter to positive, because there is no positive signal to concentrate, only cost to avoid.** MY DESIGN ERROR: VOLUME is degenerate on A2L/L2N (100% take rate -- compares a London break bar to an Asian median) and DAYBIAS degenerate on A2L, so ~9 of 12 cells were meaningful tests. Prediction wrong that filters would only trade less; they genuinely selected better trades. |
| 27 | 2026-08-10 | **pre-registered, ES 2009-2016, 5-min** | ES as MES | entry timing: 3 arms x IMMEDIATE/PULLBACK/BIAS | limit at the level, strict trade-through, 6-bar window | 17,288 signals | -4.4/signal avg | **ALL SIX NON-CONTROL CELLS FAIL ALL FIVE CRITERIA.** Validity check passed: IMMEDIATE on 5-min reproduces 30-min to within $0.11 (A2L -5.06 vs -5.09, L2N -3.60 vs -3.71, NYOR -3.58 vs -3.69). **ADVERSE SELECTION DID DOUBLE DAMAGE.** Predicted filled trades would improve on a cheaper fill; instead EVERY ONE got worse (L2N -3.60 -> -6.60) despite saving $0.63 a round turn -- the trades that come back to your limit are the ones about to fail. And the 11-13% that never retraced would have earned +$9.06 / +$23.89 / +$13.93 under immediate entry: a break that never looks back is a real move. **The 10-18 ticks of excursion inside the 30-min entry bar are NOT reachable.** BIAS only improves per-signal loss by trading less. Prediction: right on conclusion, wrong on fill rate (87-89% vs 50-75%) and wrong that filled trades would improve. |
| 26 | 2026-08-10 | **pre-registered, ES 2009-2016** | ES priced as MES | cross-session breakouts A2L/L2N/NYOR | two-sided, 1 contract, stop at opposite side, $3.70 RT | 5,715 | -4.16/trade avg | **ALL THREE FAIL ALL FOUR CRITERIA.** A2L -$5.09 (Sharpe -0.173, t -7.78), L2N -$3.71, NYOR -$3.69. Every one of 8 years negative for every arm. **Gross separates them: L2N +/-$0.01 and NYOR +$0.01 have NO SIGNAL AT ALL on ~1,900 trades each; A2L is -$1.39 gross at t -2.13, NEGATIVE BEFORE COST** -- breaking the Asian range predicts reversal. Two-sided design worked (long share 51-55%), so removing Leg B's long-only bias was not the problem. **REGISTERED PREDICTION WAS CORRECT** on range (-$2 to -$8), on ordering (A2L worst, NYOR best) and on mechanism (mean reversion, confirmed by A2L's significant negative gross). |
| 25 | 2026-08-10 | **pre-registered, ES 2009-2016** | ES priced as MES | overnight BASE/TOM/DOW | 18:00->09:30 ET, 1 contract, $3.70/night | 2,000 nights | -1.82/night | **ALL THREE FAIL.** BASE Sharpe_all -0.041 (p 0.992), TOM -0.012, DOW -0.026. **But the gross premium is REAL: +0.3763 pts/night, t +1.89, gross Sharpe_all 0.0422** -- inside my registered 0.04-0.06 prediction. It fails on cost arithmetic, in points and so instrument-independent: premium 0.376 pts vs 0.500 pts round-trip slippage = 0.75x, before commission. **Ceiling at ZERO cost is Sharpe 0.042, under half the 0.10 bar.** The flat-through-the-halt rule forces a nightly round trip and is itself what makes it negative. DOW picked Thu on 2009-2012 (+$2.38) and returned -$2.43 on 2013-2016. Intraday (+964 pts) beat overnight (+753 pts), so the 'all returns are overnight' claim does not reproduce here. |
| 24 | 2026-08-09 | **BLOCK A, pre-registered** | GC, SI, HG 2011-2013 | commodity ORB, frozen | unchanged params, CAPPED costs, 15-bar window, 30 contracts per metal | **1,087** | **-2.30/trade** | **FAILS ALL THREE CRITERIA.** Pooled -$2.30/trade (CI -$14 to +$9), rotation p 0.646, 0 of 3 metals positive. 2x spread -$11.60, drop-top-10 -$12.10. By year: 2011 -$11, 2012 +$2, 2013 +$3, none distinguishable from zero. **Power was adequate and pre-computed**: se $5.98, so the in-sample $37/trade would have shown t~6.2; observed t -0.38. In-sample PF 1.35 vs 0.97 here. **Registered prediction ($5-25/trade, p<0.05, gold strongest) was WRONG on sign and significance.** THE COMMODITY ORB IS CLOSED. |
| 23 | 2026-08-07 | **OUT OF SAMPLE** | MGC, SI, HG micros | commodity ORB, frozen | unchanged params, CAPPED costs, bars fetched past the sample end | **11** | +95/trade | **INCONCLUSIVE BY CONSTRUCTION, AND SAID SO FIRST.** t +1.43, CI [-$36, +$225]. Power computed in advance: a real edge was predicted to give t~0.7 here, so this could never confirm anything. It did not detect collapse; that is the whole claim. **SI traded 1 session in 17** (27% in-sample) because its opening range doubled, 0.38 to 0.69 pts, putting 76% of sessions past the $500 risk guard. |
| 22 | 2026-08-07 | dev | MGC, SI, HG, MCL, NG | commodity ORB | measured spreads + book-walk depth penalty | 1,271 | n/a | **DEPTH IS THE BINDING CONSTRAINT, NOT SPREAD.** Basket PF 1.39 to 1.32. **MCL turns NEGATIVE** (+$515 to -$2,714, PF 0.91): median order 4 lots against a 1-lot touch, 87% of trades exceed it. Capping size at the touch beats paying the walk: fewer dollars ($27.9k vs $36.5k) but Sharpe 0.117 to 0.130 and t +2.67 to +2.96. |
| 21 | 2026-08-07 | dev | MGC, SI, HG, MCL, NG | commodity ORB | live BID/ASK replacing the flat 1.5 ticks/side | 1,271 | n/a | **THE COST CONSTANT WAS NOT FLATTERING THE RESULT.** Assumed was LOW for SI ($7.50 vs $10.00/side) and HG ($1.88 vs $2.50), HIGH for MCL and NG. Errors offset: net $42,769 to $43,426, PF 1.39 either way. A null finding, and the one that had to be checked first. |
| 20 | 2026-08-07 | dev | 5 commodity micros | **commodity ORB** (sibling project's) | 60-min OR on 30-min bars, long only, stricter stops and slippage than theirs | 1,271 | +33.7/trade | **FIRST CANDIDATE TO CLEAR EVERY GATE.** PF 1.39, rotation p 0.0035, survives dropping the top 20 trades (PF 1.06), both halves hold. Re-tests someone else's headline with this project's apparatus. MNG spec found wrong by 2.5x and corrected. |
| 19 | 2026-08-06 | dev+val | MES via ES prices | feasibility sweep | 36 configs, block bootstrap, real Topstep rules | n/a | n/a | **NO CONFIGURATION PASSES RELIABLY.** Best P(pass) 49.2% against P(breach) 49.9%. Best pass:breach ratio is 1.53 at 31.2%/20.4%. **In-sample and optimistic.** |
| 18 | 2026-08-06 | dev | MES via ES prices | D (overnight hold) | 1 contract, **prop OFF**, unconditioned | 353 | +9.44 | Unconditioned dev result. PF 1.26, CI [-3.06, +21.75] straddles zero. |
| 17 | 2026-08-06 | **VALIDATION** | MES via ES prices | **D (overnight hold)** | frozen from run 16, 1 contract, prop ON | 25 | **-49.05** | **ALL THREE PRE-REGISTERED CRITERIA FAILED. ACCOUNT DIED at session 25 of 232 (11%).** Shape INVERTED: validation overnight +0.87 pts (net -$0.61/sess) while RTH earned +1.67. **LEG D CLOSED.** |
| 16 | 2026-08-06 | dev | MES via ES prices | **D (overnight hold)** | registered defaults, 1 contract, adverse, measured, **prop ON** | 299 | **+10.18** | **PASSED THE COMBINE.** Target hit at session 327/387. PF 1.29, Sharpe 1.42, MDD $1,082 (54% of buffer). **But CI [-2.85, +22.72] straddles zero.** |
| 15 | 2026-08-06 | dev | MES via ES prices | session decomposition | 4 windows, buy-and-hold, 1 contract | 387 | **+8.47/sess** | **FIRST POSITIVE.** Overnight (18:00-09:30) +2.68 pts/session, RTH -0.33. But **t NET = 1.35**, not the 2.15 on the gross mean. Worst night -$851 = 43% of the MLL at ONE contract. |
| 14 | 2026-08-06 | dev | MES via ES prices | barrier screen | path expectancy in R, 270 cells, 3 symmetric geometries | n/a | n/a | **NOTHING.** Best positive PATH +0.0047R, **0 of 270 cells clear the round trip**, best positive is 1.6% of the cost bar. The p=0.000 is a NEGATIVE cell and is not tradeable. |

**Distinct configurations tried: 4.** Legs A, B, C and D. Trial count for correction
purposes is 4; a nominal 0.05 is a family-wise 0.19.

**LEG D IS CLOSED. ALL FOUR LEGS ARE NOW CLOSED.** It passed the Combine on development
data, reaching the $3,000 target at session 327 of 387 with a Sharpe of 1.42, and then
failed every one of its three pre-registered validation criteria. The account was
HALTED_PERMANENT after 25 of 232 validation sessions. See
`RESULTS_VALIDATION_2026-08-06_LEGD.md`.

**The shape inverted rather than weakened.** On validation the overnight window returned
+0.87 points a session, which does not clear its own round trip, while RTH returned +1.67.
The entire premise of Leg D was that returns accrue outside the cash session; over the
following eleven months they accrued inside it.

**What Leg D demonstrated is narrower than "the effect is fake".** This project never had
the power to overturn the overnight/intraday literature: the net t was 1.35 on development
and would be 1.92 using every session including the lockbox. What it showed is that **a
documented risk premium, harvested at the only size a $50,000 evaluation account can carry,
does not survive that account's trailing drawdown rule.** The premium can be real and the
$2,000 buffer still too small to sit through the risk it pays for. Those are compatible,
and together they close the strategy without the effect needing to be false.

**The pre-commitment did its job.** A discretionary reading would have kept Leg D alive on
a 1.42 Sharpe and a Combine pass. The rules, fixed before the run, closed it.

**Significance is not available from this dataset.** At the measured drift of $8.47 a
session against a standard deviation of $123, the net t-statistic is 1.35 on development,
1.71 on development plus validation, and **1.92 using every session including the
lockbox**. No split or combination reaches 2. The question this project can answer is
whether an account survives and passes out of sample, not whether the effect is real.

**Leg D differs from A, B and C in kind, not in quality of result.** Its prior comes from
outside this dataset: the overnight/intraday decomposition is a documented property of
equity indices, not something found by searching these 387 sessions. Legs A to C were
hypotheses invented here and then tested on the data that suggested them. That difference,
and not the encouraging number, is the only honest argument for spending validation.

**Distinct configurations tried before Leg D: 2.** Runs 1 to 10 are the same frozen parameter set
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

## Registered BEFORE execution: run 19 (feasibility sweep)

Measurement only. No entry rule, no P&L, no new split. **The lockbox is not touched.**

**Stated plainly because it governs everything that follows: validation is SPENT.** Any
design chosen after seeing Leg D fail there is, by construction, fitted to data already
seen. Development and validation can now only produce IN-SAMPLE, OPTIMISTIC numbers. The
lockbox is the one remaining out-of-sample test and it is single-use.

**Why a sweep instead of a fifth leg.** Four legs have failed. Before designing another it
is worth establishing whether the ACCOUNT can support the measured edge at all, because if
it cannot then no entry rule fixes it and legs five through eight fail identically.

The structural ratio, measured:

| window | session sd | buffer / sd |
|---|---:|---:|
| GLOBEX_TO_OPEN, dev+val | $141 | 14.2 |
| FULL_SESSION, dev+val | $257 | **7.8** |

A fixed drawdown limit wants twenty or more standard deviations of room. The best here is
fourteen. **One MES contract is the smallest position that exists**, so the exposure cannot
be reduced by sizing down; that is a property of the account and the contract, not of any
signal.

**What is swept**, across every lever genuinely available: window, a causal volatility
gate, the SELF-IMPOSED daily loss cap (a DESIGN choice, not a firm rule, and the only lever
that truncates a session's loss without reducing size), and contract count.

**The bootstrap is blocked, not normal, and that correction matters.** The earlier Monte
Carlo assumed normal returns and put P(breach) at 23% over 387 sessions; the real account
died in 25. The error was not the drift estimate but the tail and the clustering. This
resamples contiguous blocks of actual sessions, mean length ten, so the sample's own worst
stretches carry into the simulation.

**Prediction.** No configuration exceeds 70% P(pass) with P(breach) under 15%, and the
volatility gate helps survival while pushing the target out of reach inside a year. If that
holds, the honest conclusion is that the $2,000 buffer cannot support one MES contract, and
the constraint is the account rather than the strategy.

### Result: prediction correct, and one bug caught on the way

**The first sweep was wrong and reported a 100% pass rate.** The daily stop was applied as
`max(final_return, -cap)`, which floors the session's FINAL return and therefore keeps
every session that traded through the stop intraday and recovered by the close. Measured on
the real moments that look-ahead was worth about **$40 a session against an $8.68 edge**,
and it turned a -$12.57 configuration into +$75.92. Fixed by modelling the stop against
each session's actual maximum adverse excursion. Regression tests build sessions as real
random walks and pin optional stopping: a driftless walk's mean is unchanged by a stop and
a positive-drift walk's mean strictly falls.

**Corrected result. Nothing passes reliably.**

| configuration | $/session | P(pass) | P(breach) |
|---|---:|---:|---:|
| GLOBEX, no gate, no stop, 1ct | 5.06 | 30.0% | 39.3% |
| **GLOBEX, no gate, $150 stop, 1ct** | 6.30 | **31.2%** | **20.4%** |
| GLOBEX, no gate, $300 stop, 2ct | 13.80 | 49.2% | 49.9% |
| FULL_SESSION, no gate, no stop, 1ct | 8.68 | 39.2% | 60.1% |

**Two findings that are real rather than artefacts.**

1. **A $150 per-session loss cap nearly halves ruin, 39.3% to 20.4%, with P(pass)
   unchanged.** Its effect on expectancy is 0.22 standard errors, which is not measurable
   on 619 sessions. This is the one genuine improvement available: it buys survival at no
   detectable cost.
2. **The volatility gate destroys the edge.** FULL_SESSION drops to -$1.76 a session at
   gate 0.60 and -$6.32 at 0.40. That is what the mechanism predicts: a risk premium pays
   in proportion to risk, so filtering out volatility filters out the compensation. Trading
   only calm sessions is closed on evidence, not opinion.

### Horizon result: time helps at one contract, and not at two

| config | 250 | 500 | 750 | 1000 |
|---|---|---|---|---|
| GLOBEX $150 stop, 1 contract | 30%/21% | 58%/32% | 66%/32% | **67%/32%** |
| GLOBEX $300 stop, 2 contracts | 48%/51% | 50%/50% | 51%/49% | 50%/50% |

**Sizing up does not convert time into edge; it converts it into a coin flip that stays a
coin flip forever.** One contract with a $150 cap converges to roughly **2:1 in favour**
and stops improving after about 750 sessions, or three years.

**And the economics close it.** At $6.30 a session and 250 sessions a year:

| | |
|---|---:|
| Gross earnings, 1 contract | **$131/month**, $1,575/year |
| Sessions to the $3,000 target | 476, about **1.9 years** |
| **Break-even evaluation fee** | **$131/month** |

Above roughly $131 a month in evaluation fees, the strategy loses money **even on the 67%
of paths where it passes.** That figure needs checking against Topstep's actual current
pricing, which is one of the unresolved items in
`config/topstep_50k_combine.v1.yaml`, but it is the number the decision turns on rather
than P(pass).

### The fee structure changes the objective (2026-08-06)

Actual costs: **$50 up front, $50 a month, $150 on passing.** The stated preference is to
resolve inside one month rather than pay again.

**Passing inside one month is arithmetically impossible, and not as a matter of tuning.**
$3,000 over 21 sessions is $143 a session. At the measured $6.30 per contract that needs
23 contracts, whose session standard deviation is roughly $2,800 against a $2,000 buffer,
so the buffer is 0.7 of one session's noise. MES has no smaller size, so this is a wall.

**The objective therefore becomes expected total fees to reach a funded account**, not
P(pass):

```
E[fees] = (1-p)/p * (50 + 50 * months_to_fail) + (50 + 50 * months_to_pass) + 150
```

That ranks configurations differently, and the difference is large. A slow grind paying a
subscription for three years per attempt can cost more than a coin flip that resolves in
months, because a **cheap failure beats an expensive success**. Ranking by P(pass) hides it
completely. The 67% one-contract plan and the 49% two-contract plan are roughly $2,200 and
$1,200 on rough duration estimates, which is why the sweep now measures time-to-resolution
directly instead of guessing it.

### Why sizing cannot be the answer (2026-08-06)

Three proposals were raised: size up to finish faster, take fewer larger trades, take more
smaller ones. **They are the same move**, and the reason none can work is one line:

> Position size multiplies BOTH the edge and the noise by the same number, so the
> per-session ratio `mu/sigma` is invariant to size.

Measured, one MES contract, overnight window, $150 cap:

| size | mu | sigma | mu/sigma | sessions to +$3,000 |
|---:|---:|---:|---:|---:|
| 1 | 6.30 | 124 | 0.0508 | 476 |
| 3 | 18.90 | 372 | 0.0508 | 159 |
| 12 | 75.60 | 1,488 | 0.0508 | 40 |

Identical every row. Size trades speed against P(pass) and touches nothing else.

**What the account demands, in the same units:** 24 sigma of gain while never giving back
16 sigma from a peak, against a per-session ratio of 0.051, an annual Sharpe near 0.8.

**Only three things move that ratio: cost, variance, and instrument.** `tools/edge_budget.py`
prices all three against the requirement, and reports P(pass) as a function of per-session
Sharpe and horizon using the real return distribution rescaled to each Sharpe, so the fat
tail and the clustering survive rather than being assumed away.

**The largest unexamined lever is cost.** The round trip is $4.95 against a gross overnight
edge of $13.42, so **37% of the edge is spent crossing the spread twice a day for a
position held fifteen hours.** A scheduled exposure has no signal urgency, so a resting
limit order is available in a way it is not for a breakout. Saving one tick a side lifts
the annual Sharpe from 0.80 to 1.24; two ticks takes it to 1.40.

**Prediction, registered before the run:** no single lever reaches the Sharpe needed for
75% P(pass) inside six months, and the cost lever is the largest of the three.

### Registered BEFORE execution: run 20 (account size)

The one lever that changes the DENOMINATOR rather than the numerator. Every other lever
tried to raise the per-session Sharpe, and each has now been measured and closed. This one
leaves the strategy untouched and changes what the account asks of it.

Sizes available: **$50k** (buffer $2,000, target $3,000), **$100k** ($3,000 / $6,000),
**$150k** ($4,500 / $9,000).

**Two effects fight, which is why this needed simulating rather than asserting.**

In favour of bigger: the buffer scales **linearly** with the account, while the drawdown
that must be survived scales as the **square root** of the time exposed. Doubling both
target and buffer doubles the room and only root-two's the danger.

| account | buffer | target | sessions to target at 1 contract | rough E[max drawdown] | **buffer / drawdown** |
|---|---:|---:|---:|---:|---:|
| $50k | 2,000 | 3,000 | 476 | 2,706 | **0.74** |
| $100k | 3,000 | 6,000 | 952 | 3,827 | **0.78** |
| $150k | 4,500 | 9,000 | 1,429 | 4,687 | **0.96** |

Against bigger: **target/buffer worsens from 1.5 on the $50k to 2.0 on both others**, so
luck alone passes less often. Gambler's-ruin on a fixed floor would be 40%, 33% and 33%.

**Prediction: the $150k geometry produces the largest edge lift over its own luck-only
baseline, but takes materially longer at any given contract count, so it wins on P(pass)
and loses on fees.** The fee schedules for the larger Combines have not been supplied, so
the cost column is comparable only within an account size and that has to be said on the
page rather than assumed away.

### Result: prediction 4 for 4, and the conclusion is the opposite of my reasoning

| account | qty | B/sd | PASS | luck | LIFT | BREACH | months |
|---|---:|---:|---:|---:|---:|---:|---:|
| 150k | 1 | 36.4 | **89%** | 11% | **+78%** | 6% | 60.6 |
| 100k | 1 | 24.3 | 80% | 17% | +63% | 19% | 38.2 |
| 150k | 2 | 18.2 | 69% | 19% | +50% | 30% | 25.1 |
| **50k** | **1** | 16.2 | **67%** | 25% | +42% | 33% | **14.6** |
| 100k | 2 | 12.1 | 55% | 19% | +36% | 45% | 12.9 |
| 150k | 3 | 12.1 | 54% | 19% | +35% | 46% | 13.0 |

Every registered claim held: largest lift on the 150k, materially longer, wins on P(pass),
loses on fees.

**P(pass) is almost entirely a function of buffer/sd.** Two rows at B/sd 12.1 give 55% and
54%. Two at 8.1 give 49% and 43%. Two at 4.0 give 38% and 42%. Once B/sd is matched the
account size barely matters, which makes B/sd the single governing parameter of the whole
problem.

**But the comparison that decides anything is at MATCHED TIME, because time is what is
being paid for. And there the $50k wins.**

| ~13-15 months | PASS | BREACH |
|---|---:|---:|
| **50k x1** | **67%** | **33%** |
| 100k x2 | 55% | 45% |
| 150k x3 | 54% | 46% |

At matched P(pass) it wins too: 50k x1 reaches 67% in 14.6 months, 150k x2 reaches 69% in
25.1.

**My pre-run reasoning was wrong, and the algebra says why.** I argued that a bigger buffer
helps because buffer scales linearly while drawdown scales as the square root of time. That
is true at a FIXED contract count, which is not the comparison that matters. At a matched
time-to-target `n`, the position size is `q = T/(mu*n)` and the drawdown works out to

```
buffer / drawdown  proportional to  (B/T) x (mu/sigma) x sqrt(n)
```

The account enters only through **B/T**, its buffer-to-target ratio: **0.667 on the $50k
against 0.500 on both others.** The $50k is 33% better on the only account term that
survives, and the larger Combines help solely by forcing a longer horizon, which is the
thing being paid for.

**Conclusion: the $50k Combine is the best of the three geometries for this strategy, and
switching account size is closed as a lever.** The best configuration in the whole project
remains what it already was: overnight window, one MES contract, $150 self-imposed session
cap, no volatility gate. 67% pass against 33% breach over roughly 15 months, in-sample and
optimistic.

### Edge budget result: the requirement is six times the edge (2026-08-06)

Measured, one MES contract, overnight window, $150 cap, 619 sessions:

| | |
|---|---:|
| gross edge | $11.25/session |
| round trip | $4.95, **44% of gross** |
| net edge | $6.30/session |
| session sd | $123.53 |
| **per-session Sharpe** | **0.0510** (annual 0.81) |
| target in sd | 24.3 |
| buffer in sd | 16.2, **and it trails** |

**Sharpe required** for a given P(pass), simulated with the real return distribution
rescaled to each Sharpe so the fat tail and clustering survive:

| P(pass) | 6mo | 12mo | 24mo |
|---:|---:|---:|---:|
| 60% | 0.200 | 0.100 | 0.075 |
| 75% | 0.300 | 0.150 | 0.075 |

**What each lever is worth:**

| lever | Sharpe | annual | change | reaches |
|---|---:|---:|---:|---|
| measured now | 0.0510 | 0.81 | | nothing in the table |
| limit entry, save 1 tick/side | 0.0712 | 1.13 | +40% | nothing |
| limit entry, save 2 ticks/side | 0.0915 | 1.45 | +79% | **75% in 24 months** |
| cut session sd by 20% | 0.0637 | 1.01 | +25% | nothing |

**Registered prediction was 2 for 2:** no lever reaches 75% inside six months (that needs
0.300, six times the measured value), and cost is the largest of the three.

**The best realistic outcome in the whole table is 75% inside 24 months**, costing
$50 + 24 x $50 + $150 = $1,400 in fees.

**Registered addition: the 2-tick saving is an ASSUMPTION and must be measured.** A resting
buy limit fills preferentially when price is falling, so the filled sessions are worse than
the unfilled ones by construction. That is adverse selection, and for a passive order it is
typically of the same order as the spread it saves. Assuming the saving without measuring
the selection is exactly the error that produced a 100% pass rate in the feasibility sweep.

`tools/limit_entry.py` measures both on MES BID/ASK bars and reports the net:

```
net = spread saved - (E[session return | filled] - E[session return])
```

**Prediction: the selection term cancels most of the saving, the net is under half a tick,
and the cost lever in the edge budget is therefore largely fictional.** If that holds, no
realistic lever reaches an acceptable pass rate and the constraint is the account, not the
strategy.

### Result: the cost lever is not fictional, it is NEGATIVE

| offset | wait | saving | adverse selection | net | vs the $6.30 net edge |
|---:|---:|---:|---:|---:|---:|
| 1 tick | 5 min | +1.25 | **-13.00** | **-11.75** | -1.9x |
| 1 tick | 60 min | +1.25 | -6.95 | -5.70 | -0.9x |
| 2 ticks | 5 min | +2.50 | **-18.99** | **-16.49** | -2.6x |
| 2 ticks | 60 min | +2.50 | -8.99 | -6.49 | -1.0x |

Adverse selection runs **five to eight times** the spread it saves. The best case nets
-$6.49 a session against a total net edge of $6.30: passive entry does not fail to help, it
removes the entire strategy and a little more.

The mechanism is plain. At a 1-tick offset and a 5-minute wait, 82% of sessions fill at
-$13.00 against the average, so the 18% that did NOT fill returned **+$59** against it. A
session that never ticks down in its first minutes is a session going up, and resting a bid
selects almost perfectly for the ones going down.

**Prediction check: direction right, magnitude badly wrong.** I expected roughly zero and
measured roughly minus one entire edge.

**Recorded and NOT chased.** That +$59 on non-filling sessions is a large conditional
effect and causal in form, since the first five minutes precede the rest. It is also 41
sessions on the 11-month sample, found while measuring something else, and partly
mechanical: a session ending far above average is unlikely to have ticked down early, so
the conditioning and the outcome share a cause. Building a fifth leg from it would mean
testing a post-hoc observation on data that is either spent or is the single-use lockbox.

**THE LEVER TABLE IS NOW CLOSED.**

| lever | verdict |
|---|---|
| Position size | Cannot change Sharpe. Arithmetic, not evidence. |
| Cost | The only available reduction costs 5-8x what it saves. **Closed.** |
| Variance | Worth +25%. Not close to enough. |
| Instrument | **Untested.** Needs data we do not have. |

The measured overnight edge is about 0.05 Sharpe a session. A $50,000 Combine asks for 24
standard deviations of gain without ever surrendering 16 from a peak. No entry rule changes
either number, and three of the four levers that could have closed the gap are now measured
and closed. See `RESULTS_2026-08-06_EDGE_BUDGET.md`.

### Cost-to-funded result, and a correction to my own reasoning

| plan | PASS | luck only | LIFT | months to pass | E[fees] |
|---|---:|---:|---:|---:|---:|
| flat 6 contracts | 39% | 29% | +10% | 0.7 | **$361** |
| flat 3 contracts | 42% | 28% | +14% | 2.0 | $488 |
| flat 1 contract | 68% | 24% | **+44%** | 14.6 | $1,217 |

**Correction.** I argued that 39% at six contracts was pure gambler's ruin, on the grounds
that a fixed floor gives `buffer/(buffer+target)` = 2000/5000 = 40%. **That baseline is
wrong for this account.** The Topstep MLL TRAILS: it ratchets up on every new peak, so a
$2,000 drawdown from a high kills the account even while it is still in profit. Measured
driftless, that costs more than ten percentage points, putting luck alone at **24-29%
rather than 40%**. Six contracts is therefore a real +10 point lift, not decoration. The
claim was wrong; the direction it pointed was not.

**The `luck only` column is now computed by the tool**, by re-running each plan with the
mean removed and everything else, volatility, fat tails and clustering, left intact. Any
plan whose lift is near zero is a coin flip with a backtest attached.

**What the table actually says.** Sizing up shortens the horizon faster than the edge
accumulates, because drift grows with n while noise grows with sqrt(n). The edge is worth
0.89 standard deviations over a one-contract path and 0.19 over a six-contract one. So
cheap plans are cheap because they resolve before the edge can matter.

**The decision reduces to one unknown.** Break-even value of a funded account between the
two ends of the table:

```
0.68V - 1,217  =  0.39V - 361     ->     V = $2,952
```

Worth more than about $2,950 and the slow one-contract plan wins; worth less and the fast
six-contract plan does. That is the number to argue about, and it is not a property of the
data.

**Registered addition: ramp sizing.** The last principled lever, and it comes from the rule
structure rather than from the data. The MLL floor is `min(peak - buffer, starting
balance)`, so it LOCKS once the account reaches +$2,000; past that point the account can
lose nothing but profit it has already earned. Sizing up from the start doubles exposure
through the only genuinely dangerous stretch, which the table above shows is fatal. Sizing
up only AFTER the lock applies the larger size to a bounded downside. **Prediction: the
ramp raises P(pass) and shortens the path without materially raising P(breach), because the
first $2,000 is still traded at one contract.**

**Registered addition: horizon sensitivity.** The one lever not yet swept. At $5-6 a
session, 250 sessions yields $1,250-1,575 against a $3,000 target, so most paths end in
neither verdict. Topstep imposes no time limit, and the MLL floor LOCKS at the starting
balance once the account is +$2,000, after which it can only give back profit already
earned. Time should therefore help asymmetrically. **Prediction: P(pass) rises materially
with horizon while P(breach) rises much less, because the lock makes the first $2,000 the
only genuinely dangerous stretch.**

---

## Registered BEFORE execution: run 17 (Leg D on VALIDATION) and run 18 (unconditioned dev)

**Run 17 spends the validation split.** Registered before execution, parameters frozen
exactly as they stand, and the pass criteria fixed here so they cannot be adjusted after
seeing the result.

Under the rule that closed Leg C, positive expectancy with a CI straddling zero means
closed as undetectable with no validation spend. Leg D does not get an exemption for being
interesting. It gets one for a reason about mechanism: its prior is external to this
dataset, so validation is testing a hypothesis the data did not generate.

**All three criteria must hold. Any one failing closes Leg D.**

1. **Shape replicates.** Overnight positive and RTH flat or negative on validation,
   measured by `session_decomposition.py`. If the shape inverts, Leg D is closed
   regardless of P&L.
2. **Survival.** No MLL breach across the validation split at one contract.
3. **Expectancy positive.** Sign only. Significance is unavailable at n=232 (net t would
   be about 1.05) and will not be claimed.

**The lockbox stays shut either way.** It is single-use and reserved for a final go/no-go
on frozen rules, not for a third look at an underpowered question.

**Run 18 is the unconditioned development result**, `--no-prop` over all 387 sessions. The
prop run stopped at session 327 because it WON, so its win rate, expectancy and drawdown
are conditioned on reaching the target. That has to be on the record next to the pass.

**Prediction.** The shape replicates (overnight positive, RTH negative), the account
survives, and validation expectancy is positive but smaller than development's $10.18,
because the development split is the stronger part of the bull market. Two of my last five
predictions were wrong on magnitude, so the interval on that guess is wide.

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
| validation | **SPENT** on run 17 (Leg D) |
| lockbox | **UNTOUCHED**, single-use, and no candidate has earned it |

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
