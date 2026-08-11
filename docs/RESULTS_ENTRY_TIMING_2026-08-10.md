# Entry timing: the better fill buys a worse trade

Run 2026-08-10, once, per `docs/PREREGISTRATION_2026-08-10_ENTRY_TIMING.md`.
ES 2009-2016, 2,015 sessions, 5-minute bars, 1 contract, priced as MES.

## Result

| arm | mode | signals | filled | fill% | $/filled | $/signal | missed CF | Sharpe_all |
|---|---|---|---|---|---|---|---|---|
| A2L | IMMEDIATE | 1,882 | 1,882 | 100% | -5.06 | -5.06 | — | -0.173 |
| A2L | PULLBACK | 1,881 | 1,665 | 89% | **-6.22** | -5.50 | **+9.06** | -0.204 |
| A2L | BIAS | 1,882 | 1,057 | 56% | -5.12 | -2.88 | +7.69 | -0.136 |
| L2N | IMMEDIATE | 1,929 | 1,929 | 100% | -3.60 | -3.60 | — | -0.072 |
| L2N | PULLBACK | 1,934 | 1,700 | 88% | **-6.60** | -5.80 | **+23.89** | -0.128 |
| L2N | BIAS | 1,933 | 1,204 | 62% | -7.03 | -4.38 | +24.53 | -0.115 |
| NYOR | IMMEDIATE | 1,948 | 1,948 | 100% | -3.58 | -3.58 | — | -0.084 |
| NYOR | PULLBACK | 1,950 | 1,697 | 87% | **-5.54** | -4.82 | **+13.93** | -0.125 |
| NYOR | BIAS | 1,949 | 1,187 | 61% | -5.69 | -3.46 | +11.84 | -0.110 |

**All six non-control cells FAIL all five criteria.**

## The validity check passed

IMMEDIATE on 5-minute reproduces the 30-minute result almost exactly:

| arm | 30-min | 5-min |
|---|---|---|
| A2L | -5.09 | **-5.06** |
| L2N | -3.71 | **-3.60** |
| NYOR | -3.69 | **-3.58** |

Two independently downloaded datasets, two separate code paths, same answer to within
eleven cents. Whatever else is wrong, the data and the engine are not.

## Adverse selection, doing double damage

I predicted the filled trades would look **better** per trade because the fill is genuinely
cheaper, and that the loss would come from missing winners. **The first half was wrong, and
wrong in the direction that matters.**

The limit entry costs 1.5 ticks round trip instead of 2.0, a saving of $0.63. Yet every
filled trade is worse:

| arm | IMMEDIATE | PULLBACK filled | change |
|---|---|---|---|
| A2L | -5.06 | -6.22 | **-1.16** |
| L2N | -3.60 | -6.60 | **-3.00** |
| NYOR | -3.58 | -5.54 | **-1.96** |

A cheaper fill and a worse outcome. **The trades that come back to your limit are the ones
about to fail.** That is adverse selection stated as plainly as data can state it: the fill
is not free information, it is a signal, and the signal is bad.

## And the missed trades were the winners

The 11-13% of signals that never retraced a single tick within thirty minutes would have
earned, under immediate entry:

    A2L   +$9.06     L2N   +$23.89     NYOR   +$13.93

A break that never looks back is a real move. Waiting for a better price systematically
declines exactly those.

**This is why the load-bearing rule was written down first.** Both halves of the trap fired
at once here, so even a filled-only report would have failed — but the missed-counterfactual
column is what makes the magnitude visible, and on a structure with any real edge that
column is where an honest test and a flattering one diverge.

## BIAS

The prior-session-midpoint filter cuts trade count to 56-62% and improves per-signal loss
by trading less. A2L/BIAS is the only cell that beats its own control on Sharpe (-0.136
against -0.173), and that is not a finding: it is the arithmetic of doing less of a losing
thing. It fails the other four criteria.

## Prediction scorecard

| registered | outcome |
|---|---|
| IMMEDIATE reproduces the 30-min result | **correct** |
| PULLBACK fills 50-75% of signals | **wrong** — 87-89% |
| filled trades look better per trade | **wrong** — every one is worse |
| over all sessions, PULLBACK <= IMMEDIATE | **correct** |
| BIAS makes it worse | correct on 2 of 3 |
| ~12% that any cell passes | none passed |

Right on the conclusion, wrong on two mechanisms, and wrong in the direction that would
have made me too optimistic rather than too pessimistic. Recorded next to Block A
(prediction wrong on sign and significance), the overnight arms (gross inside the range),
and the cross-session arms (correct throughout).

## What this closes

Nineteen structures are now closed on evidence. This one answers the specific question that
motivated buying 5-minute data: **the 10-18 ticks of favourable excursion visible inside the
30-minute entry bar are not reachable.** They sit overwhelmingly before the break, or in
trades that fail after it. A resting limit captures the wrong half.

The multi-timeframe idea is tested and closed in the form specified. What is NOT closed is
every other form of it, and that distinction should not be blurred: this tested one bias
definition, one pullback rule, and one fill window. It did not test momentum-confirmation
entries, volume-based triggers, or any bias other than the prior session's midpoint. Those
remain untested rather than disproven — but the base rate across nineteen closed structures
should inform how much any of them is worth.
