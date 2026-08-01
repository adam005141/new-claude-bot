# Historical Data Sourcing for MES / MNQ

**Date:** 2026-07-31
**Purpose:** answer the question "where do I get better historical data, can I go through
IBKR, and what is free?"

**Source quality caveat:** direct fetch of `interactivebrokers.github.io` returned HTTP
403 in this environment. The IBKR limits below come from search-engine summaries of the
official TWS API documentation, not from the pages themselves. Verify directly before
building against them. Evidence level: `moderate`.

---

## 1. Short answer

**Yes, IBKR works, and it is your best free option.** The problem is not IBKR. The problem
is the *MCP bridge* used in this session, which is a thin wrapper that omits the one
parameter that matters. The native TWS API does not have that limitation.

---

## 2. IBKR native TWS API (recommended, effectively free)

### 2.1 Why it solves the problem

The MCP bridge exposes only `period` (measured backward from now), so the retrievable
window always ends at the present moment. The native API's `reqHistoricalData` exposes
**`endDateTime`**, which lets you anchor the window anywhere in the past and page backward
through history in chunks. That single parameter is the difference between "last 2 days of
1-minute bars" and "months of 1-minute bars, contract by contract." How many months is
answered by measurement in 2.6, not by the documentation.

### 2.2 Documented limits

| Limit | Value | Impact |
|---|---|---|
| Bars of 1 minute and larger | Restrictions **lifted** | 1-min history is obtainable |
| Bars of 30 seconds or less | Limited to roughly the last 6 months | Only matters if you want sub-minute |
| **Expired futures contracts** | Documented as ~2 years past expiration. **Measured: ~8 months.** See 2.6 | Still enough for a dated-contract series, but shorter than the docs imply |
| Request pacing | Enforced ~10 seconds between historical requests, plus a rolling cap | A full pull takes hours, not minutes. Budget for it. |
| Symbol/barSize/duration combinations | Not all combinations are served | Expect to probe empirically |

The expired-futures window is what makes a defensible backtest possible: you can retrieve
each dated MES and MNQ contract over the period when it was actually the liquid front
month, which is exactly what the specification requires for executable price levels. Note
that the usable window is ~8 months in practice rather than the documented 2 years; see
2.6 for the measurement.

### 2.3 What it costs

Free with an IBKR account, given a CME real-time market data subscription (low monthly
cost, and you may already hold it). There is no per-request charge.

### 2.4 What it does not give you

**No historical bid/ask, and no depth of market.** IBKR can serve `BID`, `ASK`, and
`MIDPOINT` bar types in addition to `TRADES`, which is better than last-trade only and
lets you estimate spread far more honestly than this session's feed allows. It still does
not give you queue position or book depth. Plan cost modeling accordingly.

### 2.5 Practical setup

- Run IB Gateway or TWS on your own machine. **It cannot run in this sandbox** (no GUI, no
  credentials, and outbound network is blocked).
- Use `ib_async` (the maintained successor to `ib_insync`) from Python.
- Pull per dated contract, per bar size, paging backward with `endDateTime`.
- Persist to Parquet immediately. Re-pulling is slow because of pacing, so treat the local
  store as the system of record.
- Pull `TRADES` and `BID`/`ASK` separately so spread can be estimated.

**Roughly 11.5 months of 1-minute MES and MNQ dated-contract data at zero marginal cost.**
See 2.6 for why this is less than the documentation promises. It supports a chronological
train/validation/lockbox split, but not the specification's full regime-coverage
requirement.

### 2.6 MEASURED retention, which is shorter than documented

Evidence level: `strong` (direct measurement on the owner's account, 2026-08-01).

IBKR documentation states expired futures are available up to two years past expiration.
**That is not what a real account returns.** A live `reqContractDetails` call with
`includeExpired=True` against MES on 2026-08-01 returned:

```
MES: found 8 dated contracts (202512 to 202709)
```

Only 8 contracts, the oldest expiring 2025-12-19, roughly 7.5 months before the query.
Five of the eight are current or future contracts carrying no usable history. Contract
DISCOVERY cuts off well before the documented data-retention window.

Actual continuous coverage obtained:

| Contract | Covers | Hourly bars |
|---|---|---:|
| MES 202512 | 2025-08-20 to 2025-12-18 | 1,925 |
| MES 202603 | 2025-11-19 to 2026-03-19 | 1,894 |
| MES 202606 | 2026-02-18 to 2026-06-17 | 1,925 |
| MES 202609 | 2026-06-02 to 2026-07-31 | 981 |

Stitched: **2025-08-20 to 2026-07-31, about 11.5 months.** Consecutive contracts overlap by
roughly a month, which is the roll period and is exactly what the roll logic needs.

**Consequence for the research plan.** About 240 trading days. Split 50/30/20 gives roughly
120 development days. At ~2 trades per day that is ~240 development trades per instrument
across ALL legs, so a three-leg design lands near 80 trades per leg and fails the
200-trade gate in SPECIFICATION.md section 18.5. This is a direct argument for building one
or two legs rather than three.

Additionally, Aug 2025 to Jul 2026 is likely a SINGLE volatility regime. The
specification's walk-forward requirement for materially different regimes cannot be
satisfied by this dataset, and any conclusion drawn from it must carry that limitation
permanently rather than treating it as a detail to revisit.

To exceed this ceiling, FirstRate Data carries ~7 years of MNQ 1-minute history for a
one-off per-symbol fee. That is the cheapest route to genuine regime diversity.

---

## 3. Free and low-cost alternatives

| Source | Coverage | Cost | Verdict |
|---|---|---|---|
| **IBKR TWS API** | **~11.5 months measured**, 1-min+, TRADES/BID/ASK | Free with subscription | **Best free option.** Start here. Shorter than its docs claim; see 2.6 |
| **Databento** | CME MBO/MBP-10, full order book, tick, since 2010 | Paid, with free trial credit on signup | **Best paid option by a wide margin.** Real book data means real queue and slippage modeling. Use the trial to sample a few months and see whether the edge survives honest costs. |
| **FirstRate Data** | ~7 yr MNQ, ~19 yr NQ, 1-min bars, plus tick | Paid per-symbol, one-off, free samples available | Good value for clean OHLCV. No book depth. Free samples are enough to build and test the loader. |
| **CME DataMine** | Official exchange source, full historical | Paid, some free samples | Authoritative, but expensive and awkward for research-scale use |
| **Barchart** | ~10 yr intraday to 1-min | Premier membership | Workable, export-oriented rather than API-oriented |
| **NinjaTrader / Kinetick** | Futures historical via free sim account | Free tier for EOD, intraday with connection | Convenient if you already run NinjaTrader; awkward to get into Python |
| **Norgate Data** | Continuous + dated futures, daily and intraday | Paid subscription | Strong roll handling, weaker for sub-daily research |

Sources: [FirstRate Data MNQ](https://firstratedata.com/i/futures/MNQ),
[FirstRate Data futures index](https://firstratedata.com/it/futures),
[Barchart historical data help](https://help.barchart.com/support/solutions/articles/242748-how-can-i-download-historical-data-),
[TWS API historical limitations](https://interactivebrokers.github.io/tws-api/historical_limitations.html),
[IBKR Quant: historical options and futures data](https://www.interactivebrokers.com/campus/ibkr-quant-news/historical-options-futures-data-using-tws-api/).
Accessed 2026-07-31.

---

## 3a. Step-by-step: pulling the data with IB Gateway running

Tooling for this lives in `tools/`. You already have IB Gateway running, so start here.

### Step 1: turn on the API in IB Gateway

In Gateway: **Configure → Settings → API → Settings**.

- Tick **Enable ActiveX and Socket Clients**
- Tick **Read-Only API**. This project only reads data, and read-only makes it
  impossible for a bug to place an order.
- Note the **Socket port**. Defaults: `4002` Gateway paper, `4001` Gateway live,
  `7497` TWS paper, `7496` TWS live.
- Confirm `127.0.0.1` is under **Trusted IPs**.
- Leave Gateway running and logged in. It cannot serve data while logged out, and it
  auto-logs-out daily unless you set **Configure → Lock and Exit → Never**. A multi-hour
  pull will die at the daily restart otherwise.

### Step 2: market data subscription

Historical CME futures data requires a **CME real-time** subscription on the account
(Account Management → Market Data Subscriptions). Without it, requests return empty
rather than erroring, which looks exactly like "no data exists." If you get empty
results everywhere, check this first.

### Step 3: install dependencies

```bash
pip install ib_async pandas pyarrow
```

### Step 4: smoke test before committing hours

```bash
# Plan only, no connection. Confirms the request math.
python tools/ibkr_download.py --symbols MES --bar-size "1 min" --years 0.25 --dry-run

# Smallest real pull: one instrument, hourly bars, ~5 minutes.
python tools/ibkr_download.py --symbols MES --bar-size "1 hour" --years 2 --port 4002
python tools/validate_data.py data/
```

If the hourly pull produces files that pass validation, the connection, subscription,
and contract resolution all work. Only then start the long one.

### Step 5: the real pull

```bash
python tools/ibkr_download.py --symbols MES MNQ --bar-size "1 min" --years 2 --port 4002
```

**This takes about 2 to 2.5 hours** (roughly 700 requests at 11 seconds each). That pacing
is not padding: IBKR permits 60 historical requests per 10 minutes and rejects identical
requests inside 15 seconds, and tripping the limit gets the connection throttled.

**It is safe to interrupt.** Every request is cached to its own file and a rerun skips
what it already has. If it dies overnight, rerun the same command.

To add quote data for honest spread modeling, at 3x the runtime:

```bash
python tools/ibkr_download.py --symbols MES MNQ --what TRADES BID ASK --years 2
```

### Step 6: validate before trusting any of it

```bash
python tools/validate_data.py data/ --json data/validation_report.json
```

`PASS` means usable. `QUARANTINE` means do not use the file until you understand why.

The gate to watch is **`front_month_attribution`**. It flags contracts whose data covers
periods before they were the liquid front month. This is a real failure that the
environment audit hit: the Sep-2026 MES contract returned a full year of daily bars, but
volume was zero or single-digit for the first ten months. Research over that window would
be studying a contract nobody traded. The warning tells you where to trim.

### What you end up with

```
data/
├── MES/
│   ├── MES_202409_1min_TRADES.parquet
│   ├── MES_202409_1min_TRADES.meta.json    # provenance: source, retrieval time, row count
│   └── ...
├── MNQ/
└── _cache/                                  # per-request chunks; safe to delete after merge
```

Roughly 8 quarterly contracts per symbol, each covering its ~100-day front-month window,
unadjusted, at 1-minute resolution. That is what the specification's backtest needs.

### If something goes wrong

| Symptom | Cause |
|---|---|
| `ConnectionRefusedError` | Gateway not running, wrong port, or API not enabled |
| Connects, every file empty | Missing CME market data subscription (step 2) |
| `pacing violation` in the log | Raise `--pacing` above 11 |
| Empty only for the oldest contracts | Expected. IBKR serves expired futures ~2 years back; older is gone |
| Dies partway through | Rerun the same command; it resumes from cache |
| `clientId` already in use | Another script or TWS is connected; change `--client-id` |

> **Untested-path warning.** The IB-connected code path has not been run against a live
> gateway, because this sandbox has neither Gateway nor outbound network. The planning,
> merging, and validation logic is covered by 22 offline tests that pass. The
> `reqHistoricalData` interaction is written to the documented API and reviewed, but not
> executed. Treat your first run as the real test of it, which is why step 4 exists.

---

## 4. Recommended plan

1. **Start with IBKR TWS API.** It is free, you already have the account, and the 2-year
   expired-futures window covers the dated contracts the specification requires.
2. **Pull `TRADES` plus `BID`/`ASK`** at 1-minute resolution for every MES and MNQ dated
   contract over the last 2 years. Budget several hours for pacing.
3. **Validate on arrival** against the schema in `SPECIFICATION.md` section 4: timestamp
   monotonicity, session coverage, duplicate and gap detection, volume sanity, and a
   cross-check that each contract's volume profile shows it actually was the front month
   during the window you attribute to it.
4. **If, and only if, a candidate survives** development and validation on that data,
   spend the Databento trial to re-run the untouched test with real book data. If the edge
   evaporates under measured spread and queue behavior, it was never there. That is the
   cheapest possible way to find out, and it is far cheaper than finding out with a funded
   account.

---

## 5. What this does not fix

Better data removes the sample-size and cost-modeling blockers. It does not remove:

- **The 10-minute delayed feed in this environment**, which still prevents a credible
  real-time paper engine here. Paper trading needs to run where a real-time feed exists.
- **The multiple-testing problem.** More data means more capacity to search, and more
  search means more overfitting risk. The research registry and experiment ledger in
  `SPECIFICATION.md` section 18 become more important with more data, not less.
- **The fact that 2 years is still a narrow regime sample.** Two years of equity index
  futures may contain only one genuine volatility regime shift. Conclusions should be
  stated with that limit attached.
