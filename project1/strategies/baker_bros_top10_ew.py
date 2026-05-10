# strategies/baker_bros_top10_ew.py
STRATEGY_CONFIG = {
    "name": "Baker Bros Top-10 Equal Weight",
    "parameters": {
        "top_n": {"type": "int", "min": 1, "max": 50, "default": 10, "label": "Top N Holdings"},
        "min_weight_pct": {"type": "float", "min": 0.0, "max": 10.0, "default": 2.0, "label": "Min Weight (%)"},
        "rebal_threshold_bp": {"type": "int", "min": 10, "max": 500, "default": 50, "label": "Rebal Threshold (bp)"},
    },
}


def generate_targets(portfolio_id: str, filing_date: str | None = None, top_n: int = 10, min_weight_pct: float = 2.0, **kwargs) -> dict[str, float]:
    """Return {ticker: target_weight_pct} for the top-N equal-weight strategy."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.csv_data import load_holdings_by_date, get_all_filings

    if filing_date is None:
        filings = get_all_filings(portfolio_id)
        if filings.empty:
            return {}
        filing_date = str(filings.iloc[0]["filing_date"])

    holdings = load_holdings_by_date(portfolio_id, filing_date)
    if holdings.empty:
        return {}

    top = holdings.nlargest(top_n, "value")
    n = len(top)
    if n == 0:
        return {}

    weight = 100.0 / n
    if weight < min_weight_pct:
        return {}

    return {str(row["ticker"]): round(weight, 4) for _, row in top.iterrows()}
