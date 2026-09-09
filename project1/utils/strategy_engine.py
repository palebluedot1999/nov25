"""
Strategy 1 backtesting engine: Baker Bros Top-10 Equal-Weight.

Architecture:
- Run simulation once via run_simulation() or scripts/run_backtest.py
- Results saved per-run to data/processed/backtest_runs/<run_id>/, summarized in docs/backtest_log.csv
- Dashboard reads CSVs at render time (no re-simulation on page load)

Strategy rules:
- Top 10 Baker Bros holdings by 13F portfolio weight
- $1,000/month new capital, split equally among active (non-frozen) positions
- Sell rules (after 3-month hold): hard stop -40%, or relative bleed -25% + XBI -15pp
- Freeze rules: down >=10% AND underperforming XBI (no new capital; can still sell)
- Filing refresh: dropped names frozen; new entrants added (replace worst frozen if full)
"""

from __future__ import annotations

import logging
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.csv_data import get_all_filings, load_holdings_by_date, PROCESSED_DATA_DIR
from utils.holdings_operations import get_forward_filled_prices

logger = logging.getLogger(__name__)

PRICES_FILE = PROCESSED_DATA_DIR / "prices.csv"
BACKTEST_RUNS_DIR = PROCESSED_DATA_DIR / "backtest_runs"
BACKTEST_LOG_CSV = PROJECT_ROOT / "docs" / "backtest_log.csv"
BACKTEST_LOG_COLUMNS = [
    "run_id", "strategy", "monthly_contribution", "max_positions", "min_hold_months",
    "trade_day", "hard_stop_return", "relative_bleed_return",
    "relative_bleed_xbi_underperformance", "freeze_return_threshold", "portfolio_id",
    "benchmark_ticker", "period_start", "period_end", "cumulative_invested", "ending_value",
    "portfolio_return", "xbi_return", "vs_xbi_pp", "active_positions", "frozen_positions",
    "sold_positions", "output_dir",
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StrategyConfig:
    """All configurable parameters for the Strategy 1 backtest."""
    monthly_contribution: float = 1000.0
    max_positions: int = 10
    min_hold_months: int = 3         # sell-eligibility only; freeze can happen anytime
    trade_day: int = 1               # Nth trading day of each month
    hard_stop_return: float = -0.40
    relative_bleed_return: float = -0.25
    relative_bleed_xbi_underperformance: float = -0.15
    freeze_return_threshold: float = -0.10
    portfolio_id: str = "baker-bros"
    benchmark_ticker: str = "XBI"


@dataclass
class Position:
    """State of a single position in the portfolio."""
    ticker: str
    company_name: str
    entry_date: str           # "YYYY-MM-DD" of first buy
    entry_price: float        # price at first buy
    shares: float             # total shares held (accumulated monthly)
    cost_basis: float         # total dollars invested (accumulated monthly)
    status: str               # "active" | "frozen" | "sold"
    frozen_date: str | None = None
    sold_date: str | None = None
    sold_price: float | None = None
    sell_reason: str | None = None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _build_trade_calendar(xbi_dates: list[str], trade_day: int) -> list[str]:
    """Return the Nth trading day of each month from XBI's actual trading dates."""
    from collections import defaultdict
    month_map: dict[str, list[str]] = defaultdict(list)
    for d in sorted(xbi_dates):
        month_map[d[:7]].append(d)  # key = "YYYY-MM"

    result = []
    for ym in sorted(month_map):
        days = month_map[ym]
        idx = min(trade_day - 1, len(days) - 1)
        result.append(days[idx])
    return result


def _get_active_filing(trade_date: str, filings_list: list[dict]) -> dict | None:
    """Return the most recent filing whose filing_date <= trade_date."""
    active = None
    for f in filings_list:
        if f["filing_date"] <= trade_date:
            active = f
        else:
            break
    return active


def _select_top_holdings(holdings_df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Return top N positions by portfolio weight (ticker, company_name, weight_pct).

    Selection gates on ``resolution_status == "resolved"`` (ticker + FIGI present,
    i.e. a tradable, price-joinable security) per the security-reference spec §7 —
    not merely a non-blank ticker. ``load_holdings_by_date`` always enriches, so the
    column is present; ``.get(..., "resolved")`` keeps this sane if an un-enriched
    frame is ever passed.
    """
    df = holdings_df[
        (holdings_df.get("resolution_status", "resolved") == "resolved")
        & (holdings_df["value"] > 0)
    ].copy()

    if df.empty:
        return pd.DataFrame(columns=["ticker", "company_name", "weight_pct"])

    dropped = holdings_df[
        (holdings_df["value"] > 0)
        & (holdings_df["ticker"].fillna("").astype(str) != "")
        & (holdings_df.get("resolution_status", "resolved") != "resolved")
    ]
    if not dropped.empty:
        logger.info("Top-N: excluded %d non-resolved names: %s",
                    len(dropped), sorted(dropped["ticker"].astype(str).unique())[:10])

    df["weight_pct"] = df["value"] / df["value"].sum() * 100
    df = df.nlargest(n, "weight_pct")
    return df[["ticker", "company_name", "weight_pct"]].reset_index(drop=True)


def _months_between(date_a: str, date_b: str) -> int:
    """Calendar months elapsed from date_a to date_b."""
    a = pd.Timestamp(date_a)
    b = pd.Timestamp(date_b)
    return (b.year - a.year) * 12 + (b.month - a.month)


def _position_return(pos: Position, current_price: float) -> float:
    """Total return based on weighted average cost per share."""
    if pos.shares <= 0 or pos.cost_basis <= 0:
        return 0.0
    avg_cost = pos.cost_basis / pos.shares
    return (current_price - avg_cost) / avg_cost


def _xbi_return_since(entry_date: str, current_date: str, xbi_prices: dict[str, float]) -> float:
    """XBI price return from entry_date to current_date. Returns 0.0 if prices missing."""
    p0 = xbi_prices.get(entry_date)
    p1 = xbi_prices.get(current_date)
    if not p0 or not p1:
        return 0.0
    return (p1 - p0) / p0


def _evaluate_sells(
    positions: dict[str, Position],
    date: str,
    price_lookup: dict[str, dict[str, float]],
    xbi_prices: dict[str, float],
    config: StrategyConfig,
) -> list[tuple[str, str]]:
    """Return (ticker, reason) pairs for positions that hit a sell rule.

    Sell rules only apply after min_hold_months have elapsed.
    Hard stop takes priority over relative bleed check.
    """
    to_sell = []
    for ticker, pos in positions.items():
        if pos.status not in ("active", "frozen"):
            continue
        if _months_between(pos.entry_date, date) < config.min_hold_months:
            continue
        price = price_lookup.get(ticker, {}).get(date)
        if price is None:
            continue

        pos_ret = _position_return(pos, price)

        if pos_ret <= config.hard_stop_return:
            to_sell.append((ticker, f"hard_stop ({pos_ret*100:.1f}%)"))
            continue

        if pos_ret <= config.relative_bleed_return:
            xbi_ret = _xbi_return_since(pos.entry_date, date, xbi_prices)
            if (pos_ret - xbi_ret) <= config.relative_bleed_xbi_underperformance:
                to_sell.append((ticker, f"relative_bleed ({pos_ret*100:.1f}% vs XBI {xbi_ret*100:.1f}%)"))

    return to_sell


def _evaluate_freezes(
    positions: dict[str, Position],
    date: str,
    price_lookup: dict[str, dict[str, float]],
    xbi_prices: dict[str, float],
    config: StrategyConfig,
) -> tuple[list[str], list[str]]:
    """Return (tickers_to_freeze, tickers_to_unfreeze).

    Freeze: active position is down >= freeze_return_threshold AND underperforming XBI.
    Unfreeze: frozen position where either condition no longer holds.
    No min_hold restriction on freezing.
    """
    to_freeze: list[str] = []
    to_unfreeze: list[str] = []

    for ticker, pos in positions.items():
        if pos.status not in ("active", "frozen"):
            continue
        price = price_lookup.get(ticker, {}).get(date)
        if price is None:
            continue

        pos_ret = _position_return(pos, price)
        xbi_ret = _xbi_return_since(pos.entry_date, date, xbi_prices)
        should_freeze = pos_ret <= config.freeze_return_threshold and pos_ret < xbi_ret

        if pos.status == "active" and should_freeze:
            to_freeze.append(ticker)
        elif pos.status == "frozen" and not should_freeze:
            to_unfreeze.append(ticker)

    return to_freeze, to_unfreeze


def _handle_filing_refresh(
    positions: dict[str, Position],
    new_top10: pd.DataFrame,
    trade_date: str,
    price_lookup: dict[str, dict[str, float]],
    config: StrategyConfig,
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Handle a new 13F filing. Mutates positions in place.

    Returns (new_entrant_tickers, log_entries).
    log_entries: list of (ticker, action, reason) for transaction logging.

    Steps:
    1. Freeze active positions that dropped from the new top-10.
    2. Find new entrant candidates (in top-10, not currently held).
    3. If portfolio is at capacity and there are new entrants, sell the worst frozen.
    4. Return entrant tickers that fit within available capacity.
    """
    log_entries: list[tuple[str, str, str]] = []
    top10_tickers = set(new_top10["ticker"].tolist())

    # Step 1: Freeze dropped active names
    for ticker, pos in positions.items():
        if pos.status == "active" and ticker not in top10_tickers:
            pos.status = "frozen"
            pos.frozen_date = trade_date
            log_entries.append((ticker, "freeze", "filing_refresh_dropped"))

    # Step 2: New entrant candidates (not currently held at all)
    currently_held = {t for t, p in positions.items() if p.status != "sold"}
    new_entrant_candidates = [
        row["ticker"] for _, row in new_top10.iterrows()
        if row["ticker"] not in currently_held
    ]  # ordered by weight_pct desc (new_top10 is already sorted)

    if not new_entrant_candidates:
        return [], log_entries

    # Step 3: Check capacity and free a slot if needed
    non_sold_count = sum(1 for p in positions.values() if p.status != "sold")
    slots = config.max_positions - non_sold_count

    if slots <= 0:
        frozen = [(t, p) for t, p in positions.items() if p.status == "frozen"]
        if frozen:
            worst_ticker = min(
                frozen,
                key=lambda tp: _position_return(
                    tp[1], price_lookup.get(tp[0], {}).get(trade_date, tp[1].entry_price)
                ),
            )[0]
            pos = positions[worst_ticker]
            sell_price = price_lookup.get(worst_ticker, {}).get(trade_date, pos.entry_price)
            pos.status = "sold"
            pos.sold_date = trade_date
            pos.sold_price = sell_price
            pos.sell_reason = "replaced_by_new_entrant"
            log_entries.append((worst_ticker, "sell", "replaced_by_new_entrant"))
            slots = 1

    # Step 4: Return entrants within capacity
    new_entrants = new_entrant_candidates[: max(0, slots)]
    return new_entrants, log_entries


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------

def _append_backtest_log(
    run_id: str,
    config: StrategyConfig,
    performance_df: pd.DataFrame,
    positions_df: pd.DataFrame,
    output_dir: Path,
) -> None:
    """Append one summary row for this run to docs/backtest_log.csv.

    Creates the file with a header row if it doesn't exist yet. No-ops if
    performance_df has no data (e.g. cumulative_invested never went positive).
    """
    invested = performance_df[performance_df["cumulative_invested"] > 0]
    if invested.empty:
        return

    first = invested.iloc[0]
    last = performance_df.iloc[-1]

    row = {
        "run_id": run_id,
        "strategy": "baker_bros_top10_ew",
        "monthly_contribution": config.monthly_contribution,
        "max_positions": config.max_positions,
        "min_hold_months": config.min_hold_months,
        "trade_day": config.trade_day,
        "hard_stop_return": config.hard_stop_return,
        "relative_bleed_return": config.relative_bleed_return,
        "relative_bleed_xbi_underperformance": config.relative_bleed_xbi_underperformance,
        "freeze_return_threshold": config.freeze_return_threshold,
        "portfolio_id": config.portfolio_id,
        "benchmark_ticker": config.benchmark_ticker,
        "period_start": first["date"],
        "period_end": last["date"],
        "cumulative_invested": last["cumulative_invested"],
        "ending_value": last["portfolio_value"],
        "portfolio_return": round(last["portfolio_return"], 6),
        "xbi_return": round(last["xbi_return"], 6),
        "vs_xbi_pp": round((last["portfolio_return"] - last["xbi_return"]) * 100, 2),
        "active_positions": int((positions_df["status"] == "active").sum()) if not positions_df.empty else 0,
        "frozen_positions": int((positions_df["status"] == "frozen").sum()) if not positions_df.empty else 0,
        "sold_positions": int((positions_df["status"] == "sold").sum()) if not positions_df.empty else 0,
        "output_dir": str(output_dir.relative_to(PROJECT_ROOT)).replace("\\", "/"),
    }

    log_row_df = pd.DataFrame([row], columns=BACKTEST_LOG_COLUMNS)
    write_header = not BACKTEST_LOG_CSV.exists()
    BACKTEST_LOG_CSV.parent.mkdir(parents=True, exist_ok=True)
    log_row_df.to_csv(BACKTEST_LOG_CSV, mode="a", header=write_header, index=False)


def run_simulation(
    config: StrategyConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run the Strategy 1 backtest. Saves 3 CSVs and returns DataFrames.

    Returns (positions_df, transactions_df, performance_df).
    """
    if config is None:
        config = StrategyConfig()

    print("Loading price data...")
    if not PRICES_FILE.exists():
        raise FileNotFoundError(f"prices.csv not found: {PRICES_FILE}")

    # Get actual XBI trading dates (for trade calendar and loop)
    prices_raw = pd.read_csv(PRICES_FILE, parse_dates=["date"])
    xbi_raw = prices_raw[prices_raw["ticker"] == config.benchmark_ticker].sort_values("date")
    if xbi_raw.empty:
        raise ValueError(f"No price data for benchmark: {config.benchmark_ticker}")

    xbi_trading_dates = xbi_raw["date"].dt.strftime("%Y-%m-%d").tolist()
    print(f"  XBI: {xbi_trading_dates[0]} to {xbi_trading_dates[-1]} ({len(xbi_trading_dates)} trading days)")

    # Forward-filled prices for daily valuation (covers weekends and price gaps)
    print("  Forward-filling prices (may take a few seconds)...")
    prices_ff = get_forward_filled_prices(start_date=xbi_trading_dates[0])
    prices_ff["date"] = pd.to_datetime(prices_ff["date"])
    prices_ff["date_str"] = prices_ff["date"].dt.strftime("%Y-%m-%d")

    # Build price lookup: {ticker: {date_str: close}}
    price_lookup: dict[str, dict[str, float]] = {
        ticker: dict(zip(grp["date_str"], grp["close"]))
        for ticker, grp in prices_ff.groupby("ticker")
    }
    xbi_prices = price_lookup.get(config.benchmark_ticker, {})
    print(f"  Price lookup: {len(price_lookup)} tickers")

    # Trade calendar
    trade_calendar = set(_build_trade_calendar(xbi_trading_dates, config.trade_day))
    print(f"  Trade calendar: {len(trade_calendar)} monthly trade days")

    # Filings sorted ascending by filing_date
    filings_df = get_all_filings(config.portfolio_id).sort_values("filing_date")
    if filings_df.empty:
        raise ValueError(f"No filings found for: {config.portfolio_id}")
    filings_list = filings_df.to_dict("records")
    print(f"  Filings: {len(filings_list)} ({filings_list[0]['filing_date']} to {filings_list[-1]['filing_date']})")

    # State
    positions: dict[str, Position] = {}
    transactions: list[dict] = []
    daily_perf: list[dict] = []
    cumulative_invested: float = 0.0
    xbi_shares: float = 0.0
    last_filing_date: str | None = None
    holdings_cache: dict[str, pd.DataFrame] = {}  # filing_date → top10 df

    print("\nRunning simulation...")
    n = len(xbi_trading_dates)
    last_pct = -1

    for i, date in enumerate(xbi_trading_dates):
        pct = i * 100 // n
        if pct >= last_pct + 10:
            print(f"  {pct}% ({date})")
            last_pct = pct

        # --- Daily valuation ---
        portfolio_value = 0.0
        active_count = 0
        frozen_count = 0
        for ticker, pos in positions.items():
            if pos.status == "sold":
                continue
            p = price_lookup.get(ticker, {}).get(date)
            if p is not None:
                portfolio_value += pos.shares * p
            if pos.status == "active":
                active_count += 1
            else:
                frozen_count += 1

        xbi_price_today = xbi_prices.get(date, 0.0)
        xbi_value = xbi_shares * xbi_price_today
        port_ret = (portfolio_value / cumulative_invested - 1) if cumulative_invested > 0 else 0.0
        xbi_ret_total = (xbi_value / cumulative_invested - 1) if cumulative_invested > 0 else 0.0

        daily_perf.append({
            "date": date,
            "portfolio_value": round(portfolio_value, 2),
            "cumulative_invested": round(cumulative_invested, 2),
            "portfolio_return": round(port_ret, 6),
            "xbi_value": round(xbi_value, 2),
            "xbi_return": round(xbi_ret_total, 6),
            "active_positions": active_count,
            "frozen_positions": frozen_count,
        })

        if date not in trade_calendar:
            continue

        # --- Trade day ---
        active_filing = _get_active_filing(date, filings_list)
        if active_filing is None:
            continue

        filing_date = active_filing["filing_date"]
        filing_changed = filing_date != last_filing_date

        # Load and cache top-10
        if filing_date not in holdings_cache:
            hdf = load_holdings_by_date(config.portfolio_id, filing_date)
            holdings_cache[filing_date] = _select_top_holdings(hdf, config.max_positions)
        top10 = holdings_cache[filing_date]
        if top10.empty:
            continue

        # A. Evaluate sells (before freeze/refresh)
        sells = _evaluate_sells(positions, date, price_lookup, xbi_prices, config)
        for ticker, reason in sells:
            pos = positions[ticker]
            sell_price = price_lookup.get(ticker, {}).get(date, pos.entry_price)
            pos.status = "sold"
            pos.sold_date = date
            pos.sold_price = sell_price
            pos.sell_reason = reason
            transactions.append({
                "date": date,
                "ticker": ticker,
                "company_name": pos.company_name,
                "action": "sell",
                "shares": round(pos.shares, 6),
                "price": round(sell_price, 4),
                "dollar_amount": round(pos.shares * sell_price, 2),
                "reason": reason,
            })

        # B. Evaluate freezes / unfreezes
        to_freeze, to_unfreeze = _evaluate_freezes(positions, date, price_lookup, xbi_prices, config)
        for ticker in to_freeze:
            pos = positions[ticker]
            pos.status = "frozen"
            pos.frozen_date = date
            transactions.append({
                "date": date, "ticker": ticker, "company_name": pos.company_name,
                "action": "freeze", "shares": 0,
                "price": price_lookup.get(ticker, {}).get(date),
                "dollar_amount": 0, "reason": "freeze_threshold",
            })
        for ticker in to_unfreeze:
            pos = positions[ticker]
            pos.status = "active"
            pos.frozen_date = None
            transactions.append({
                "date": date, "ticker": ticker, "company_name": pos.company_name,
                "action": "unfreeze", "shares": 0,
                "price": price_lookup.get(ticker, {}).get(date),
                "dollar_amount": 0, "reason": "recovered",
            })

        # C. Handle filing change
        new_entrants: list[str] = []
        if filing_changed:
            new_entrants, log_entries = _handle_filing_refresh(
                positions, top10, date, price_lookup, config
            )
            for ticker, action, reason in log_entries:
                pos = positions.get(ticker)
                company = pos.company_name if pos else ticker
                p = price_lookup.get(ticker, {}).get(date)
                dollar = round(pos.shares * p, 2) if (pos and action == "sell" and p) else 0
                transactions.append({
                    "date": date, "ticker": ticker, "company_name": company,
                    "action": action,
                    "shares": round(pos.shares, 6) if (pos and action == "sell") else 0,
                    "price": p, "dollar_amount": dollar, "reason": reason,
                })
            last_filing_date = filing_date

        # D. Eligible for capital: active positions + new entrants (no duplicates)
        eligible: list[str] = [t for t, p in positions.items() if p.status == "active"]
        for t in new_entrants:
            if t not in eligible:
                eligible.append(t)

        if not eligible:
            continue

        # E. Split contribution equally
        per_name = config.monthly_contribution / len(eligible)
        month_invested = 0.0

        # F. Execute buys
        for ticker in eligible:
            price = price_lookup.get(ticker, {}).get(date)
            if price is None or price <= 0:
                cname = positions[ticker].company_name if ticker in positions else ticker
                transactions.append({
                    "date": date, "ticker": ticker, "company_name": cname,
                    "action": "skip", "shares": 0, "price": None,
                    "dollar_amount": 0, "reason": "no_price",
                })
                continue

            shares_bought = per_name / price

            if ticker in positions and positions[ticker].status == "active":
                # Add to existing position
                pos = positions[ticker]
                pos.shares += shares_bought
                pos.cost_basis += per_name
            else:
                # New position
                row = top10[top10["ticker"] == ticker]
                cname = row["company_name"].iloc[0] if not row.empty else ticker
                positions[ticker] = Position(
                    ticker=ticker,
                    company_name=cname,
                    entry_date=date,
                    entry_price=price,
                    shares=shares_bought,
                    cost_basis=per_name,
                    status="active",
                )

            month_invested += per_name
            transactions.append({
                "date": date,
                "ticker": ticker,
                "company_name": positions[ticker].company_name,
                "action": "buy",
                "shares": round(shares_bought, 6),
                "price": round(price, 4),
                "dollar_amount": round(per_name, 2),
                "reason": "monthly_contribution_equal_weight",
            })

        # G. Track XBI investment (same dollar amount for fair benchmark comparison)
        if xbi_price_today > 0 and month_invested > 0:
            xbi_shares += month_invested / xbi_price_today
        cumulative_invested += month_invested

    print("  100% — simulation complete")

    # --- Build output DataFrames ---
    latest_date = xbi_trading_dates[-1]
    print(f"\nBuilding output DataFrames (as of {latest_date})...")

    positions_df = _build_positions_df(positions, price_lookup, xbi_prices, latest_date, config)
    transactions_df = pd.DataFrame(transactions) if transactions else pd.DataFrame(
        columns=["date", "ticker", "company_name", "action", "shares", "price", "dollar_amount", "reason"]
    )
    performance_df = pd.DataFrame(daily_perf)

    # Save to a run-specific folder so results aren't overwritten by the next run
    run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_dir = BACKTEST_RUNS_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    positions_csv = output_dir / "positions.csv"
    transactions_csv = output_dir / "transactions.csv"
    performance_csv = output_dir / "performance.csv"

    positions_df.to_csv(positions_csv, index=False)
    transactions_df.to_csv(transactions_csv, index=False)
    performance_df.to_csv(performance_csv, index=False)

    print(f"  Positions:    {len(positions_df)} rows -> {positions_csv}")
    print(f"  Transactions: {len(transactions_df)} rows -> {transactions_csv}")
    print(f"  Performance:  {len(performance_df)} rows -> {performance_csv}")

    _append_backtest_log(run_id, config, performance_df, positions_df, output_dir)
    print(f"  Logged run {run_id} to {BACKTEST_LOG_CSV}")

    return positions_df, transactions_df, performance_df


def _build_positions_df(
    positions: dict[str, Position],
    price_lookup: dict[str, dict[str, float]],
    xbi_prices: dict[str, float],
    latest_date: str,
    config: StrategyConfig,
) -> pd.DataFrame:
    """Build the positions snapshot DataFrame."""
    rows = []
    for ticker, pos in positions.items():
        if pos.status == "sold":
            current_price = pos.sold_price or 0.0
            eval_date = pos.sold_date or latest_date
        else:
            current_price = price_lookup.get(ticker, {}).get(latest_date, 0.0)
            eval_date = latest_date

        avg_cost = pos.cost_basis / pos.shares if pos.shares > 0 else 0.0
        current_value = pos.shares * current_price
        total_return = _position_return(pos, current_price) if current_price > 0 else 0.0
        xbi_ret = _xbi_return_since(pos.entry_date, eval_date, xbi_prices)
        days_held = (pd.Timestamp(eval_date) - pd.Timestamp(pos.entry_date)).days

        rows.append({
            "ticker": ticker,
            "company_name": pos.company_name,
            "status": pos.status,
            "entry_date": pos.entry_date,
            "entry_price": round(pos.entry_price, 4),
            "avg_cost": round(avg_cost, 4),
            "shares": round(pos.shares, 6),
            "cost_basis": round(pos.cost_basis, 2),
            "current_price": round(current_price, 4),
            "current_value": round(current_value, 2),
            "total_return": round(total_return, 6),
            "xbi_return_since_entry": round(xbi_ret, 6),
            "relative_return_vs_xbi": round(total_return - xbi_ret, 6),
            "days_held": days_held,
            "sell_eligible": _months_between(pos.entry_date, eval_date) >= config.min_hold_months,
            "distance_to_hard_stop": round(total_return - config.hard_stop_return, 6),
            "distance_to_freeze": round(total_return - config.freeze_return_threshold, 6),
            "frozen_date": pos.frozen_date,
            "sold_date": pos.sold_date,
            "sell_reason": pos.sell_reason,
        })

    return pd.DataFrame(rows)
