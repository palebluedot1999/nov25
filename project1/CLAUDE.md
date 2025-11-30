# Project Context for Claude

## Overview
Hedge fund portfolio tracker that scrapes SEC 13F filings and displays analysis in a Streamlit dashboard.

## Current State
- **CSV Migration Complete**: Fully operational with CSV-only storage
- **Target Fund**: Baker Bros. Advisors LP (CIK 1263508)
- **Benchmark**: XBI (SPDR S&P Biotech ETF)
- **Python**: 3.12.10 (installed via `py install 3.12`)
- **Historical Data**: 5 years (20 quarterly filings from 2021-2025)

## Setup Instructions
```bash
# Activate virtual environment
source .venv/Scripts/activate

# Initialize CSV data files (if needed)
python scripts/initialize_csv_files.py

# Backfill historical holdings (if needed)
python scripts/backfill_historical_holdings.py

# Run dashboard
streamlit run dashboard/app.py
```

## Tech Stack
- **Backend**: Python
- **Dashboard**: Streamlit
- **Storage**: CSV-only (no database)
- **Data Sources**: SEC EDGAR (13F filings), Yahoo Finance (prices)

## Key Files
- `dashboard/app.py` - Main Streamlit app (run with `streamlit run dashboard/app.py`)
- `scrapers/sec_edgar.py` - 13F filing scraper (outputs CSV)
- `scrapers/yahoo_finance.py` - Price data fetcher
- `utils/csv_data.py` - CSV data layer (replaces database)
- `utils/data_processing.py` - Data transformation utilities
- `utils/price_operations.py` - Smart incremental price fetching logic
- `utils/security_operations.py` - Security addition with OpenFIGI bi-directional lookup
- `utils/fund_operations.py` - Batch CIK processing and portfolio creation
- `scripts/fetch_all_prices.py` - Bulk fetch 5yr prices for all holdings
- `scripts/consolidate_prices.py` - Merge individual price files into master table
- `data/portfolios.csv` - Portfolio definitions
- `data/holdings/*.csv` - Historical quarterly holdings (one per filing)

## Data Structure
```
data/
├── portfolios.csv              # Portfolio metadata
├── strategies.csv              # Strategy definitions
├── tags.csv                    # Custom tags
├── transactions.csv            # Manual trade entries
├── raw/                        # Raw data from external sources
│   ├── cusip_cache.csv         # CUSIP↔Ticker mapping cache (160+ entries)
│   ├── 13f_filings/            # SEC 13F filings (one CSV per quarter)
│   │   ├── baker-bros_2021-02-16_holdings.csv
│   │   ├── baker-bros_2021-05-17_holdings.csv
│   │   └── ... (20 quarterly files)
│   └── yahoo_prices/           # Yahoo Finance price data (one CSV per ticker)
│       ├── AAPL.csv
│       ├── XBI.csv
│       └── ... (160 ticker files)
└── processed/                  # Processed/consolidated data
    └── prices.csv              # Master price table (all tickers consolidated with source column)
```

## Design Decisions
- **CSV-only storage**: Simplified architecture, no database overhead
- **One holdings CSV per quarter**: Each file includes filing_date and period_end_date columns
- **Positions tab shows latest filing**: Most recent CSV by filing date
- **Quarterly filing data used as cost basis for P&L**
- **Data fetched on-demand when dashboard loads** (no background scheduler)

## What's Working
- SEC EDGAR scraper for 13F filings (saves to CSV with dates)
- Yahoo Finance price fetcher (saves to CSV)
- **Bulk price fetcher** for all 160 holdings (5 years of data)
- **Smart incremental price updates** - Only fetches missing dates (checks raw files first, falls back to processed)
- **Price consolidation** into master prices.csv table (185K+ records)
- CSV data layer with all operations (portfolios, holdings, prices, transactions)
- Dashboard with Overview, Positions, Calendar, Data Management pages
- **Top 10 Holdings Weight Over Time** chart on Overview page
- **Trade entry form** on Positions page (date, time, ticker, direction, quantity, price, cost, strategy)
- Historical holdings view (20 quarters of Baker Bros data)
- **Redesigned Data Management page** with 4 sections:
  - Smart Price Pull: Incremental updates with progress tracking
  - Add New Security: Ticker/CUSIP resolution (see details below)
  - Add Fund Portfolio: Batch CIK processing with auto-name fetching from SEC
  - Process Raw Data: Consolidate raw files into master tables

### Add New Security Feature
Smart CUSIP/ticker resolution system in Data Management page:

**How it works:**
- **CUSIP → Ticker**: Auto-resolved via OpenFIGI API ✓
  - Primary use case: 13F filings provide CUSIPs
  - Works perfectly for adding securities from SEC filings
- **Ticker → CUSIP**: Cache lookup only
  - Checks `data/raw/cusip_cache.csv` first
  - If not found, prompts for manual CUSIP entry
  - Note: OpenFIGI and Yahoo Finance APIs don't provide CUSIP data (proprietary)
- **Both provided**: Added directly to cache

**Why this approach:**
- CUSIP data is proprietary (managed by CUSIP Global Services)
- Free APIs (OpenFIGI, Yahoo Finance) don't return CUSIPs
- For 13F filings workflow, we always have the CUSIP
- Manual entry fallback allows flexibility for edge cases

**Location:** `dashboard/pages/6_⚙️_Data_Management.py`
**Backend:** `utils/security_operations.py`
**Cache:** `data/raw/cusip_cache.csv` (160+ entries)

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
  - All tests passing ✓

### Requirements
```bash
pip install pytest pytest-cov
```

## Next Steps / Future Enhancements
- [ ] Update P&L and tracking error analysis modules to use CSV storage
- [ ] Add Whale Wisdom scraper
- [ ] Add DataRoma scraper
- [ ] Add more interactive Plotly charts
- [ ] Historical position change visualization (QoQ analysis)
- [ ] Multi-fund comparison view
- [ ] More unit tests for scrapers and analysis modules
- [x] ~~CUSIP-to-ticker mapping~~ (✓ Implemented via OpenFIGI API)
- [x] ~~CSV-only storage migration~~ (✓ Complete - database removed)
- [x] ~~Unit tests for security operations~~ (✓ 11 tests passing)

## User Preferences
- Wants flexibility to add more funds later
- Prefers data to load fresh on page open
- Interested in comprehensive analysis (P&L, tracking error, positions, calendar, benchmarks)

## Notes
- SEC requires User-Agent with contact email (configured in settings.py)
- 13F filings are quarterly, ~45 days after quarter end
- Values in 13F are reported in thousands (scraper multiplies by 1000)
- OpenFIGI API key is optional but recommended (set `OPENFIGI_API_KEY` env var)
- CUSIP cache auto-builds from 13F filings and can be viewed/edited in Data Management page
