# Evidence Status and Environment Audit

**Document version:** 1.0
**Date of audit:** 2026-07-31
**Auditor:** automated environment probe, results recorded verbatim below.

This document exists to fix the evidence boundary before any specification or code is
read. Nothing in this repository is a backtest result. No performance number anywhere in
this repository has been measured. Every quantitative claim is labeled.

---

## 1. Headline finding

**This environment cannot produce a credible backtest of an intraday MES or MNQ system.**

No backtest has been run. No equity curve, trade log, fill record, win rate, or
expectancy exists in this repository. The specification in `SPECIFICATION.md` is a
design document whose parameters are almost entirely `AWAITING VALIDATION`.

---

## 2. Tooling available

| Capability | Status | Notes |
|---|---|---|
| Python 3.11 | Available | pandas 3.0.5 / numpy 2.4.6 installable from PyPI |
| Node 22 | Available | Not required by the design |
| Git repository | Available | Empty at audit time except README |
| Live order submission | **Not available, and not wanted** | IBKR MCP exposes `create_order_instruction`, which only creates a reviewable instruction a human must submit manually in IBKR. It is never called by this project. |
| External data egress | **Blocked** | Proxy returns HTTP 403 on CONNECT to non-allowlisted hosts. Verified against Yahoo Finance via `yfinance`. |
| Web search | Available | Used for rule research |
| Direct web fetch | **Mostly blocked** | `cmegroup.com`, `topstep.com`, and `interactivebrokers.github.io` all returned HTTP 403 to direct fetch. Primary-source verification therefore relies on search result summaries, which is weaker evidence. See section 6. |

---

## 3. Market data available: IBKR MCP bridge only

Contracts resolve correctly:

| Instrument | Underlying contract id | Exchange |
|---|---|---|
| MES (Micro E-mini S&P 500) | 362673777 | CME |
| MNQ (Micro E-mini Nasdaq-100) | 362687422 | CME |

Dated contracts are listed from `202409` through `202709`.

### 3.1 The binding constraint

`get_price_history` accepts a `period` measured backward from *now*. There is **no
end-date or offset parameter**, and there is a hard **3500-bar cap** per call.
Consequently the retrievable window always terminates at the present moment and cannot
be shifted backward.

This was verified experimentally rather than assumed:

| Probe | Result | Interpretation |
|---|---|---|
| MES `202512` (expired 2025-12-19), ONE_WEEK bars, ONE_YEAR period | **Returns data**, 21 bars, volume up to 10.9M/week | Expired contracts are *not* purged |
| MES `202606` (expired 2026-06-18), ONE_DAY bars, THREE_MONTHS period | **Returns data**, 34 bars, volume ~1.4M/day | Expired contract readable when its life overlaps the window |
| MES `202606`, FIFTEEN_MINS bars, ONE_MONTH period | **Empty** | Window (Jul 1 to now) begins after the contract stopped trading |
| MES `202503` (expired 2025-03-21), ONE_DAY bars, ONE_YEAR period | **Empty** | Contract life falls entirely before the window start |

The mechanism is therefore: `window = [now - period, now]`, bounded by the 3500-bar cap.
Contract selection cannot move the window. Fine-resolution history is permanently
restricted to the recent past.

### 3.2 Measured resolution limits

| Step | Maximum period accepted | Approx bars | Approx trading days |
|---|---|---:|---:|
| 1 min | TWO_DAYS | 2,567 (observed) | ~2 |
| 5 min | ONE_WEEK | ~1,900 (computed) | ~5 |
| 15 min | ONE_MONTH | ~2,800 (computed) | ~22 |
| 30 min | ONE_MONTH | ~1,400 (computed) | ~22 |
| 1 hour | THREE_MONTHS | ~2,100 (computed) | ~65 |

Confirmed rejections, each returning
`"Combination of period and step will provide more then allowed 3500 data points"`:
1min/ONE_MONTH, 5min/TWO_WEEKS, 30min/THREE_MONTHS, 1hr/SIX_MONTHS.

Rows marked "computed" are derived from the stated 3500-bar cap and an assumed ~1380
traded minutes per near-24-hour session. Only the 1-min row was directly observed. The
daily-bar probe returned the full requested year (251 bars), confirming that when a
request is under the cap the entire period is returned rather than truncated.

### 3.3 Data content limitations

Verified by inspecting a returned 1-min payload (2,567 bars, MES `202609`):

- Fields present: `time, open, high, low, close, volume`. Nothing else.
- `source: "Last"`. **No bid, no ask, no spread, no depth of market, no tick data.**
- `delayed: 600`. **Quotes are 10 minutes delayed.**
- Zero-volume bars in the sample: 0 (data is dense within the window).

Three independent consequences, each disqualifying on its own for a micro-futures
intraday system:

1. **Cost modeling would be pure assumption.** Spread, queue position, fill probability,
   and adverse selection cannot be measured from last-trade OHLCV. For MES and MNQ,
   round-trip cost is the controlling viability test, so this is not a minor gap.
2. **No credible real-time paper engine.** A 10-minute delayed feed cannot drive a paper
   engine whose decisions are supposed to match live timing.
3. **Order-flow features are impossible.** Cumulative delta and bid/ask imbalance require
   fields this feed does not contain. Any such feature in the specification is therefore
   marked unavailable in this environment.

### 3.4 Sample size consequence

At the deepest usable intraday resolution (15-minute bars, ~22 trading days), a system
taking on the order of 2 trades per day yields roughly 40 to 50 trades in total, drawn
from a single contract, a single volatility regime, and no roll cycle, **before** any
train / validation / lockbox split.

The validation standard this project is held to requires a chronological three-way split,
walk-forward windows spanning materially different volatility regimes, block-bootstrap
confidence intervals, parameter-stability checks, and an explicit multiple-testing
correction. A ~45-trade single-regime sample fails every one of those requirements. It is
not a small sample, it is not a sample at all for this purpose.

---

## 4. What follows from this

Per the project's own evidence rules, no backtest will be run in this environment and
described as evidence. The specification is unaffected and is delivered at
implementation grade. Obtaining real data is the gating task, and the options are set out
in `DATA_SOURCING.md`.

The recommended path is the native IBKR TWS API, because it removes the exact constraint
that blocks the MCP bridge. See `DATA_SOURCING.md` section 2.

---

## 5. Claim labeling convention used throughout this repository

Every substantive claim carries one of these labels:

| Label | Meaning |
|---|---|
| `FIXED-MARKET` | Fixed by verified exchange or contract specification |
| `FIXED-FIRM` | Fixed by verified proprietary firm rule |
| `DESIGN` | Chosen as a design constraint, not derived from data |
| `EST-DEV` | Estimated from development data (none exists yet) |
| `AWAITING-VALIDATION` | Cannot be known until a backtest is run |
| `UNRESOLVED` | Requires an explicit decision from the account owner |

And every empirical claim carries an evidence level: `strong`, `moderate`, `weak`,
or `unsupported`, plus whether it is in-sample, validation, untouched test, or
prospective.

**At the time of writing, every performance-related parameter in the specification is
`AWAITING-VALIDATION` with evidence level `unsupported`.** This is the honest state of
the project, not a placeholder to be filled in optimistically later.

---

## 6. Source quality caveat

Direct fetch of primary sources is blocked by the environment proxy (HTTP 403 against
`cmegroup.com`, `topstep.com`, and `interactivebrokers.github.io`). Rule and specification
research therefore relies on search-engine summaries of those primary sources rather than
on the pages themselves.

This is a real degradation of evidence quality and is flagged wherever it applies. Before
any capital is committed, every `FIXED-MARKET` and `FIXED-FIRM` value in this repository
must be re-verified by a human loading the official page directly. The values are recorded
with their source URLs and access dates specifically so that this re-verification is
mechanical.
