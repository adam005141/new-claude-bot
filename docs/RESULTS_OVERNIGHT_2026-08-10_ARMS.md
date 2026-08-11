# Overnight arms: the premium is real, and smaller than the cost of harvesting it

Run 2026-08-10, once, per `docs/PREREGISTRATION_2026-08-09_EVENT_OVERNIGHT.md` and its two
amendments. ES 2009-2016, 2,000 sessions, priced as MES, 18:00 ET to 09:30 ET.

## Result

| arm | sessions | nights | f | net | $/night | Sharpe_all | p |
|---|---|---|---|---|---|---|---|
| BASE | 2,000 | 2,000 | 1.00 | -3,637 | -1.82 | **-0.041** | 0.992 |
| TOM | 2,000 | 384 | 0.19 | -468 | -1.22 | **-0.012** | 0.715 |
| DOW (Thu) | 995 | 202 | 0.20 | -490 | -2.43 | **-0.026** | 0.800 |

All arms **FAIL** every criterion except "beats BASE", which they clear only by losing
less. DOW's weekday was chosen on 2009-2012 (Thu, +$2.38/night there) and scored only on
2013-2016, where it returned -$2.43/night. That reversal is what the handicap exists to
catch.

## The effect is real. It just cannot pay for its own execution.

Gross, before any cost:

    overnight premium   +0.3763 points/night   t = +1.89   Sharpe_all = 0.0422

**My registered prediction was that BASE would land at Sharpe_all 0.04-0.06. Gross came in
at 0.042, inside that range.** The overnight equity premium is present in ES futures over
2009-2016, at roughly the documented size.

The problem is arithmetic, and it is instrument-independent because it is in points:

    overnight premium     0.3763 points a night
    round-trip slippage   0.5000 points a night   (one tick per side)
    ratio                 0.75x

The premium is three quarters of the slippage **before commission**. No contract size fixes
this: both sides scale with point value, so the ratio is identical on MES, ES, or anything
else.

| cost model | $/night | Sharpe_all |
|---|---|---|
| registered (1 tick/side + $1.20) | -1.82 | -0.041 |
| half-spread only + commission | -0.57 | -0.013 |
| half-spread, zero commission | +0.63 | +0.014 |
| **zero cost, impossible** | **+1.88** | **+0.042** |

**The ceiling at literally zero cost is Sharpe 0.042, less than half the 0.10 needed.** Even
if execution were free, this could not pass.

## The account rule is what kills it

A buy-and-hold investor harvests this premium and pays the spread once. The evaluation
requires flat through the 17:00-18:00 ET maintenance halt, which forces a **round trip every
night**. That converts a real premium of 0.38 points into a guaranteed loss of 0.12 points a
night before commission.

The rule does not merely tax the strategy. It is the reason the strategy is negative.

## What is not claimed

The classic "all equity returns accrue overnight" result does **not** reproduce here. Over
2009-2016, gross, within-session:

    overnight (18:00 -> 09:30)   +752.5 points
    intraday  (09:30 -> close)   +963.8 points

Intraday beat overnight. The premium exists but it is not dominant, and the split is roughly
44/56. Whether that is a futures-versus-cash difference, a window difference (this misses
16:00-18:00 ET), or a period-specific result is not established here and is not claimed.

## Where this leaves the FOMC arm

Still held pending a sourced calendar, and **more interesting after this result, not less**.

FOMC nights pay the same $3.70 as any other night, but there are only ~64 of them across
2009-2016, so total cost is about $237. If the documented pre-FOMC drift near 49bp holds on
ES at an average index level around 1,500, that is roughly 7 points, or $37 a night gross on
a micro. Cost stops being the binding constraint.

The bar is then criterion 3. At f = 0.032, sqrt(f) = 0.18, so the arm needs a per-night
Sharpe above roughly 0.56 to reach Sharpe_all of 0.10. That is a large per-night Sharpe but
not an absurd one for a scheduled-event window.

So the pre-registered prediction that FOMC "fails on sample size alone" may be wrong. It is
left standing as written rather than revised, and the arm will be run once dates are
available.

## Ledger position

BASE, TOM and DOW join the closed list. That is ten structures now closed on evidence. The
one thing that changed is the reason: this is the first that failed with a **real, measured,
positive gross edge**. Everything before it failed because there was nothing there.
