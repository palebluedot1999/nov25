# Project Context for Claude

## Overview
Hedge fund portfolio tracker that scrapes SEC 13F filings and displays analysis in a Streamlit dashboard.

## Current State
- **Target Fund**: Baker Bros. Advisors LP (CIK 1263508)
- **Benchmark**: XBI (SPDR S&P Biotech ETF)

## Setup Instructions
```bash
# Activate virtual environment
source .venv/Scripts/activate

# Initialize CSV data files (if needed)
python scripts/initialize_csv_files.py

# Backfill historical holdings (if needed)
python scripts/backfill_historical_holdings.py

# Fetch security metadata (optional - enriches with fundamentals)
python scripts/fetch_security_metadata.py

# Run dashboard
streamlit run dashboard/app.py
```

## Key Files
- `dashboard/app.py` - Main Streamlit app (run with `streamlit run dashboard/app.py`)
- `scrapers/sec_edgar.py` - 13F filing scraper (outputs CSV)
- `scrapers/yahoo_finance.py` - Price data fetcher
- `utils/csv_data.py` - CSV data layer (replaces database)
- `utils/data_processing.py` - Data transformation utilities
- `utils/price_operations.py` - Smart incremental price fetching with parallel processing
- `utils/security_operations.py` - Security addition with OpenFIGI CUSIP/ticker lookup and one-click orchestration function
- `utils/metadata_operations.py` - Fetch and manage security fundamental data with background processing
- `utils/security_consolidation.py` - Merge CUSIP cache with metadata into master securities table
- `utils/fund_operations.py` - Batch CIK processing and portfolio creation
- `utils/holdings_operations.py` - Process quarterly 13F filings into daily holdings, forward-fill prices, calculate position values
- `scripts/background_price_fetch.py` - Background price fetching with status tracking
- `scripts/background_metadata_fetch.py` - Background metadata fetching with status tracking
- `scripts/fetch_all_prices.py` - Bulk fetch 5yr prices for all holdings
- `scripts/fetch_security_metadata.py` - Fetch fundamental data from Yahoo Finance
- `scripts/consolidate_prices.py` - Merge individual price files into master table
- `scripts/consolidate_securities.py` - Merge CUSIP cache + metadata into securities.csv
- `scripts/consolidate_holdings.py` - Process quarterly 13F filings into daily holdings table
- `scripts/backfill_13f_value_scale.py` - One-time migration: normalizes pre-2022-12-31 13F `value` from thousands to whole dollars. Run once per checkout, BEFORE any re-scrape; guarded against double-application.
- `utils/security_reference.py` - Sweep 13F CUSIPs, resolve identifiers (OpenFIGI + SEC company_tickers name-match), build the master security_reference.csv; `enrich_holdings_with_reference()` fills tickers/names everywhere
- `scripts/build_security_reference.py` - Build data/processed/security_reference.csv + a coverage report (flags: --force, --no-api)
- `config/security_overrides.csv` - Committed manual CUSIP->identifier overrides / suppressions
- `data/processed/security_reference.csv` - Master security reference: one row per CUSIP ever held, with identifiers + provenance + filing history
- `data/raw/portfolios.csv` - Portfolio definitions
- `data/raw/13f_filings/*.csv` - Historical quarterly 13F filings (one per filing)

## Design Decisions
- **CSV-only storage**: Simplified architecture, no database overhead
- **One holdings CSV per quarter**: Each file includes filing_date and period_end_date columns
- **Positions tab shows latest filing**: Most recent CSV by filing date
- **Quarterly filing data used as cost basis for P&L**
- **Data fetched on-demand when dashboard loads** (no background scheduler)

## Data Platform
Raw inputs live in `data/raw/`, derived tables in `data/processed/` (all gitignored; `config/security_overrides.csv` is the one committed data-shaped file). Full schema catalogue: `docs/superpowers/specs/2026-09-08-security-reference-data-design.md` §3.

## Strategies

The strategy/backtest system (`strategies/`, `utils/strategy_registry.py`, `utils/strategy_engine.py`, `utils/drift.py`) turns a fund's 13F holdings into target weights, backtests them, and drives the Trades/Research pages. See `docs/STRATEGIES.md` for the full roster of every strategy conceived (including ones that were built and later reverted) and `docs/backtest_log.csv` for every backtest run's parameters and results.

## What's Working
- SEC EDGAR scraper for 13F filings (saves to CSV with dates)
- Yahoo Finance price fetcher (saves to CSV)
- **Background price fetching** with 10x parallel processing and real-time status tracking
- **Smart incremental price updates** - Only fetches missing dates (checks raw files first, falls back to processed)
- **Security metadata enrichment** - 31 fundamental fields (sector, industry, financials, ratios)
- **Price consolidation** into master prices.csv table (188K+ records)
- CSV data layer with all operations (portfolios, holdings, prices)
- **Dashboard pages**: `1_Dashboard, 2_Trades, 3_Research, 4_Signals, 5_Admin`
- **Top 10 Holdings Weight Over Time** chart
- Historical holdings view (46 filings of Baker Bros data)
- **Redesigned Data Management** with 4 sections:
  - **Add New Security**: One-click workflow - automatically fetches prices and metadata (see `dashboard-feature-reference` skill)
  - **View Securities**: Master table with all 162 securities and their metadata in bordered container
  - **Bulk Operations** (Advanced): Background price/metadata fetch, consolidation, **Compute QoQ Changes** per fund (collapsed by default)
  - **Advanced Tools**: Batch CIK processing and fund portfolio management (collapsed by default)
- **Portfolio Size Analysis**: Real-time portfolio value tracking with daily granularity (2025 YTD)
- **QoQ Analytics**: Shares Δ%, Value Δ%, Weight Δ (basis points) auto-computed on first load and cached in `qoq_changes.csv`

Details on View Securities, Add New Security, Bulk Metadata Fetch, and QoQ Analytics: see the `dashboard-feature-reference` skill.

### Portfolio Size Analysis
Accurate portfolio value tracking by joining daily holdings with price data (`dashboard/pages/7_Portfolio_Size.py`, `utils/holdings_operations.py`). Full implementation details, accuracy analysis, and usage guide: see `docs/PORTFOLIO_SIZE_IMPLEMENTATION.md` and `docs/PORTFOLIO_SIZE_QUICKSTART.md`.

## Testing

Unit tests are located in the `tests/` directory.

### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_security_operations.py -v

# With coverage (requires pytest-cov)
pytest tests/ --cov=utils --cov=scrapers
```

### Test Files
- `tests/test_security_operations.py` - CUSIP/ticker resolution tests (11 tests)
  - Tests CUSIP→ticker auto-resolution via OpenFIGI
  - Tests ticker→CUSIP cache lookup
  - Tests input validation and edge cases
  - Tests adding securities to cache
  - All tests passing

### Requirements
```bash
pip install pytest pytest-cov
```

## Next Steps / Future Enhancements
- [ ] Implement P&L and tracking error analysis (currently placeholders in dashboard)
- [ ] Add Whale Wisdom scraper
- [ ] Add DataRoma scraper
- [ ] Add more interactive Plotly charts
- [x] ~~Historical position change visualization (QoQ analysis)~~ (Complete - Shares Δ%, Value Δ%, Weight Δ bp on Fund Tracking page)
- [ ] Multi-fund comparison view
- [ ] Date range selector for Portfolio Size page (currently hardcoded to 2025 YTD)
- [ ] Intraday holdings tracking (merge 13F filings + manual transactions)
- [ ] More unit tests for scrapers and analysis modules
- [x] ~~CUSIP-to-ticker mapping~~ (Implemented via OpenFIGI API)
- [x] ~~CSV-only storage migration~~ (Complete - database removed)
- [x] ~~Unit tests for security operations~~ (11 tests passing)
- [x] ~~Portfolio size estimation~~ (Complete - 118K daily holdings, 4-6% accuracy vs 13F filings)

## User Preferences
- Wants flexibility to add more funds later
- Prefers data to load fresh on page open
- Interested in comprehensive analysis (P&L, tracking error, positions, calendar, benchmarks)

## Notes
- SEC requires User-Agent with contact email (configured in settings.py)
- 13F filings are quarterly, ~45 days after quarter end
- 13F values are whole dollars. SEC's Form 13F amendment (effective for reporting
  periods ending 2022-12-31 and later) changed the required unit from thousands of
  dollars to whole dollars. New scrapes are normalized at ingestion by
  `normalize_13f_value()` in `scrapers/sec_edgar.py`. Filings scraped under the old
  scraper (periods before 2022-12-31) are still in thousands and must be corrected
  once per checkout by running `python scripts/backfill_13f_value_scale.py` and then
  regenerating `qoq_changes.csv`. Because `data/` is gitignored, each clone/worktree
  has its own data copy and needs its own one-time run — done BEFORE any re-scrape on
  that checkout, never after (the fixed scraper already emits whole dollars, and the
  backfill would double-scale them; a sentinel file and a per-share sanity check guard
  against that).
- Data-migration scripts that mutate `data/` (e.g. `scripts/backfill_13f_value_scale.py`)
  must be run in the canonical checkout, not a git worktree: `data/` is gitignored, so a
  worktree operates on a disposable private copy and its migration never reaches the repo.
- OpenFIGI API key is optional but recommended (set `OPENFIGI_API_KEY` env var)
- CUSIP cache auto-builds from 13F filings and can be viewed/edited in Data Management page
- Portfolio size calculations use forward-filled prices (weekends/holidays use last trading day price)
- Position exits are detected automatically by comparing consecutive quarterly filings
