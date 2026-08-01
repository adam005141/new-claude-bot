# MES / MNQ Intraday Trading System

Session-aware, evidence-first research project for Micro E-mini S&P 500 (MES) and Micro
E-mini Nasdaq-100 (MNQ) intraday futures.

> **Status: SPECIFICATION ONLY.**
> No strategy code has been written. No backtest has been run. No performance number in
> this repository has been measured. There is no live order path and none is planned.

---

## Read in this order

| Document | Purpose |
|---|---|
| [`docs/EVIDENCE_STATUS.md`](docs/EVIDENCE_STATUS.md) | **Start here.** Environment audit and why a credible backtest is not currently possible |
| [`docs/DATA_SOURCING.md`](docs/DATA_SOURCING.md) | How to obtain usable historical data, including free options |
| [`docs/SPECIFICATION.md`](docs/SPECIFICATION.md) | The 22-section implementation-grade specification |
| [`config/instruments.yaml`](config/instruments.yaml) | Contract specs, trading hours, roll policy |
| [`config/topstep_50k_combine.v1.yaml`](config/topstep_50k_combine.v1.yaml) | Versioned prop rule config with sources, dates, and unresolved semantics |
| [`docs/WINDOWS_SETUP.md`](docs/WINDOWS_SETUP.md) | **Windows walkthrough**: install to downloaded data, step by step |
| [`tools/`](tools/) | Data acquisition: IBKR downloader and ingest validator |

## Getting data

**On Windows, follow [`docs/WINDOWS_SETUP.md`](docs/WINDOWS_SETUP.md)** for the full
walkthrough from installing Python through to validated data. The condensed version:

```bash
pip install -r requirements.txt

python tools/ibkr_download.py --symbols MES --bar-size "1 hour" --years 2 --dry-run   # plan
python tools/ibkr_download.py --symbols MES --bar-size "1 hour" --years 2             # smoke test
python tools/ibkr_download.py --symbols MES MNQ --bar-size "1 min" --years 2          # ~4.5 hours
python tools/validate_data.py data/
```

The long pull is resumable: every request is cached, and a rerun skips what it has.

---

## The headline finding

The IBKR MCP bridge available in this environment returns bars only within
`[now - period, now]`, with no end-date parameter and a 3500-bar cap. Fine-resolution
history is therefore permanently limited to the recent past: roughly **2 days at 1-minute
resolution, 1 week at 5-minute, 1 month at 15-minute**. The feed also carries last-trade
OHLCV only, with **no bid/ask and no depth**, and is **10 minutes delayed**.

That supports roughly 45 trades from a single contract in a single volatility regime,
against a specification that requires a minimum of 200 trades per leg. No backtest was run,
because running one and reporting the output would have produced a number that looks like
evidence and is not.

**This is a tooling limitation, not an IBKR limitation.** The native TWS API exposes
`endDateTime` and serves expired futures contracts up to about two years past expiration,
which is sufficient. See [`docs/DATA_SOURCING.md`](docs/DATA_SOURCING.md).

---

## Design commitments

- **Micros are the execution instruments.** ES and NQ are reference-only and structurally
  cannot generate orders.
- **Cost is the controlling test.** A micro pays a parent-sized spread for one tenth the
  dollar move. The expected-move floor is a hard gate at signal time, not a diagnostic.
- **Risk derives from the $2,000 loss buffer**, never the $50,000 headline balance.
  Topstep enforces no daily loss limit, so the buffer is the only firm circuit breaker
  and the engine adds a self-imposed daily stop by default.
- **One-contract exits are the primary path.** Scale-outs are structurally forbidden at
  sizes that cannot execute them.
- **Adverse assumptions on every ambiguity.** Same-bar stop-and-target resolves to the
  stop; limit orders fill only on trade-through; stops fill at the worse of stop and next
  open.
- **Everything fails closed.** There is no degraded-but-trading mode.
- **"Neither instrument has an edge" is a success condition** of the validation design.

---

## Open decisions

Nine decisions await owner approval, listed in
[`docs/SPECIFICATION.md`](docs/SPECIFICATION.md) section 22. The gating one is the data
source; nothing else can proceed without it.

Six Topstep rule semantics remain unresolved and each defaults to the most conservative
interpretation. They are enumerated in
[`config/topstep_50k_combine.v1.yaml`](config/topstep_50k_combine.v1.yaml) under
`unresolved_semantics` and must be verified against Topstep's own documentation before any
capital is committed.

---

## Verification caveat

Direct fetch of `cmegroup.com`, `topstep.com`, and `interactivebrokers.github.io` returned
HTTP 403 from this environment. Contract specifications and firm rules were gathered from
search-engine summaries of those primary sources rather than the pages themselves. Every
such value is recorded with its source URL and access date so that human re-verification is
mechanical. Evidence level is `moderate` throughout, and this is flagged wherever it
applies.
