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

**Distinct configurations tried: 1.** Runs 1 to 6 are the same frozen parameter set
evaluated under three predeclared cost scenarios, which is a robustness check rather than a
search. No parameter has been tuned against a result.

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

## Notes

- Runs 1-6 used engine 0.1.0 at commit `0670cb2`.
- Rejection counters from runs before `0670cb2` are not comparable across reasons; filters
  were evaluated at different points in the chain. Trade results are unaffected.
- Costs in all runs are **assumed**, not measured. No BID/ASK data exists yet, so the
  fragility gate can be demonstrated but not properly evaluated.
