# Intraday reversion: negative before costs, and Leg A is confirmed not underpowered

Run 2026-08-10, once, per `docs/PREREGISTRATION_2026-08-10_INTRADAY_REVERSION.md`.
ES 2009-2016, 2,015 sessions, 5-minute, NY window, VWAP anchor, 1 contract.

| arm | signals | taken | take% | **gross/trade** | net/trade | net/signal | WR | skip CF | p |
|---|---|---|---|---|---|---|---|---|---|
| REV | 1,969 | 1,969 | 100% | **-1.59** | -5.29 | -5.29 | 56% | — | 1.000 |
| REV-HTF | 1,969 | 105 | 5% | **+1.82** | -1.88 | -0.10 | 57% | -5.48 | 0.900 |

**Both FAIL all three criteria.** Under a doubled spread: -$7.79 and -$0.23 per signal.

## The headline: reversion is negative BEFORE costs

I registered that REV would come back "slightly positive in GROSS and negative in NET,
gross roughly +$2 to +$5". **Gross is -$1.59.** Fading a 2-sigma extension from session VWAP
loses money on ES before a cent of cost is paid.

The win rate is 56%, so price usually does return to the anchor. It just does not return
often enough, or far enough, to pay for the times it keeps going — and with a 4-sigma stop
those losses are large. That is the classic reversion payoff shape, and here it is
net-negative on its own terms.

**This confirms Leg A rather than overturning it.** Leg A died on 177 trades of MES and I
argued that was underpowered, not disproven. On eleven times the sample and a different
instrument, it is disproven: the structure has negative gross edge.

## The HTF filter works, and cannot save it

REV-HTF is the one genuinely encouraging number in this run, and it is not enough.

- It flips gross from **-$1.59 to +$1.82**
- The trades it declines would have lost **-$5.48** each — it is removing exactly the right
  ones
- But **+$1.82 gross against a $3.70 round turn** is still a loss

The higher-timeframe filter is doing real work. Fading extensions only when the larger
picture is quiet identifies the subset where reversion actually pays. That subset just does
not pay enough.

## A second design flaw, recorded

I predicted REV-HTF would trade **40-60%** as often. It trades **5%** — 105 signals in eight
years.

The reason is collinearity I should have anticipated: the filter requires the 60-minute move
to be under 1.0 session sigma, but a 2-sigma extension from VWAP almost always *is* a large
recent move. The condition is close to the negation of the entry signal, so it almost never
fires.

That is the same class of error as the VOLUME filter comparing a London break bar to an
Asian median. Two pre-registrations in a row have contained a filter that was nearly
degenerate against its own signal. The fix for next time is explicit: **state the expected
take rate in the pre-registration and check it before running**, so a collinear filter is
caught by arithmetic rather than by the result.

## Prediction scorecard

| registered | outcome |
|---|---|
| REV gross +$2 to +$5, net slightly negative | **wrong on gross** — -$1.59, negative before cost |
| REV-HTF trades 40-60% as often | **wrong** — 5% |
| REV-HTF improves gross per trade | **correct** — -1.59 to +1.82 |
| trending sessions are where fading loses | **correct** — skipped CF -$5.48 |
| ~30% that an arm passes | none passed |

Sixth prediction recorded. The direction of the error matters: I was **too optimistic**
about the raw reversion effect and **right about the mechanism** that would improve it.

## Where the whole search now stands

Thirty-three cells closed on evidence, across momentum and reversion, on four instruments,
at horizons from five minutes to overnight, over eight to sixteen years.

The best result found anywhere: **$3.90 gross against a $3.70 round turn, at p = 0.477.**

Everything measured in ES intraday is either negative before cost, or positive by an amount
smaller than the spread:

| structure | gross edge | round trip |
|---|---|---|
| breakout, London into NY | +$0.01 | $3.70 |
| breakout, NY opening range | +$0.01 | $3.70 |
| breakout, Asia into London | **-$1.39** | $3.70 |
| VWAP reversion, 2 sigma | **-$1.59** | $3.70 |
| VWAP reversion, HTF-filtered | +$1.82 | $3.70 |
| strength-filtered breakout | +$3.90 | $3.70 |
| overnight drift | +$1.88 | $3.70 |

That is the shape of an efficiently-priced market at this horizon, measured seven different
ways.
