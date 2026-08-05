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

**Distinct configurations tried: 1.** Runs 1 to 10 are the same frozen parameter set
evaluated under three predeclared cost scenarios, a measured-cost re-run, and a three-year
re-run on validated proxy data. That is robustness checking, not a search. **No parameter
has been tuned against any result at any point.**

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

**Splits consumed:**

| Split | Status |
|---|---|
| development | used (runs 1-6) |
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
the opening hour is NOT wider than midday (1.00x for both instruments), and MNQ is NOT
the cheaper instrument in dollars per contract.

## Notes

- Runs 1-6 used engine 0.1.0 at commit `0670cb2`.
- Rejection counters from runs before `0670cb2` are not comparable across reasons; filters
  were evaluated at different points in the chain. Trade results are unaffected.
- Runs 1-6 used **assumed** costs. Runs 7-8 used **measured** spreads from 348,857 MES and
  348,741 MNQ quote-bars. The MES adverse prior matched measurement exactly, so the verdict
  is unchanged and the fragility gate is now properly evaluated rather than merely
  demonstrated.
