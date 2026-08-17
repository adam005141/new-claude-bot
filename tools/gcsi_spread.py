#!/usr/bin/env python3
"""
The gold/silver spread, actually traded. Implements the 2026-08-13 pre-registration.

Fade the prior q-bar move in log(GC) - log(SI), hold q bars, non-overlapping, no stop.
One MGC against the causal dollar-neutral quantity of SIL.

Reports mean win and mean loss SEPARATELY. A mean alone hides the asymmetry that made VWAP
reversion lose money at a 59.8% win rate.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.data import build_continuous            # noqa: E402
from engine.overnight import minutes_since_open     # noqa: E402
from tools.feasibility import stationary_bootstrap  # noqa: E402

GC_PT, SI_PT = 10.0, 1000.0
GC_RT, SI_RT = 5.20, 31.20
HORIZONS, WINDOWS = (2, 4, 8), {"ALL": None, "NY": (0, 390)}


def aligned(start, end):
    def load(s):
        c = build_continuous("data_history", s, bar_size="30min")
        c = c[~c["thin_session"]].copy(); c["mso"] = minutes_since_open(c)
        sd = c["session_date"].astype(str)
        return c[(sd >= start) & (sd <= end)]
    a, b = load("GC"), load("SI")
    j = (a[["timestamp_utc","session_date","contract_month","mso","close"]]
         .rename(columns={"close":"gc","contract_month":"cm_a"})
         .merge(b[["timestamp_utc","contract_month","close"]]
                .rename(columns={"close":"si","contract_month":"cm_b"}), on="timestamp_utc")
         ).sort_values("timestamp_utc").reset_index(drop=True)
    last = j.groupby("session_date")[["gc","si"]].last()
    j["ratio"] = j["session_date"].map(((GC_PT*last["gc"])/(SI_PT*last["si"])).shift(1))
    return j.dropna(subset=["ratio"])


def blocks(j, win):
    out = []
    for _, g in j.groupby(["session_date","cm_a","cm_b"], sort=True):
        g = g.sort_values("mso")
        if win is not None: g = g[(g.mso >= win[0]) & (g.mso < win[1])]
        m = g.mso.to_numpy()
        if len(m) < 6: continue
        step = int(np.median(np.diff(m))); cuts = np.flatnonzero(np.diff(m) != step)+1
        arr = (np.log(g.gc.to_numpy(float)), np.log(g.si.to_numpy(float)),
               g.gc.to_numpy(float), g.si.to_numpy(float), g.ratio.to_numpy(float),
               g.timestamp_utc.to_numpy(), g.session_date.to_numpy())
        for p in np.split(np.arange(len(m)), cuts):
            if len(p) >= 6: out.append(tuple(x[p] for x in arr))
    return out


def trade(bs, q, delay=0, ledger=False):
    rows = []
    for lg, ls, gc, si, ratio, ts, sd in bs:
        t = q
        while t + delay + q < len(lg):
            prior = (lg[t]-ls[t]) - (lg[t-q]-ls[t-q])
            if prior != 0.0:
                d = -1.0 if prior > 0 else 1.0   # fade: long spread = long GC, short SI
                e = t + delay
                pnl = (d*(gc[e+q]-gc[e])*GC_PT) - (d*(si[e+q]-si[e])*SI_PT*ratio[e])
                if ledger:
                    rows.append({"session_date": sd[t], "dir": "LONG_GC" if d>0 else "SHORT_GC",
                                 "entry_utc": pd.Timestamp(ts[e]), "exit_utc": pd.Timestamp(ts[e+q]),
                                 "gc_in": gc[e], "gc_out": gc[e+q], "si_in": si[e], "si_out": si[e+q],
                                 "si_per_gc": round(float(ratio[e]),4),
                                 "gross_usd": round(float(pnl),2)})
                else:
                    rows.append(pnl)
            t += 2*q + delay
    return pd.DataFrame(rows) if ledger else np.asarray(rows, float)


def _bt(ef, n, rng):
    b = stationary_bootstrap(ef, n, rng); s = b.std(ddof=1)
    return float(b.mean()/(s/np.sqrt(len(b)))) if s > 0 else 0.0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2009-01-01"); ap.add_argument("--end", default="2016-12-31")
    ap.add_argument("--draws", type=int, default=800); ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--report", type=Path)
    a = ap.parse_args(argv)
    j = aligned(a.start, a.end)
    med = float(j.ratio.median()); rt = GC_RT + med*SI_RT

    print("GOLD/SILVER SPREAD, ACTUALLY TRADED")
    print("="*104)
    print(f"{len(j):,} aligned 30-min bars, {j.session_date.nunique():,} sessions. "
          f"1 MGC vs {med:.2f} SIL. Pair round turn ${rt:.2f}. Pre-registered. Runs ONCE.")
    print(f"\n  {'cell':<9}{'trades':>8}{'mean $':>9}{'t':>7}{'p':>8}{'WR':>7}"
          f"{'mean WIN':>10}{'mean LOSS':>11}{'W/L size':>10}{'delay1 $':>10}{'keep':>7}"
          f"{'net':>9}")
    rng = np.random.default_rng(a.seed); res = {}
    for w, wr_ in WINDOWS.items():
        bs = blocks(j, wr_)
        for q in HORIZONS:
            x = trade(bs, q)
            if len(x) < 100: continue
            se = x.std(ddof=1)/np.sqrt(len(x)); t = float(x.mean()/se)
            p = float(np.mean([_bt(x-x.mean(), len(x), rng) >= t for _ in range(a.draws)]))
            d1 = trade(bs, q, delay=1)
            wins, losses = x[x > 0], x[x < 0]
            mw, ml = float(wins.mean()), float(losses.mean())
            keep = float(d1.mean()/x.mean()) if x.mean() > 0 else float("nan")
            res[f"{w}/q{q}"] = {"n": len(x), "usd": float(x.mean()), "t": t, "p": p,
                                "wr": float((x > 0).mean()), "mean_win": mw, "mean_loss": ml,
                                "wl_ratio": abs(mw/ml), "delay1": float(d1.mean()),
                                "keep": keep, "rt": rt}
            print(f"  {w+'/q'+str(q):<9}{len(x):>8,}{x.mean():>9.2f}{t:>7.2f}{p:>8.4f}"
                  f"{(x>0).mean():>7.1%}{mw:>10.2f}{ml:>11.2f}{abs(mw/ml):>10.2f}"
                  f"{d1.mean():>10.2f}{(f'{keep:.0%}' if keep==keep else '-'):>7}"
                  f"{x.mean()-rt:>9.2f}")

    alpha = 0.05/len(res)
    print("\n" + "="*104)
    print(f"  PRE-REGISTERED DECISION (Bonferroni across {len(res)}, p < {alpha:.4f})")
    print(f"  {'cell':<10}{'mean>0':>8}{'p<a':>6}{'keeps 60%':>11}{'>cost':>8}   verdict")
    v = {}
    for k, s in res.items():
        cs = (s["usd"]>0, s["p"]<alpha, s["keep"]==s["keep"] and s["keep"]>=0.60, s["usd"]>s["rt"])
        v[k] = all(cs); y = lambda b: "yes" if b else "no"
        print(f"  {k:<10}{y(cs[0]):>8}{y(cs[1]):>6}{y(cs[2]):>11}{y(cs[3]):>8}   "
              f"{'PASS' if all(cs) else 'FAIL'}")

    best = max(res, key=lambda k: res[k]["usd"])
    w, q = best.split("/q")
    led = trade(blocks(j, WINDOWS[w]), int(q), ledger=True)
    led["net_usd"] = (led.gross_usd - rt).round(2)
    led["cum_gross"] = led.gross_usd.cumsum().round(2)
    Path("export").mkdir(exist_ok=True)
    led.to_csv("export/GCSI_spread_trades.csv", index=False)
    print(f"\n  best cell {best}: ledger -> export/GCSI_spread_trades.csv ({len(led):,} trades)")
    print(f"  gross total ${led.gross_usd.sum():,.0f}   net total ${led.net_usd.sum():,.0f}")
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps({"cells":res,"alpha":alpha,"verdicts":v}, indent=2, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
