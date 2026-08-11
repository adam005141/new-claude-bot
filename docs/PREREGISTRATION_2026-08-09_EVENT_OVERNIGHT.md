# Pre-registration: is the overnight index premium concentrated in catalyst windows?

Written **2026-08-09, before any ES data earlier than 2024 exists on disk**. Committed
before the download. Nothing below may be revised after seeing a result.

## Why this and not another price pattern

Six structures have now been closed on evidence: four legs on MES/MNQ, two mechanism-free
screens, and the commodity ORB, which cleared every gate in-sample and returned
-$2.30/trade out of regime across 1,087 trades with adequate power.

The common feature of all six is that they are **price patterns on liquid futures**. The
prior for a seventh is poor and I am not going to spend the download quota on one.

This is a different class: an effect with published evidence and a proposed economic
mechanism (compensation for holding risk through scheduled uncertainty), rather than a
shape found by searching. It is also the only family in which this project ever saw a
positive development result — Leg D, the plain overnight hold, returned +$10.18/session in
development before dying in validation at session 25 of 232.

**This re-opens a closed leg.** That is disclosed, and it counts toward the multiple-testing
burden. It is justified by roughly ten times the data and a decision rule fixed in advance,
not by disliking the earlier answer.

## The binding constraint is Sharpe, not edge

Measured against the real MLL rules, per-session Sharpe maps to pass probability roughly:

| per-session Sharpe | 50k pass | vs luck |
|---|---|---|
| 0.00 | 23% | — |
| 0.05 | 40% | +17 |
| 0.10 | 59% | +36 |
| 0.15 | 76% | +53 |

The documented overnight equity premium is worth roughly **0.05**. That is a coin flip that
costs $50/month for about three months. So the question is not whether the premium exists;
it is whether it can be concentrated enough to reach 0.10 or better.

### The concentration arithmetic, derived before the test

Trade a fraction `f` of nights, with mean `m` and standard deviation `s` on the nights
traded, and zero otherwise. Over all sessions:

    mean_all = f * m
    sd_all   = sqrt(f) * s
    Sharpe_all = sqrt(f) * (m / s)

**Position size cannot repair this.** Size multiplies edge and noise identically, so it
moves time-to-target but never Sharpe. That result is already established in this project
and is not re-litigated here.

Therefore a conditioned window beats holding every night **only if**

    Sharpe_conditioned  >  Sharpe_baseline / sqrt(f)

At f = 0.20 that is 2.2x the baseline Sharpe. At f = 0.03 (pre-FOMC, eight nights a year)
it is 5.8x. Concentration is not free, and a window that merely has a higher mean is not
enough — it has to beat that threshold.

## What is tested

Enter at the session open **18:00 ET**, exit at **09:30 ET**. That window is forced by the
account rules: flat is required from 17:00 to 18:00 ET, which is the CME maintenance halt,
so a continuous 16:00-to-09:30 hold is not tradeable. This is the same window Leg D used.

Instrument: **ES 2008-2016**, priced and costed as **MES** ($5/point), the contract a small
account can actually trade. Same substitution used for silver and copper.

Four arms. Three conditioning schemes plus the unconditional control:

| arm | window | f (approx) | source of the hypothesis |
|---|---|---|---|
| **BASE** | every night | 1.00 | control, not a hypothesis |
| **TOM** | last trading day of month + first 3 | 0.19 | turn-of-month effect |
| **FOMC** | night before a scheduled FOMC announcement | 0.03 | pre-FOMC announcement drift |
| **DOW** | best single weekday, chosen on 2008-2012 only | 0.20 | weekend/day-of-week effect |

DOW is deliberately handicapped: the weekday is selected on 2008-2012 and then applied
unchanged to 2013-2016. Choosing it on the full sample would be selection, and reporting it
as a finding would be dishonest.

## Decision rule, fixed in advance

Computed on 2008-2016, net of measured costs, with entries blocked on roll sessions.

An arm **passes** only if all three hold:

1. mean net per session **> $0**
2. rotation-null one-sided **p < 0.05**, Bonferroni-corrected across the three conditioning
   arms (so nominal **p < 0.0167**); BASE is a control and is not corrected because it is
   not a hypothesis
3. **Sharpe_all > 0.10**, the level that reaches ~59% pass on a 50k account

And a fourth, which is the whole point of the exercise:

4. **Sharpe_all must exceed BASE's Sharpe_all.** An arm that beats zero but not the plain
   overnight hold has demonstrated nothing about concentration.

## Registered prediction

> BASE comes in at Sharpe_all near 0.04-0.06, consistent with the documented premium, with
> p < 0.05 given roughly 2,200 sessions.
>
> FOMC shows the largest per-night mean by a wide margin but fails criterion 3 on sample
> size alone: eight nights a year over nine years is ~72 nights, and sqrt(0.03) = 0.17 caps
> Sharpe_all at about 0.17 x Sharpe_conditioned even if the conditioned Sharpe is large.
>
> TOM is the most likely of the three to pass, landing near 0.06-0.09.
>
> **Most likely overall outcome: no arm reaches 0.10, and the honest conclusion is that the
> overnight premium is real but too small to pass this evaluation reliably.** Probability I
> would put on at least one arm passing all four criteria: roughly 25%.

Confidence is low-to-moderate and deliberately so. Recorded so the error rate stays visible
next to Block A, where my registered prediction was wrong on sign and significance.

## What I will not do

- Not add a fourth conditioning scheme after seeing the first three
- Not tune the window definitions (TOM is exactly -1 to +3; FOMC is exactly the one night
  before; DOW is chosen on 2008-2012 and frozen)
- Not switch instruments if ES fails
- Not re-run a failed arm with a fix

If nothing passes, that is the answer, and it goes in the ledger next to the seven
structures already closed.

## Held back

**2017-2023 is not downloaded and must not be**, so that a passing arm has somewhere
genuinely unseen to be confirmed. If an arm passes on 2008-2016, the confirmation set is
specified now: same code, same parameters, 2017-2023, single run.

---

## Amendment 1, 2026-08-10: the window narrows to 2009-2016

Recorded **before any result was computed**, and forced by data availability rather than
chosen.

Barchart's ES intraday archive begins **2008-05-04**. ESH08 returns a file containing a
header and a provenance footer and nothing else; ESM08 starts 2008-05-04, already inside
its own roll. The continuous series has 43 tradeable sessions in 2008 and a 24-day hole in
October, then runs clean at 257-259 sessions a year from 2009.

The tested window is therefore **2009-2016, eight full years, 2,053 sessions**, not the
nine years registered. Nothing else changes.

This costs the 2008 crash, which was the most distinctive regime in the registered span.
That is a real loss and it is not recoverable: the data does not exist to buy. There is no
point spending further quota on 2008 contracts.

Power is barely affected. Eight years still gives ~2,050 sessions for BASE, ~390 for TOM,
and ~64 for FOMC.

## Amendment 2, 2026-08-10: the FOMC arm is blocked pending dates

The FOMC arm needs the exact announcement dates for 2009-2016. This environment's egress
proxy blocks federalreserve.gov, and web search returned 2009-2013 complete, 2014 partial,
and almost nothing for 2015-2016.

An incomplete schedule does not weaken the arm, it corrupts it: a missed meeting is a night
labelled "no event" that was in fact the event, which contaminates both the treatment and
the control. Guessing the remainder from memory is exactly the kind of fabricated input
this project refuses.

The arm is therefore **held, not dropped**, until a complete and sourced list is supplied.
BASE, TOM and DOW are unaffected and may run first. If FOMC never runs, the Bonferroni
correction across the conditioning arms drops from three to two (nominal p < 0.025), and
that change is recorded here rather than applied silently.
