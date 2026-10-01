#!/usr/bin/env python3
"""
Rebuild the data from the committed raw CSVs and re-run the headline tests.

    python reproduce.py            headline tests, full bootstrap draws
    python reproduce.py --quick    same tests, 50 draws: means and t exact, p NOT reliable
    python reproduce.py --all      also the slow ones (volume conditioning, ICT, trend)

Each test prints its full table and pre-registered verdict, and the same text is saved to
results/<test>.txt. Every test's output is under 45 lines.

The processed parquet under data_history/ and data_5min/ is gitignored, so a fresh clone
has only data_raw/. The first run rebuilds it, which takes under a minute; later runs skip
that step unless --rebuild is passed.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

IMPORTS = [
    ("data_raw/barchart", "data_history", "30min"),      # ES, GC, SI, HG
    ("data_raw/barchart_nq", "data_history", "30min"),   # NQ
    ("data_raw/barchart_5min", "data_5min", "5min"),     # ES 5-minute
]

# What a correct build produces. Checked by count, not by folder existence: a copy built
# before the NQ import, or by an older importer, has the ES folder and is still wrong.
EXPECTED = {("data_history", "ES"): 35, ("data_history", "GC"): 30,
            ("data_history", "SI"): 30, ("data_history", "HG"): 30,
            ("data_history", "NQ"): 33, ("data_5min", "ES"): 32}

# (tool, what it tests, published headline to compare against)
HEADLINE = [
    ("cross_session", "session breakouts A2L/L2N/NYOR",
     "A2L -5.09, L2N -3.71, NYOR -3.69 net per trade"),
    ("intraday_reversion", "VWAP reversion",
     "REV -1.59 gross / -5.29 net per trade"),
    ("reversion_horizon", "reversion edge vs holding time",
     "q=1 +0.205 at t 19.36, decaying to zero by 60 min"),
    ("esnq_spread", "ES/NQ spread",
     "ASIA/q1 +0.430 at t 25.09, keeps 6% under delay"),
    ("surviving_cells", "cells that survived bounce dilution",
     "SI/ASIA/q4 +7.218 at t 3.09, keeps 112%"),
    ("passive_execution", "passive fills on silver",
     "TAKE +7.29; unfilled counterfactuals 25-38x filled"),
    ("gcsi_spread", "gold/silver spread",
     "ALL/q8 +3.88, win 49.45 vs loss 50.80, net -20.83"),
]
SLOW = [
    ("volume_conditioned", "volume-conditioned reversion",
     "THIN keeps 20%, HEAVY keeps 86% under delay"),
    ("ict_quant", "ICT structures and quant filters", "all five fail"),
    ("trend_confluence", "4h trend and confluence", "all five fail"),
]


QUICK_WARNING = """\
QUICK MODE: 50 bootstrap draws. Means, t-statistics and the strategy verdicts are exact,
but a p-value can only be resolved to 1/50 = 0.02, and the Bonferroni thresholds here run
from 0.0025 to 0.025. Any 'p<a' marked yes, and any MEASUREMENT verdict that depends on
it, is unconfirmed in this mode. Known case: surviving_cells ES/LONDON/q1 shows PASS here
but its true p is 0.0060 against a 0.0025 threshold, so it FAILS. Run without --quick to
get the published verdicts exactly."""


def child_env() -> dict:
    env = dict(os.environ)
    # Some tools print non-ASCII (sigma, dashes). Windows consoles and redirects default to
    # cp1252 and would raise UnicodeEncodeError without UTF-8 mode.
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # A child writing to a pipe block-buffers by default, so its output would still arrive
    # in one lump at the end. Unbuffered makes the streaming real.
    env["PYTHONUNBUFFERED"] = "1"
    return env


def check_data() -> list[str]:
    """Every way the existing build differs from a correct one. Empty means it is good."""
    problems = []
    for (top, sym), want in EXPECTED.items():
        d = ROOT / top / sym
        got = len(list(d.glob("*.parquet"))) if d.is_dir() else 0
        if got != want:
            problems.append(f"{top}/{sym}: {got} contract files, expected {want}")
    return problems


def rebuild(force: bool) -> None:
    problems = check_data()
    if not problems and not force:
        print("data already built and verified: every instrument has its expected "
              "contract count\n")
        return
    if problems:
        print("EXISTING DATA IS INCOMPLETE OR STALE, rebuilding:")
        for pr in problems:
            print(f"  {pr}")
    # Move any old build aside rather than deleting it, so nothing local is lost and no
    # stale file can be picked up alongside the fresh ones.
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for top in ("data_history", "data_5min"):
        d = ROOT / top
        if d.is_dir():
            d.rename(ROOT / f"{top}.old-{stamp}")
            print(f"  moved old {top}/ to {top}.old-{stamp}/ (safe to delete)")
    print("REBUILDING DATA FROM data_raw/  (under a minute)")
    for src, out, bar in IMPORTS:
        cmd = [sys.executable, "tools/import_barchart.py", "--src", src, "--out", out,
               "--bar-size", bar]
        r = subprocess.run(cmd, cwd=ROOT, env=child_env(), capture_output=True, text=True,
                           encoding="utf-8")
        tail = [ln for ln in r.stdout.splitlines() if "written" in ln or "timezone" in ln]
        print(f"  {src:<24} -> {out:<13} {' | '.join(tail) or r.stderr.strip()[-200:]}")
        if r.returncode != 0:
            sys.exit(f"import failed for {src}; see the message above")
    left = check_data()
    if left:
        sys.exit("rebuild finished but the data is still wrong:\n  " + "\n  ".join(left))
    print("  verified: every instrument has its expected contract count\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="50 bootstrap draws")
    ap.add_argument("--all", action="store_true", help="include the slow tests")
    ap.add_argument("--rebuild", action="store_true", help="rebuild data even if present")
    args = ap.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    rebuild(args.rebuild)
    if args.quick:
        print(QUICK_WARNING + "\n")
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)

    tests = HEADLINE + (SLOW if args.all else [])
    summary = []
    for tool, what, published in tests:
        cmd = [sys.executable, f"tools/{tool}.py"] + (["--draws", "50"] if args.quick else [])
        print("=" * 100)
        print(f"{tool}: {what}")
        print(f"published: {published}")
        print("=" * 100, flush=True)
        t0 = time.time()
        # Streamed line by line, so a long test shows progress instead of looking frozen.
        lines = []
        with subprocess.Popen(cmd, cwd=ROOT, env=child_env(), stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                              bufsize=1) as proc:
            for line in proc.stdout:
                print(line, end="", flush=True)
                lines.append(line)
        rc = proc.returncode
        secs = time.time() - t0
        (out_dir / f"{tool}.txt").write_text("".join(lines), encoding="utf-8")
        print(f"\n[{secs:.0f}s, full output in results/{tool}.txt]\n", flush=True)
        summary.append((tool, "ok" if rc == 0 else f"FAILED ({rc})", secs))

    print("=" * 100)
    print("RUN SUMMARY")
    for tool, status, secs in summary:
        print(f"  {tool:<22}{status:<14}{secs:>7.0f}s")
    if args.quick:
        print("\n" + QUICK_WARNING)
    print("\nNone of these is a tradeable strategy. See docs/EXPERIMENT_LEDGER.md for why.")
    return 0 if all(s == "ok" for _, s, _ in summary) else 1


if __name__ == "__main__":
    sys.exit(main())
