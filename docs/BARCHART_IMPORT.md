# Getting Deeper History from Barchart

Barchart Premier is a viable route to the multi-year history this project needs. This
document covers what to download, the limits you will hit, and the one failure mode that
would silently invalidate every result.

---

## 1. Download the MICROS, not ES

The link you started from was `ESM26`, the full-size E-mini. **Download `MES` and `MNQ`
instead.**

ES and MES track the same index within a tick, so ES would serve for signal research. But
using it would introduce a cross-instrument assumption that has to be documented and
validated, and it buys nothing: MES launched in May 2019, so Barchart's ~10-year intraday
window already covers its entire history. There is no reason to accept the assumption when
the real instrument is available.

**Barchart symbol format:** root + month code + two-digit year.

| Month code | Month | | Month code | Month |
|---|---|---|---|---|
| H | March | | U | September |
| M | June | | Z | December |

Equity-index futures are quarterly, so only `H`, `M`, `U`, `Z` are used.

Examples: `MESM26` = MES June 2026 · `MNQZ25` = MNQ December 2025 · `MESH24` = MES March
2024.

For five years of both instruments you need roughly **40 contracts**: `MESH22` through
`MESU26`, and the same for `MNQ`.

---

## 2. The limits you will hit

| Limit | Value | What it means here |
|---|---|---|
| Downloads per day | 250 (Premier) | Two days of downloading covers 5-7 years |
| Records per request | **10,000** | This is the binding one |
| Intraday history | ~10 years | More than enough |

**10,000 records is what shapes the work.** At 1-minute resolution:

| Coverage | Minutes/day | Days per download | Downloads for 5y, both instruments |
|---|---:|---:|---:|
| Full session (~23h) | 1,380 | 7.2 | **~360** |
| RTH only (6.5h) | 390 | 25.6 | **~101** |

Each dated contract is the liquid front month for roughly 65 trading days, so at full
session that is about 9 downloads per contract.

**Recommendation: download the full session.** RTH-only is nearly four times cheaper, but
it changes what "session" means: session VWAP would anchor at 09:30 instead of 18:00, and
relative volume would be computed over a different window. Results would not be directly
comparable to the IBKR runs already recorded. Leg B alone would survive RTH-only data, but
comparability is worth the extra downloads.

---

## 3. The failure mode that matters

**Barchart writes intraday timestamps in whatever timezone your account is set to, and the
CSV contains no timezone marker.**

If your account is set to Central Time and the data is read as Eastern, every bar shifts by
an hour. The opening range gets built from 08:30 data. The RTH filter admits the wrong
bars. And the backtest runs perfectly and reports entirely plausible numbers. Nothing
crashes, nothing looks wrong, and the results are worthless.

This is the worst class of bug in this project, so `tools/import_barchart.py` does not
accept a timezone on trust. It **infers** the timezone from the data: the US equity open at
09:30 ET produces an unmistakable volume spike, so the importer finds that spike and works
out which timezone assumption puts it in the right place.

On test data the correct timezone scores about **19x** baseline while the wrong one scores
about **2.5x**. If no candidate wins decisively, the importer **refuses to import** rather
than guess.

It also verifies every file individually against the resolved timezone, so a single export
made after you changed your account setting cannot shift one contract by an hour while
everything else stays correct.

Note that the check is *relative*, not a fixed threshold. A one-hour shift still lands the
"09:30" window inside elevated RTH volume and scores around 2.5x, which would sail past any
absolute cut-off. What exposes it is another timezone scoring far better on the same file.

---

## 4. Procedure

### Step 1: download

On Barchart, for each contract, use **Historical Data Download**, select 1-minute
intraday, and step through the contract's active window in chunks under 10,000 records
(about 7 days each at full session).

Save the files with the contract symbol in the filename, for example
`MESM26_2026-04-01.csv`. The importer reads the symbol from the filename.

You do NOT need to move them. Point `--src` at wherever the browser saved them:

```powershell
py tools\import_barchart.py --src $HOME\Downloads --out data
```

The importer only picks up files that carry a contract symbol, either in the filename or
in a `Symbol` column inside the CSV, so bank statements and invoices sitting in the same
folder are counted and skipped rather than aborting the run.

### Step 2: check ONE file before downloading hundreds

```powershell
py tools\import_barchart.py --check downloads\MESM26_2026-04-01.csv
```

You want to see a decisive timezone verdict:

```
  timezone       America/Chicago   (opening-spike scores: Chicago=18.95x, New_York=2.54x, ...)
```

If it says `UNRESOLVED`, stop and fix it before spending your download quota. The usual
cause is a missing Volume column, which the inference needs.

### Step 3: import

```powershell
py tools\import_barchart.py --src downloads --out data
```

This writes `data\MES\MES_202606_1min_TRADES.parquet` and a `.meta.json` recording the
timezone used **and how it was determined**.

### Step 4: validate

```powershell
py tools\validate_data.py data --json data\validation_report.json
```

The same gates as the IBKR data: session completeness, front-month attribution, OHLC
coherence, gaps, price continuity.

### Step 5: re-run with the rules frozen

```powershell
py run_backtest.py --data data --split dev --measured-costs config\measured_costs.json --report out
```

---

## 4a. If you downloaded ES instead of MES

Barchart's contract picker makes this easy to do: `ESH24` and `MESH24` sit next to each
other. The importer labels ES data as ES, so nothing is silently mixed up, but the
question of whether ES can substitute for MES has to be answered before using it.

**Do not assume either way.** SPECIFICATION.md section 3 forbids transferring parent
levels to micro execution, but that rule was written as a precaution rather than a
measurement. Since the IBKR MES data overlaps the Barchart ES data, the assumption can be
tested directly:

```powershell
py tools\compare_es_mes.py --data data
```

It reports three things, in increasing order of importance:

1. **Price basis**, ES minus MES, in ticks.
2. **Opening-range level differences**, computed independently on each.
3. **Whether Leg B's entry trigger fires identically on both.** This is the decisive one.
   Feature levels agreeing on average is not the question; whether the strategy would have
   taken the same trades is.

Verdict thresholds, fixed in advance so the answer is not chosen after seeing it:

| Trigger disagreement | Verdict |
|---|---|
| ≤ 2% | ES is an acceptable proxy for signal research |
| 2% to 10% | Marginal: exploratory only, re-run the verdict on MES |
| > 10% | Not acceptable, re-download as MES |

Leg B's edge is a few ticks wide. A disagreement rate above 10% would mean the ES
backtest is testing a materially different strategy from the one you would trade.

**Regardless of the outcome, costs, fills, and sizing come from MES.** ES quotes a
different book with different depth, and `config/measured_costs.json` is already built
from MES quotes.

---

## 5. The discipline that makes this worth doing

**Freeze the rules before you look at the new data.**

The parameters in `engine/config.py` are exactly as they were when Leg B failed on 11
months. If they are adjusted after seeing the deeper history, the new sample is
contaminated in precisely the way tuning would have contaminated the old one, and the
larger dataset buys nothing at all.

Register the run in `docs/EXPERIMENT_LEDGER.md` **before** executing it.

---

## 6. What deeper history does and does not fix

**Fixes:** statistical power. Development n goes from 72 toward roughly 800, and the
minimum detectable edge drops from ~0.28R to ~0.06R, which is inside the range where a real
intraday edge could live. It also supplies genuine volatility-regime diversity, which 11
months of one regime cannot.

**Does not fix:** the concentration failure. Leg B's development result turned negative
after removing a single day out of 115. That is a property of what was measured, not of how
much was measured. A larger sample gives a fairer test; it does not make the previous
result better.

**Also unchanged:** costs still come from IBKR quote measurement. Barchart supplies trade
data only, so `config/measured_costs.json` remains the cost source and remains a lower
bound on real execution cost.
