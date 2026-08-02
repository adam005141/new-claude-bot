# MES / MNQ Intraday System: Implementation-Grade Specification

**Document version:** 1.0
**Date:** 2026-07-31
**Status:** SPECIFICATION ONLY. No code has been written. No backtest has been run.
**Prerequisite reading:** `EVIDENCE_STATUS.md`

> **Nothing in this document is a result.** Every performance-related value is labeled
> `AWAITING-VALIDATION` with evidence level `unsupported`. Where a number appears, it is
> either a contract specification, a firm rule, an arithmetic consequence of those, or an
> explicitly labeled prior estimate. There are no measured statistics because no
> measurement has been made.

**Label key:** `FIXED-MARKET` (verified exchange spec) · `FIXED-FIRM` (verified firm rule)
· `DESIGN` (chosen constraint) · `EST-DEV` (estimated from development data, none exists)
· `AWAITING-VALIDATION` (unknowable until backtested) · `UNRESOLVED` (needs owner decision)

---

## 1. Executive conclusion

**Should MES, MNQ, both, or neither proceed? Currently unanswerable, and that is the
honest answer.**

The question is not close. Deciding it requires a backtest, a backtest requires data, and
the data available in this environment supports roughly 45 trades from a single contract
in a single volatility regime. That is not evidence about anything.

What this document therefore delivers is a falsifiable design: exact rules, exact
parameters, exact acceptance gates, and a validation protocol strict enough that it can
return "neither instrument has an edge, stop the project." That outcome is a success
condition of the design, not a failure of it.

**Recommended scope, per the owner's Step 0 answer:** build one shared framework with
independent MES and MNQ configurations, evaluate each instrument on its own merits, and
additionally evaluate the combined portfolio. Three verdicts are reported separately and
none is allowed to hide the others.

**Prior belief, stated so it can be held against me:** most published intraday
VWAP and opening-range rules on micro index futures do not survive honest cost modeling
and multiple-testing correction. Micro contracts pay the same spread in ticks as their
parent while capturing one tenth the dollar move, so cost as a fraction of expectancy is
roughly an order of magnitude worse than on ES or NQ. My prior is that most candidates in
section 8 will fail. Evidence level: `weak` (mechanism reasoning plus general literature,
not a measurement on this data). The design is built to detect that failure rather than to
argue around it.

---

## 2. Edge thesis and competing explanations

Each candidate family carries a stated economic mechanism and, mandatorily, the competing
explanation that would produce the same backtest without any real edge.

| Family | Proposed mechanism | Competing explanation that must be ruled out |
|---|---|---|
| A. VWAP band reversion | Institutional execution algorithms benchmark to VWAP, creating transient liquidity provision that pushes price back toward it | Simple short-horizon mean reversion present in any noisy series; also survivorship of the specific band multiple chosen from many tried |
| B. Opening range breakout | Overnight information accumulates and is repriced in the opening auction; the first range establishes a reference that triggers stop and momentum flow | Volatility clustering alone will produce apparent breakout profits in trending samples; result is highly sensitive to the range length, which is a free parameter |
| C. Overnight range breakout | Same repricing logic anchored to the lower-liquidity overnight session | Overnight ranges are narrow, so breakouts are frequent and cost-dominated; apparent edge is often a drift artifact |
| D. Time-of-day drift | Persistent intraday seasonality in index futures | Almost certainly not exploitable after cost; included as a *baseline to beat*, not a candidate |

**Ruling these out is the job of section 20's null tests, not of argument.** A family that
cannot beat its own competing explanation is rejected regardless of its backtest.

---

## 3. Instruments, contract handling, and roll rules

Full detail in `config/instruments.yaml`. Summary:

| | MES | MNQ | ES | NQ |
|---|---:|---:|---:|---:|
| Role | **Execution** | **Execution** | Reference only | Reference only |
| Point value | $5.00 | $2.00 | $50.00 | $20.00 |
| Tick | 0.25 pt | 0.25 pt | 0.25 pt | 0.25 pt |
| Tick value | $1.25 | $0.50 | $12.50 | $5.00 |
| Orderable | Yes | Yes | **No** | **No** |

`FIXED-MARKET`, evidence level `moderate` (see source warning in the config).

**Reference feeds cannot produce orders.** This is enforced structurally, not by
convention: reference adapters expose a read-only feature interface with no order method,
and the router additionally rejects any intent whose symbol is not in
`execution_instruments`. A signal computed on ES produces an order on MES at MES's own
price, never a transferred parent fill price.

**Reference-feed guards** (`DESIGN`): maximum permitted staleness 2 seconds relative to
the micro's own timestamp; out-of-order, duplicate, or missing reference bars cause the
dependent signal to be suppressed, not estimated. **Fail closed:** if a required reference
feed is unavailable, the strategy does not trade that signal. It does not fall back to a
partially evaluated version.

**Reference feeds are opt-in and must earn their place.** Section 18 requires an ablation
comparing micro-only against parent-assisted features on the same untouched test period.
The parent feed is retained only if it improves untouched net results after accounting for
added complexity, data cost, and the operational failure mode of a second feed. Default is
**off**.

**Roll:** volume-crossover on trailing one-session volume, evaluated at session close using
only data available at that close, effective at the *start* of the following session, never
intrabar. New entries stop 5 sessions before expiry. Open positions are closed in the
expiring contract and are never migrated. Back-adjusted prices are forbidden from feeding
any executable level. Roll weeks are tagged so all results can be reported with and
without them.

---

## 4. Data schema and quality requirements

**Required schema** (per instrument, per dated contract):

```
timestamp_utc      : datetime64[ns, UTC]   monotonic, unique, bar-OPEN convention
contract_id        : str                   the exact dated contract
open, high, low, close : float64           unadjusted traded prices
volume             : int64                 >= 0
bid, ask           : float64               optional; enables honest spread modeling
```

**Validation gates run on ingest.** Any failure quarantines the affected session rather
than silently repairing it:

1. Timestamp monotonic and unique; no duplicates.
2. `low <= min(open, close) <= max(open, close) <= high`.
3. Bar count per session within tolerance of the expected count for that session type.
4. Gap detection: any missing interval longer than `max_gap_bars` (default 3) flags the
   session.
5. Volume sanity: a session whose volume is under `min_session_volume_pct` (default 20%)
   of the trailing 20-session median is flagged as non-representative, which is how a
   contract that is not yet the front month gets excluded.
6. Front-month attribution check: the contract's volume must actually dominate its stated
   active window. This directly catches the failure mode observed in `EVIDENCE_STATUS.md`,
   where the Sep-2026 contract showed zero volume for months before becoming front month.
7. Price continuity: an inter-bar jump exceeding `max_jump_atr` (default 10 ATR) flags for
   review rather than being treated as a tradable move.

**Provenance is recorded per dataset**: source, retrieval timestamp, contract ids, bar
size, adjustment status (must be `unadjusted` for executable data), and a content hash.
Every backtest run records the dataset hash it consumed.

---

## 5. Session calendar and clock logic

`DESIGN`. All boundaries are **named parameters**, defined in `America/New_York`, resolved
through a DST-aware library (`zoneinfo`). **Eastern Time is never implemented as a fixed
UTC offset.** Exchange timestamps are additionally retained in UTC.

| Session id | Default window (ET) | Default enabled |
|---|---|---|
| `ASIA` | 18:00 to 03:00 | No |
| `LONDON` | 03:00 to 07:00 | No |
| `EU_NY_OVERLAP` | 07:00 to 09:30 | No |
| `NY_PREMARKET` | 08:00 to 09:30 | No |
| `RTH_OPEN` | 09:30 to 10:30 | **Yes** |
| `RTH_MIDDAY` | 10:30 to 14:00 | **Yes** |
| `RTH_AFTERNOON` | 14:00 to 15:50 | **Yes** |
| `RTH_CLOSE` | 15:50 to 16:00 | No (flatten only) |
| `MAINTENANCE` | 17:00 to 18:00 | No (never tradable) |

Defaults reflect liquidity, not a belief that these windows are profitable. **Every
session is a hypothesis and may be disabled by evidence. No trade is a valid output.**

**Distinct clock concepts, deliberately not conflated:** the equity cash close (16:00 ET),
the futures settlement time, the CME maintenance break (17:00 to 18:00 ET), the firm's
required flat time (default 15:10 CT = 16:10 ET, `UNRESOLVED`), and the firm's daily-loss
reset (17:00 CT = 18:00 ET, `FIXED-FIRM`). These are five different parameters and are
never derived from one another.

Holiday and early-close calendar is loaded from an explicit exchange calendar file. An
unknown date fails closed to "do not trade."

---

## 6. Feature definitions

All features are computed on **completed bars only** and are available at the close of the
bar that produces them. A feature is never available on the bar it is computed from.

Let bar $i$ have typical price $TP_i = (H_i + L_i + C_i)/3$ and volume $V_i$.

**Session VWAP**, anchored at session start $s$:

$$\mathrm{VWAP}_t = \frac{\sum_{i=s}^{t} TP_i V_i}{\sum_{i=s}^{t} V_i}$$

**VWAP bands.** Volume-weighted population variance about the running VWAP:

$$\sigma_t^2 = \frac{\sum_{i=s}^{t} V_i (TP_i - \mathrm{VWAP}_t)^2}{\sum_{i=s}^{t} V_i},
\qquad \mathrm{Band}_t^{(k)} = \mathrm{VWAP}_t \pm k\,\sigma_t$$

This is the population form, not the sample form, and uses the *current* VWAP rather than
a per-bar historical VWAP. Both choices are stated because they are the two places where
implementations silently differ.

**Warm-up:** bands are undefined until `min_vwap_bars` (default 20) bars into the session.
No signal fires before then.

**ATR($n$)**, Wilder smoothing, default $n = 14$, computed on the decision timeframe.

**Relative volume:** $\mathrm{RVOL}_t = \dfrac{\sum_{i=s}^{t} V_i}{\mathrm{median}\left(\sum_{i=s}^{t'} V_i\right)}$
over the same elapsed-time point in the prior `rvol_lookback` (default 20) sessions. Uses
prior sessions only, so it is causal.

**Realized volatility:** standard deviation of log returns over the last `rv_window`
(default 30) bars.

**VWAP slope, ATR-normalized:**
$\mathrm{slope}_t = \dfrac{\mathrm{VWAP}_t - \mathrm{VWAP}_{t-k}}{k \cdot \mathrm{ATR}_t}$,
default $k = 10$.

**Opening range:** high and low of the first `or_minutes` (default 30) after the RTH open.
Available only *after* that window closes.

**Overnight range:** high and low from 18:00 ET to 09:30 ET.

**Scheduled news state:** a binary flag from a pre-loaded economic calendar, known before
the session. `news_blackout_minutes` (default ±15) around high-impact releases.

**Explicitly unavailable in this environment:** cumulative delta, bid/ask imbalance, and
any order-book feature. The feed carries last-trade OHLCV only. These features are
specified as `UNRESOLVED` pending a data source that actually contains the fields, and any
implementation must refuse to synthesize them from trade prices.

---

## 7. Regime classification

Causal, computed from information available at decision time only. Volatility percentiles
use a trailing distribution that ends at the **prior session close**, never including the
current session.

```
rv_pct   = percentile_rank(RV_t, RV over trailing 60 sessions up to PRIOR close)
slope    = |VWAP_slope_t|

REGIME = TREND    if slope >= theta_trend AND RVOL_t >= theta_rvol
       = RANGE    if slope <  theta_range AND rv_pct in [rv_lo, rv_hi]
       = NEUTRAL  otherwise        -> NEUTRAL never trades
```

Defaults (`DESIGN`, `AWAITING-VALIDATION`): `theta_trend` 0.35, `theta_range` 0.15,
`theta_rvol` 1.10, `rv_lo` 0.20, `rv_hi` 0.80.

The gap between `theta_range` and `theta_trend` is deliberate. It creates a NEUTRAL
no-trade band rather than forcing every bar into a regime, which prevents the classifier
from manufacturing trades at the boundary.

**Each regime route reports its own cost-adjusted performance, sample size, and
uncertainty interval. A losing leg is never permitted to hide inside a profitable
combined statistic.** A leg that is not independently justified is deleted, not retained
because the blend looks acceptable.

---

## 8. Entry rules

All conditions must hold simultaneously on a completed bar. Entry is submitted for the
**next** bar. Every threshold below is `DESIGN` and `AWAITING-VALIDATION`.

### Leg A: VWAP band reversion (RANGE regime only)

```
LONG:
  REGIME == RANGE
  AND close[t-1] <  VWAP[t-1] - k_entry * sigma[t-1]
  AND close[t]   >= VWAP[t]   - k_entry * sigma[t]      # rejection, not just touch
  AND bars_since_session_start >= min_vwap_bars
  AND RVOL[t] >= rvol_min
  AND NOT news_blackout[t]
  AND session in enabled_sessions
  AND expected_move_floor_satisfied(...)                # section 13.4, hard gate

SHORT: mirror with + k_entry and close[t] <= VWAP[t] + k_entry * sigma[t]
```

Default `k_entry` 2.0, `rvol_min` 0.80.

The two-bar structure (excursion then reclaim) is what distinguishes this from a pure
touch rule. A touch rule enters into continuing momentum; the reclaim requires the market
to demonstrate rejection first. This costs entry price and is expected to reduce win rate
while improving payoff. Which effect dominates is `AWAITING-VALIDATION`.

### Leg B: Opening range breakout (TREND or NEUTRAL, not RANGE)

```
LONG:
  now > opening_range_end
  AND REGIME != RANGE
  AND close[t] > OR_high + b_buffer * ATR[t]
  AND RVOL[t] >= rvol_breakout
  AND OR_width <= or_max_width_atr * ATR[t]      # reject already-exhausted ranges
  AND NOT news_blackout[t]
  AND expected_move_floor_satisfied(...)
  AND first_entry_of_session_for_this_leg        # no re-entry by default

SHORT: mirror on OR_low
```

Defaults: `b_buffer` 0.25, `rvol_breakout` 1.20, `or_max_width_atr` 2.5.

### Leg C: Overnight range breakout

Structurally identical to Leg B, anchored to the overnight range, evaluated in the first
`on_break_window` (default 60) minutes after the RTH open. **Prior: this is the weakest
of the three**, because overnight ranges are narrow relative to cost. Specified so it can
be tested and rejected on evidence rather than dismissed on assertion.

### Instrument differences

MES and MNQ get **independent parameter sets**. They are not assumed to share thresholds.
MNQ's higher volatility means an identical ATR multiple implies a materially different
dollar risk, and its cost-per-point profile differs (section 13.4). Forcing shared
parameters would be a modeling convenience with no justification.

---

## 9. Exits, stops, targets, time stops

**Protective stop, always submitted with entry** (`DESIGN`):

```
stop_distance = max(m_stop * ATR[t], min_stop_ticks * tick_size)
long_stop  = entry_price - stop_distance
short_stop = entry_price + stop_distance
```

Defaults `m_stop` 1.5, `min_stop_ticks` 8 (MES), 12 (MNQ). The floor prevents a
low-volatility regime from producing a stop so tight that cost and noise dominate.

**Targets.** Leg A targets the mean: `target = VWAP[t]` at fill time, recomputed but never
moved against the position. Legs B and C use a measured move:
`target = entry ± r_target * OR_width`, default `r_target` 1.0.

**Time stop:** exit at market after `max_bars_in_trade` (default 24 decision bars) if
neither stop nor target has been reached.

**Session exit:** all positions flat at `flat_time` (default 15:50 ET), and unconditionally
before the firm's required flat time.

### 9.1 One-contract exit path (mandatory)

Position sizing (section 10) frequently produces **one contract**. Partial exits and
runners require at least two. The single-contract path is therefore the *primary* exit
specification, and it is complete without any scale-out:

```
Exactly one of these terminates the trade:
  1. Protective stop hit
  2. Target hit
  3. Time stop expired
  4. Session/flat-time exit
  5. Risk-engine halt (section 12)
```

**Scale-outs are disabled by default and are forbidden from appearing in any backtest run
at a size that cannot execute them.** The engine asserts `qty >= 2` before permitting a
partial-exit plan; the assertion failing is a bug, not a fallback. This single rule
eliminates the most common way micro-futures backtests overstate results.

**Trailing stop** is available only when `qty >= 2` and is off by default.

---

## 10. Position sizing

### 10.1 Risk budget derivation

Sizing derives from the **usable loss buffer**, never from the $50,000 headline balance.

| Quantity | Value | Basis |
|---|---:|---|
| Headline balance | $50,000 | Not risk capital. Never used in sizing. |
| MLL buffer | $2,000 | `FIXED-FIRM` |
| Usable MLL after 25% reserve | **$1,500** | `DESIGN` |
| Firm daily loss limit | **None** | `FIXED-FIRM`, see below |
| Self-imposed daily stop | **$300** | `DESIGN`, owner may disable |

**Topstep enforces no daily loss limit.** It removed the default DLL on TopstepX Combines
effective 2024-08-25, replacing it with an optional self-set "Personal DLL" that acts as a
timeout and is not a rule violation. The owner has elected not to enable it.

> **Platform caveat, `UNRESOLVED`.** The removal reportedly applies only to the TopstepX
> platform. NinjaTrader, Tradovate, Quantower, and TradingView are reported to still
> enforce a DLL objective on Combine accounts. If orders route through any of those, a
> firm-enforced DLL may still apply. See section 22 decision 10.

**Consequence: the $2,000 MLL is the only firm loss constraint, so there is no circuit
breaker between one bad session and evaluation failure.** A single day can consume the
entire buffer. This makes the self-imposed daily stop a risk recommendation rather than a
redundancy, and it is why the engine implements one by default.

**Per-trade risk target `R_target` = $100** (`DESIGN`, `AWAITING-VALIDATION`). Against the
usable MLL this is **15 full stops**; against the default $300 self-imposed daily stop it
is **3 per session**, so the buffer spans at least 5 independent losing days.

If the owner disables the self-imposed stop, sizing is unchanged but the engine will permit
a single session to consume the full usable buffer. That is a legitimate choice and is
logged as such, but it makes the losing-streak validation in section 10.4 strictly more
important, not less.

### 10.2 Stop distance to integer contracts

$$\mathrm{qty} = \left\lfloor \frac{R_{target}}{\text{stop\_distance} \times \text{point\_value}} \right\rfloor$$

**Rounding is always down.** Rounding up breaches the risk target by construction.

The table the design brief requires, presented parametrically because **the actual
stop-distance distribution is `AWAITING-VALIDATION`** and inventing one would be exactly
the "convenient stop inserted to make a contract look viable" that must be avoided:

**MES** (point value $5.00, `R_target` $100):

| Stop (pts) | $/contract | Stressed $/contract (+ $4.95 adverse cost) | % usable MLL | Max qty | Viable? |
|---:|---:|---:|---:|---:|---|
| 5 | $25 | $29.95 | 2.0% | 4 | Yes |
| 8 | $40 | $44.95 | 3.0% | 2 | Yes |
| 10 | $50 | $54.95 | 3.7% | 2 | Yes |
| 15 | $75 | $79.95 | 5.3% | 1 | Yes |
| 20 | $100 | $104.95 | 7.0% | 1 | Marginal |
| 30 | $150 | $154.95 | 10.3% | 0 | **No trade** |

**MNQ** (point value $2.00, `R_target` $100):

| Stop (pts) | $/contract | Stressed $/contract (+ $2.70 adverse cost) | % usable MLL | Max qty | Viable? |
|---:|---:|---:|---:|---:|---|
| 20 | $40 | $42.70 | 2.8% | 2 | Yes |
| 30 | $60 | $62.70 | 4.2% | 1 | Yes |
| 40 | $80 | $82.70 | 5.5% | 1 | Yes |
| 50 | $100 | $102.70 | 6.8% | 1 | Marginal |
| 60 | $120 | $122.70 | 8.2% | 0 | **No trade** |

**ES and NQ: max quantity 0. Reference only. Not authorized.**

### 10.3 Operational consequences of micro sizing

**1. Granularity.** In the viable band, quantity is 1 to 4 contracts. At `qty = 1` with a
15-point MES stop, realized risk is $75 against a $100 target, a **25% shortfall**. At a
20-point stop it is $100, on target. Realized risk therefore varies roughly ±25% around
target purely from rounding, with no relationship to signal quality.

**Consequence: volatility targeting is close to meaningless at this size.** It is an
attempt to control a quantity that integer rounding controls far more coarsely.
Recommendation (`DESIGN`, `UNRESOLVED` pending owner decision): use **fixed 1 contract**
per instrument, and treat sizing as a solved constant rather than a tunable. This is more
honest than a volatility-targeting layer whose output is dominated by `floor()`.

**2. Wide stops force no-trade.** At MES stops beyond ~20 points or MNQ beyond ~50, one
contract already exceeds `R_target`, so rounding down gives zero and the setup is skipped.
This is correct behavior and must be logged as a *rejected opportunity*, so the reported
opportunity count is not silently reduced.

**3. Cost does not scale down.** Commission and spread are per contract and do not shrink
with the multiplier. A micro pays the same tick spread as its parent while capturing one
tenth the dollar move. **This is the single most likely reason a candidate fails**, and it
is why section 13.4's expected-move floor is a hard gate rather than a diagnostic.

### 10.4 Survival check

Usable MLL of $1,500 absorbs **15 full $100 losses**; usable DLL absorbs **8 per day**.

Whether 15 is sufficient is `AWAITING-VALIDATION` and requires: the empirical maximum
losing streak, a block-bootstrap distribution of streak lengths, correlated MES/MNQ
same-day losses, gap losses through the stop, and worst-case execution stress.

**Predeclared rejection rule:** if the 95th percentile bootstrapped losing streak exceeds
**12** consecutive full stops, the sizing is rejected and `R_target` is reduced before any
other change is considered. This threshold is fixed now, before any data is seen, so it
cannot be relaxed later to accommodate a result.

---

## 11. Portfolio coordination

MES and MNQ are both long US equity beta. **Two positions are not two independent bets.**

- **Simultaneous positions:** permitted only when portfolio heat allows (`DESIGN`).
- **Correlation measurement:** rolling 20-session correlation of daily returns, computed
  through the **prior** session close only. No lookahead.
- **Portfolio max open risk:** `max_portfolio_heat` = $150 (`DESIGN`), i.e. 10% of usable
  MLL. This is less than 2 × `R_target`, so two full-size positions cannot both be open.
- **Same-direction rule:** if rolling correlation ≥ `corr_threshold` (default 0.75) and
  signals agree in direction, the pair is treated as **one** position for heat purposes.
  Only the higher-expected-net-edge instrument is taken.
- **Conflict rule:** opposing signals on correlated instruments indicate the regime
  classifier disagrees with itself. Both are **suppressed**. This is deliberately
  conservative and will forgo some genuine spread opportunities.
- **Priority:** when both qualify and budget permits one, rank by expected net edge
  (expectancy per trade in R, from the *development* set only, frozen before validation).
  Ties break to MES as the lower-dollar-volatility instrument.

**Comparisons are normalized by dollar risk and realized volatility, never by raw points
or contract counts.** Integer micro sizing is still enforced after normalization.

**Stress tests (mandatory):** overnight gap scenarios, simultaneous stop-outs on both
instruments, and correlation regime shift (correlation jumping to 0.95 in a stress event,
which is when diversification assumptions fail).

**Acceptance:** the combined portfolio is reported alongside MES-only and MNQ-only, and is
adopted **only** if it improves the predeclared objective on untouched data *without*
worse tail risk. A better Sharpe with a fatter left tail is a rejection, not a trade-off.

---

## 12. Risk state machines

### 12.1 Personal / research mode

States: `IDLE → ARMED → IN_POSITION → {FLAT, HALTED_DAY, HALTED_PERMANENT}`

Halt triggers: max daily loss, max portfolio heat, max entries per session
(`max_entries` default 4 per instrument), data staleness, connectivity loss, order
rejection, and position-reconciliation mismatch.

### 12.2 Prop mode

**Identical signal logic, frozen.** The prop layer sits strictly above it and only ever
*removes* permission. It never alters a signal, a threshold, or an exit.

```
ACTIVE
  ├─ equity <= MLL_floor + safety_margin      -> HALTED_PERMANENT (flatten immediately)
  ├─ daily_loss >= self_imposed_daily_stop    -> HALTED_DAY (flatten, resume 17:00 CT)
  │     ($300 default; DESIGN, not a firm rule; owner may disable)
  ├─ balance >= target_balance ($53,000)      -> HALTED_TARGET (flatten, stop trading)
  ├─ now >= required_flat_time                -> FLATTEN_ONLY
  └─ any risk/data/reconciliation fault       -> HALTED_DAY (fail closed)
```

The MLL branch is the only firm-enforced loss constraint. The daily branch is this
project's own choice and is clearly separated from firm rules in the config, so disabling
it can never be mistaken for relaxing a Topstep requirement.

`MLL_floor` ratchets on **end-of-day balance** only, never intraday, never downward, and
locks permanently at $50,000.

**Consistency guard** (`DESIGN`, because the firm rule is only weakly verified): if
session realized profit reaches `consistency_day_cap` (default $1,400, just under the
inferred $1,500 limit), the engine moves to `FLATTEN_ONLY` for the session. This
deliberately forgoes profit to protect evaluation validity.

**Fail-closed principle:** the engine halts if account state, rule state, clock state,
market data, or position state is stale, missing, or self-contradictory. There is no
"assume it is fine and continue" path.

**Both modes are reported separately. Unclamped personal-mode performance is never used to
imply the prop version is viable.**

---

## 13. Order and fill model

### 13.1 Order types

Entries: limit at the signal bar's close, `entry_timeout_bars` (default 2) then cancelled.
Stops: stop-market, submitted immediately on fill. Exits: market.

### 13.2 Fill assumptions (backtest)

`DESIGN`, deliberately conservative:

- **Limit entries fill only if price trades strictly through the limit**, not merely to it.
  Without queue data this is the only defensible assumption; assuming a touch fills is the
  standard way backtests invent edge.
- **Stops fill at the worse of the stop price and the next bar's open**, modeling gaps.
- **Same-bar stop and target ambiguity resolves to the stop.** Always. When intrabar
  sequence is unknown, the adverse sequence is assumed. The alternative, assuming the
  target filled first, is the second standard way backtests invent edge.
- **Partial fills:** at 1 to 4 contracts on liquid micros, assumed not to occur during
  enabled sessions; the assumption is logged and flagged if any session's volume fails the
  section 4 liquidity gate.
- **Latency:** `latency_ms` default 250, applied as a delay between decision and order
  arrival.
- **Rejections:** modeled at `reject_rate` (default 0.1%), triggering the re-check path.

### 13.3 Cost model

**Prior estimates requiring verification against the actual broker and firm fee schedule.
These are not measured values.** Evidence level: `weak`.

| Scenario | MES round trip | MNQ round trip |
|---|---:|---:|
| Base (commission $1.20 + 2 ticks) | **$3.70** | **$2.20** |
| Adverse (+ 1 tick slippage) | **$4.95** | **$2.70** |
| Severe (3 ticks + 2 ticks slippage) | **$7.45** | **$3.70** |

Break-even move, base case: **MES 0.74 points (~3 ticks)**; **MNQ 1.10 points (~4.4 ticks)**.

Note that MNQ's cost is *lower in dollars* and its typical move is *larger in points*, so
MNQ may be materially more cost-efficient per unit of expected move despite its higher
volatility. This is a genuine hypothesis worth testing, not a conclusion.

### 13.4 Minimum expected-move floor (hard gate)

The controlling test is cost as a fraction of **gross expectancy per trade**, not as a
fraction of average win. A setup is permitted only if:

$$\text{expected\_move} \times \text{point\_value} \times P(\text{target}) \;\geq\;
\frac{\text{RT cost}_{adverse}}{1 - \mu_{min}}$$

where `mu_min` (default 0.25, `DESIGN`) is the required net-expectancy margin. Any setup
whose expected move cannot clear this floor **under the adverse cost scenario** is
rejected at signal time, before sizing.

Required reporting per instrument and session bucket: round-trip cost in dollars, in
ticks, as a percentage of average gross win, **as a percentage of gross expectancy per
trade** (controlling), and as a percentage of the expected favorable move captured.

**Fragility rule:** if the edge disappears when costs move from base to adverse, it is
labeled **fragile** and does not proceed, regardless of its base-case statistics.

---

## 14. Parameter table

| Parameter | Default | Unit | Range | Status |
|---|---:|---|---|---|
| `k_entry` | 2.0 | σ | 1.0–3.0 | Tunable, `AWAITING-VALIDATION` |
| `min_vwap_bars` | 20 | bars | 10–60 | Fixed `DESIGN` |
| `rvol_min` | 0.80 | ratio | 0.5–1.5 | Tunable |
| `rvol_breakout` | 1.20 | ratio | 1.0–2.0 | Tunable |
| `or_minutes` | 30 | min | 5–60 | Tunable (**high overfit risk**) |
| `b_buffer` | 0.25 | ATR | 0.0–1.0 | Tunable |
| `or_max_width_atr` | 2.5 | ATR | 1.0–5.0 | Tunable |
| `m_stop` | 1.5 | ATR | 0.75–3.0 | Tunable |
| `min_stop_ticks` (MES/MNQ) | 8 / 12 | ticks | 4–24 | Fixed `DESIGN` |
| `r_target` | 1.0 | ×OR width | 0.5–3.0 | Tunable |
| `max_bars_in_trade` | 24 | bars | 6–96 | Tunable |
| `theta_trend` | 0.35 | norm slope | 0.1–1.0 | Tunable |
| `theta_range` | 0.15 | norm slope | 0.0–0.5 | Tunable |
| `R_target` | 100 | USD | 50–200 | Fixed `DESIGN` |
| `max_portfolio_heat` | 150 | USD | 100–300 | Fixed `DESIGN` |
| `corr_threshold` | 0.75 | corr | 0.5–0.95 | Fixed `DESIGN` |
| `max_entries_per_session` | 3 | count/session | 1–6 | Tunable, raised from 1 for sample size |
| `reentry_cooldown_bars` | 3 | bars | 0–20 | Fixed `DESIGN` |
| `reentry_new_extreme_atr` | 0.5 | ATR | 0.0–3.0 | Fixed `DESIGN` |
| `or_max_width_norm` | 1.5 | ×random-walk baseline | 0.5–4.0 | Tunable (replaces `or_max_width_atr`) |
| `mu_min` | 0.25 | fraction | 0.1–0.5 | Fixed `DESIGN` |
| `latency_ms` | 250 | ms | 50–1000 | Fixed `DESIGN` |
| `flat_time` | 15:50 | ET | — | Fixed `DESIGN` |
| Session enable flags | see §5 | bool | — | Tunable |

**Tunable parameter count: 13.** Every one is a multiple-testing liability, and the total
search burden is counted in section 18, including variants tried and discarded.

---

## 15. Event processing order

Deterministic and identical in backtest and paper. When events share a timestamp, this
order is authoritative:

```
1. Advance clock; recompute session and DST-aware boundaries
2. Ingest bar; run quality gates (quarantine on failure)
3. Ingest reference feed; apply staleness check (suppress dependents on failure)
4. Reconcile positions and account state (halt on mismatch)
5. Process fills from orders resting since the prior bar
6. Apply exits in strict order: STOP -> TARGET -> TIME -> SESSION
7. Update features (completed bars only)
8. Classify regime
9. Evaluate risk state machine (may halt; halts preempt all entry logic)
10. Evaluate entry signals
11. Apply expected-move floor gate
12. Size positions (integer, round down)
13. Apply portfolio coordination
14. Submit orders with latency offset
15. Log decision, intent, and state
```

Step 6 preceding step 10 guarantees an exit is always processed before a new entry on the
same timestamp. Step 9 preceding step 10 guarantees a halt cannot be overridden by a
signal.

**No completed bar, future-confirmed swing, finalized session statistic, revised economic
value, or later-known news label may influence a decision timestamped earlier.** This is
enforced by property-based tests (section 18), not by review alone.

---

## 16. Canonical decision engine (pseudocode)

```python
def on_bar(bar, state, cfg):
    state.clock.advance(bar.timestamp_utc)
    session = classify_session(state.clock, cfg.sessions)      # DST-aware

    if not quality_gates(bar, state):
        return halt(state, "DATA_QUALITY")

    ref = state.reference.get(bar.timestamp_utc)
    ref_ok = ref is not None and ref.age <= cfg.max_ref_age

    if not reconcile(state.positions, state.broker_view):
        return halt(state, "RECONCILIATION")

    process_fills(state, bar)

    for pos in state.open_positions:                            # order is authoritative
        if hit_stop(pos, bar):    close(pos, adverse_price(pos, bar), "STOP");   continue
        if hit_target(pos, bar):  close(pos, pos.target,             "TARGET"); continue
        if pos.bars_held >= cfg.max_bars_in_trade: close(pos, bar.close, "TIME"); continue
        if state.clock.at_or_after(cfg.flat_time):  close(pos, bar.close, "SESSION")

    feats  = compute_features(state.history, cfg)               # completed bars only
    regime = classify_regime(feats, state.prior_session_stats, cfg)

    risk = state.risk.evaluate(state.account, state.clock, cfg.prop_rules)
    if risk.halted:
        flatten_all(state, reason=risk.reason)
        return                                                  # halt preempts entries

    if session not in cfg.enabled_sessions or regime == NEUTRAL:
        return

    for inst in cfg.execution_instruments:                      # MES, MNQ only
        sig = evaluate_entry(inst, feats, regime, session, cfg, ref if ref_ok else None)
        if sig is None:
            continue
        if not expected_move_floor_ok(sig, cfg.costs.adverse, cfg.mu_min):
            log_rejected_opportunity(sig, "MOVE_FLOOR"); continue

        stop_dist = max(cfg.m_stop * feats.atr, cfg.min_stop_ticks * inst.tick_size)
        qty = floor(cfg.R_target / (stop_dist * inst.point_value))   # ALWAYS round down
        if qty < 1:
            log_rejected_opportunity(sig, "SIZE_ZERO"); continue

        qty = portfolio_coordinator.adjust(inst, sig, qty, state, cfg)
        if qty < 1:
            log_rejected_opportunity(sig, "PORTFOLIO_HEAT"); continue

        assert inst.orderable, "reference instrument cannot be ordered"   # structural
        submit_bracket(inst, sig.side, qty, stop_dist, sig.target, cfg.latency_ms)
```

---

## 17. Failure behavior

| Failure | Response |
|---|---|
| Missing / stale / out-of-order bar | Quarantine session; no trading |
| Reference feed stale beyond `max_ref_age` | Suppress dependent signals; **do not substitute** |
| Broker disconnect | Halt; flatten if reconnection exceeds `max_disconnect_s` (default 30) |
| Order rejection | Retry once, then halt for the session |
| Position mismatch | Immediate halt; manual intervention required |
| Unknown calendar date | Fail closed to no-trade |
| Clock/DST inconsistency | Halt |
| Rule config missing or unparseable | Refuse to start |

Every path fails **closed**. There is no degraded-but-trading mode.

---

## 18. Validation and multiple-testing plan

### 18.1 Research registry (written before any search)

Records: candidate family, economic thesis, exact variants, parameter ranges, **planned
configuration count**, primary selection metric, minimum trade count, rejection criteria,
and the chronological split. The registry is committed *before* the first run and is not
edited afterward; revisions are appended as new versions.

### 18.2 Chronological splits

1. **Development** (earliest ~50%): construction and free exploration.
2. **Validation** (~30%): limited selection, configuration count capped in the registry.
3. **Lockbox** (latest ~20%): **used exactly once**, never reused after being seen.
4. **Walk-forward:** rolling windows spanning materially different volatility regimes.
5. **Prospective paper:** only after rule and code are frozen.

### 18.3 Selection-aware correction

Family-wise permutation testing across **all** configurations tried, including discarded
ones, plus deflated Sharpe accounting for the true trial count and the non-normality of
trade returns.

**Limitation, stated plainly:** these corrections assume the trial count is known. In
practice, informal exploration inflates the true count beyond what any ledger captures.
The correction is therefore a lower bound on the required hurdle, not an exact adjustment.
This is a reason for skepticism about a marginal result, not a reason to skip the
correction.

### 18.4 Required additional analyses

Day-block and week-block bootstrap confidence intervals · parameter stability and
neighboring-parameter checks (a narrow optimum is a rejection signal) · breakdowns by year,
quarter, session, direction, and volatility regime · best-trade and best-day concentration
· results after removing the top 1, 3, and 5 trades and days · worse-cost and delayed-entry
stress · roll-week, holiday, high-volatility, and low-liquidity stress · comparison against
section 20 baselines · feature and reference-feed ablation · **backtest-versus-paper
decision parity on identical replay data**.

### 18.5 Minimum sample, and the ceiling that constrains it

`min_trades_per_leg` = **200** on the development set, per instrument per leg (`DESIGN`).
A leg below this is not evaluated, it is discarded.

**The dataset imposes a hard ceiling that interacts with this gate.** With 231 sessions
obtained (2025-09-10 to 2026-07-31) and a once-per-session entry cap, the maximum possible
development sample is 115 trades per instrument, at 100% participation. The gate was
therefore *unreachable by construction*, not merely hard to reach.

Re-entry was enabled in response (`max_entries_per_session` = 3, fenced by
`reentry_cooldown_bars` and `reentry_new_extreme_atr`, so a whipsaw around the range edge
cannot be booked as a series of independent trades). This raises the ceiling:

| Entry cap | Ceiling / instrument | Development ceiling |
|---|---:|---:|
| 1 (once daily) | 231 | 115 |
| 3 (current) | 693 | 346 |

**Power, which is the honest framing.** Assuming a per-trade standard deviation of ~1.2R:

| Development n | Minimum detectable edge (95%, two-sided) |
|---:|---:|
| 78 | 0.266R |
| 115 | 0.219R |
| 346 | 0.126R |
| 692 (both instruments pooled) | 0.089R |

A plausible post-cost intraday edge is **0.02 to 0.10R**. Even at the re-entry ceiling the
detection threshold sits above that band, and multiple-testing correction raises it
further. Pooling MES and MNQ does not fully help, because the two are highly correlated
and therefore do not contribute independent observations.

**Consequence, stated plainly: this dataset can only detect a LARGE edge.** A small but
genuine edge is indistinguishable from noise here, and a positive development result is
more likely to be noise than signal. This is a property of the sample, not of the engine,
and no amount of care in the code changes it. It is the primary argument for acquiring
deeper history before drawing any conclusion.

### 18.6 Warning signs treated as failures, not successes

Unusually high in-sample Sharpe · suspiciously smooth equity curve · narrow parameter
optimum · a small cluster of trades driving most profit. Each triggers mandatory
investigation before any further work.

---

## 19. Performance reporting

**All tables below are empty because no backtest has been run. They are the required
output format, not results.**

Required separate tables: MES · MNQ · combined portfolio · each leg · long and short ·
each enabled session and regime · personal and prop modes · base, adverse, and severe costs.

| Metric | Value |
|---|---|
| Date range and exact contracts | `unknown until backtested` |
| Eligible opportunities / executed trades | `unknown until backtested` |
| Trades per day / % no-trade days | `unknown until backtested` |
| Win rate | `unknown until backtested` |
| Average win / average loss / payoff ratio | `unknown until backtested` |
| Expectancy per trade (USD, ticks, R) | `unknown until backtested` |
| Profit factor | `unknown until backtested` |
| Sharpe / Sortino (state calculation frequency) | `unknown until backtested` |
| Annualized return (only if defensible) | `unknown until backtested` |
| Max drawdown (USD, R, % usable risk capital) | `unknown until backtested` |
| Drawdown duration and recovery | `unknown until backtested` |
| Worst day / week / month / losing streak | `unknown until backtested` |
| Exposure and average holding time | `unknown until backtested` |
| Turnover and total modeled costs | `unknown until backtested` |
| Tail loss (CVaR 95/99) | `unknown until backtested` |
| Bootstrap confidence intervals | `unknown until backtested` |
| Profit concentration | `unknown until backtested` |
| Prop pass / fail / expiry rates with timing | `unknown until backtested` |

**No blended statistic is ever reported without its components.**

---

## 20. Benchmarks and null tests

Defined **before** any final result is examined:

1. **Time-matched random entry control.** Same eligibility windows, holding-period
   opportunities, exits, sizing, and costs. **≥1,000 repetitions** to form a distribution.
   A single seed is not a control.
2. **Entry ablation.** Permute or remove the entry signal, preserving exit and risk logic.
   Isolates whether value comes from entry or from the exit/risk scaffolding.
3. **Predeclared simple baseline.** Fixed opening-range breakout with default parameters,
   and a time-of-day rule.
4. **Passive index exposure**, normalized for exposure and risk, as **context only**.
   Buy-and-hold is explicitly *not* a pass/fail test for an intraday strategy with
   materially different overnight exposure.

**Acceptance:** a candidate must beat the relevant null *distribution* (not a point
estimate) on the instrument for which the edge is claimed, after multiple-testing
adjustment. A raw profit-factor threshold is never treated as proof. A candidate may
succeed on one instrument and fail on the other; that is a legitimate outcome.

---

## 21. Failure modes and conditions where the system must not trade

**Must not trade:** before VWAP warm-up · in NEUTRAL regime · during news blackout · during
the maintenance break · on quarantined sessions · when a required reference feed is stale ·
within 5 sessions of expiry in the expiring contract · when `qty` rounds to 0 · when the
expected-move floor fails · when any risk state machine is halted · when the calendar is
unknown · on early-close days unless explicitly enabled.

**Most likely reasons this system fails in live trading**, ranked:

1. **Cost dominance.** Micros pay parent-sized spreads for one tenth the dollar move. Most
   likely single cause of failure.
2. **Overfitting.** 13 tunable parameters across 3 legs and 2 instruments is a large
   search space relative to any realistic sample.
3. **Regime dependence.** Two years of data may contain only one genuine regime.
4. **Execution divergence.** Backtest limit-fill assumptions are optimistic even when
   conservative, because queue position is unobservable.
5. **Correlated MES/MNQ losses.** Correlation rises exactly when it hurts most.
6. **Rule misinterpretation.** The unresolved Topstep semantics in
   `config/topstep_50k_combine.v1.yaml` could each individually cause an unexpected breach.

---

## 22. Decisions requiring owner approval

| # | Decision | Recommendation |
|---|---|---|
| 1 | **Data source.** Nothing proceeds without it. | IBKR native TWS API, `DATA_SOURCING.md` §2 |
| 2 | **Fixed 1 contract vs volatility targeting** (§10.3) | Fixed 1 contract; rounding dominates targeting at this size |
| 3 | **Reference feeds ES/NQ**: test or skip | Default off; enable only if ablation justifies it |
| 4 | **Sessions to enable** beyond RTH | Start RTH only; extend on evidence |
| 5 | **Objective function** | Net expectancy per trade with a drawdown constraint, **not** prop pass probability |
| 6 | **`R_target` $100** | Accept pending streak validation (§10.4) |
| 7 | **Verify Topstep rules directly** | Required before any capital; 6 semantics unresolved |
| 8 | **Confirm automation is permitted** | Load-bearing, currently weak-source only |
| 9 | **Legs to build first** | A and B only; defer C as weakest |
| 10 | **Execution platform** (TopstepX vs Tradovate / NinjaTrader / Quantower / TradingView) | Determines whether a firm DLL applies at all; blocking for the risk engine |
| 11 | **Self-imposed daily stop $300** (§10.1) | Keep enabled; the MLL is otherwise the only circuit breaker |

### Why maximizing prop pass probability is the wrong objective

Pass probability is a **single-threshold, single-path** statistic. It is maximized by
strategies that take large concentrated risk early: reach $3,000 fast, then stop. Such a
strategy can have a high pass rate and negative long-run expectancy, because the metric
does not price the paths where it blows through the MLL, and it ignores everything after
the evaluation ends.

Optimizing it also directly conflicts with the consistency rule, which penalizes exactly
the outsized winning day that maximizes pass speed.

**The evaluation is a filter to pass, not an objective to optimize.** Build a system with
genuine positive net expectancy, then measure what the prop constraints cost it. The
recommended objective is net expectancy per trade subject to a drawdown constraint, with
pass probability **reported** as a diagnostic and never optimized against.

---

## Sources

Exchange specifications: [CME MES contract specs](https://www.cmegroup.com/markets/equities/sp/micro-e-mini-sandp-500.contractSpecs.html),
[Ironbeam MES](https://www.ironbeam.com/knowledge-base/micro-e-mini-sp-500-futures-mes-contract-specifications/),
[Ironbeam MNQ](https://www.ironbeam.com/knowledge-base/micro-e-mini-nasdaq-100-futures-mnq-contract-specifications/),
[MetroTrade MNQ](https://help.metrotrade.com/kb/micro-e-mini-nasdaq-100-futures-mnq-contract-specifications).

Firm rules: [Topstep Maximum Loss Limit](https://help.topstep.com/en/articles/8284204-what-is-the-maximum-loss-limit),
[Topstep Daily Loss Limit](https://help.topstep.com/en/articles/10490293-daily-loss-limit-in-the-trading-combine-and-express-funded-account),
[Topstep Trading Combine Parameters](https://help.topstep.com/en/articles/8284197-trading-combine-parameters),
[Topstep Consistency Rule discussion](https://www.quantvps.com/blog/topstep-consistency-rule).

Data: [TWS API historical limitations](https://interactivebrokers.github.io/tws-api/historical_limitations.html),
[FirstRate Data MNQ](https://firstratedata.com/i/futures/MNQ).

All accessed 2026-07-31. **Direct fetch of cmegroup.com, topstep.com, and
interactivebrokers.github.io returned HTTP 403 from this environment; these values come
from search-engine summaries of those pages and require human re-verification.**
