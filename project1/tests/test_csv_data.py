import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import pytest

from utils import csv_data
from utils.csv_data import _sanitize_ticker_for_filename, load_prices, save_prices


# --- _sanitize_ticker_for_filename (CodeQL py/path-injection) ----------------

@pytest.mark.parametrize("raw, expected", [
    ("aapl", "AAPL"),
    ("  msft ", "MSFT"),
    ("BRK.B", "BRK.B"),
    ("RDS-A", "RDS-A"),
    ("XBI", "XBI"),
    ("SRZNW", "SRZNW"),
])
def test_sanitize_accepts_and_normalizes_real_tickers(raw, expected):
    assert _sanitize_ticker_for_filename(raw) == expected


@pytest.mark.parametrize("bad", [
    "../secrets",
    "/etc/passwd",
    "a/b",
    "a\\b",
    "..",
    ".hidden",
    "-x",
    "",
    "   ",
    "A" * 21,
    "AA PL",
    "AAPL;rm",
    None,
    123,
])
def test_sanitize_rejects_path_separators_and_junk(bad):
    with pytest.raises(ValueError):
        _sanitize_ticker_for_filename(bad)


# --- the flagged call sites -------------------------------------------------

def test_load_prices_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(csv_data, "PRICES_DIR", tmp_path)
    # a real secret sitting one level up from PRICES_DIR
    (tmp_path.parent / "secret.csv").write_text("date,close\n2025-01-01,1\n")

    with pytest.raises(ValueError):
        load_prices("../secret")


def test_load_prices_unknown_valid_ticker_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(csv_data, "PRICES_DIR", tmp_path)
    out = load_prices("NOPE")
    assert isinstance(out, pd.DataFrame) and out.empty


def test_save_prices_stores_normalized_ticker_and_path(tmp_path, monkeypatch):
    monkeypatch.setattr(csv_data, "PRICES_DIR", tmp_path)
    df = pd.DataFrame({"date": ["2025-01-02"], "close": [10.0]})

    save_prices("  aapl ", df)

    written = tmp_path / "AAPL.csv"
    assert written.exists()
    back = pd.read_csv(written)
    assert set(back["ticker"]) == {"AAPL"}


def test_save_prices_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(csv_data, "PRICES_DIR", tmp_path)
    df = pd.DataFrame({"date": ["2025-01-02"], "close": [10.0]})

    with pytest.raises(ValueError):
        save_prices("../../evil", df)
    # nothing escaped PRICES_DIR
    assert not (tmp_path.parent.parent / "evil.csv").exists()
