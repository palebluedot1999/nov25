"""
Core portfolio strategy backtesting engine.

Handles:
- Monthly simulation loop across all strategy streams
- Position state management (active, frozen, sold)
- Sell rule evaluation (hard stop, relative bleed)
- Freeze/unfreeze rule evaluation
- Capital allocation (base equal/conviction, enhanced momentum-tilted)
- Filing refresh logic per strategy
- Transaction logging and daily portfolio valuation
"""

import sys
from dataclasses import dataclass, field
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.strategy_config import (
    STRATEGY_REGISTRY,
    STREAM_IDS,
    StrategyConfig,
    get_strategy_for_stream,
    is_enhanced,
)
from utils.strategy_selectors import get_selector
from utils.csv_data import (
    get_holdings_files,
    load_qoq_changes,
    PROCESSED_DATA_DIR,
    RAW_DATA_DIR,
)


# ---------------------------------------------------------------------------
# Position dataclass
# ---------------------------------------------------------------------------

@dataclass
class Position:
    """State of a single position within a strategy stream."""
    ticker: str
    company_name: str
    entry_date: str
    entry_price: float
    shares: float
    cost_basis: float
    status: str  # "active" | "frozen" | "sold"
    frozen_date: Optional[str] = None
    sold_date: Optional[str] = None
    sold_price: Optional[float] = None
    sell_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_all_prices() -> pd.DataFrame:
    """Load the master prices table and index for fast lookup."""
    prices_path = PROCESSED_DATA_DIR / "prices.csv"
    df = pd.read_csv(prices_path, parse_dates=["date"])
    df["date_str"] = df["date"].dt.strftime("%Y-%m-%d")
    return df


def _build_price_lookup(prices_df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """Build {ticker: {date_str: close_price}} lookup dict."""
    lookup = {}
    for ticker, group in prices_df.groupby("ticker"):
        lookup[ticker] = dict(zip(group["date_str"], group["close"]))
    return lookup


def _build_volume_lookup(prices_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Build {ticker: DataFrame with date_str, volume} for volume spike detection."""
    lookup = {}
    for ticker, group in prices_df.groupby("ticker"):
        g = group[["date_str", "volume"]].copy().sort_values("date_str").reset_index(drop=True)
        lookup[ticker] = g
    return lookup


def _load_filings_metadata(portfolio_id: str) -> List[Dict]:
    """Load all filing metadata sorted by filing_date ascending.

    Returns list of dicts with keys: filing_date, period_end_date, filepath.
    """
    files = get_holdings_files(portfolio_id)
    filings = []
    for f in files:
        parts = f.stem.split("_")
        if len(parts) >= 2:
            filing_date = parts[1]
            # Read period_end_date from file
            try:
                sample = pd.read_csv(f, nrows=1)
                period_end = sample["period_end_date"].iloc[0] if "period_end_date" in sample.columns else filing_date
            except Exception:
                period_end = filing_date
            filings.append({
                "filing_date": filing_date,
                "period_end_date": str(period_end),
                "filepath": f,
            })
    filings.sort(key=lambda x: x["filing_date"])
    return filings


def _load_filing_holdings(filepath: Path) -> pd.DataFrame:
    """Load a single 13F filing CSV."""
    df = pd.read_csv(filepath)
    # Ensure required columns exist
    for col in ["ticker", "cusip", "company_name", "shares", "value"]:
        if col not in df.columns:
            df[col] = None
    return df


# ---------------------------------------------------------------------------
# Trade calendar
# ---------------------------------------------------------------------------

def _build_trade_calendar(
    trading_dates: List[str],
    config: StrategyConfig,
) -> List[str]:
    """Build list of monthly trade dates.

    For each month, find the Nth trading day (config.trade_day).
    """
    if not trading_dates:
        return []

    trade_dates = []
    current_month = None

    month_dates = []
    for d in sorted(trading_dates):
        ym = d[:7]  # "YYYY-MM"
        if ym != current_month:
            if month_dates and len(month_dates) >= config.trade_day:
                trade_dates.append(month_dates[config.trade_day - 1])
            month_dates = [d]
            current_month = ym
        else:
            month_dates.append(d)

    # Handle last month
    if month_dates and len(month_dates) >= config.trade_day:
        trade_dates.append(month_dates[config.trade_day - 1])

    return trade_dates


# ---------------------------------------------------------------------------
# Filing lookup
# ---------------------------------------------------------------------------

def _get_active_filing(
    trade_date: str,
    filings: List[Dict],
) -> Optional[Dict]:
    """Return the most recent filing whose filing_date <= trade_date."""
    active = None
    for f in filings:
        if f["filing_date"] <= trade_date:
            active = f
        else:
            break
    return active


# ---------------------------------------------------------------------------
# Sell / Freeze evaluation
# ---------------------------------------------------------------------------

def _position_return(position: Position, current_price: float) -> float:
    """Calculate total return from entry price."""
    if position.entry_price <= 0:
        return 0.0
    return (current_price - position.entry_price) / position.entry_price


def _months_held(entry_date: str, current_date: str) -> int:
    """Count calendar months between entry and current date."""
    entry = datetime.strptime(entry_date, "%Y-%m-%d")
    current = datetime.strptime(current_date, "%Y-%m-%d")
    return (current.year - entry.year) * 12 + (current.month - entry.month)


def _evaluate_sell_rules(
    position: Position,
    current_date: str,
    current_price: float,
    xbi_return_from_entry: float,
    config: StrategyConfig,
) -> Optional[str]:
    """Check if a position triggers a sell rule.

    Only fires if held >= min_hold_months.
    Returns sell reason string or None.
    """
    if _months_held(position.entry_date, current_date) < config.min_hold_months:
        return None

    pos_return = _position_return(position, current_price)

    # Hard stop: total return <= -40%
    if pos_return <= config.hard_stop_return:
        return "hard_stop"

    # Relative bleed: return <= -25% AND underperformance vs XBI >= 15pp
    if pos_return <= config.relative_bleed_return:
        relative_perf = pos_return - xbi_return_from_entry
        if relative_perf <= config.relative_bleed_xbi_underperformance:
            return "relative_bleed"

    return None


def _evaluate_freeze_rules(
    position: Position,
    current_price: float,
    xbi_return_from_entry: float,
    config: StrategyConfig,
) -> bool:
    """Check if a position should be frozen.

    BOTH must be true:
    1. Down >= 10% from entry
    2. Underperforming XBI over same holding period
    """
    pos_return = _position_return(position, current_price)

    down_enough = pos_return <= config.freeze_return_threshold
    underperforming_xbi = pos_return < xbi_return_from_entry

    return down_enough and underperforming_xbi


# ---------------------------------------------------------------------------
# Capital allocation
# ---------------------------------------------------------------------------

def _allocate_capital_base(
    contribution: float,
    active_tickers: List[str],
    weighting: str,
    conviction_scores: Dict[str, float],
    config: StrategyConfig,
) -> Dict[str, float]:
    """Base (.0) capital allocation.

    For "equal": split evenly.
    For "conviction": weight by conviction_score with 15% cap and
    iterative redistribution.
    """
    if not active_tickers:
        return {}

    if weighting == "equal":
        per_name = contribution / len(active_tickers)
        return {t: per_name for t in active_tickers}

    # Conviction-weighted with cap
    # Get scores for active tickers
    scores = {t: conviction_scores.get(t, 1.0) for t in active_tickers}
    total_score = sum(scores.values())
    if total_score <= 0:
        per_name = contribution / len(active_tickers)
        return {t: per_name for t in active_tickers}

    # Iterative capping
    allocation = {}
    remaining_contribution = contribution
    uncapped = set(active_tickers)

    for _ in range(10):  # max iterations
        total_uncapped_score = sum(scores[t] for t in uncapped)
        if total_uncapped_score <= 0:
            break

        any_capped = False
        for t in list(uncapped):
            raw_weight = scores[t] / total_uncapped_score
            raw_amount = remaining_contribution * raw_weight

            if raw_amount > contribution * config.conviction_cap:
                allocation[t] = contribution * config.conviction_cap
                remaining_contribution -= allocation[t]
                uncapped.discard(t)
                any_capped = True

        if not any_capped:
            # Distribute remaining among uncapped
            total_uncapped_score = sum(scores[t] for t in uncapped)
            for t in uncapped:
                allocation[t] = remaining_contribution * (scores[t] / total_uncapped_score)
            break

    return allocation


def _allocate_capital_enhanced(
    base_allocation: Dict[str, float],
    price_lookup: Dict[str, Dict[str, float]],
    xbi_prices: Dict[str, float],
    trade_date: str,
    trading_dates: List[str],
    config: StrategyConfig,
) -> Tuple[Dict[str, float], Dict[str, bool]]:
    """Enhanced (.1) capital allocation.

    Tilts base allocation by trailing 1-month relative momentum vs XBI.
    Also flags volume spikes.
    """
    if not base_allocation:
        return {}, {}

    total_contribution = sum(base_allocation.values())

    # Find the date N trading days ago for momentum
    trade_idx = None
    for i, d in enumerate(trading_dates):
        if d >= trade_date:
            trade_idx = i
            break
    if trade_idx is None:
        trade_idx = len(trading_dates) - 1

    lookback_idx = max(0, trade_idx - config.momentum_lookback)
    lookback_date = trading_dates[lookback_idx]

    # XBI return over lookback period
    xbi_now = xbi_prices.get(trade_date, 0)
    xbi_then = xbi_prices.get(lookback_date, 0)
    xbi_momentum = (xbi_now - xbi_then) / xbi_then if xbi_then > 0 else 0.0

    # Calculate relative momentum for each ticker
    momentum_scores = {}
    for ticker in base_allocation:
        ticker_prices = price_lookup.get(ticker, {})
        p_now = ticker_prices.get(trade_date, 0)
        p_then = ticker_prices.get(lookback_date, 0)
        if p_then > 0 and p_now > 0:
            ticker_momentum = (p_now - p_then) / p_then
            momentum_scores[ticker] = ticker_momentum - xbi_momentum
        else:
            momentum_scores[ticker] = 0.0

    # Tilt: multiply base weight by (1 + relative_momentum), renormalize
    adjusted = {}
    for ticker, base_amt in base_allocation.items():
        base_weight = base_amt / total_contribution if total_contribution > 0 else 0
        tilt = max(0.01, 1.0 + momentum_scores.get(ticker, 0.0))  # floor at 0.01 to avoid negative/zero
        adjusted[ticker] = base_weight * tilt

    # Renormalize
    total_adj = sum(adjusted.values())
    if total_adj > 0:
        enhanced_alloc = {t: (w / total_adj) * total_contribution for t, w in adjusted.items()}
    else:
        enhanced_alloc = base_allocation.copy()

    # Volume spike flags
    volume_flags = {}
    vol_short = config.volume_spike_lookback_short
    vol_long = config.volume_spike_lookback_long

    for ticker in base_allocation:
        ticker_prices_dict = price_lookup.get(ticker, {})
        # Get recent trading dates with data for this ticker
        recent_dates = [d for d in trading_dates[max(0, trade_idx - vol_long):trade_idx + 1]
                        if d in ticker_prices_dict]

        if len(recent_dates) < vol_short + 1:
            volume_flags[ticker] = False
            continue

        # We need volume data - check if available in the price lookup
        # Volume is not in price_lookup (only close). We'll flag False for now
        # and compute volume flags separately if volume data is loaded.
        volume_flags[ticker] = False

    return enhanced_alloc, volume_flags


def _compute_volume_flags(
    tickers: List[str],
    volume_lookup: Dict[str, pd.DataFrame],
    trade_date: str,
    config: StrategyConfig,
) -> Dict[str, bool]:
    """Compute volume spike flags for a list of tickers on a given trade date."""
    flags = {}
    for ticker in tickers:
        vol_df = volume_lookup.get(ticker)
        if vol_df is None or vol_df.empty:
            flags[ticker] = False
            continue

        # Filter to dates <= trade_date
        mask = vol_df["date_str"] <= trade_date
        recent = vol_df[mask]
        if len(recent) < config.volume_spike_lookback_long:
            flags[ticker] = False
            continue

        short_avg = recent.tail(config.volume_spike_lookback_short)["volume"].mean()
        long_avg = recent.tail(config.volume_spike_lookback_long)["volume"].mean()

        if long_avg > 0:
            flags[ticker] = short_avg >= config.volume_spike_multiplier * long_avg
        else:
            flags[ticker] = False

    return flags


# ---------------------------------------------------------------------------
# Filing refresh logic
# ---------------------------------------------------------------------------

def _handle_filing_refresh(
    strategy_id: str,
    positions: Dict[str, Position],
    new_targets: pd.DataFrame,
    trade_date: str,
    price_lookup: Dict[str, Dict[str, float]],
    config: StrategyConfig,
    transactions: List[Dict],
    stream_id: str,
    active_filing_date: str,
) -> None:
    """Handle arrival of a new 13F filing. Modifies positions in place.

    Strategy-specific refresh logic:
    - 1/2 (top holdings): Names dropped from top-10 → freeze.
      New entrants replace worst-performing frozen name if no open slots.
    - 3 (active accumulation): Names no longer accumulated → freeze.
      New accumulators replace worst frozen if no open slots.
    - 4 (new initiations): Existing non-qualifying names stay active
      (only leave via sell/freeze thresholds). New names added if slots open.
    """
    target_tickers = set(new_targets["ticker"].tolist())
    held_tickers = {t for t, p in positions.items() if p.status != "sold"}

    if strategy_id in ("1", "2", "3"):
        # Freeze names that dropped out of target list
        for ticker, pos in positions.items():
            if pos.status == "active" and ticker not in target_tickers:
                pos.status = "frozen"
                pos.frozen_date = trade_date
                transactions.append({
                    "stream_id": stream_id,
                    "date": trade_date,
                    "ticker": ticker,
                    "company_name": pos.company_name,
                    "action": "freeze",
                    "shares": 0,
                    "price": price_lookup.get(ticker, {}).get(trade_date, 0),
                    "dollar_amount": 0,
                    "reason": "filing_refresh_dropped",
                    "filing_date": active_filing_date,
                    "volume_spike": False,
                    "momentum_score": None,
                })

    # Strategy 4: do NOT freeze existing active names just because they're
    # not in the new target list. They stay active unless sell/freeze
    # thresholds fire.

    # Add new entrants if slots available
    total_held = len([p for p in positions.values() if p.status != "sold"])
    open_slots = config.max_positions - total_held

    new_entrants = [t for t in new_targets["ticker"].tolist() if t not in held_tickers]

    if open_slots <= 0 and new_entrants:
        # Replace worst-performing frozen name
        frozen = [(t, p) for t, p in positions.items() if p.status == "frozen"]
        if frozen:
            # Find worst by total return from entry
            worst_ticker = None
            worst_return = float("inf")
            for t, p in frozen:
                price = price_lookup.get(t, {}).get(trade_date, p.entry_price)
                ret = _position_return(p, price)
                if ret < worst_return:
                    worst_return = ret
                    worst_ticker = t

            if worst_ticker:
                pos = positions[worst_ticker]
                sell_price = price_lookup.get(worst_ticker, {}).get(trade_date, pos.entry_price)
                pos.status = "sold"
                pos.sold_date = trade_date
                pos.sold_price = sell_price
                pos.sell_reason = "replaced_by_new_entrant"
                transactions.append({
                    "stream_id": stream_id,
                    "date": trade_date,
                    "ticker": worst_ticker,
                    "company_name": pos.company_name,
                    "action": "sell",
                    "shares": pos.shares,
                    "price": sell_price,
                    "dollar_amount": pos.shares * sell_price,
                    "reason": "replaced_by_new_entrant",
                    "filing_date": active_filing_date,
                    "volume_spike": False,
                    "momentum_score": None,
                })
                open_slots = 1  # freed one slot

    # Mark new entrants to be picked up in the allocation step
    # We store them as pending positions with 0 shares — the allocation
    # step will give them capital
    for ticker in new_entrants[:max(0, open_slots)]:
        if ticker in positions and positions[ticker].status == "sold":
            # Re-entering a previously sold name: create new position
            # (keep the old one as sold, create new entry)
            pass  # will be created in allocation step
        # Don't create position yet — allocation step handles entry


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------

def run_backtest(
    config: StrategyConfig,
    stream_ids: Optional[List[str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Run the full backtest for all specified streams.

    Returns (positions_df, transactions_df, performance_df).
    """
    if stream_ids is None:
        stream_ids = STREAM_IDS.copy()

    print("Loading data...")
    prices_df = _load_all_prices()
    price_lookup = _build_price_lookup(prices_df)
    volume_lookup = _build_volume_lookup(prices_df)

    # XBI prices for benchmark calculations
    xbi_ticker = config.benchmark_ticker
    xbi_prices = price_lookup.get(xbi_ticker, {})
    if not xbi_prices:
        print(f"WARNING: No price data for benchmark {xbi_ticker}")

    # All trading dates (from XBI)
    xbi_df = prices_df[prices_df["ticker"] == xbi_ticker].sort_values("date_str")
    trading_dates = xbi_df["date_str"].tolist()
    if not trading_dates:
        print("ERROR: No trading dates found for XBI")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    print(f"  Price data: {trading_dates[0]} to {trading_dates[-1]} ({len(trading_dates)} trading days)")

    # Filings
    filings = _load_filings_metadata(config.portfolio_id)
    print(f"  Filings: {len(filings)} ({filings[0]['filing_date']} to {filings[-1]['filing_date']})")

    # Pre-load all QoQ changes
    qoq_all = pd.DataFrame()
    qoq_path = PROCESSED_DATA_DIR / "qoq_changes.csv"
    if qoq_path.exists():
        qoq_all = pd.read_csv(qoq_path)
        qoq_all = qoq_all[qoq_all["portfolio_id"] == config.portfolio_id]

    # Build trade calendar
    trade_calendar = _build_trade_calendar(trading_dates, config)
    trade_set = set(trade_calendar)
    print(f"  Trade calendar: {len(trade_calendar)} monthly trade days")

    # Find effective start: first trade date where a filing exists
    first_filing_date = filings[0]["filing_date"]
    start_idx = 0
    for i, d in enumerate(trading_dates):
        if d >= first_filing_date:
            start_idx = i
            break

    print(f"  Effective backtest start: {trading_dates[start_idx]}")
    print()

    # Initialize state per stream
    positions: Dict[str, Dict[str, Position]] = {sid: {} for sid in stream_ids}
    transactions: Dict[str, List[Dict]] = {sid: [] for sid in stream_ids}
    daily_values: Dict[str, List[Dict]] = {sid: [] for sid in stream_ids}
    cumulative_invested: Dict[str, float] = {sid: 0.0 for sid in stream_ids}
    # Track which filing is active per stream (to detect changes)
    last_active_filing: Dict[str, Optional[str]] = {sid: None for sid in stream_ids}
    # Cache selector results per (strategy_id, filing_date)
    selector_cache: Dict[str, pd.DataFrame] = {}

    # XBI tracking: invest same dollar amounts on same dates for fair comparison
    xbi_shares: Dict[str, float] = {sid: 0.0 for sid in stream_ids}

    print("Running simulation...")
    total_days = len(trading_dates) - start_idx
    last_pct = -1

    for day_idx in range(start_idx, len(trading_dates)):
        date = trading_dates[day_idx]

        # Progress reporting
        pct = int((day_idx - start_idx) / total_days * 100)
        if pct >= last_pct + 10:
            print(f"  {pct}% ({date})")
            last_pct = pct

        is_trade_day = date in trade_set

        # Determine active filing
        active_filing = _get_active_filing(date, filings)

        for sid in stream_ids:
            strategy_meta = get_strategy_for_stream(sid)
            strategy_id = strategy_meta["strategy_id"]
            enhanced = is_enhanced(sid)
            pos_dict = positions[sid]

            # --- Daily valuation ---
            portfolio_value = 0.0
            active_count = 0
            frozen_count = 0
            for t, p in pos_dict.items():
                if p.status == "sold":
                    continue
                price = price_lookup.get(t, {}).get(date)
                if price is not None:
                    portfolio_value += p.shares * price
                if p.status == "active":
                    active_count += 1
                elif p.status == "frozen":
                    frozen_count += 1

            # XBI equivalent value
            xbi_price = xbi_prices.get(date, 0)
            xbi_value = xbi_shares[sid] * xbi_price if xbi_price > 0 else 0

            daily_values[sid].append({
                "date": date,
                "stream_id": sid,
                "portfolio_value": portfolio_value,
                "cumulative_invested": cumulative_invested[sid],
                "xbi_value": xbi_value,
                "active_positions": active_count,
                "frozen_positions": frozen_count,
                "total_positions": active_count + frozen_count,
            })

            if not is_trade_day or active_filing is None:
                continue

            # --- Trade day logic ---
            active_filing_date = active_filing["filing_date"]
            filing_changed = (last_active_filing[sid] != active_filing_date)
            last_active_filing[sid] = active_filing_date

            # STEP A: Evaluate sells
            for ticker in list(pos_dict.keys()):
                pos = pos_dict[ticker]
                if pos.status not in ("active", "frozen"):
                    continue
                price = price_lookup.get(ticker, {}).get(date)
                if price is None:
                    continue

                # XBI return over same holding period
                xbi_entry = xbi_prices.get(pos.entry_date, 0)
                xbi_now = xbi_prices.get(date, 0)
                xbi_ret = (xbi_now - xbi_entry) / xbi_entry if xbi_entry > 0 else 0.0

                sell_reason = _evaluate_sell_rules(pos, date, price, xbi_ret, config)
                if sell_reason:
                    pos.status = "sold"
                    pos.sold_date = date
                    pos.sold_price = price
                    pos.sell_reason = sell_reason
                    transactions[sid].append({
                        "stream_id": sid,
                        "date": date,
                        "ticker": ticker,
                        "company_name": pos.company_name,
                        "action": "sell",
                        "shares": pos.shares,
                        "price": price,
                        "dollar_amount": pos.shares * price,
                        "reason": sell_reason,
                        "filing_date": active_filing_date,
                        "volume_spike": False,
                        "momentum_score": None,
                    })

            # STEP B: Evaluate freezes / unfreezes
            for ticker in list(pos_dict.keys()):
                pos = pos_dict[ticker]
                if pos.status not in ("active", "frozen"):
                    continue
                price = price_lookup.get(ticker, {}).get(date)
                if price is None:
                    continue

                xbi_entry = xbi_prices.get(pos.entry_date, 0)
                xbi_now = xbi_prices.get(date, 0)
                xbi_ret = (xbi_now - xbi_entry) / xbi_entry if xbi_entry > 0 else 0.0

                should_freeze = _evaluate_freeze_rules(pos, price, xbi_ret, config)

                if pos.status == "active" and should_freeze:
                    pos.status = "frozen"
                    pos.frozen_date = date
                    transactions[sid].append({
                        "stream_id": sid,
                        "date": date,
                        "ticker": ticker,
                        "company_name": pos.company_name,
                        "action": "freeze",
                        "shares": 0,
                        "price": price,
                        "dollar_amount": 0,
                        "reason": "freeze_triggered",
                        "filing_date": active_filing_date,
                        "volume_spike": False,
                        "momentum_score": None,
                    })
                elif pos.status == "frozen" and not should_freeze:
                    pos.status = "active"
                    pos.frozen_date = None
                    transactions[sid].append({
                        "stream_id": sid,
                        "date": date,
                        "ticker": ticker,
                        "company_name": pos.company_name,
                        "action": "unfreeze",
                        "shares": 0,
                        "price": price,
                        "dollar_amount": 0,
                        "reason": "unfreeze_improved",
                        "filing_date": active_filing_date,
                        "volume_spike": False,
                        "momentum_score": None,
                    })

            # STEP C: Handle filing change
            # Get selector targets (cached per strategy + filing)
            cache_key = f"{strategy_id}_{active_filing_date}"
            if cache_key not in selector_cache:
                holdings_df = _load_filing_holdings(active_filing["filepath"])
                qoq_df = qoq_all[qoq_all["filing_date"] == active_filing_date] if not qoq_all.empty else pd.DataFrame()
                selector_fn = get_selector(strategy_meta["selector"])
                selector_cache[cache_key] = selector_fn(holdings_df, qoq_df, config)

            new_targets = selector_cache[cache_key]

            if filing_changed and not new_targets.empty:
                _handle_filing_refresh(
                    strategy_id, pos_dict, new_targets, date,
                    price_lookup, config, transactions[sid], sid,
                    active_filing_date,
                )

            # STEP D: Allocate capital
            if new_targets.empty:
                continue

            target_tickers = set(new_targets["ticker"].tolist())
            conviction_scores = dict(zip(
                new_targets["ticker"], new_targets["conviction_score"]
            ))

            # Determine active tickers for allocation (non-frozen, non-sold, in target list OR already held active)
            active_tickers = []
            total_held = len([p for p in pos_dict.values() if p.status != "sold"])
            new_entrant_count = 0
            for ticker in target_tickers:
                if ticker in pos_dict and pos_dict[ticker].status == "active":
                    # Existing active position — always receives capital
                    active_tickers.append(ticker)
                elif ticker not in pos_dict or pos_dict[ticker].status == "sold":
                    # New entrant OR previously sold re-entering — check capacity
                    if total_held + new_entrant_count < config.max_positions:
                        active_tickers.append(ticker)
                        new_entrant_count += 1
                # Frozen positions: skip (no capital this month)

            # Also include currently active positions not in target list
            # (for strategy 4, existing names stay active)
            if strategy_id == "4":
                for ticker, pos in pos_dict.items():
                    if pos.status == "active" and ticker not in active_tickers:
                        active_tickers.append(ticker)
                        if ticker not in conviction_scores:
                            conviction_scores[ticker] = 1.0

            if not active_tickers:
                continue

            # Base allocation
            base_alloc = _allocate_capital_base(
                config.monthly_contribution,
                active_tickers,
                strategy_meta["weighting"],
                conviction_scores,
                config,
            )

            # Enhanced allocation
            volume_flags = {}
            if enhanced:
                base_alloc, volume_flags = _allocate_capital_enhanced(
                    base_alloc, price_lookup, xbi_prices, date,
                    trading_dates, config,
                )
                # Compute volume flags separately
                volume_flags = _compute_volume_flags(
                    active_tickers, volume_lookup, date, config,
                )

            # STEP E: Execute buys
            month_invested = 0.0
            for ticker, dollar_amount in base_alloc.items():
                if dollar_amount <= 0:
                    continue
                price = price_lookup.get(ticker, {}).get(date)
                if price is None or price <= 0:
                    continue

                shares_to_buy = dollar_amount / price

                if ticker in pos_dict and pos_dict[ticker].status != "sold":
                    # Add to existing position
                    pos = pos_dict[ticker]
                    pos.shares += shares_to_buy
                    pos.cost_basis += dollar_amount
                else:
                    # Open new position
                    # Find company name
                    name_row = new_targets[new_targets["ticker"] == ticker]
                    cname = name_row["company_name"].iloc[0] if not name_row.empty else ticker
                    pos_dict[ticker] = Position(
                        ticker=ticker,
                        company_name=cname,
                        entry_date=date,
                        entry_price=price,
                        shares=shares_to_buy,
                        cost_basis=dollar_amount,
                        status="active",
                    )

                month_invested += dollar_amount

                # Compute momentum score for logging
                momentum = None
                if enhanced:
                    t_idx = trading_dates.index(date) if date in trading_dates else 0
                    lb_idx = max(0, t_idx - config.momentum_lookback)
                    lb_date = trading_dates[lb_idx]
                    tp = price_lookup.get(ticker, {})
                    xp_now = xbi_prices.get(date, 0)
                    xp_then = xbi_prices.get(lb_date, 0)
                    p_now = tp.get(date, 0)
                    p_then = tp.get(lb_date, 0)
                    if p_then > 0 and xp_then > 0:
                        momentum = (p_now - p_then) / p_then - (xp_now - xp_then) / xp_then

                transactions[sid].append({
                    "stream_id": sid,
                    "date": date,
                    "ticker": ticker,
                    "company_name": pos_dict[ticker].company_name,
                    "action": "buy",
                    "shares": shares_to_buy,
                    "price": price,
                    "dollar_amount": dollar_amount,
                    "reason": "monthly_allocation" if ticker in {t for t, p in pos_dict.items() if p.entry_date != date} else "new_position",
                    "filing_date": active_filing_date,
                    "volume_spike": volume_flags.get(ticker, False),
                    "momentum_score": momentum,
                })

            cumulative_invested[sid] += month_invested

            # XBI equivalent: invest same dollar amount in XBI
            if xbi_price > 0 and month_invested > 0:
                xbi_shares[sid] += month_invested / xbi_price

    print("  100% — simulation complete")
    print()

    # Build output DataFrames
    print("Building output DataFrames...")
    positions_df = _build_positions_df(positions, price_lookup, xbi_prices, trading_dates[-1], config)
    transactions_df = _build_transactions_df(transactions)
    performance_df = _build_performance_df(daily_values)

    print(f"  Positions: {len(positions_df)} rows")
    print(f"  Transactions: {len(transactions_df)} rows")
    print(f"  Performance: {len(performance_df)} rows")

    return positions_df, transactions_df, performance_df


# ---------------------------------------------------------------------------
# Output DataFrame builders
# ---------------------------------------------------------------------------

def _build_positions_df(
    positions: Dict[str, Dict[str, Position]],
    price_lookup: Dict[str, Dict[str, float]],
    xbi_prices: Dict[str, float],
    latest_date: str,
    config: StrategyConfig,
) -> pd.DataFrame:
    """Build the positions output DataFrame."""
    rows = []
    for sid, pos_dict in positions.items():
        strategy_id = sid.split(".")[0]
        variant = "enhanced" if sid.endswith(".1") else "base"
        for ticker, pos in pos_dict.items():
            current_price = price_lookup.get(ticker, {}).get(latest_date, 0)
            if pos.status == "sold":
                current_price = pos.sold_price or 0
                eval_date = pos.sold_date or latest_date
            else:
                eval_date = latest_date

            current_value = pos.shares * current_price
            total_return = (current_value - pos.cost_basis) / pos.cost_basis if pos.cost_basis > 0 else 0

            xbi_entry = xbi_prices.get(pos.entry_date, 0)
            xbi_eval = xbi_prices.get(eval_date, 0)
            xbi_return = (xbi_eval - xbi_entry) / xbi_entry if xbi_entry > 0 else 0

            entry_dt = datetime.strptime(pos.entry_date, "%Y-%m-%d")
            eval_dt = datetime.strptime(eval_date, "%Y-%m-%d")
            days_held = (eval_dt - entry_dt).days

            rows.append({
                "stream_id": sid,
                "strategy_id": strategy_id,
                "variant": variant,
                "ticker": ticker,
                "company_name": pos.company_name,
                "entry_date": pos.entry_date,
                "entry_price": pos.entry_price,
                "shares": pos.shares,
                "cost_basis": pos.cost_basis,
                "current_price": current_price,
                "current_value": current_value,
                "total_return": total_return,
                "xbi_return_since_entry": xbi_return,
                "relative_return_vs_xbi": total_return - xbi_return,
                "status": pos.status,
                "frozen_date": pos.frozen_date,
                "sold_date": pos.sold_date,
                "sold_price": pos.sold_price,
                "sell_reason": pos.sell_reason,
                "days_held": days_held,
                "sell_eligible": _months_held(pos.entry_date, eval_date) >= config.min_hold_months,
                "distance_to_hard_stop": total_return - config.hard_stop_return,
                "distance_to_relative_bleed": total_return - config.relative_bleed_return,
                "distance_to_freeze": total_return - config.freeze_return_threshold,
            })

    return pd.DataFrame(rows)


def _build_transactions_df(
    transactions: Dict[str, List[Dict]],
) -> pd.DataFrame:
    """Build the transactions output DataFrame."""
    all_rows = []
    for sid, txns in transactions.items():
        strategy_id = sid.split(".")[0]
        variant = "enhanced" if sid.endswith(".1") else "base"
        for txn in txns:
            txn["strategy_id"] = strategy_id
            txn["variant"] = variant
            all_rows.append(txn)
    return pd.DataFrame(all_rows)


def _build_performance_df(
    daily_values: Dict[str, List[Dict]],
) -> pd.DataFrame:
    """Build the performance output DataFrame."""
    all_rows = []
    for sid, values in daily_values.items():
        for v in values:
            invested = v["cumulative_invested"]
            port_val = v["portfolio_value"]
            xbi_val = v["xbi_value"]
            v["portfolio_return"] = (port_val - invested) / invested if invested > 0 else 0
            v["xbi_return"] = (xbi_val - invested) / invested if invested > 0 else 0
            all_rows.append(v)
    return pd.DataFrame(all_rows)
