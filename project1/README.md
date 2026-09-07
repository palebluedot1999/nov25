# Hedge Fund Portfolio Tracker

A Python/Streamlit tool for tracking hedge fund 13F holdings and running a strategy-driven paper-trading brokerage workflow on top of them — scrape SEC 13F filings, derive a target portfolio from a strategy, compare it against your actual brokerage holdings, and log trades to close the drift.

## Quick Start

```bash
source .venv/Scripts/activate
streamlit run dashboard/Home.py
```

Open `http://localhost:8501` in your browser — it redirects straight to the Dashboard page.

## How it fits together

1. **Scrape** — SEC EDGAR 13F filings (`scrapers/sec_edgar.py`) and Yahoo Finance prices/fundamentals (`scrapers/yahoo_finance.py`) land in `data/raw/`.
2. **Strategy** — a strategy module in `strategies/` (auto-discovered by `utils/strategy_registry.py`) turns a fund's latest 13F holdings into a target weight per ticker.
3. **Drift** — `utils/drift.py` compares those targets against your actual brokerage holdings (`utils/brokerage.py`) and produces buy/sell recommendations.
4. **Trade** — you stage and confirm trades on the Trades page; confirmed trades are appended to `data/raw/trade_log.csv`, which is the single source of truth for your current holdings (`reconcile_holdings_from_log()` rebuilds `brokerage_holdings.csv` from it on every mutation).

## Dashboard Pages

| Page | What it's for |
|---|---|
| **Dashboard** | Header strip (targets last updated, last trade, drift age), portfolio value over time, drift table for the selected strategy |
| **Trades** | Stage recommended trades, confirm execution, manually edit current holdings ("My Holdings"), view/edit trade history |
| **Research** | Backtest a strategy over a date range, compare strategies, promote one to "Live" |
| **Signals** | Baker Bros holdings + QoQ analytics (Shares Δ%, Value Δ%, Weight Δ bp), multi-ticker price charts |
| **Admin** | Fetch 13Fs/prices/metadata, add securities, consolidate data files, batch-add funds by CIK |

## Project Structure

```
project1/
├── config/                  # App settings (SEC User-Agent, etc.)
├── scrapers/                 # SEC EDGAR + Yahoo Finance fetchers
├── strategies/                # Strategy modules (STRATEGY_CONFIG + generate_targets())
│   └── baker_bros_top10_ew.py
├── utils/
│   ├── csv_data.py            # CSV data layer
│   ├── strategy_registry.py   # Auto-discover strategies, Live/Research status
│   ├── brokerage.py           # Holdings/staged trades/trade log, derived from trade history
│   ├── drift.py               # Target vs. actual drift + trade recommendations
│   ├── strategy_engine.py     # Backtest simulation
│   ├── holdings_operations.py # Quarterly 13F → daily holdings, forward-filled pricing
│   ├── price_operations.py    # Parallel incremental price fetching
│   ├── security_operations.py / security_consolidation.py / metadata_operations.py
│   ├── fund_operations.py     # Batch CIK processing
│   └── data_processing.py     # QoQ change computation
├── dashboard/
│   ├── Home.py                # Redirects to Dashboard
│   └── pages/
│       ├── 1_Dashboard.py
│       ├── 2_Trades.py
│       ├── 3_Research.py
│       ├── 4_Signals.py
│       └── 5_Admin.py
├── scripts/                  # One-off init/backfill/consolidation scripts
├── tests/                    # pytest suite (brokerage, drift, strategy registry, security ops)
├── data/
│   ├── raw/                   # 13F filings, Yahoo prices, cusip cache, trade log, staged trades, brokerage holdings
│   └── processed/             # Master tables: prices, securities, holdings, qoq_changes
├── docs/                      # Design specs and implementation notes
└── requirements.txt
```

## Tech Stack

- **Python** 3.12, **Streamlit**, **Pandas**, **Plotly**
- **Storage**: CSV-only, no database
- **Data sources**: SEC EDGAR (13F filings), Yahoo Finance (prices + fundamentals), OpenFIGI (CUSIP↔ticker, optional)

## Setup

```bash
# 1. Python 3.12 + venv
py install 3.12
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv\Scripts\activate on cmd

# 2. Dependencies
pip install -r requirements.txt

# 3. Set your SEC User-Agent (required by SEC — needs a real contact email)
#    edit config/settings.py

# 4. Initialize CSV data files
python scripts/initialize_csv_files.py

# 5. (optional) Backfill 5 years of historical 13F filings
python scripts/backfill_historical_holdings.py

# 6. (optional) Fetch security fundamentals
python scripts/fetch_security_metadata.py

# 7. Run it
streamlit run dashboard/Home.py
```

Or drive the same steps from the dashboard's **Admin** page instead of the CLI.

## Default Fund

- **Baker Bros. Advisors LP** (CIK 1263508), benchmarked against **XBI**
- Add more funds via Admin → Advanced (batch CIK add), or by editing `data/raw/portfolios.csv` directly

## Testing

```bash
pytest tests/ -v
```

Covers brokerage (holdings/trade-log reconciliation), drift calculation, strategy registry discovery, and CUSIP/ticker resolution.

## Notes

- 13F filings are quarterly, filed ~45 days after quarter end; SEC reports position values in thousands (the scraper converts to dollars).
- Data is fetched on dashboard load — there's no background scheduler.
- CUSIP↔ticker mapping is cached in `data/raw/cusip_cache.csv` to minimize OpenFIGI calls.

## Open items

- P&L and tracking-error analysis (still placeholders)
- Whale Wisdom / DataRoma scrapers
- Multi-fund comparison view
- More unit test coverage for scrapers and analysis modules

## License

MIT
