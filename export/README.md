# Futures bar data: schema, provenance, and the things that will bite you

One file: `futures_bars.csv.gz` (14.9 MB gzipped) or `futures_bars.parquet` (15.1 MB),
identical content. **1,429,311 bars**, 4 instruments, 65 contract months, 2008-2016.

This README exists because the bars alone are not enough to use them correctly. Every
section below is something that was measured or verified in the project that produced this
file, not assumed.

## Schema

| column | type | notes |
|---|---|---|
| `symbol` | string | `ES`, `GC`, `SI`, `HG` |
| `contract_month` | string | `YYYYMM`, e.g. `201109` for Sep 2011 |
| `bar_size` | string | `5min` or `30min` |
| `timestamp_utc` | datetime, UTC, tz-aware | **bar OPEN time**, not close |
| `open` `high` `low` `close` | float64 | see the float32 warning below |
| `volume` | int32 | contracts traded in the bar |

Integrity checks, all passing on the shipped file: **0** duplicate
`(symbol, contract, bar_size, timestamp)` rows, **0** rows violating
`low <= open/close <= high`, **0** null OHLC, **0** non-positive prices, **0** negative
volume.

**Do not cast prices to float32.** It was tried and rejected: the values do not round-trip
exactly, because tick sizes like gold's 0.10 and copper's 0.0005 are not binary fractions.
Keep float64 or convert to scaled integers.

## Coverage

| series | bars | contracts | first | last |
|---|---:|---:|---|---|
| ES 30min | 206,171 | 35 | 2008-05-04 | 2016-12-16 |
| ES 5min | 639,968 | 32 | 2008-12-03 | 2016-12-16 |
| GC 30min | 223,321 | 30 | 2008-06-02 | 2016-12-28 |
| HG 30min | 184,971 | 30 | 2009-06-16 | 2016-12-28 |
| SI 30min | 174,880 | 30 | 2008-11-11 | 2016-12-28 |

ES 30min and ES 5min are the **same market at two resolutions**, independently downloaded.
They were cross-validated against each other: 26 bars out of 108,852 disagreed (0.024%),
every one of them the first bar of a file in an incomplete window. The 30-minute series can
also be rebuilt from the 5-minute one, which is a useful self-check.

## Timezone handling, which is where most people go wrong

`timestamp_utc` is UTC and tz-aware. **Convert to `America/New_York` with a DST-aware
library. Never apply a fixed UTC offset.** The eight years here span sixteen DST
transitions and US and EU transition dates do not coincide, so a fixed offset silently
misclassifies the London session for several weeks a year.

The source exports were in `America/Chicago`. That was not taken on faith: it was inferred
by **two independent methods** that had to agree, and the importer aborts if they disagree.

1. The volume spike at the 09:30 ET equity open.
2. The nightly CME maintenance halt at 17:00-18:00 ET, detected as a bar-count hole. This
   one works on thin instruments and coarse bars where the volume method does not.

## CME session boundaries

A CME futures session runs **18:00 ET to roughly 17:00 ET the next day**. So Monday
evening's 18:00 bar belongs to **Tuesday's** session.

**The halt window, measured on this data rather than assumed.** Bar counts per 5-minute ET
slot for ES, as a fraction of the median active slot:

| ET slot | fill | |
|---|---:|---|
| 16:00-16:15 | 98% | normal |
| **16:20-16:30** | **0%** | daily settlement break |
| 16:30-17:00 | 88% | normal |
| 17:00-17:15 | 73% | partial |
| 17:15-17:30 | 38% | partial |
| **17:30-18:00** | **0-1.5%** | maintenance halt |
| 18:00 onward | 100% | next session |

Two corrections to the folklore. First, the fully empty window is **17:30-18:00 ET**, not
17:00-18:00: there are real bars between 17:00 and 17:30 and a model that discards them
throws away data. The 73% and 38% fills are because the session close time **changed during
2008-2016**, so the boundary is not constant across this sample. Second, ES has a **second**
break at **16:20-16:30 ET** for daily settlement, which is entirely absent from the metals
and is easy to mistake for missing data.

Metals show the same 17:30-18:00 hole (GC: exactly 0 bars) and no 16:20 break.

Assign a session date by shifting into ET and adding 6 hours before taking the date:

```python
ET = ZoneInfo("America/New_York")
session_date = (ts.tz_convert(ET) + pd.Timedelta(hours=6)).date
```

**Minutes since open (`mso`)** is the DST-correct intraday clock. `mso = 0` is 09:30 ET.
It must be measured against the bar's own *session*, not against wall-clock time: a naive
clock-only version reads an 18:00 ET bar as +510 minutes after the open instead of -930
before it. Nothing traded overnight in the original code, so that bug was invisible until
overnight features were added.

Session windows used in the project, in `mso`:

| session | mso range |
|---|---|
| Asia | -930 to -390 |
| London | -390 to 0 |
| New York | 0 to 390 |

## Prices are UNADJUSTED and per-contract. Nothing here is stitched.

Each row carries its own `contract_month` at that contract's own raw prices. **No continuous
series is built and no back-adjustment is applied**, deliberately: stitching is a decision
(which roll rule, which adjustment) and baking it into the export would hide that decision.

A roll therefore shows up as a **price discontinuity between sessions**. That gap is real.
Smoothing it away manufactures overnight P&L nobody could have earned.

### The roll rule this data was analysed with

Volume crossover, decided **one session in arrears** so it is causal, with two corrections
that were each found by a bug that had already corrupted results:

1. **A volume floor.** A session must carry at least 1% of total volume to vote. Without it
   a 2-lot session in April 2011 latched the December contract and served it for all of
   2013.
2. **Asymmetric confirmation.** Move forward to a later contract immediately on a
   crossover, but move *backward* only after the earlier contract has won **3 consecutive
   sessions**. Without it a single anomalous session (2011-09-26, 1,077 lots) latched silver
   to `201212` and corrupted 211 of 820 sessions.

A plain `cummax` on the volume winner is wrong in both directions. Both bugs produced
plausible-looking output.

## Contract specifications, verified against CME

The bars are for the **full-size** contracts. Analysis in this project priced them as the
**micro** equivalents, which trade the same underlying at a smaller multiplier.

| | full-size point value | micro | micro point value | tick | micro tick value |
|---|---:|---|---:|---:|---:|
| ES | $50.00 | MES | $5.00 | 0.25 | $1.25 |
| GC | $100.00 | MGC (10 oz) | $10.00 | 0.10 | $1.00 |
| SI | $5,000 | SIL (1,000 oz) | $1,000 | 0.005 | $5.00 |
| HG | $25,000 | MHG (2,500 lb) | $2,500 | 0.0005 | $1.25 |

Verify against CME directly before trusting any of these. One spec in this project was
wrong by 2.5x until it was checked: MNG was recorded at 2,500 MMBtu when it is 1,000.

## The 20,000-bar download cap

The source (Barchart) caps a single download at **20,000 bars and truncates from the OLDEST
end**. **32 of 157 contract-series in this file sit at that cap**, meaning their early
history is missing, not absent from the market.

Practical consequence: at 5-minute resolution one download covers roughly one front-month
window, so a contract's coverage begins partway into its life. Do not read a contract's
first bar as the start of its trading history, and do not compute "days to first trade"
style features from it.

## Known data caveats

- **Thin sessions.** Some sessions have almost no volume in the active contract. Flag them;
  do not silently drop them, and do not let them vote in a roll decision.
- **Entries near expiry.** The project blocked new entries within 5 sessions of expiry and
  during roll sessions.
- **Incomplete windows.** The first bar of each file in a truncated window is the one place
  the 5-min and 30-min ES series disagree.
- **Volume is contract volume**, not aggregated across the curve.

## Load it

```python
import pandas as pd

df = pd.read_csv("futures_bars.csv.gz", parse_dates=["timestamp_utc"])
# or: df = pd.read_parquet("futures_bars.parquet")

df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
es = df[(df.symbol == "ES") & (df.bar_size == "5min")]
```

| symbol | bars | contract | first bar (UTC) | last bar (UTC) |
|---|---:|---|---|---|
| ES 30min | 1,364 | 200806 | 2008-05-04 | 2008-06-20 |
| ES 30min | 3,100 | 200809 | 2008-05-05 | 2008-09-19 |
| ES 30min | 3,457 | 200812 | 2008-06-24 | 2008-12-19 |
| ES 30min | 4,272 | 200903 | 2008-09-22 | 2009-03-20 |
| ES 30min | 5,195 | 200906 | 2008-11-04 | 2009-06-19 |
| ES 30min | 5,573 | 200909 | 2008-12-23 | 2009-09-18 |
| ES 30min | 5,661 | 200912 | 2008-11-04 | 2009-12-18 |
| ES 30min | 5,415 | 201003 | 2009-01-20 | 2010-03-19 |
| ES 30min | 5,445 | 201006 | 2009-04-15 | 2010-06-18 |
| ES 30min | 5,715 | 201009 | 2009-09-09 | 2010-09-17 |
| ES 30min | 6,247 | 201012 | 2010-01-05 | 2010-12-17 |
| ES 30min | 5,706 | 201103 | 2010-03-15 | 2011-03-18 |
| ES 30min | 5,392 | 201106 | 2010-06-24 | 2011-06-17 |
| ES 30min | 5,712 | 201109 | 2010-08-10 | 2011-09-16 |
| ES 30min | 6,058 | 201112 | 2010-10-21 | 2011-12-16 |
| ES 30min | 6,047 | 201203 | 2011-03-07 | 2012-03-16 |
| ES 30min | 5,645 | 201206 | 2011-04-18 | 2012-06-15 |
| ES 30min | 6,026 | 201209 | 2011-06-17 | 2012-09-21 |
| ES 30min | 6,131 | 201212 | 2011-09-21 | 2012-12-21 |
| ES 30min | 5,679 | 201303 | 2012-03-19 | 2013-03-15 |
| ES 30min | 5,993 | 201306 | 2012-04-24 | 2013-06-21 |
| ES 30min | 6,443 | 201309 | 2012-09-20 | 2013-09-20 |
| ES 30min | 6,933 | 201312 | 2012-10-17 | 2013-12-20 |
| ES 30min | 6,726 | 201403 | 2013-03-08 | 2014-03-21 |
| ES 30min | 6,364 | 201406 | 2013-03-28 | 2014-06-20 |
| ES 30min | 6,593 | 201409 | 2013-07-29 | 2014-09-19 |
| ES 30min | 6,810 | 201412 | 2013-09-25 | 2014-12-19 |
| ES 30min | 6,765 | 201503 | 2014-01-06 | 2015-03-20 |
| ES 30min | 6,845 | 201506 | 2014-05-29 | 2015-06-19 |
| ES 30min | 6,305 | 201509 | 2014-07-17 | 2015-09-18 |
| ES 30min | 7,068 | 201512 | 2014-09-23 | 2015-12-18 |
| ES 30min | 6,974 | 201603 | 2015-01-07 | 2016-03-18 |
| ES 30min | 7,240 | 201606 | 2015-04-16 | 2016-06-17 |
| ES 30min | 7,547 | 201609 | 2015-07-08 | 2016-09-16 |
| ES 30min | 7,725 | 201612 | 2015-09-29 | 2016-12-16 |
| ES 5min | 19,999 | 200903 | 2008-12-03 | 2009-03-20 |
| ES 5min | 19,999 | 200906 | 2009-03-09 | 2009-06-19 |
| ES 5min | 19,999 | 200909 | 2009-06-09 | 2009-09-18 |
| ES 5min | 19,999 | 200912 | 2009-09-06 | 2009-12-18 |
| ES 5min | 19,999 | 201003 | 2009-12-03 | 2010-03-19 |
| ES 5min | 19,999 | 201006 | 2010-03-09 | 2010-06-18 |
| ES 5min | 19,999 | 201009 | 2010-06-08 | 2010-09-17 |
| ES 5min | 19,999 | 201012 | 2010-09-07 | 2010-12-17 |
| ES 5min | 19,999 | 201103 | 2010-12-06 | 2011-03-18 |
| ES 5min | 19,999 | 201106 | 2011-03-07 | 2011-06-17 |
| ES 5min | 19,999 | 201109 | 2011-06-07 | 2011-09-16 |
| ES 5min | 19,999 | 201112 | 2011-09-06 | 2011-12-16 |
| ES 5min | 19,999 | 201203 | 2011-11-30 | 2012-03-16 |
| ES 5min | 19,999 | 201206 | 2012-03-06 | 2012-06-15 |
| ES 5min | 19,999 | 201209 | 2012-06-12 | 2012-09-21 |
| ES 5min | 19,999 | 201212 | 2012-09-11 | 2012-12-21 |
| ES 5min | 19,999 | 201303 | 2012-11-23 | 2013-03-15 |
| ES 5min | 19,999 | 201306 | 2013-03-11 | 2013-06-21 |
| ES 5min | 19,999 | 201309 | 2013-06-11 | 2013-09-20 |
| ES 5min | 19,999 | 201312 | 2013-09-10 | 2013-12-20 |
| ES 5min | 19,999 | 201403 | 2013-12-04 | 2014-03-21 |
| ES 5min | 19,999 | 201406 | 2014-03-10 | 2014-06-20 |
| ES 5min | 19,999 | 201409 | 2014-06-10 | 2014-09-19 |
| ES 5min | 19,999 | 201412 | 2014-09-09 | 2014-12-19 |
| ES 5min | 19,999 | 201503 | 2014-12-05 | 2015-03-20 |
| ES 5min | 19,999 | 201506 | 2015-03-10 | 2015-06-19 |
| ES 5min | 19,999 | 201509 | 2015-06-09 | 2015-09-18 |
| ES 5min | 19,999 | 201512 | 2015-09-08 | 2015-12-18 |
| ES 5min | 19,999 | 201603 | 2015-12-03 | 2016-03-18 |
| ES 5min | 19,999 | 201606 | 2016-03-07 | 2016-06-17 |
| ES 5min | 19,999 | 201609 | 2016-06-06 | 2016-09-16 |
| ES 5min | 19,999 | 201612 | 2016-09-05 | 2016-12-16 |
| GC 30min | 5,991 | 201102 | 2009-09-03 | 2011-02-24 |
| GC 30min | 6,188 | 201104 | 2009-10-13 | 2011-04-27 |
| GC 30min | 7,822 | 201106 | 2008-06-02 | 2011-06-28 |
| GC 30min | 6,314 | 201108 | 2009-11-18 | 2011-08-29 |
| GC 30min | 11,990 | 201112 | 2008-12-04 | 2011-12-28 |
| GC 30min | 7,571 | 201202 | 2010-08-19 | 2012-02-27 |
| GC 30min | 6,909 | 201204 | 2010-06-11 | 2012-04-26 |
| GC 30min | 7,518 | 201206 | 2009-06-04 | 2012-06-27 |
| GC 30min | 6,034 | 201208 | 2011-02-25 | 2012-08-29 |
| GC 30min | 12,299 | 201212 | 2009-12-02 | 2012-12-27 |
| GC 30min | 6,362 | 201302 | 2011-04-08 | 2013-02-26 |
| GC 30min | 6,000 | 201304 | 2011-06-17 | 2013-04-26 |
| GC 30min | 7,145 | 201306 | 2011-06-14 | 2013-06-26 |
| GC 30min | 6,406 | 201308 | 2012-01-27 | 2013-08-28 |
| GC 30min | 10,586 | 201312 | 2012-01-05 | 2013-12-27 |
| GC 30min | 6,982 | 201402 | 2012-08-10 | 2014-02-26 |
| GC 30min | 6,287 | 201404 | 2012-07-19 | 2014-04-28 |
| GC 30min | 6,672 | 201406 | 2011-06-15 | 2014-06-26 |
| GC 30min | 5,576 | 201408 | 2012-12-20 | 2014-08-27 |
| GC 30min | 9,916 | 201412 | 2011-12-29 | 2014-12-29 |
| GC 30min | 6,035 | 201502 | 2013-04-18 | 2015-02-25 |
| GC 30min | 5,856 | 201504 | 2013-12-04 | 2015-04-28 |
| GC 30min | 7,003 | 201506 | 2012-07-09 | 2015-06-26 |
| GC 30min | 5,923 | 201508 | 2014-03-10 | 2015-08-27 |
| GC 30min | 10,405 | 201512 | 2012-12-28 | 2015-12-29 |
| GC 30min | 6,320 | 201602 | 2014-05-09 | 2016-02-25 |
| GC 30min | 6,236 | 201604 | 2014-11-06 | 2016-04-27 |
| GC 30min | 7,600 | 201606 | 2013-06-27 | 2016-06-28 |
| GC 30min | 6,282 | 201608 | 2015-02-05 | 2016-08-29 |
| GC 30min | 11,093 | 201612 | 2013-12-01 | 2016-12-28 |
| HG 30min | 5,994 | 201103 | 2009-06-16 | 2011-03-29 |
| HG 30min | 5,092 | 201105 | 2010-01-29 | 2011-05-26 |
| HG 30min | 4,918 | 201107 | 2010-02-05 | 2011-07-27 |
| HG 30min | 4,966 | 201109 | 2010-01-21 | 2011-09-28 |
| HG 30min | 7,085 | 201112 | 2010-02-03 | 2011-12-28 |
| HG 30min | 6,460 | 201203 | 2010-07-19 | 2012-03-28 |
| HG 30min | 5,479 | 201205 | 2010-07-23 | 2012-05-29 |
| HG 30min | 5,539 | 201207 | 2010-10-04 | 2012-07-27 |
| HG 30min | 5,527 | 201209 | 2010-11-17 | 2012-09-26 |
| HG 30min | 7,136 | 201212 | 2011-01-13 | 2012-12-27 |
| HG 30min | 6,586 | 201303 | 2011-03-31 | 2013-03-26 |
| HG 30min | 5,274 | 201305 | 2011-10-03 | 2013-05-29 |
| HG 30min | 5,210 | 201307 | 2012-01-29 | 2013-07-29 |
| HG 30min | 5,736 | 201309 | 2012-05-14 | 2013-09-26 |
| HG 30min | 7,503 | 201312 | 2010-12-15 | 2013-12-27 |
| HG 30min | 6,549 | 201403 | 2012-09-18 | 2014-03-27 |
| HG 30min | 5,444 | 201405 | 2013-01-09 | 2014-05-28 |
| HG 30min | 5,413 | 201407 | 2013-04-15 | 2014-07-29 |
| HG 30min | 5,608 | 201409 | 2013-04-16 | 2014-09-26 |
| HG 30min | 7,285 | 201412 | 2012-07-19 | 2014-12-29 |
| HG 30min | 6,944 | 201503 | 2013-05-24 | 2015-03-27 |
| HG 30min | 6,056 | 201505 | 2014-02-24 | 2015-05-27 |
| HG 30min | 5,827 | 201507 | 2013-12-03 | 2015-07-29 |
| HG 30min | 6,091 | 201509 | 2013-04-17 | 2015-09-28 |
| HG 30min | 7,609 | 201512 | 2013-07-11 | 2015-12-29 |
| HG 30min | 7,196 | 201603 | 2014-09-15 | 2016-03-29 |
| HG 30min | 6,136 | 201605 | 2014-12-16 | 2016-05-26 |
| HG 30min | 6,141 | 201607 | 2014-12-24 | 2016-07-27 |
| HG 30min | 6,125 | 201609 | 2015-01-28 | 2016-09-28 |
| HG 30min | 8,042 | 201612 | 2015-01-09 | 2016-12-28 |
| SI 30min | 6,301 | 201103 | 2009-09-21 | 2011-03-29 |
| SI 30min | 5,485 | 201105 | 2009-12-21 | 2011-05-26 |
| SI 30min | 6,213 | 201107 | 2008-11-19 | 2011-07-27 |
| SI 30min | 5,524 | 201109 | 2009-12-16 | 2011-09-28 |
| SI 30min | 10,302 | 201112 | 2008-11-11 | 2011-12-28 |
| SI 30min | 6,152 | 201203 | 2010-07-14 | 2012-03-28 |
| SI 30min | 4,747 | 201205 | 2010-07-14 | 2012-05-29 |
| SI 30min | 5,133 | 201207 | 2009-09-30 | 2012-07-26 |
| SI 30min | 4,587 | 201209 | 2011-04-12 | 2012-09-26 |
| SI 30min | 9,324 | 201212 | 2008-11-20 | 2012-12-27 |
| SI 30min | 5,485 | 201303 | 2011-09-26 | 2013-03-26 |
| SI 30min | 4,626 | 201305 | 2011-11-17 | 2013-05-29 |
| SI 30min | 4,975 | 201307 | 2010-07-22 | 2013-07-29 |
| SI 30min | 4,638 | 201309 | 2012-04-17 | 2013-09-25 |
| SI 30min | 8,515 | 201312 | 2010-03-03 | 2013-12-27 |
| SI 30min | 5,467 | 201403 | 2012-11-30 | 2014-03-26 |
| SI 30min | 4,480 | 201405 | 2012-07-23 | 2014-05-27 |
| SI 30min | 4,749 | 201407 | 2011-07-07 | 2014-07-29 |
| SI 30min | 4,191 | 201409 | 2013-01-30 | 2014-09-25 |
| SI 30min | 7,950 | 201412 | 2011-12-08 | 2014-12-29 |
| SI 30min | 5,421 | 201503 | 2013-12-19 | 2015-03-27 |
| SI 30min | 4,486 | 201505 | 2014-02-14 | 2015-05-27 |
| SI 30min | 4,848 | 201507 | 2012-09-25 | 2015-07-29 |
| SI 30min | 4,516 | 201509 | 2014-03-26 | 2015-09-28 |
| SI 30min | 7,975 | 201512 | 2012-12-03 | 2015-12-29 |
| SI 30min | 5,842 | 201603 | 2014-10-13 | 2016-03-29 |
| SI 30min | 4,714 | 201605 | 2014-12-16 | 2016-05-26 |
| SI 30min | 5,032 | 201607 | 2013-10-08 | 2016-07-26 |
| SI 30min | 4,685 | 201609 | 2015-02-24 | 2016-09-28 |
| SI 30min | 8,517 | 201612 | 2014-01-21 | 2016-12-28 |
## Per-contract coverage

(Above.) A row at exactly 19,999-20,000 bars is at the download cap and is truncated at its
old end.

## What has already been tested on this data

Forty-three pre-registered strategy cells, zero passes. Momentum, mean reversion,
cross-session breakouts, entry-timing variants, ICT structures (fair value gaps, liquidity
sweeps, inversions), and quant filters. Raw entry-to-exit with no fees or slippage did not
change the answer.

The three most statistically reliable measurements are all **negative**: VWAP reversion
t -2.80, the inverted fair value gap t -2.86, and the Asia-to-London breakout t -2.09 gross.

Two process notes worth carrying over, both learned the hard way here:

1. **State a filter's expected take rate before you run it.** Four filters in this project
   turned out to be near-collinear with their own signal (take rates of 97%, 92%, 100%, 5%
   against predictions of roughly half). Each was caught only by that check. The common
   cause every time was a filter and a signal computed from overlapping windows of the same
   price series.
2. **The block bootstrap needs about 700 observations.** Measured on demeaned iid input with
   mean block 10: the studentised null t reaches its nominal 99th percentile of 2.326 only
   near n = 700, and is badly under-dispersed below it (1.62 at n = 63). A bootstrap p from
   a small sample is anti-conservative and should not be read as a probability.

2017-2023 was deliberately left undownloaded as an untouched confirmation set. If you plan
to test anything, keeping it untouched is worth more than the extra sample.
