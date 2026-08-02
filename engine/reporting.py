"""
Performance reporting.

Net results are primary; gross is shown only alongside them. No blended statistic is
reported without the components that produced it, and every breakdown carries its own
sample size so a 6-trade bucket can never be mistaken for evidence.

Confidence intervals come from a DAY-BLOCK bootstrap rather than a per-trade bootstrap.
Intraday trades within a session are not independent: they share the day's regime, its
news, and its volatility. Resampling individual trades would understate uncertainty,
often by a lot.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Metrics:
    trades: int
    win_rate: float
    avg_win_usd: float
    avg_loss_usd: float
    payoff_ratio: float
    expectancy_usd: float
    expectancy_r: float
    profit_factor: float
    gross_usd: float
    net_usd: float
    total_costs_usd: float
    max_drawdown_usd: float
    max_drawdown_r: float
    sharpe_daily: float
    sortino_daily: float
    worst_day_usd: float
    best_day_usd: float
    max_losing_streak: int
    avg_bars_held: float
    trades_per_day: float
    no_trade_day_pct: float
    profit_concentration_top5: float
    cvar_95_usd: float
    mean_risk_deviation: float

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _empty() -> Metrics:
    """Zeroed metrics. Built by keyword so adding a field can never silently misalign."""
    zeros = {name: (0 if f.type in ("int", int) else 0.0)
             for name, f in Metrics.__dataclass_fields__.items()}
    return Metrics(**zeros)


def compute_metrics(trades: pd.DataFrame, sessions_in_sample: int | None = None) -> Metrics:
    if trades is None or trades.empty:
        return _empty()

    net = trades["net_usd"].to_numpy(dtype=float)
    wins, losses = net[net > 0], net[net < 0]

    equity = np.cumsum(net)
    peak = np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:]
    dd = equity - peak
    max_dd = float(-dd.min()) if len(dd) else 0.0

    by_day = trades.groupby("session_date")["net_usd"].sum()
    traded_days = len(by_day)
    total_days = sessions_in_sample or traded_days

    daily = by_day.to_numpy(dtype=float)
    sharpe = float(daily.mean() / daily.std(ddof=1) * np.sqrt(252)) if len(daily) > 1 and daily.std(ddof=1) > 0 else 0.0
    downside = daily[daily < 0]
    sortino = (float(daily.mean() / downside.std(ddof=1) * np.sqrt(252))
               if len(downside) > 1 and downside.std(ddof=1) > 0 else 0.0)

    streak = best_streak = 0
    for v in net:
        streak = streak + 1 if v < 0 else 0
        best_streak = max(best_streak, streak)

    total_profit = float(net[net > 0].sum())
    top5 = float(np.sort(net)[::-1][:5].sum())
    concentration = top5 / total_profit if total_profit > 0 else 0.0

    tail = np.sort(net)[:max(1, int(0.05 * len(net)))]
    risk = trades["risk_usd"].replace(0, np.nan)

    return Metrics(
        trades=len(trades),
        win_rate=float(len(wins) / len(net)),
        avg_win_usd=float(wins.mean()) if len(wins) else 0.0,
        avg_loss_usd=float(losses.mean()) if len(losses) else 0.0,
        payoff_ratio=float(wins.mean() / abs(losses.mean())) if len(wins) and len(losses) else 0.0,
        expectancy_usd=float(net.mean()),
        expectancy_r=float((trades["net_usd"] / risk).mean()),
        profit_factor=float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else float("inf"),
        gross_usd=float(trades["gross_usd"].sum()),
        net_usd=float(net.sum()),
        total_costs_usd=float(trades["commission_usd"].sum()),
        max_drawdown_usd=max_dd,
        max_drawdown_r=float(max_dd / trades["risk_usd"].mean()) if trades["risk_usd"].mean() else 0.0,
        sharpe_daily=sharpe,
        sortino_daily=sortino,
        worst_day_usd=float(by_day.min()),
        best_day_usd=float(by_day.max()),
        max_losing_streak=best_streak,
        avg_bars_held=float(trades["bars_held"].mean()),
        trades_per_day=float(len(trades) / total_days) if total_days else 0.0,
        no_trade_day_pct=float(1.0 - traded_days / total_days) if total_days else 0.0,
        profit_concentration_top5=concentration,
        cvar_95_usd=float(tail.mean()),
        mean_risk_deviation=float(trades["risk_deviation"].mean()),
    )


def block_bootstrap_ci(trades: pd.DataFrame, n: int = 2000, seed: int = 7,
                       alpha: float = 0.05) -> dict[str, tuple[float, float]]:
    """
    Day-block bootstrap over whole sessions.

    Resampling days rather than trades preserves within-day dependence, which is exactly
    the dependence that makes a naive per-trade interval far too narrow.
    """
    if trades is None or trades.empty:
        return {}
    rng = np.random.default_rng(seed)
    by_day = [g["net_usd"].to_numpy(dtype=float)
              for _, g in trades.groupby("session_date", sort=True)]
    if len(by_day) < 3:
        return {}

    n_days = len(by_day)
    totals, expectancies = np.empty(n), np.empty(n)
    for i in range(n):
        idx = rng.integers(0, n_days, n_days)
        sample = np.concatenate([by_day[j] for j in idx])
        totals[i] = sample.sum()
        expectancies[i] = sample.mean()

    lo, hi = 100 * alpha / 2, 100 * (1 - alpha / 2)
    return {
        "net_usd": (float(np.percentile(totals, lo)), float(np.percentile(totals, hi))),
        "expectancy_usd": (float(np.percentile(expectancies, lo)),
                           float(np.percentile(expectancies, hi))),
    }


def concentration_test(trades: pd.DataFrame) -> dict[str, float]:
    """Net P&L after removing the best N trades and the best N days."""
    if trades is None or trades.empty:
        return {}
    net = trades["net_usd"].to_numpy(dtype=float)
    by_day = trades.groupby("session_date")["net_usd"].sum().to_numpy(dtype=float)
    out = {"net_usd": float(net.sum())}
    for k in (1, 3, 5):
        out[f"net_excl_top{k}_trades"] = float(np.sort(net)[::-1][k:].sum())
        if len(by_day) > k:
            out[f"net_excl_top{k}_days"] = float(np.sort(by_day)[::-1][k:].sum())
    return out


def breakdown(trades: pd.DataFrame, by: str) -> pd.DataFrame:
    """Per-bucket metrics with sample sizes attached, sorted by trade count."""
    if trades is None or trades.empty or by not in trades.columns:
        return pd.DataFrame()
    rows = []
    for key, g in trades.groupby(by, sort=True):
        m = compute_metrics(g)
        rows.append({by: key, "trades": m.trades, "win_rate": m.win_rate,
                     "expectancy_usd": m.expectancy_usd, "net_usd": m.net_usd,
                     "profit_factor": m.profit_factor,
                     "max_drawdown_usd": m.max_drawdown_usd})
    return pd.DataFrame(rows).sort_values("trades", ascending=False)


def format_report(metrics: Metrics, title: str, ci: dict | None = None,
                  min_trades: int = 200) -> str:
    """Human-readable summary. Always states whether the sample clears the gate."""
    m = metrics
    lines = [
        f"=== {title} ===",
        f"  trades              {m.trades:>12,}",
        f"  win rate            {m.win_rate:>12.1%}",
        f"  avg win / avg loss  {m.avg_win_usd:>12,.2f} / {m.avg_loss_usd:,.2f}",
        f"  payoff ratio        {m.payoff_ratio:>12.2f}",
        f"  expectancy USD      {m.expectancy_usd:>12,.2f}",
        f"  expectancy R        {m.expectancy_r:>12.3f}",
        f"  profit factor       {m.profit_factor:>12.2f}",
        f"  gross / net USD     {m.gross_usd:>12,.2f} / {m.net_usd:,.2f}",
        f"  commissions USD     {m.total_costs_usd:>12,.2f}",
        f"  max drawdown USD    {m.max_drawdown_usd:>12,.2f}",
        f"  sharpe (daily,ann)  {m.sharpe_daily:>12.2f}",
        f"  sortino             {m.sortino_daily:>12.2f}",
        f"  worst / best day    {m.worst_day_usd:>12,.2f} / {m.best_day_usd:,.2f}",
        f"  max losing streak   {m.max_losing_streak:>12}",
        f"  trades per day      {m.trades_per_day:>12.2f}",
        f"  no-trade days       {m.no_trade_day_pct:>12.1%}",
        f"  top-5 concentration {m.profit_concentration_top5:>12.1%}",
        f"  CVaR 95 USD         {m.cvar_95_usd:>12,.2f}",
        f"  mean risk deviation {m.mean_risk_deviation:>12.1%}   (integer rounding vs target)",
    ]
    if ci:
        for k, (lo, hi) in ci.items():
            lines.append(f"  95% CI {k:<13}[{lo:>10,.2f}, {hi:>10,.2f}]")
    if m.trades < min_trades:
        lines.append(f"  ** SAMPLE BELOW GATE: {m.trades} < {min_trades} trades. "
                     f"Not evidence. **")
    return "\n".join(lines)
