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
    initial = pd.DataFrame({"ticker": ["ABBV"], "shares": [100.0], "last_updated": ["2026-01-01"]})
    brokerage.save_brokerage_holdings(initial)

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
