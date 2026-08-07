# Edge Budget: what the account requires, and why no lever reaches it

**Run date:** 2026-08-06
**Tools:** `edge_budget.py`, `limit_entry.py`
**Data:** development plus validation, 619 sessions, MES via ES. Quote work on MES BID/ASK.
**Ledger:** runs registered before execution; predictions checked below.
**Lockbox:** **UNTOUCHED.**

---

## The question three proposals were really asking

Size up to finish faster. Fewer larger trades. More smaller trades. All three are the same
move, and it cannot work for one reason:

> **Position size multiplies the edge and the noise by the same number, so the per-session
> ratio `mu/sigma` is invariant to size.**

| size | mu | sigma | mu/sigma | sessions to +$3,000 |
|---:|---:|---:|---:|---:|
| 1 | 6.30 | 124 | **0.0508** | 476 |
| 3 | 18.90 | 372 | **0.0508** | 159 |
| 12 | 75.60 | 1,488 | **0.0508** | 40 |

Size trades speed against P(pass) and touches nothing else. That is why the cost sweep
showed six contracts resolving in three weeks at a 39% pass rate: it is the same edge,
observed for less time.

**Only three things move the ratio: cost, variance, and instrument.**

---

## What the account demands

| | measured |
|---|---:|
| gross edge | $11.25/session |
| round trip | $4.95, **44% of gross** |
| net edge | $6.30/session |
| session sd | $123.53 |
| **per-session Sharpe** | **0.0510** (annual 0.81) |
| target | 24.3 sd of gain |
| buffer | 16.2 sd, **and it trails** |

**Sharpe required**, simulated under the real rules with the actual return distribution
rescaled to each level so the fat tail and clustering survive:

| P(pass) | 6mo | 12mo | 24mo |
|---:|---:|---:|---:|
| 60% | 0.200 | 0.100 | 0.075 |
| 75% | **0.300** | 0.150 | 0.075 |

Passing 75% of the time inside six months needs **six times** the measured edge.

---

## Every lever, priced

| lever | Sharpe | annual | change | reaches |
|---|---:|---:|---:|---|
| measured now | 0.0510 | 0.81 | | nothing |
| cut session sd by 20% | 0.0637 | 1.01 | +25% | nothing |
| limit entry, save 1 tick/side | 0.0712 | 1.13 | +40% | nothing |
| limit entry, save 2 ticks/side | 0.0915 | 1.45 | +79% | 75% in 24 months |

The whole table rested on one assumption: that passive entry can save the spread.

---

## The cost lever is not merely fictional. It is negative.

Measured on MES BID/ASK, a resting buy limit at the 18:00 ET Globex open:

| offset | wait | saving | **adverse selection** | **net** | vs the $6.30 net edge |
|---:|---:|---:|---:|---:|---:|
| 1 tick | 5 min | +1.25 | **-13.00** | **-11.75** | -1.9x |
| 1 tick | 60 min | +1.25 | -6.95 | -5.70 | -0.9x |
| 2 ticks | 5 min | +2.50 | **-18.99** | **-16.49** | -2.6x |
| 2 ticks | 60 min | +2.50 | -8.99 | -6.49 | -1.0x |

**Adverse selection runs five to eight times the spread it saves.** The best case still
nets -$6.49 a session against a total net edge of $6.30. Passive entry does not fail to
help; it removes the entire strategy and a little more.

The mechanism is not subtle. At a 1-tick offset and a 5-minute wait, 82% of sessions fill
at -$13.00 against the average, which means the 18% that did **not** fill returned
**+$59** against it. A session that never ticks down in its first minutes is a session
that is going up. Resting a bid selects almost perfectly for the ones going down.

**Prediction check.** Registered beforehand: *"the selection term cancels most of the
saving, the net is under half a tick, and the cost lever is therefore largely fictional."*
Direction right, magnitude badly wrong. I expected roughly zero and measured roughly minus
one entire edge.

---

## An observation I am recording and not chasing

Sessions that did not fill a passive bid in their first five minutes returned about
**+$59 above average**, on 18% of sessions.

That is a large conditional effect and it is causal in form: the first five minutes are
observable before the rest of the session. It is also, and decisively:

- **41 sessions** on the 11-month MES sample, found while measuring something else;
- **partly mechanical**, since a session that ends far above average is unlikely to have
  ticked down early, which makes the conditioning and the outcome share their cause;
- exactly the shape of thing the forward-return and barrier screens were built to test, and
  both of those found nothing across 460 and 270 cells with family-wise nulls.

Chasing it would mean building a fifth leg from a post-hoc observation on 41 sessions, and
testing it on data that is either already spent or is the single-use lockbox. Recorded so
it is not lost, not pursued.

---

## Where this leaves the account

| lever | verdict |
|---|---|
| Position size | Cannot change Sharpe. Arithmetic, not evidence. |
| Cost | The only available reduction costs 5-8x what it saves. **Closed.** |
| Variance | Worth +25%. Not close to enough. |
| Instrument | **Untested.** Needs data we do not have. |

Three of the four are closed. What remains is the one that changes the denominator rather
than the numerator: **an instrument whose session risk is smaller relative to a fixed
$2,000 buffer**, or a buffer that is larger relative to MES.

Micro Dow (MYM) at $0.50 a point is the only genuinely smaller equity-index micro. Whether
its edge-to-cost ratio survives the smaller point value is an empirical question and needs
its own data.

**The honest summary of the whole exercise:** the measured overnight edge is about 0.05
Sharpe a session. A $50,000 Combine asks for 24 standard deviations of gain without ever
surrendering 16 from a peak. Those two numbers are what they are, no entry rule changes
either, and the levers that could have closed the gap have now each been measured and
found insufficient or actively harmful.
