import pandas as pd
import pytest
from pathlib import Path


@pytest.fixture()
def brokerage(monkeypatch, tmp_path):
    import utils.brokerage as b
    monkeypatch.setattr(b, "BROKERAGE_HOLDINGS_FILE", tmp_path / "brokerage_holdings.csv")
    monkeypatch.setattr(b, "STAGED_TRADES_FILE", tmp_path / "staged_trades.csv")
    monkeypatch.setattr(b, "TRADE_LOG_FILE", tmp_path / "trade_log.csv")
    return b


def test_load_brokerage_holdings_returns_empty_df_when_no_file(brokerage):
    df = brokerage.load_brokerage_holdings()
    assert df.empty
    assert list(df.columns) == ["ticker", "shares", "last_updated"]


def test_save_and_load_brokerage_holdings(brokerage):
    df = pd.DataFrame({"ticker": ["ABBV", "BEAM"], "shares": [100.0, 200.0], "last_updated": ["", ""]})
    brokerage.save_brokerage_holdings(df)
    loaded = brokerage.load_brokerage_holdings()
    assert set(loaded["ticker"]) == {"ABBV", "BEAM"}
    assert loaded[loaded["ticker"] == "ABBV"].iloc[0]["shares"] == 100.0


def test_save_staged_and_load(brokerage):
    staged = pd.DataFrame({
        "ticker": ["BEAM"],
        "action": ["BUY"],
        "suggested_shares": [142.0],
        "actual_shares": [141.0],
        "exec_price": [87.45],
        "notes": [""],
    })
    brokerage.save_staged_trades(staged)
    loaded = brokerage.load_staged_trades()
    assert len(loaded) == 1
    assert loaded.iloc[0]["ticker"] == "BEAM"


def test_confirm_execution_updates_holdings(brokerage):
    initial = pd.DataFrame({"ticker": ["ABBV"], "shares": [100.0]})
    brokerage.set_manual_holdings(initial)

    staged = pd.DataFrame({
        "ticker": ["ABBV", "BEAM"],
        "action": ["SELL", "BUY"],
        "suggested_shares": [10.0, 50.0],
        "actual_shares": [10.0, 50.0],
        "exec_price": [136.0, 62.0],
        "notes": ["", ""],
    })
    brokerage.confirm_execution(staged, strategy_name="Top-10 EW")

    holdings = brokerage.load_brokerage_holdings()
    abbv = holdings[holdings["ticker"] == "ABBV"].iloc[0]["shares"]
    beam = holdings[holdings["ticker"] == "BEAM"].iloc[0]["shares"]
    assert abbv == 90.0
    assert beam == 50.0


def test_manual_holdings_survive_subsequent_trade(brokerage):
    """A manually-entered starting position must not be wiped out by an unrelated trade.

    Regression test: confirm_execution() rebuilds brokerage_holdings.csv entirely from
    trade_log.csv (reconcile_holdings_from_log). A manual entry that never became a log
    row used to vanish the moment any trade — even in a different ticker — was confirmed.
    """
    brokerage.set_manual_holdings(pd.DataFrame({"ticker": ["ABBV"], "shares": [100.0]}))

    staged = pd.DataFrame({
        "ticker": ["BEAM"],
        "action": ["BUY"],
        "suggested_shares": [50.0],
        "actual_shares": [50.0],
        "exec_price": [62.0],
        "notes": [""],
    })
    brokerage.confirm_execution(staged, strategy_name="Top-10 EW")

    holdings = brokerage.load_brokerage_holdings()
    abbv = holdings[holdings["ticker"] == "ABBV"].iloc[0]["shares"]
    assert abbv == 100.0


def test_set_manual_holdings_logs_adjustment_entries(brokerage):
    """set_manual_holdings() records the delta as trade-log rows, not a side-channel write."""
    brokerage.set_manual_holdings(pd.DataFrame({"ticker": ["ABBV"], "shares": [100.0]}))
    log = brokerage.load_trade_log()
    assert len(log) == 1
    assert log.iloc[0]["ticker"] == "ABBV"
    assert log.iloc[0]["action"] == "BUY"
    assert log.iloc[0]["actual_shares"] == 100.0
    assert log.iloc[0]["strategy"] == "Manual Adjustment"


def test_set_manual_holdings_computes_delta_against_existing_position(brokerage):
    """A second manual edit logs only the difference from the current derived position."""
    brokerage.set_manual_holdings(pd.DataFrame({"ticker": ["ABBV"], "shares": [100.0]}))
    brokerage.set_manual_holdings(pd.DataFrame({"ticker": ["ABBV"], "shares": [80.0]}))

    log = brokerage.load_trade_log()
    assert len(log) == 2
    assert log.iloc[1]["action"] == "SELL"
    assert log.iloc[1]["actual_shares"] == 20.0

    holdings = brokerage.load_brokerage_holdings()
    assert holdings[holdings["ticker"] == "ABBV"].iloc[0]["shares"] == 80.0


def test_set_manual_holdings_closes_removed_position(brokerage):
    """Removing a ticker from the manual editor logs a SELL that zeroes it out."""
    brokerage.set_manual_holdings(pd.DataFrame({"ticker": ["ABBV"], "shares": [100.0]}))
    brokerage.set_manual_holdings(pd.DataFrame({"ticker": [], "shares": []}))

    holdings = brokerage.load_brokerage_holdings()
    abbv_rows = holdings[holdings["ticker"] == "ABBV"]
    assert abbv_rows.empty or abbv_rows.iloc[0]["shares"] == 0.0


def test_set_manual_holdings_noop_when_unchanged(brokerage):
    """Re-saving the same values logs no new rows."""
    brokerage.set_manual_holdings(pd.DataFrame({"ticker": ["ABBV"], "shares": [100.0]}))
    brokerage.set_manual_holdings(pd.DataFrame({"ticker": ["ABBV"], "shares": [100.0]}))
    log = brokerage.load_trade_log()
    assert len(log) == 1


def test_confirm_execution_writes_trade_log(brokerage):
    staged = pd.DataFrame({
        "ticker": ["BEAM"],
        "action": ["BUY"],
        "suggested_shares": [142.0],
        "actual_shares": [141.0],
        "exec_price": [87.45],
        "notes": ["test note"],
    })
    brokerage.confirm_execution(staged, strategy_name="Top-10 EW", notes="test")
    log = brokerage.load_trade_log()
    assert len(log) == 1
    assert log.iloc[0]["ticker"] == "BEAM"
    assert log.iloc[0]["strategy"] == "Top-10 EW"


def test_confirm_execution_clears_staged_trades(brokerage):
    staged = pd.DataFrame({
        "ticker": ["BEAM"], "action": ["BUY"],
        "suggested_shares": [10.0], "actual_shares": [10.0],
        "exec_price": [87.0], "notes": [""],
    })
    brokerage.save_staged_trades(staged)
    brokerage.confirm_execution(staged, strategy_name="Top-10 EW")
    remaining = brokerage.load_staged_trades()
    assert remaining.empty


def test_confirm_execution_uses_suggested_when_actual_is_nan(brokerage):
    """When actual_shares is NaN (user cleared the cell), falls back to suggested_shares."""
    import numpy as np
    staged = pd.DataFrame({
        "ticker": ["BEAM"],
        "action": ["BUY"],
        "suggested_shares": [142.0],
        "actual_shares": [np.nan],
        "exec_price": [87.45],
        "notes": [""],
    })
    brokerage.confirm_execution(staged, strategy_name="Top-10 EW")
    log = brokerage.load_trade_log()
    assert log.iloc[0]["actual_shares"] == 142.0  # fell back to suggested
    holdings = brokerage.load_brokerage_holdings()
    assert holdings[holdings["ticker"] == "BEAM"].iloc[0]["shares"] == 142.0
