import pandas as pd


def calculate_drift(
    target_weights: dict[str, float],
    brokerage_holdings: pd.DataFrame,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute drift between strategy targets and actual brokerage holdings.

    Args:
        target_weights: {ticker: weight_pct} from strategy.generate_targets()
        brokerage_holdings: DataFrame with columns [ticker, shares]
        prices: DataFrame with columns [ticker, close]

    Returns:
        DataFrame: ticker, target_weight, actual_weight, drift_bp, action
        Sorted by abs(drift_bp) descending.
    """
    merged = brokerage_holdings.merge(prices[["ticker", "close"]], on="ticker", how="left")
    merged["value"] = merged["shares"] * merged["close"].fillna(0)
    total_value = merged["value"].sum()

    actual_weights: dict[str, float] = {}
    if total_value > 0:
        for _, row in merged.iterrows():
            actual_weights[str(row["ticker"])] = row["value"] / total_value * 100

    all_tickers = set(target_weights) | set(actual_weights)
    rows = []
    for ticker in all_tickers:
        target = target_weights.get(ticker, 0.0)
        actual = actual_weights.get(ticker, 0.0)
        drift_bp = round((target - actual) * 100)
        if drift_bp > 0:
            action = "BUY"
        elif drift_bp < 0:
            action = "SELL"
        else:
            action = "HOLD"
        rows.append({
            "ticker": ticker,
            "target_weight": round(target, 2),
            "actual_weight": round(actual, 2),
            "drift_bp": drift_bp,
            "action": action,
        })

    df = pd.DataFrame(rows)
    df = df.sort_values("drift_bp", key=abs, ascending=False).reset_index(drop=True)
    return df


def generate_trade_recommendations(
    drift_df: pd.DataFrame,
    total_portfolio_value: float,
    prices: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convert drift into suggested share counts given a total portfolio value.

    Returns:
        DataFrame: ticker, action, drift_bp, suggested_shares, delta_value, price, priority
    """
    prices_dict = dict(zip(prices["ticker"], prices["close"]))
    rows = []
    for _, row in drift_df.iterrows():
        drift_bp = row["drift_bp"]
        if drift_bp == 0:
            continue
        ticker = row["ticker"]
        target_value = total_portfolio_value * row["target_weight"] / 100
        actual_value = total_portfolio_value * row["actual_weight"] / 100
        delta_value = target_value - actual_value
        price = prices_dict.get(ticker, 0.0)
        suggested_shares = round(delta_value / price) if price > 0 else 0
        abs_drift = abs(drift_bp)
        priority = "High" if abs_drift >= 100 else ("Medium" if abs_drift >= 50 else "Low")
        rows.append({
            "ticker": ticker,
            "action": row["action"],
            "drift_bp": drift_bp,
            "suggested_shares": suggested_shares,
            "delta_value": round(delta_value, 2),
            "price": round(price, 2),
            "priority": priority,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("drift_bp", key=abs, ascending=False).reset_index(drop=True)
