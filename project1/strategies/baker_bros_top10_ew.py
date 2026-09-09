# strategies/baker_bros_top10_ew.py
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

STRATEGY_CONFIG = {
    "name": "Baker Bros Top-10 Equal Weight",
    "parameters": {
        "top_n": {"type": "int", "min": 1, "max": 50, "default": 10, "label": "Top N Holdings"},
        "min_weight_pct": {"type": "float", "min": 0.0, "max": 10.0, "default": 2.0, "label": "Min Weight (%)"},
        "rebal_threshold_bp": {"type": "int", "min": 10, "max": 500, "default": 50, "label": "Rebal Threshold (bp)",
                               "note": "Enforced by drift layer, not generate_targets"},
    },
}


def generate_targets(portfolio_id: str, filing_date: str | None = None, top_n: int = 10, min_weight_pct: float = 2.0, **kwargs) -> dict[str, float]:
    """Return {ticker: target_weight_pct} for the top-N equal-weight strategy."""
    from utils.csv_data import load_holdings_by_date, get_all_filings

    if filing_date is None:
        filings = get_all_filings(portfolio_id)
        if filings.empty:
            return {}
        filing_date = str(filings.iloc[0]["filing_date"])

    holdings = load_holdings_by_date(portfolio_id, filing_date)
    if holdings.empty:
        return {}

    # Only tradable, price-joinable securities (ticker + FIGI). A blank ticker must
    # never become a "" target-weight key flowing to the drift layer / Trades page.
    # load_holdings_by_date enriches, so resolution_status is normally present; if a
    # future un-enriched path lacks the column, fall through without gating.
    if "resolution_status" in holdings.columns:
        holdings = holdings[holdings["resolution_status"] == "resolved"]
        if holdings.empty:
            return {}

    top = holdings.nlargest(top_n, "value")
    n = len(top)
    if n == 0:
        return {}

    weight = 100.0 / n
    if weight < min_weight_pct:
        warnings.warn(f"top_n={n} produces weight={weight:.1f}% which is below min_weight_pct={min_weight_pct}%")
        return {}

    return {str(row["ticker"]): round(weight, 4) for _, row in top.iterrows()}
