#!/usr/bin/env python3
"""
Trade ledger for the VWAP reversion arm (REV), the last signed claim in the project.

REV was reported at -$1.59 gross and -$5.29 net a trade, t -2.80, and it is one of only
three structures this project called significantly NEGATIVE. A signed claim is the only kind
where a bug changes the answer, so it gets a ledger.

The signal selection below is the same as tools/intraday_reversion.session_trades and the
exit walk is that module's own `_walk`, called with detail=True. The published mean is the
fidelity test and is asserted.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.data import build_continuous            # noqa: E402
from engine.overnight import minutes_since_open     # noqa: E402
import tools.intraday_reversion as R                # noqa: E402

COST = 2.0 * 1.0 * R.TICK * R.POINT + R.COMMISSION_RT      # $3.70, as published


def main() -> int:
    c = build_continuous("data_5min", "ES", bar_size="5min")
    c = c[~c["thin_session"] & ~c["entries_blocked"]].copy()
    c["mso"] = minutes_since_open(c)
    sd = c["session_date"].astype(str)
    c = c[(sd >= "2009-01-01") & (sd <= "2016-12-31")]

    rows = []
    for sess, s in c.groupby("session_date", sort=True):
        w = s[(s["mso"] >= R.NY[0]) & (s["mso"] < R.NY[1])].sort_values("mso")
        if len(w) < R.MIN_BARS + 3:
            continue
        px = w["close"].to_numpy(float); hi = w["high"].to_numpy(float)
        lo = w["low"].to_numpy(float);   op = w["open"].to_numpy(float)
        ts = w["timestamp_utc"].to_numpy(); cm = w["contract_month"].to_numpy()
        vol = pd.to_numeric(w["volume"], errors="coerce").fillna(0.0).to_numpy(float)
        tp = (hi + lo + px) / 3.0
        cv = np.cumsum(vol)
        vwap = np.where(cv > 0, np.cumsum(tp * vol) / np.maximum(cv, 1e-12),
                        np.cumsum(tp) / np.arange(1, len(tp) + 1))
        spread = px - vwap
        sdv = pd.Series(spread).expanding(min_periods=R.MIN_BARS).std(ddof=1).to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            z = np.where(sdv > 0, spread / sdv, np.nan)
        for i in range(R.MIN_BARS, len(w) - 1):
            if not np.isfinite(z[i]) or abs(z[i]) < R.K_ENTRY:
                continue
            d = -1 if z[i] > 0 else 1
            r = R._walk(i, d, px, hi, lo, op, vwap, sdv, COST, detail=True)
            if r is None:
                break
            rows.append({
                "session_date": sess, "contract": str(cm[i]),
                "dir": "SHORT" if d < 0 else "LONG",
                "entry_utc": pd.Timestamp(ts[i]), "exit_utc": pd.Timestamp(ts[r["exit_bar"]]),
                "z_at_entry": round(float(z[i]), 3),
                "vwap_at_entry": round(float(vwap[i]), 4),
                "sigma_at_entry": round(float(sdv[i]), 4),
                "entry_px": r["entry_px"], "exit_px": round(r["exit_px"], 4),
                "reason": r["reason"], "bars_held": r["exit_bar"] - i,
                "gross_usd": round(r["net"] + COST, 2), "net_usd": round(r["net"], 2)})
            break
    t = pd.DataFrame(rows).sort_values("entry_utc").reset_index(drop=True)
    t["cum_net"] = t["net_usd"].cumsum().round(2)
    Path("export").mkdir(exist_ok=True)
    t.to_csv("export/ES_REV_vwap_trades.csv", index=False)

    print("VWAP REVERSION (REV) TRADE LEDGER -- the last signed claim")
    print("=" * 92)
    print(f"{len(t):,} trades, published mean net -5.29 / gross -1.59")
    print(f"  mean net   {t.net_usd.mean():>8.2f}   "
          f"{'OK' if abs(t.net_usd.mean() + 5.29) < 0.02 else '** MISMATCH **'}")
    print(f"  mean gross {t.gross_usd.mean():>8.2f}   "
          f"{'OK' if abs(t.gross_usd.mean() + 1.59) < 0.02 else '** MISMATCH **'}")
    print(f"  gross total {t.gross_usd.sum():>11,.0f}   net total {t.net_usd.sum():>11,.0f}")
    print(f"  win rate gross {(t.gross_usd > 0).mean():.1%}   "
          f"median bars held {t.bars_held.median():.0f}")
    print("\n  exit reason mix")
    print(t.groupby("reason").agg(n=("net_usd", "size"), mean_gross=("gross_usd", "mean"),
                                  total_gross=("gross_usd", "sum"))
          .to_string(float_format=lambda v: f"{v:,.2f}"))
    d = np.where(t["dir"] == "SHORT", -1, 1)
    print("\n  INVARIANTS")
    inv = {
        "gross = (exit-entry)*dir*5": np.allclose((t.exit_px - t.entry_px) * d * R.POINT,
                                                  t.gross_usd, atol=0.02),
        "net = gross - 3.70": np.allclose(t.gross_usd - COST, t.net_usd, atol=0.01),
        "|z| >= 2.0 at every entry": bool((t.z_at_entry.abs() >= R.K_ENTRY - 1e-9).all()),
        "direction fades the extension": bool(((t["dir"] == "SHORT") == (t.z_at_entry > 0)).all()),
        "exit strictly after entry": bool((t.exit_utc > t.entry_utc).all()),
        "one trade per session": bool(t.session_date.is_unique)}
    for k, v in inv.items():
        print(f"    {k:<34}{'OK' if v else '** FAIL **'}")
    print(f"\n  ledger -> export/ES_REV_vwap_trades.csv ({len(t):,} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
