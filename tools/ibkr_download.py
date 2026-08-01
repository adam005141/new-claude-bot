#!/usr/bin/env python3
"""
Download MES / MNQ dated-contract historical bars from IB Gateway or TWS.

Why this exists
---------------
The IBKR MCP bridge only accepts a `period` measured backward from now, so it can
never reach further back than a few days at fine resolution. The native TWS API
exposes `endDateTime`, which lets us anchor the window anywhere in the past and page
backward. It also serves expired futures contracts up to roughly two years past
expiration, which is what makes a proper dated-contract series possible.

Design notes
------------
* Pure planning logic (contract windows, request chunking) is separated from all IB
  calls so it can be unit tested without a gateway. See tests/test_download_plan.py.
* Every request is cached to its own Parquet file, so an interrupted run resumes
  without re-fetching. A full 2-year 1-minute pull is measured in hours because of
  IBKR's pacing limits, so resumability is not optional.
* Only the front-month window of each dated contract is fetched. Pulling a contract
  outside its liquid window returns thin or empty data that must not enter research.

UNTESTED PATH WARNING
---------------------
The IB-connected code path in this file has NOT been executed against a live gateway.
This sandbox has no IB Gateway and no outbound network. The planning and merging logic
is unit tested; the `reqHistoricalData` interaction is written to the documented API
and reviewed, but not run. Treat the first live run as a test.

Usage
-----
    # Smoke test: one contract, one day, verify the connection works at all
    python tools/ibkr_download.py --symbols MES --bar-size "1 min" --years 0.25 --dry-run
    python tools/ibkr_download.py --symbols MES --bar-size "1 min" --years 0.25

    # Full pull (hours; safe to interrupt and rerun)
    python tools/ibkr_download.py --symbols MES MNQ --bar-size "1 min" --years 2

    # Add quote data for honest spread modeling (triples runtime)
    python tools/ibkr_download.py --symbols MES MNQ --what TRADES BID ASK --years 2
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("ibkr_download")

# ---------------------------------------------------------------------------
# IBKR request limits.
#
# Duration caps per bar size are conservative: IBKR's published table permits
# larger windows for some sizes, but oversized requests fail intermittently
# rather than cleanly, which is worse during a multi-hour run.
# ---------------------------------------------------------------------------
# IBKR's durationStr is SESSION-RELATIVE, not wall-clock relative. If endDateTime falls
# partway through a live trading session, "1 D" returns only the elapsed part of that
# session, not a full day.
#
# This is not hypothetical. A run on 2026-08-01 stepping endDateTime by exactly one day at
# 00:00 UTC produced 60-bar, 120-bar, and 301-bar responses on weekdays (00:00 UTC is
# 19:00/20:00 ET, one to five hours into the session that just opened) while weekend
# anchors, which have no live session to truncate against, returned the full 1380. Overall
# completeness was about 26%.
#
# Fix: request a LONGER duration than the step, so every session is fully contained in at
# least one request regardless of where the anchor lands. Overlap is removed by
# deduplicating on timestamp during the merge. Request count is unchanged for 1-minute
# data; only the bytes per response go up.
DURATION_FOR_BAR_SIZE: dict[str, tuple[str, int, int]] = {
    # bar size -> (IBKR durationStr, days the duration covers, days to step the cursor)
    "1 min":      ("2 D", 2, 1),
    "5 mins":     ("1 W", 7, 5),
    "15 mins":    ("1 W", 7, 5),
    "30 mins":    ("1 M", 30, 25),
    "1 hour":     ("1 M", 30, 25),
    "1 day":      ("1 Y", 365, 300),
}

# IBKR allows at most 60 historical requests per 10 minutes, and rejects identical
# requests repeated within 15 seconds. 11s keeps us just inside both.
DEFAULT_PACING_SECONDS = 11.0

# A quarterly contract is the liquid front month for roughly one quarter. The extra
# days cover the roll period, when both contracts carry real volume.
DEFAULT_ACTIVE_WINDOW_DAYS = 100

VALID_WHAT_TO_SHOW = {"TRADES", "BID", "ASK", "MIDPOINT", "BID_ASK"}


# ---------------------------------------------------------------------------
# Pure planning logic. No IB dependency, fully unit tested.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContractSpec:
    """A dated futures contract and the window over which it was the front month."""
    symbol: str
    contract_month: str          # YYYYMM
    last_trade_date: str         # YYYYMMDD
    exchange: str = "CME"

    @property
    def expiry(self) -> datetime:
        return datetime.strptime(self.last_trade_date, "%Y%m%d").replace(tzinfo=timezone.utc)

    def active_window(self, days: int = DEFAULT_ACTIVE_WINDOW_DAYS) -> tuple[datetime, datetime]:
        """The window to fetch: roughly the quarter during which this was front month."""
        end = self.expiry
        return end - timedelta(days=days), end


@dataclass(frozen=True)
class Request:
    """One `reqHistoricalData` call."""
    symbol: str
    contract_month: str
    last_trade_date: str
    exchange: str
    end_dt: datetime
    duration: str
    bar_size: str
    what_to_show: str

    def cache_name(self) -> str:
        safe_bar = self.bar_size.replace(" ", "")
        return (
            f"{self.symbol}_{self.contract_month}_{safe_bar}_{self.what_to_show}"
            f"_{self.end_dt.strftime('%Y%m%dT%H%M%S')}.parquet"
        )


def plan_requests(
    contracts: list[ContractSpec],
    bar_size: str,
    what_to_show: list[str],
    start: datetime,
    end: datetime,
    active_window_days: int = DEFAULT_ACTIVE_WINDOW_DAYS,
) -> list[Request]:
    """
    Build the full request list, paging backward through each contract's active window.

    Requests are emitted newest-first within a contract, which is the direction
    `endDateTime` naturally walks.
    """
    if bar_size not in DURATION_FOR_BAR_SIZE:
        raise ValueError(f"unsupported bar size {bar_size!r}; expected one of "
                         f"{sorted(DURATION_FOR_BAR_SIZE)}")
    for w in what_to_show:
        if w not in VALID_WHAT_TO_SHOW:
            raise ValueError(f"unsupported whatToShow {w!r}; expected one of "
                             f"{sorted(VALID_WHAT_TO_SHOW)}")

    duration, _duration_days, step_days = DURATION_FOR_BAR_SIZE[bar_size]
    requests: list[Request] = []

    for c in sorted(contracts, key=lambda x: x.contract_month):
        win_start, win_end = c.active_window(active_window_days)
        # Clip the contract's own window to the caller's overall date range.
        win_start = max(win_start, start)
        win_end = min(win_end, end)
        if win_start >= win_end:
            continue

        for what in what_to_show:
            cursor = win_end
            while cursor > win_start:
                requests.append(Request(
                    symbol=c.symbol,
                    contract_month=c.contract_month,
                    last_trade_date=c.last_trade_date,
                    exchange=c.exchange,
                    end_dt=cursor,
                    duration=duration,
                    bar_size=bar_size,
                    what_to_show=what,
                ))
                cursor -= timedelta(days=step_days)

    return requests


def estimate_runtime_seconds(n_requests: int, pacing: float = DEFAULT_PACING_SECONDS) -> float:
    return n_requests * pacing


def format_duration(seconds: float) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m" if h else (f"{m}m {s}s" if m else f"{s}s")


# ---------------------------------------------------------------------------
# IB-connected code. Imports ib_async lazily so planning/tests work without it.
# ---------------------------------------------------------------------------

def connect(host: str, port: int, client_id: int):
    from ib_async import IB
    ib = IB()
    log.info("connecting to %s:%s (clientId=%s)", host, port, client_id)
    ib.connect(host, port, clientId=client_id, timeout=20)
    log.info("connected: server version %s", ib.client.serverVersion())
    return ib


def discover_contracts(ib, symbol: str, exchange: str = "CME") -> list[ContractSpec]:
    """Resolve every dated contract for a symbol, including expired ones."""
    from ib_async import Future

    template = Future(symbol=symbol, exchange=exchange, includeExpired=True)
    details = ib.reqContractDetails(template)
    if not details:
        log.warning("no contracts returned for %s on %s", symbol, exchange)
        return []

    specs: list[ContractSpec] = []
    for d in details:
        c = d.contract
        ltd = (c.lastTradeDateOrContractMonth or "").strip()
        if len(ltd) != 8:          # want YYYYMMDD, skip bare YYYYMM entries
            continue
        specs.append(ContractSpec(
            symbol=symbol,
            contract_month=ltd[:6],
            last_trade_date=ltd,
            exchange=exchange,
        ))

    # Deduplicate: reqContractDetails can return several rows per expiry.
    unique = {s.contract_month: s for s in specs}
    out = sorted(unique.values(), key=lambda s: s.contract_month)
    log.info("%s: found %d dated contracts (%s to %s)",
             symbol, len(out),
             out[0].contract_month if out else "-",
             out[-1].contract_month if out else "-")
    return out


def fetch_one(ib, req: Request, timeout: int = 120):
    """Execute a single historical request. Returns a DataFrame, possibly empty."""
    import pandas as pd
    from ib_async import Future, util

    contract = Future(
        symbol=req.symbol,
        lastTradeDateOrContractMonth=req.last_trade_date,
        exchange=req.exchange,
        includeExpired=True,
    )
    qualified = ib.qualifyContracts(contract)
    if not qualified:
        log.warning("could not qualify %s %s", req.symbol, req.contract_month)
        return pd.DataFrame()

    bars = ib.reqHistoricalData(
        qualified[0],
        endDateTime=req.end_dt,
        durationStr=req.duration,
        barSizeSetting=req.bar_size,
        whatToShow=req.what_to_show,
        useRTH=False,            # keep the full session; filter later, never at source
        formatDate=2,            # epoch seconds, UTC
        timeout=timeout,
    )
    if not bars:
        return pd.DataFrame()

    df = util.df(bars)
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.rename(columns={"date": "timestamp_utc"})
    df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    df["symbol"] = req.symbol
    df["contract_month"] = req.contract_month
    df["contract_id"] = f"{req.symbol}{req.contract_month}"
    df["bar_size"] = req.bar_size
    df["what_to_show"] = req.what_to_show

    # BID / ASK / MIDPOINT bars carry volume -1. Null it rather than let a sentinel
    # propagate into volume-weighted features such as VWAP.
    if req.what_to_show != "TRADES" and "volume" in df.columns:
        df["volume"] = None

    return df


def run(args) -> int:
    import pandas as pd

    out_dir = Path(args.out)
    cache_dir = out_dir / "_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(args.years * 365))

    ib = None
    if not args.dry_run:
        ib = connect(args.host, args.port, args.client_id)

    try:
        # ---- Plan -------------------------------------------------------
        all_contracts: list[ContractSpec] = []
        for symbol in args.symbols:
            if args.dry_run:
                # Synthesize the standard quarterly cycle so --dry-run works offline.
                all_contracts += _synthetic_contracts(symbol, start, end)
            else:
                all_contracts += discover_contracts(ib, symbol, args.exchange)

        requests = plan_requests(
            all_contracts, args.bar_size, args.what, start, end, args.active_window_days
        )
        todo = [r for r in requests if not (cache_dir / r.cache_name()).exists()]

        log.info("planned %d requests (%d already cached, %d to fetch)",
                 len(requests), len(requests) - len(todo), len(todo))
        log.info("estimated runtime: %s at %.1fs pacing",
                 format_duration(estimate_runtime_seconds(len(todo), args.pacing)), args.pacing)

        if args.dry_run:
            for r in requests[:10]:
                log.info("  %s %s %s end=%s dur=%s",
                         r.symbol, r.contract_month, r.what_to_show,
                         r.end_dt.date(), r.duration)
            if len(requests) > 10:
                log.info("  ... and %d more", len(requests) - 10)
            return 0

        # ---- Fetch ------------------------------------------------------
        failures = 0
        for i, req in enumerate(todo, 1):
            path = cache_dir / req.cache_name()
            try:
                df = fetch_one(ib, req, timeout=args.timeout)
                # Empty is a legitimate result (window predates the contract's life).
                # Cache a marker so a resume does not retry it forever.
                df.to_parquet(path, index=False)
                log.info("[%d/%d] %s %s %s end=%s -> %d bars",
                         i, len(todo), req.symbol, req.contract_month,
                         req.what_to_show, req.end_dt.date(), len(df))
            except Exception as exc:                     # noqa: BLE001
                failures += 1
                log.error("[%d/%d] FAILED %s %s end=%s: %s",
                          i, len(todo), req.symbol, req.contract_month, req.end_dt.date(), exc)
                if failures > args.max_failures:
                    log.error("too many failures (%d), aborting; rerun to resume", failures)
                    return 2
            time.sleep(args.pacing)

        # ---- Merge ------------------------------------------------------
        merge_cache(cache_dir, out_dir, args.bar_size)
        return 0

    finally:
        if ib is not None:
            ib.disconnect()
            log.info("disconnected")


def merge_cache(cache_dir: Path, out_dir: Path, bar_size: str) -> list[Path]:
    """Merge cached chunks into one Parquet per symbol/contract/whatToShow."""
    import pandas as pd

    safe_bar = bar_size.replace(" ", "")
    groups: dict[tuple[str, str, str], list[Path]] = {}
    for p in sorted(cache_dir.glob(f"*_{safe_bar}_*.parquet")):
        parts = p.stem.split("_")
        if len(parts) < 4:
            continue
        symbol, contract_month, _bar, what = parts[0], parts[1], parts[2], parts[3]
        groups.setdefault((symbol, contract_month, what), []).append(p)

    written: list[Path] = []
    for (symbol, contract_month, what), paths in sorted(groups.items()):
        frames = []
        for p in paths:
            try:
                df = pd.read_parquet(p)
                if not df.empty:
                    frames.append(df)
            except Exception as exc:                     # noqa: BLE001
                log.warning("unreadable cache file %s: %s", p.name, exc)
        if not frames:
            continue

        merged = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(subset=["timestamp_utc"], keep="last")
            .sort_values("timestamp_utc")
            .reset_index(drop=True)
        )
        dest_dir = out_dir / symbol
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{symbol}_{contract_month}_{safe_bar}_{what}.parquet"
        merged.to_parquet(dest, index=False)
        written.append(dest)

        meta = {
            "symbol": symbol,
            "contract_month": contract_month,
            "bar_size": bar_size,
            "what_to_show": what,
            "rows": int(len(merged)),
            "first_bar": str(merged["timestamp_utc"].iloc[0]),
            "last_bar": str(merged["timestamp_utc"].iloc[-1]),
            "source": "IBKR TWS API reqHistoricalData",
            "adjustment": "unadjusted",
            "retrieved_utc": datetime.now(timezone.utc).isoformat(),
            "chunks_merged": len(frames),
        }
        dest.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
        log.info("merged %-28s %6d bars  %s -> %s",
                 dest.name, len(merged), meta["first_bar"][:10], meta["last_bar"][:10])

    return written


def _synthetic_contracts(symbol: str, start: datetime, end: datetime) -> list[ContractSpec]:
    """Standard Mar/Jun/Sep/Dec cycle, third Friday. Used only by --dry-run."""
    out = []
    for year in range(start.year, end.year + 1):
        for month in (3, 6, 9, 12):
            d = datetime(year, month, 1, tzinfo=timezone.utc)
            fridays = [x for x in range(1, 29)
                       if datetime(year, month, x, tzinfo=timezone.utc).weekday() == 4]
            third_friday = d.replace(day=fridays[2])
            if start - timedelta(days=DEFAULT_ACTIVE_WINDOW_DAYS) <= third_friday <= end:
                out.append(ContractSpec(
                    symbol=symbol,
                    contract_month=f"{year}{month:02d}",
                    last_trade_date=third_friday.strftime("%Y%m%d"),
                ))
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Download MES/MNQ dated-contract history from IB Gateway or TWS.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--symbols", nargs="+", default=["MES", "MNQ"])
    p.add_argument("--exchange", default="CME")
    p.add_argument("--bar-size", default="1 min", choices=sorted(DURATION_FOR_BAR_SIZE))
    p.add_argument("--what", nargs="+", default=["TRADES"], choices=sorted(VALID_WHAT_TO_SHOW),
                   help="TRADES for OHLCV. Add BID and ASK for spread modeling (3x runtime).")
    p.add_argument("--years", type=float, default=2.0,
                   help="How far back to fetch. IBKR serves expired futures ~2 years.")
    p.add_argument("--out", default="data")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4002,
                   help="4002 Gateway paper, 4001 Gateway live, 7497 TWS paper, 7496 TWS live")
    p.add_argument("--client-id", type=int, default=17)
    p.add_argument("--pacing", type=float, default=DEFAULT_PACING_SECONDS,
                   help="Seconds between requests. Below ~11 risks IBKR pacing violations.")
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--max-failures", type=int, default=20)
    p.add_argument("--active-window-days", type=int, default=DEFAULT_ACTIVE_WINDOW_DAYS)
    p.add_argument("--dry-run", action="store_true",
                   help="Plan and print requests without connecting to IB.")
    p.add_argument("--merge-only", action="store_true",
                   help="Skip fetching; just merge whatever is already cached.")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    if args.merge_only:
        out_dir = Path(args.out)
        merge_cache(out_dir / "_cache", out_dir, args.bar_size)
        return 0
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
