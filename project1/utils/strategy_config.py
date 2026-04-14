"""
Strategy backtesting configuration.

Handles:
- All tunable parameters as a StrategyConfig dataclass
- Strategy registry mapping IDs to metadata and selector functions
- Stream ID definitions (strategy × variant)
"""

from dataclasses import dataclass


@dataclass
class StrategyConfig:
    """All tunable parameters for the backtesting engine."""

    # Capital
    monthly_contribution: float = 1000.0

    # Position limits
    max_positions: int = 10
    min_hold_months: int = 3

    # Trade timing (Nth trading day of each month)
    trade_day: int = 1

    # Sell rules (evaluated after min_hold_months)
    hard_stop_return: float = -0.40
    relative_bleed_return: float = -0.25
    relative_bleed_xbi_underperformance: float = -0.15

    # Freeze rules (both must be true simultaneously)
    freeze_return_threshold: float = -0.10

    # Conviction cap (max single-name weight in monthly allocation)
    conviction_cap: float = 0.15

    # Enhanced variant parameters
    momentum_lookback: int = 21  # trading days (~1 month)
    volume_spike_multiplier: float = 2.0
    volume_spike_lookback_short: int = 5  # trading days
    volume_spike_lookback_long: int = 60  # trading days

    # Strategy 4: major step-up threshold
    step_up_threshold: float = 0.50  # 50% QoQ share increase

    # Benchmark
    benchmark_ticker: str = "XBI"

    # Portfolio ID for 13F data
    portfolio_id: str = "baker-bros"


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY = {
    "1": {
        "strategy_id": "1",
        "name": "Top Holdings, Equal Weight",
        "short_name": "Top EW",
        "description": (
            "Top 10 positions by 13F portfolio weight, "
            "equal weight capital allocation."
        ),
        "selector": "select_top_holdings",
        "weighting": "equal",
        "benchmark": "XBI",
    },
    "2": {
        "strategy_id": "2",
        "name": "Top Holdings, Conviction Rank",
        "short_name": "Top CR",
        "description": (
            "Top 10 positions by 13F portfolio weight, "
            "conviction-weighted allocation with 15% per-name cap."
        ),
        "selector": "select_top_holdings",
        "weighting": "conviction",
        "benchmark": "XBI",
    },
    "3": {
        "strategy_id": "3",
        "name": "Active Accumulation, Conviction Rank",
        "short_name": "Accum CR",
        "description": (
            "Top 10 actively accumulated positions (QoQ weight and shares both up), "
            "weighted by magnitude of QoQ weight change with 15% cap."
        ),
        "selector": "select_active_accumulation",
        "weighting": "conviction",
        "benchmark": "XBI",
    },
    "4": {
        "strategy_id": "4",
        "name": "New Initiations, Equal Weight",
        "short_name": "New Init EW",
        "description": (
            "New positions and major step-ups (shares delta >= 50%), "
            "equal weight allocation. May run fewer than 10 names."
        ),
        "selector": "select_new_initiations",
        "weighting": "equal",
        "benchmark": "XBI",
    },
}

STREAM_IDS = ["1.0", "1.1", "2.0", "2.1", "3.0", "3.1", "4.0", "4.1"]


def get_strategy_for_stream(stream_id: str) -> dict:
    """Return the strategy registry entry for a given stream ID."""
    strategy_id = stream_id.split(".")[0]
    return STRATEGY_REGISTRY[strategy_id]


def is_enhanced(stream_id: str) -> bool:
    """Return True if the stream is an enhanced (.1) variant."""
    return stream_id.endswith(".1")
