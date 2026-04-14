"""
Dashboard query API for strategy backtesting results.

Handles:
- Loading backtest output CSVs (positions, transactions, performance)
- Computing summary statistics across all 8 streams
- Generating sell/freeze alerts with distance-to-threshold
- Trade recommendations for the next trade day
- Filing comparison (diff view)
- Volume spike flags for enhanced variants

All functions are pure data — no Streamlit imports. Caching is done at the
page level. Functions return DataFrames or dicts suitable for direct display.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.csv_data import PROCESSED_DATA_DIR
from utils.strategy_config import STRATEGY_REGISTRY, STREAM_IDS, StrategyConfig


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

_POSITIONS_PATH = PROCESSED_DATA_DIR / "strategy_positions.csv"
_TRANSACTIONS_PATH = PROCESSED_DATA_DIR / "strategy_transactions.csv"
_PERFORMANCE_PATH = PROCESSED_DATA_DIR / "strategy_performance.csv"


def _load_csv(path: Path) -> pd.DataFrame:
    """Load a CSV, returning empty DataFrame if file doesn't exist."""
    if path.exists():
        df = pd.read_csv(path)
        # Ensure stream_id is string (pandas reads "1.0" as float 1.0)
        if "stream_id" in df.columns:
            df["stream_id"] = df["stream_id"].astype(str)
            # Fix "1.0" that pandas read as float -> "1.0" not "1."
            df["stream_id"] = df["stream_id"].apply(
                lambda x: f"{float(x):.1f}" if x.replace(".", "").isdigit() else x
            )
        return df
    return pd.DataFrame()


def load_positions() -> pd.DataFrame:
    """Load strategy_positions.csv."""
    return _load_csv(_POSITIONS_PATH)


def load_transactions() -> pd.DataFrame:
    """Load strategy_transactions.csv."""
    return _load_csv(_TRANSACTIONS_PATH)


def load_performance() -> pd.DataFrame:
    """Load strategy_performance.csv."""
    return _load_csv(_PERFORMANCE_PATH)


def backtest_data_exists() -> bool:
    """Check if backtest output CSVs exist."""
    return _POSITIONS_PATH.exists() and _PERFORMANCE_PATH.exists()


# ---------------------------------------------------------------------------
# Strategy info (from registry)
# ---------------------------------------------------------------------------

def get_strategy_info(strategy_id: str) -> dict:
    """Return metadata for a strategy from the registry."""
    return STRATEGY_REGISTRY.get(strategy_id, {
        "strategy_id": strategy_id,
        "name": f"Strategy {strategy_id}",
        "description": "",
        "benchmark": "XBI",
    })


# ---------------------------------------------------------------------------
# Summary across all streams
# ---------------------------------------------------------------------------

def get_all_streams_summary() -> pd.DataFrame:
    """Summary table for the Strategy Dashboard.

    Returns DataFrame with one row per stream: stream_id, strategy_name,
    variant, position counts, trailing returns, vs XBI, Sharpe ratio.
    """
    perf_df = load_performance()
    pos_df = load_positions()

    if perf_df.empty:
        return pd.DataFrame()

    rows = []
    for sid in STREAM_IDS:
        strategy_id = sid.split(".")[0]
        meta = get_strategy_info(strategy_id)
        variant = "Enhanced" if sid.endswith(".1") else "Base"

        # Position counts (from positions CSV — non-sold)
        sp = pos_df[pos_df["stream_id"] == sid]
        active = len(sp[sp["status"] == "active"])
        frozen = len(sp[sp["status"] == "frozen"])

        # Performance time-series for this stream
        stream_perf = perf_df[perf_df["stream_id"] == sid].copy()
        if stream_perf.empty:
            rows.append({
                "stream_id": sid,
                "strategy_name": meta["name"],
                "variant": variant,
                "active": active,
                "frozen": frozen,
                "total": active + frozen,
            })
            continue

        stream_perf = stream_perf.sort_values("date")
        latest = stream_perf.iloc[-1]
        latest_date = latest["date"]

        # Trailing returns from performance data
        return_data = _compute_trailing_returns(stream_perf, latest_date)

        # Sharpe ratio (annualized from daily returns)
        sharpe = _compute_sharpe(stream_perf)

        row = {
            "stream_id": sid,
            "strategy_name": meta["name"],
            "variant": variant,
            "active": active,
            "frozen": frozen,
            "total": active + frozen,
            "total_invested": latest["cumulative_invested"],
            "portfolio_value": latest["portfolio_value"],
            "total_return": latest["portfolio_return"] * 100,
            "sharpe": sharpe,
        }
        row.update(return_data)
        rows.append(row)

    return pd.DataFrame(rows)


def _compute_trailing_returns(
    stream_perf: pd.DataFrame,
    latest_date: str,
) -> Dict[str, Optional[float]]:
    """Compute trailing returns for various lookback periods."""
    result = {}
    latest_dt = pd.to_datetime(latest_date)

    periods = {
        "return_1m": 30,
        "return_3m": 91,
        "return_6m": 182,
        "return_1y": 365,
    }

    latest_row = stream_perf.iloc[-1]
    latest_port_val = latest_row["portfolio_value"]
    latest_xbi_val = latest_row["xbi_value"]

    for key, days in periods.items():
        cutoff = (latest_dt - timedelta(days=days)).strftime("%Y-%m-%d")
        past = stream_perf[stream_perf["date"] <= cutoff]
        if past.empty:
            result[key] = None
            result[key.replace("return", "vs_xbi")] = None
            continue

        past_row = past.iloc[-1]
        past_port_val = past_row["portfolio_value"]
        past_xbi_val = past_row["xbi_value"]
        past_invested = past_row["cumulative_invested"]

        if past_port_val > 0:
            port_ret = (latest_port_val - past_port_val) / past_port_val * 100
        elif past_invested > 0:
            port_ret = (latest_port_val - past_invested) / past_invested * 100
        else:
            port_ret = None

        if past_xbi_val > 0:
            xbi_ret = (latest_xbi_val - past_xbi_val) / past_xbi_val * 100
        else:
            xbi_ret = None

        result[key] = port_ret
        xbi_key = key.replace("return", "vs_xbi")
        if port_ret is not None and xbi_ret is not None:
            result[xbi_key] = port_ret - xbi_ret
        else:
            result[xbi_key] = None

    # YTD
    ytd_start = f"{latest_dt.year}-01-01"
    ytd_past = stream_perf[stream_perf["date"] <= ytd_start]
    if not ytd_past.empty:
        ytd_row = ytd_past.iloc[-1]
        if ytd_row["portfolio_value"] > 0:
            result["return_ytd"] = (latest_port_val - ytd_row["portfolio_value"]) / ytd_row["portfolio_value"] * 100
            if ytd_row["xbi_value"] > 0:
                xbi_ytd = (latest_xbi_val - ytd_row["xbi_value"]) / ytd_row["xbi_value"] * 100
                result["vs_xbi_ytd"] = result["return_ytd"] - xbi_ytd
            else:
                result["vs_xbi_ytd"] = None
        else:
            result["return_ytd"] = None
            result["vs_xbi_ytd"] = None
    else:
        result["return_ytd"] = None
        result["vs_xbi_ytd"] = None

    return result


def _compute_sharpe(
    stream_perf: pd.DataFrame,
    risk_free_annual: float = 0.05,
) -> Optional[float]:
    """Annualized Sharpe ratio from daily portfolio values."""
    if len(stream_perf) < 30:
        return None

    values = stream_perf["portfolio_value"].values
    # Skip leading zeros (before first trade)
    nonzero = np.nonzero(values)[0]
    if len(nonzero) < 30:
        return None

    values = values[nonzero[0]:]
    daily_returns = np.diff(values) / values[:-1]
    daily_returns = daily_returns[np.isfinite(daily_returns)]

    if len(daily_returns) < 30:
        return None

    daily_rf = (1 + risk_free_annual) ** (1 / 252) - 1
    excess = daily_returns - daily_rf
    std = np.std(excess, ddof=1)
    if std <= 0:
        return None

    return float(np.mean(excess) / std * np.sqrt(252))


# ---------------------------------------------------------------------------
# Per-stream queries
# ---------------------------------------------------------------------------

def get_stream_positions(stream_id: str) -> pd.DataFrame:
    """Current holdings for a stream (non-sold positions)."""
    pos_df = load_positions()
    if pos_df.empty:
        return pd.DataFrame()
    return pos_df[(pos_df["stream_id"] == stream_id) & (pos_df["status"] != "sold")].copy()


def get_stream_all_positions(stream_id: str) -> pd.DataFrame:
    """All positions (including sold) for a stream."""
    pos_df = load_positions()
    if pos_df.empty:
        return pd.DataFrame()
    return pos_df[pos_df["stream_id"] == stream_id].copy()


def get_stream_performance(
    stream_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Time-series performance for a stream, optionally filtered by date."""
    perf_df = load_performance()
    if perf_df.empty:
        return pd.DataFrame()

    df = perf_df[perf_df["stream_id"] == stream_id].copy()
    if start_date:
        df = df[df["date"] >= start_date]
    if end_date:
        df = df[df["date"] <= end_date]
    return df.sort_values("date")


def get_stream_transactions(
    stream_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """Trade log for a stream, optionally filtered by date."""
    txn_df = load_transactions()
    if txn_df.empty:
        return pd.DataFrame()

    df = txn_df[txn_df["stream_id"] == stream_id].copy()
    if start_date:
        df = df[df["date"] >= start_date]
    if end_date:
        df = df[df["date"] <= end_date]
    return df.sort_values("date", ascending=False)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

def get_sell_freeze_alerts(stream_id: str) -> pd.DataFrame:
    """Positions approaching sell or freeze thresholds.

    Returns DataFrame with columns: ticker, status, total_return,
    distance_to_hard_stop, distance_to_relative_bleed, distance_to_freeze,
    days_held, sell_eligible, alert_level.
    """
    positions = get_stream_positions(stream_id)
    if positions.empty:
        return pd.DataFrame()

    df = positions[["ticker", "status", "total_return", "days_held", "sell_eligible",
                     "distance_to_hard_stop", "distance_to_relative_bleed",
                     "distance_to_freeze"]].copy()

    # Alert level
    def _alert_level(row):
        dists = [row["distance_to_hard_stop"], row["distance_to_relative_bleed"],
                 row["distance_to_freeze"]]
        min_dist = min(dists)
        if min_dist <= 0.05:
            return "critical"
        elif min_dist <= 0.15:
            return "warning"
        return "ok"

    df["alert_level"] = df.apply(_alert_level, axis=1)
    # Only return warnings and critical
    df = df[df["alert_level"] != "ok"]
    return df.sort_values("distance_to_hard_stop")


# ---------------------------------------------------------------------------
# Volume spike flags (enhanced variants)
# ---------------------------------------------------------------------------

def get_volume_spike_flags(stream_id: str) -> pd.DataFrame:
    """Positions with volume spike flags from latest transactions."""
    txn_df = load_transactions()
    if txn_df.empty:
        return pd.DataFrame()

    stream_txns = txn_df[(txn_df["stream_id"] == stream_id) & (txn_df["action"] == "buy")]
    if stream_txns.empty:
        return pd.DataFrame()

    # Get latest transaction per ticker
    latest = stream_txns.sort_values("date").groupby("ticker").last().reset_index()
    flagged = latest[latest["volume_spike"] == True][["ticker", "date", "volume_spike"]]
    return flagged


# ---------------------------------------------------------------------------
# Filing comparison
# ---------------------------------------------------------------------------

def get_filing_comparison(
    strategy_id: str,
    old_filing_date: str,
    new_filing_date: str,
) -> pd.DataFrame:
    """Diff view: how a new filing changes a strategy's target portfolio.

    Returns DataFrame with columns: ticker, company_name, old_status,
    new_status, action_required.
    """
    txn_df = load_transactions()
    if txn_df.empty:
        return pd.DataFrame()

    # Look at transactions on/near the new filing date
    stream_base = f"{strategy_id}.0"
    txns = txn_df[
        (txn_df["stream_id"] == stream_base)
        & (txn_df["filing_date"] == new_filing_date)
    ]

    if txns.empty:
        return pd.DataFrame()

    rows = []
    for _, txn in txns.iterrows():
        rows.append({
            "ticker": txn["ticker"],
            "company_name": txn.get("company_name", ""),
            "action": txn["action"],
            "reason": txn["reason"],
            "date": txn["date"],
        })

    return pd.DataFrame(rows).drop_duplicates(subset="ticker", keep="last")
