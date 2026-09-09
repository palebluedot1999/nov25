"""Tests for utils/holdings_operations.py — keep every CUSIP, carry filing_value,
and detect position exits keyed on CUSIP (not ticker)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import pytest

from utils import csv_data
from utils import holdings_operations as ho
from utils import security_reference as sr

_FILING_COLS = [
    "company_name", "share_class", "cusip", "value", "shares", "option_type",
    "investment_discretion", "voting_authority_sole", "voting_authority_shared",
    "voting_authority_none", "ticker", "portfolio_id", "filing_date", "period_end_date",
]


def _filing(path, rows, filing_date, period_end):
    df = pd.DataFrame(rows)
    df["portfolio_id"] = "baker-bros"
    df["filing_date"] = filing_date
    df["period_end_date"] = period_end
    for c in _FILING_COLS:
        if c not in df.columns:
            df[c] = ""
    df[_FILING_COLS].to_csv(path, index=False)


@pytest.fixture
def filings_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ho, "FILINGS_DIR", tmp_path)
    # reference with one resolved, one unresolved CUSIP
    ref = tmp_path / "ref.csv"
    pd.DataFrame([
        {**{c: "" for c in sr._REFERENCE_COLS}, "cusip": "111111111", "ticker": "ACME",
         "name": "Acme Bio Inc.", "resolution_status": "resolved"},
        {**{c: "" for c in sr._REFERENCE_COLS}, "cusip": "999999999", "ticker": "",
         "name": "Ghost Inc", "resolution_status": "unresolved"},
    ]).to_csv(ref, index=False)
    monkeypatch.setattr(sr, "SECURITY_REFERENCE_FILE", ref)
    return tmp_path


def test_unresolved_position_is_kept_with_filing_value(filings_dir):
    _filing(filings_dir / "baker-bros_2025-02-14_holdings.csv", [
        {"company_name": "Acme Bio Inc.", "cusip": "111111111", "ticker": "ACME", "value": 100.0, "shares": 10},
        {"company_name": "Ghost Inc", "cusip": "999999999", "ticker": "", "value": 40.0, "shares": 4},
    ], "2025-02-14", "2024-12-31")

    out = ho.process_quarterly_filings_to_daily_holdings("baker-bros", start_date="2024-12-31", end_date="2025-01-05")

    assert set(out.columns) == {"portfolio", "cusip", "ticker", "shares", "filing_value", "eod_date"}
    ghost = out[out["cusip"] == "999999999"]
    assert not ghost.empty                      # NOT dropped
    assert (ghost["ticker"] == "").all()        # blank string, not NaN
    assert ghost["ticker"].isna().sum() == 0
    assert (ghost["filing_value"] == 40.0).all()


def test_exit_detected_for_blank_ticker_position(filings_dir):
    _filing(filings_dir / "baker-bros_2025-02-14_holdings.csv", [
        {"company_name": "Acme Bio Inc.", "cusip": "111111111", "ticker": "ACME", "value": 100.0, "shares": 10},
        {"company_name": "Ghost Inc", "cusip": "999999999", "ticker": "", "value": 40.0, "shares": 4},
    ], "2025-02-14", "2024-12-31")
    _filing(filings_dir / "baker-bros_2025-05-15_holdings.csv", [
        {"company_name": "Acme Bio Inc.", "cusip": "111111111", "ticker": "ACME", "value": 110.0, "shares": 11},
    ], "2025-05-15", "2025-03-31")

    out = ho.process_quarterly_filings_to_daily_holdings("baker-bros", start_date="2024-12-31", end_date="2025-04-01")

    ghost = out[(out["cusip"] == "999999999")]
    # a shares=0 record on the next period end (2025-03-31)
    assert (ghost["shares"] == 0.0).any()
    assert ghost[ghost["shares"] == 0.0]["eod_date"].iloc[0] == "2025-03-31"


def test_left_join_keeps_unpriced_rows():
    holdings = pd.DataFrame([
        {"portfolio": "baker-bros", "cusip": "111111111", "ticker": "ACME", "shares": 10,
         "filing_value": 100.0, "eod_date": "2025-01-02"},
        {"portfolio": "baker-bros", "cusip": "999999999", "ticker": "", "shares": 4,
         "filing_value": 40.0, "eod_date": "2025-01-02"},
        {"portfolio": "baker-bros", "cusip": "111111111", "ticker": "ACME", "shares": 10,
         "filing_value": 100.0, "eod_date": "2025-01-03"},   # price gap this day
    ])
    prices = pd.DataFrame([{"ticker": "ACME", "date": "2025-01-02", "close": 5.0}])

    out = ho.calculate_portfolio_values(holdings, prices)

    assert len(out) == 3                        # nothing dropped
    priced = out[(out["cusip"] == "111111111") & (out["eod_date"] == "2025-01-02")].iloc[0]
    assert priced["has_price"] is True or priced["has_price"] == True
    assert priced["position_value"] == 50.0
    gap = out[(out["cusip"] == "111111111") & (out["eod_date"] == "2025-01-03")].iloc[0]
    assert bool(gap["has_price"]) is False
    assert pd.isna(gap["position_value"])
    blank = out[out["cusip"] == "999999999"].iloc[0]
    assert bool(blank["has_price"]) is False


def test_save_processed_holdings_roundtrips_blank_tickers(tmp_path):
    df = pd.DataFrame([
        {"portfolio": "baker-bros", "cusip": "111111111", "ticker": "ACME", "shares": 10,
         "filing_value": 100.0, "eod_date": "2025-01-02"},
        {"portfolio": "baker-bros", "cusip": "999999999", "ticker": "", "shares": 4,
         "filing_value": 40.0, "eod_date": "2025-01-02"},
    ])
    out_file = tmp_path / "holdings.csv"
    ho.save_processed_holdings(df, out_file)
    back = pd.read_csv(out_file, dtype={"ticker": str}).fillna({"ticker": ""})
    assert list(back.columns) == ["portfolio", "cusip", "ticker", "shares", "filing_value", "eod_date"]
    # blank ticker sorts first lexically when eod_date ties (categorical sort, no error)
    assert back["ticker"].tolist() == ["", "ACME"]


def test_load_holdings_by_date_enriches_blank_ticker(tmp_path, monkeypatch):
    hd = tmp_path / "baker-bros_2025-02-14_holdings.csv"
    _filing(hd, [
        {"company_name": "Ghost Inc", "cusip": "999999999", "ticker": "", "value": 40.0, "shares": 4},
        {"company_name": "Acme Bio Inc.", "cusip": "111111111", "ticker": "", "value": 100.0, "shares": 10},
    ], "2025-02-14", "2024-12-31")
    monkeypatch.setattr(csv_data, "HOLDINGS_DIR", tmp_path)
    ref = tmp_path / "ref.csv"
    pd.DataFrame([
        {**{c: "" for c in sr._REFERENCE_COLS}, "cusip": "111111111", "ticker": "ACME",
         "name": "Acme Bio Inc.", "resolution_status": "resolved"},
    ]).to_csv(ref, index=False)
    monkeypatch.setattr(sr, "SECURITY_REFERENCE_FILE", ref)

    out = csv_data.load_holdings_by_date("baker-bros", "2025-02-14").set_index("cusip")
    assert out.loc["111111111", "ticker"] == "ACME"
    assert out.loc["999999999", "ticker"] == ""
    assert out.loc["999999999", "resolution_status"] == "unresolved"
