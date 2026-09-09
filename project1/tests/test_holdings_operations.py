"""Tests for utils/holdings_operations.py — keep every CUSIP, carry filing_value,
and detect position exits keyed on CUSIP (not ticker)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import pytest

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
