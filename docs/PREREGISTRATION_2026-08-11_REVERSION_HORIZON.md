# Pre-registration: at what holding horizon does the measured reversion pay?

Written **2026-08-11, after the return-structure diagnostic and before this test was run**.
Nothing below may be revised after seeing a result.

## What motivated this, disclosed

`tools/return_structure.py` measured the ES 5-minute return process directly. It is a
property measurement, not a strategy, and it found:

| | ac(1) | Bartlett 2se | VR(2) | z |
|---|---:|---:|---:|---:|
| ALL | **-0.0311** | 0.0027 | 0.969 | **-7.8** |
| ASIA | -0.0550 | 0.0043 | 0.945 | -9.1 |
| LONDON | -0.0400 | 0.0050 | 0.960 | -7.2 |
| NY | -0.0209 | 0.0051 | 0.980 | -3.2 |

Every variance ratio is below 1 out to q = 32, most at |z| > 3. **ES 5-minute returns are
significantly mean-reverting at every horizon and in every session window.** The random walk
is rejected, in the direction opposite to what every breakout cell in this project bet on.

**This diagnostic is why I am running this test, and that is selection.** I am disclosing it
rather than pretending the horizon sweep was an independent idea. What makes it worth
spending trials on anyway is the next section.

## Why this test is decisive rather than another null

Expected move scales as the square root of time. **Cost does not scale at all.** So for a
reversal trade held q bars, edge grows like `sqrt(q)` while the round turn stays at $3.70,
and `edge / cost` is monotone increasing in holding time.

That means a sweep over q has a special property the previous forty-three cells did not:
**it produces a ceiling.** If the best horizon in the sweep still falls short of cost, then
no entry refinement, no filter, and no confluence rescues this family, because they all
operate inside the same edge budget. A negative result here closes reversion permanently
rather than leaving it open to a forty-fourth variant.

## The structure

At the close of bar `t`, having observed the return over the preceding `q` bars, take the
**opposite** side and hold exactly `q` bars. Exit at market.

- **Non-overlapping**, so trades are statistically independent and the t-statistic is honest
- Strictly within one session and one contract; no trade spans a roll or the overnight halt
- Both directions, 1 contract, priced as MES at $5 a point
- No stop, no filter, no discretion. This is a measurement of the family's ceiling, and a
  stop would only subtract from it

| q (bars) | 1 | 2 | 3 | 6 | 12 | 24 | 48 | 78 |
|---|---|---|---|---|---|---|---|---|
| minutes | 5 | 10 | 15 | 30 | 60 | 120 | 240 | 390 |

Eight horizons. Bonferroni gives nominal **p < 0.00625**.

Take rate is **100% by construction** — this trades every non-overlapping window and has no
filter, so the degeneracy failure mode that caught four previous arms cannot occur here.

## Decision rule

Raw P&L is `(exit - entry) x $5 x 1 contract`, per the standing scope change. But this test
is specifically about whether the edge covers the spread, so **both bars are reported and
both are binding**:

1. mean **> $0 per trade** raw — is the reversion there at all
2. mean **> $3.70 per trade** — does it cover the measured round turn
3. Bonferroni **p < 0.00625**
4. **t > 2.0 after removing the best 5% of trades**

An arm "passes as a measurement" on 1, 3, 4. It "passes as a strategy" only with 2 as well.
Those are reported as separate columns and must not be conflated.

**On the standing instruction to ignore fees and slippage.** That instruction is honoured in
column 1. It cannot be honoured in a conclusion, because a $0.50 raw edge against a $3.70
round turn is not a strategy that can be traded by anyone at any account size. Ignoring cost
is a valid way to isolate whether a signal exists. It is not a way to make the spread stop
existing.

## Registered prediction

> **Every horizon shows a positive raw mean, and no horizon clears $3.70.**
>
> The raw edge is essentially guaranteed positive: it is the same property the diagnostic
> already measured at z = -7.8, and this trade is the most direct possible expression of it.
> A negative raw result would mean the diagnostic and the backtest disagree, which would
> indicate a bug in one of them rather than a fact about the market.
>
> **Magnitude is the whole question.** The diagnostic put the 1-bar ceiling at $0.11-$0.14.
> If the reversion coefficient held constant across horizons, edge would scale as `sqrt(q)`
> and reach roughly **$0.12 x sqrt(78) = $1.06** at the session horizon. But the variance
> ratios keep falling with q (0.969 at q=2 down to 0.926 at q=32), which means the effective
> coefficient *grows* with horizon, so the true profile should rise somewhat faster than
> `sqrt(q)`.
>
> I therefore expect the mean to rise monotonically with q and **peak between $0.50 and
> $2.50 at q = 48 or 78**, against a $3.70 cost. Best guess at the peak: **$1.50**.
>
> **The t-statistics will be enormous at small q** — 550,050 bars means 550,050 trades at
> q = 1 — and this is exactly where a t-statistic misleads. A $0.12 edge at t = 20 is still
> $0.12. I am flagging that in advance so I do not report significance as success.
>
> Probability any horizon clears $3.70: **under 10%.** Probability the raw means are
> positive and significant: **above 90%.** Those two together are the finding.

Ninth prediction. Prior eight: Block A (wrong on sign and significance), overnight arms
(gross inside range), cross-session (correct throughout), entry timing (right on conclusion,
wrong on fill rate and direction), entry variants (wrong that filters would only trade
less), reversion (wrong on gross sign and take rate), ICT/quant (right that none passed,
wrong on SWEEP and VOLLOW mechanisms), trend/confluence (right on the arithmetic, wrong that
removing the stop would help).

## What I will not do

- Not add a ninth horizon after seeing these eight
- Not add a filter, a stop, or a session restriction to rescue a horizon that falls short
- Not report a raw-positive result as a working strategy when it fails the cost bar
- Not report a pass as a result: cumulative count becomes fifty-one and 2017-2023 remains
  the confirmation set
