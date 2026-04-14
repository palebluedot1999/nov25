"""
Strategy-specific position selection logic.

Handles:
- Selecting candidate positions from 13F filing data
- Ranking candidates by strategy-specific conviction scores
- Returning standardized DataFrames consumed by the simulation engine

Each selector takes a filing's holdings DataFrame and the corresponding QoQ
changes DataFrame, and returns a ranked list of up to 10 candidates.
"""

import pandas as pd

from utils.strategy_config import StrategyConfig


def select_top_holdings(
    holdings_df: pd.DataFrame,
    qoq_df: pd.DataFrame,
    config: StrategyConfig,
) -> pd.DataFrame:
    """Select top 10 positions by 13F portfolio weight.

    Used by strategies 1 (equal weight) and 2 (conviction rank).
    The engine determines how to weight capital based on the strategy's
    weighting scheme; the conviction_score here is the portfolio weight
    so conviction-rank strategies can use it directly.

    Args:
        holdings_df: Current filing holdings with columns including
            ticker, cusip, company_name, shares, value.
        qoq_df: QoQ changes (unused for this selector, but kept for
            consistent interface).
        config: Strategy configuration.

    Returns:
        DataFrame with columns: ticker, company_name, conviction_score,
        selection_reason. Sorted by conviction_score descending, max 10 rows.
    """
    df = holdings_df.copy()

    # Filter to rows with valid ticker and positive value
    df = df[df["ticker"].notna() & (df["ticker"] != "") & (df["value"] > 0)]

    if df.empty:
        return _empty_candidates()

    # Calculate portfolio weight from value
    total_value = df["value"].sum()
    df["weight_pct"] = df["value"] / total_value * 100

    # Rank by weight, take top N
    df = df.nlargest(config.max_positions, "weight_pct")

    return pd.DataFrame({
        "ticker": df["ticker"].values,
        "company_name": df["company_name"].values,
        "conviction_score": df["weight_pct"].values,
        "selection_reason": "top_holding_by_weight",
    })


def select_active_accumulation(
    holdings_df: pd.DataFrame,
    qoq_df: pd.DataFrame,
    config: StrategyConfig,
) -> pd.DataFrame:
    """Select top 10 positions being actively accumulated.

    Used by strategy 3. Filters for positions where BOTH:
    - QoQ weight change is positive (weight increased)
    - QoQ shares change is positive (actually bought more shares)

    Ranked by magnitude of QoQ weight change. Conviction score is the
    weight change magnitude for conviction-rank allocation.

    Args:
        holdings_df: Current filing holdings.
        qoq_df: QoQ changes with columns: ticker, shares_delta_pct,
            qoq_weight_delta, company_name.
        config: Strategy configuration.

    Returns:
        DataFrame with columns: ticker, company_name, conviction_score,
        selection_reason. May return fewer than 10 if not enough qualify.
    """
    if qoq_df.empty:
        return _empty_candidates()

    df = qoq_df.copy()

    # Filter: both weight and shares increased
    df = df[
        df["ticker"].notna()
        & (df["ticker"] != "")
        & (df["qoq_weight_delta"] > 0)
        & (df["shares_delta_pct"] > 0)
    ]

    if df.empty:
        return _empty_candidates()

    # Rank by magnitude of weight change (largest positive first)
    df = df.nlargest(config.max_positions, "qoq_weight_delta")

    return pd.DataFrame({
        "ticker": df["ticker"].values,
        "company_name": df["company_name"].values,
        "conviction_score": df["qoq_weight_delta"].abs().values,
        "selection_reason": "active_accumulation",
    })


def select_new_initiations(
    holdings_df: pd.DataFrame,
    qoq_df: pd.DataFrame,
    config: StrategyConfig,
) -> pd.DataFrame:
    """Select new initiations and major step-ups.

    Used by strategy 4. Prioritizes:
    1. New initiations (is_new=True) — sorted by value descending
    2. Major step-ups (shares_delta_pct >= step_up_threshold) — sorted
       by shares_delta_pct descending

    May return fewer than 10 names. Does NOT backfill with lower-conviction
    names. All conviction scores are 1.0 (equal weight).

    Args:
        holdings_df: Current filing holdings.
        qoq_df: QoQ changes with columns: ticker, is_new, shares_delta_pct,
            company_name, value.
        config: Strategy configuration.

    Returns:
        DataFrame with columns: ticker, company_name, conviction_score,
        selection_reason. May return fewer than 10.
    """
    if qoq_df.empty:
        return _empty_candidates()

    df = qoq_df.copy()
    df = df[df["ticker"].notna() & (df["ticker"] != "")]

    # Handle is_new as string or bool
    if df["is_new"].dtype == object:
        df["is_new_bool"] = df["is_new"].str.lower() == "true"
    else:
        df["is_new_bool"] = df["is_new"].astype(bool)

    # 1. New initiations (prioritized)
    new_positions = df[df["is_new_bool"]].copy()
    new_positions = new_positions.sort_values("value", ascending=False)

    # 2. Major step-ups (shares increased >= threshold)
    threshold_pct = config.step_up_threshold * 100  # convert 0.50 to 50.0
    step_ups = df[
        ~df["is_new_bool"]
        & (df["shares_delta_pct"] >= threshold_pct)
    ].copy()
    step_ups = step_ups.sort_values("shares_delta_pct", ascending=False)

    # Combine: new initiations first, then step-ups, up to max_positions
    combined = pd.concat([new_positions, step_ups], ignore_index=True)
    # Remove duplicates (a ticker could theoretically appear in both)
    combined = combined.drop_duplicates(subset="ticker", keep="first")
    combined = combined.head(config.max_positions)

    if combined.empty:
        return _empty_candidates()

    reasons = []
    for _, row in combined.iterrows():
        if row["is_new_bool"]:
            reasons.append("new_initiation")
        else:
            reasons.append(f"step_up_{row['shares_delta_pct']:.0f}pct")

    return pd.DataFrame({
        "ticker": combined["ticker"].values,
        "company_name": combined["company_name"].values,
        "conviction_score": 1.0,  # equal weight for all
        "selection_reason": reasons,
    })


# ---------------------------------------------------------------------------
# Selector dispatch
# ---------------------------------------------------------------------------

SELECTOR_MAP = {
    "select_top_holdings": select_top_holdings,
    "select_active_accumulation": select_active_accumulation,
    "select_new_initiations": select_new_initiations,
}


def get_selector(selector_name: str):
    """Return the selector function by name."""
    return SELECTOR_MAP[selector_name]


def _empty_candidates() -> pd.DataFrame:
    """Return an empty candidates DataFrame with the correct schema."""
    return pd.DataFrame(
        columns=["ticker", "company_name", "conviction_score", "selection_reason"]
    )
