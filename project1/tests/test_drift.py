import pandas as pd
import pytest
from utils.drift import calculate_drift, generate_trade_recommendations


def make_prices(*tickers_prices):
    tickers, closes = zip(*tickers_prices)
    return pd.DataFrame({"ticker": list(tickers), "close": list(closes)})


def test_calculate_drift_no_holdings_all_buy():
    """With empty holdings, all target positions show as BUY."""
    targets = {"ABBV": 50.0, "BEAM": 50.0}
    holdings = pd.DataFrame(columns=["ticker", "shares"])
    prices = make_prices(("ABBV", 100.0), ("BEAM", 50.0))
    result = calculate_drift(targets, holdings, prices)
    assert set(result["ticker"]) == {"ABBV", "BEAM"}
    assert all(result["actual_weight"] == 0.0)
    assert all(result["action"] == "BUY")


def test_calculate_drift_perfectly_aligned():
    """Equal holdings at equal prices → zero drift."""
    targets = {"ABBV": 50.0, "BEAM": 50.0}
    holdings = pd.DataFrame({"ticker": ["ABBV", "BEAM"], "shares": [5.0, 10.0]})
    prices = make_prices(("ABBV", 100.0), ("BEAM", 50.0))
    # ABBV: 5*100=500, BEAM: 10*50=500 → each 50%
    result = calculate_drift(targets, holdings, prices)
    assert all(result["drift_bp"] == 0)
    assert all(result["action"] == "HOLD")


def test_calculate_drift_excess_position_is_sell():
    """Holding more than target produces negative drift and SELL action."""
    targets = {"ABBV": 30.0, "BEAM": 70.0}
    holdings = pd.DataFrame({"ticker": ["ABBV", "BEAM"], "shares": [5.0, 10.0]})
    prices = make_prices(("ABBV", 100.0), ("BEAM", 50.0))
    # ABBV: 500/1000=50% vs target 30% → -2000bp SELL
    result = calculate_drift(targets, holdings, prices)
    abbv = result[result["ticker"] == "ABBV"].iloc[0]
    assert abbv["drift_bp"] < 0
    assert abbv["action"] == "SELL"


def test_calculate_drift_sorted_by_abs_drift():
    """Rows are sorted by absolute drift descending."""
    targets = {"A": 90.0, "B": 10.0}
    holdings = pd.DataFrame({"ticker": ["A", "B"], "shares": [1.0, 9.0]})
    prices = make_prices(("A", 100.0), ("B", 100.0))
    result = calculate_drift(targets, holdings, prices)
    assert abs(result.iloc[0]["drift_bp"]) >= abs(result.iloc[1]["drift_bp"])


def test_calculate_drift_unknown_holding_shows_as_sell():
    """A holding not in targets appears with target_weight=0 and SELL action."""
    targets = {"ABBV": 100.0}
    holdings = pd.DataFrame({"ticker": ["ABBV", "EXTRA"], "shares": [5.0, 5.0]})
    prices = make_prices(("ABBV", 100.0), ("EXTRA", 100.0))
    result = calculate_drift(targets, holdings, prices)
    extra = result[result["ticker"] == "EXTRA"].iloc[0]
    assert extra["target_weight"] == 0.0
    assert extra["action"] == "SELL"


def test_generate_trade_recommendations_skips_zero_drift():
    """Positions with zero drift are excluded from recommendations."""
    drift_df = pd.DataFrame({
        "ticker": ["ABBV", "BEAM"],
        "action": ["HOLD", "BUY"],
        "target_weight": [50.0, 50.0],
        "actual_weight": [50.0, 0.0],
        "drift_bp": [0, 5000],
    })
    prices = make_prices(("ABBV", 100.0), ("BEAM", 50.0))
    result = generate_trade_recommendations(drift_df, total_portfolio_value=10000, prices=prices)
    assert "ABBV" not in result["ticker"].values
    assert "BEAM" in result["ticker"].values


def test_generate_trade_recommendations_calculates_shares():
    """Suggested shares = delta_value / price."""
    drift_df = pd.DataFrame({
        "ticker": ["BEAM"],
        "action": ["BUY"],
        "target_weight": [50.0],
        "actual_weight": [0.0],
        "drift_bp": [5000],
    })
    prices = make_prices(("BEAM", 50.0))
    result = generate_trade_recommendations(drift_df, total_portfolio_value=10000, prices=prices)
    # target_value = 10000 * 50% = 5000; actual = 0; delta = 5000; shares = 5000/50 = 100
    assert result.iloc[0]["suggested_shares"] == 100
