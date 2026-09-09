import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from utils.strategy_engine import _select_top_holdings


def test_select_top_holdings_gates_on_resolution_status():
    """Only resolution_status == 'resolved' rows are eligible for the top-N, even
    when a non-resolved row has a bigger value and a non-blank ticker (spec §7).

    Regression for Finding 1: the old filter was
    ``ticker.notna() & (ticker != "") & (value > 0)``, which would have kept the
    ticker_only row.
    """
    frame = pd.DataFrame([
        {"ticker": "RSV", "company_name": "Resolved Co", "value": 1_000_000,
         "resolution_status": "resolved"},
        {"ticker": "TKO", "company_name": "TickerOnly Co", "value": 9_000_000,
         "resolution_status": "ticker_only"},
    ])

    out = _select_top_holdings(frame, n=5)

    assert "TKO" not in set(out["ticker"])   # non-resolved, dropped despite larger value
    assert "RSV" in set(out["ticker"])       # resolved, kept
