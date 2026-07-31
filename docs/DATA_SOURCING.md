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
1-minute bars" and "two years of 1-minute bars, contract by contract."

### 2.2 Documented limits

| Limit | Value | Impact |
|---|---|---|
| Bars of 1 minute and larger | Restrictions **lifted** | 1-min history is obtainable |
| Bars of 30 seconds or less | Limited to roughly the last 6 months | Only matters if you want sub-minute |
| **Expired futures contracts** | Available up to roughly **2 years past expiration** | This is the key one: it lets you build a proper dated-contract series |
| Request pacing | Enforced ~10 seconds between historical requests, plus a rolling cap | A full pull takes hours, not minutes. Budget for it. |
| Symbol/barSize/duration combinations | Not all combinations are served | Expect to probe empirically |

The 2-year expired-futures window is what makes a defensible backtest possible: you can
retrieve each dated MES and MNQ contract over the period when it was actually the liquid
front month, which is exactly what the specification requires for executable price levels.

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

**Roughly 2 years of 1-minute MES and MNQ dated-contract data, with bid/ask, at zero
marginal cost.** That is enough to support the walk-forward and lockbox design in the
specification, though 2 years still spans a limited set of volatility regimes, and the
specification's regime-coverage requirement should be re-checked against what you actually
retrieve.

---

## 3. Free and low-cost alternatives

| Source | Coverage | Cost | Verdict |
|---|---|---|---|
| **IBKR TWS API** | ~2 yr expired futures, 1-min+, TRADES/BID/ASK | Free with subscription | **Best free option.** Start here. |
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
