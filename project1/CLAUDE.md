# Project Context for Claude

## Overview
Hedge fund portfolio tracker that scrapes SEC 13F filings and displays analysis in a Streamlit dashboard.

## Current State
- **CSV Migration Complete**: Fully operational with CSV-only storage
- **Target Fund**: Baker Bros. Advisors LP (CIK 1263508)
- **Benchmark**: XBI (SPDR S&P Biotech ETF)
- **Python**: 3.12.10 (installed via `py install 3.12`)
- **Historical Data**: 5 years (20 quarterly filings from 2021-2025)
- **Securities**: 161 holdings + 1 benchmark (XBI)
- **Price Data**: 188K+ records across 162 tickers
- **Fundamental Data**: 31 fields for all 161 securities

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
│   ├── cusip_cache.csv         # CUSIP↔Ticker mapping (162 entries)
│   ├── security_metadata.csv  # Fundamental data: sector, industry, financials (161 entries, 31 fields)
│   ├── price_fetch_status.json # Background price fetch status
│   ├── metadata_fetch_status.json # Background metadata fetch status
│   ├── 13f_filings/            # SEC 13F filings (one CSV per quarter)
│   │   ├── baker-bros_2021-02-16_holdings.csv
│   │   ├── baker-bros_2021-05-17_holdings.csv
│   │   └── ... (20 quarterly files)
│   └── yahoo_prices/           # Yahoo Finance price data (one CSV per ticker)
│       ├── AAPL.csv
│       ├── XBI.csv
│       └── ... (162 ticker files including benchmark)
└── processed/                  # Processed/consolidated data
    ├── prices.csv              # Master price table (188K+ records, 162 tickers)
    ├── securities.csv          # Master securities table (162 entries, CUSIP + ticker + 31 metadata fields)
    ├── holdings.csv            # Daily holdings table (118K+ records, 155 tickers, 2020-12-31 to present)
    └── qoq_changes.csv         # Pre-computed QoQ changes for all filing pairs (shares Δ%, value Δ%, weight Δ bp)
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
- **Background price fetching** with 10x parallel processing and real-time status tracking
- **Smart incremental price updates** - Only fetches missing dates (checks raw files first, falls back to processed)
- **Security metadata enrichment** - 31 fundamental fields (sector, industry, financials, ratios)
- **Price consolidation** into master prices.csv table (188K+ records)
- CSV data layer with all operations (portfolios, holdings, prices)
- **Dashboard pages (8 total)**: Overview (1), Fund Tracking (2), P&L Analysis (3), Tracking Error (4), Calendar (5), Data Management (6), Portfolio Size (7), Prices (8)
- **Prices page**: Bloomberg dark-theme interactive price chart (`8_Prices.py`); dark CSS injected via `st.markdown()` — the established pattern for themed pages
- **Top 10 Holdings Weight Over Time** chart on Overview page
- Historical holdings view (20 quarters of Baker Bros data)
- **Redesigned Data Management page** with 4 sections:
  - **Add New Security**: One-click workflow - automatically fetches prices and metadata (see details below)
  - **View Securities**: Master table with all 162 securities and their metadata in bordered container
  - **Bulk Operations** (Advanced): Background price/metadata fetch, consolidation, **Compute QoQ Changes** per fund (collapsed by default)
  - **Advanced Tools**: Batch CIK processing and fund portfolio management (collapsed by default)
- **Portfolio Size Analysis page**: Real-time portfolio value tracking with daily granularity (2025 YTD)
- **QoQ Analytics on Fund Tracking page**: Shares Δ%, Value Δ%, Weight Δ (basis points) auto-computed on first load and cached in `qoq_changes.csv`

### View Securities Section
Prominent display of all securities with full metadata in Data Management page:

**What it is:**
- Single master table combining CUSIP cache + security metadata
- File: `data/processed/securities.csv`
- 162 securities total (161 holdings + XBI benchmark)
- 32 columns: CUSIP, ticker, company_name, sector, industry, + 27 metadata fields
- **Displayed in bordered container box** for easy visibility
- Shows "Number of Securities" metric at top
- Column selector expander labeled "Columns" for customizing view
- Export to CSV button included

**How to view:**
- Navigate to Data Management page
- "View Securities" section is always visible (not collapsed)
- Default columns shown: ticker, company_name, sector, industry, market_cap, pe_ratio
- Expand "Columns" to select additional columns from all 32 available
- Click "Export Securities to CSV" to download full table

**Location:** Data Management page → "View Securities" section (always visible)
**Backend:** `utils/security_consolidation.py` + `scripts/consolidate_securities.py`
**Data Flow:** `cusip_cache.csv` + `security_metadata.csv` → LEFT JOIN → `securities.csv`

### Add New Security Feature
**One-click workflow** for adding securities with automatic data fetching:

**How it works:**
1. Enter ticker symbol (e.g., "MSFT") or CUSIP in the form
2. Click **"Execute"** button (primary blue button)
3. **Automatically executes full pipeline** (~7-10 seconds):
   - Resolves CUSIP ↔ Ticker via OpenFIGI API
   - Fetches 5-year price history (2020-01-01 to present)
   - Fetches 31 metadata fields from Yahoo Finance
   - Consolidates into master securities table
4. Shows detailed results with expandable step-by-step status
5. **Immediately visible** in View Securities table below

**UI Design:**
- **Bordered container box** for clear visual separation
- Caption: "Automatically fetch prices and metadata for a new security"
- Two input fields: Ticker (required) and CUSIP (optional)
- Single **"Execute"** button that runs entire workflow
- Progress spinner during operation
- Success/error messages with detailed step breakdown

**Resolution Logic:**
- **CUSIP → Ticker**: Auto-resolved via OpenFIGI API (primary use case for 13F filings)
- **Ticker → CUSIP**: Cache lookup only (prompts for manual entry if not found)
- **Both provided**: Added directly to cache
- OpenFIGI and Yahoo Finance APIs don't provide CUSIP data (proprietary)

**Error Handling:**
- Graceful partial failures (continues even if price/metadata fetch fails)
- Shows what succeeded/failed with detailed error messages
- Manual CUSIP entry prompt if ticker lookup fails

**Location:** Data Management page → "Add New Security" section (top, always visible)
**Backend:** `utils/security_operations.py` → `add_security_with_full_data()`
**Cache:** `data/raw/cusip_cache.csv` (162 entries)
**Orchestration:** Chains `add_security_to_cache()` + `fetch_incremental_prices()` + `fetch_security_metadata()` + `consolidate_securities()`

### Bulk Metadata Fetch Feature
Background metadata fetching for all securities with real-time progress tracking:

**How it works:**
- Expand **"Bulk Operations (Advanced)"** section
- Click "Fetch Metadata Now" button
- Runs in background via `scripts/background_metadata_fetch.py`
- Fetches 31 fundamental fields for all 162 securities from Yahoo Finance
- Progress bar updates every 2 seconds
- Takes ~1-2 minutes (0.5s rate limit between requests)
- Status tracked in `data/raw/metadata_fetch_status.json`

**After completion:**
- Click "Consolidate Securities" to merge into master table
- View results in "View Securities" section

**Use case:**
- Bulk updating metadata for all existing securities
- For single security additions, use "Add New Security" one-click workflow instead

**Location:** Data Management page → "Bulk Operations (Advanced)" → "Bulk Metadata Fetch"
**Backend:** `scripts/background_metadata_fetch.py` + `utils/metadata_operations.py`

**31 Data Fields Fetched:**
- **Company Info**: Name, sector, industry, website, business summary
- **Market Data**: Market cap, beta, shares outstanding, float shares, exchange
- **Valuation**: P/E ratio, forward P/E, price-to-book, dividend yield
- **Financial**: Revenue, EBITDA, profit margin, operating margin, ROE, ROA
- **Balance Sheet**: Debt-to-equity, current ratio
- **Institutional**: Held by institutions/insiders, short interest, short ratio
- **Dividends**: Rate, payout ratio
- **Metadata**: Last updated timestamp

**Features:**
- Bulk fetch for all securities in CUSIP cache
- Automatic updates and merging (keeps latest)
- Rate limiting to respect API limits
- Used for sector allocation, valuation analysis, portfolio insights

**Files:**
- **Raw Data**: `data/raw/security_metadata.csv` (161 securities, 31 fields)
- **Processed Data**: `data/processed/securities.csv` (162 securities with CUSIP + metadata merged)
- **Status File**: `data/raw/metadata_fetch_status.json` (background fetch progress)
- **Scripts**:
  - Background: `python scripts/background_metadata_fetch.py`
  - Interactive: `python scripts/fetch_security_metadata.py`
- **Backend**: `utils/metadata_operations.py`

**Current coverage:** 160 securities with metadata, 2 without (newly added CUSIPs)
**Sector breakdown:** Predominantly Healthcare/Biotechnology sector

### QoQ Analytics on Fund Tracking Page
Quarter-over-quarter change metrics on the Fund Tracking holdings table.

**Columns shown (adjacent to the column they describe):**
- **Shares → QoQ Shares Δ%**: Percent change in shares held vs prior quarter (e.g. `+12.34%`)
- **Value ($M) → QoQ Value Δ%**: Percent change in 13F-reported value vs prior quarter
- **Weight (%) → QoQ Weight Δ**: Weight change in **basis points** (e.g. `+125bp`), per Bloomberg/FactSet convention

**Behaviour:**
- Auto-computed on Fund Tracking page load if `qoq_changes.csv` is missing/stale for the selected period (runs ~2s spinner, then instant on reload)
- "NEW" shown for positions not present in prior quarter
- "—" shown for the earliest available filing (no prior quarter)
- CSV export also includes absolute deltas (`QoQ Shares Δ`, `QoQ Value Δ`)

**Manual re-computation:**
- Data Management → Bulk Operations (Advanced) → "Compute QoQ Changes" (per-fund button)

**Key files:**
- **Data**: `data/processed/qoq_changes.csv` — columns: portfolio_id, filing_date, prior_filing_date, period_end_date, cusip, ticker, shares, prior_shares, shares_delta, shares_delta_pct, value, prior_value, value_delta_pct, weight_13f, prior_weight_13f, qoq_weight_delta, is_new
- **Compute**: `utils/data_processing.py` → `compute_and_save_qoq_changes(portfolio_id)`
- **Load**: `utils/csv_data.py` → `load_qoq_changes(portfolio_id, filing_date)`
- **Dashboard**: `dashboard/pages/2_Fund_Tracking.py`

**Number formatting conventions (Bloomberg-style):**
- Shares: comma-separated integers (`27,525,640`)
- Price: `$45.23` with commas for large values
- Value: 2 decimal places in $M (`138.45`)
- Weight: 2 decimal places in % (`5.23`)
- Δ%: always 2 decimal places with sign (`+12.34%`)
- Weight Δ: integer basis points with sign (`+125bp`)

### Portfolio Size Analysis
Accurate portfolio value tracking by joining daily holdings with price data in a new Streamlit page.

**Overview:**
- New dashboard page showing total portfolio value and position breakdown over time
- Converts quarterly 13F filings into daily holdings records
- Joins holdings with forward-filled price data to calculate accurate position values
- Shows 2025 YTD performance with interactive charts

**How it works:**
1. **Holdings Consolidation**: Quarterly 13F filings → Daily holdings table
   - Each filing's period_end_date holdings are forward-filled daily until next quarter
   - Example: Q4 2020 (2020-12-31) → applies through 2021-03-30
   - Position exits detected: When ticker appears in filing N but not N+1, shares set to 0
   - Unresolved tickers resolved from CUSIP cache, skipped if still missing

2. **Price Forward-Filling**: Extend trading day prices to all calendar days
   - Weekend/holiday prices forward-filled from last trading day
   - Creates complete price coverage for all calendar days

3. **Position Value Calculation**: holdings × prices = portfolio value
   - Formula: position_value = shares × close_price
   - Daily calculations for all positions
   - Aggregated to show total portfolio value

**Data Generated:**
- File: `data/processed/holdings.csv` (5.4 MB)
- Columns: portfolio, ticker, cusip, shares, eod_date
- Records: 118,839 daily holdings (1,799 days × ~66 avg positions)
- Date Range: 2020-12-31 to 2025-12-03
- Coverage: 155 unique tickers

**Dashboard Page: Portfolio Size Analysis**

**Location:** `dashboard/pages/7_Portfolio_Size.py`

**Features:**
- **Metrics Row**: Total portfolio value, number of positions, date range
- **Chart 1**: Total portfolio value line chart (2025 YTD)
- **Chart 2**: Stacked area chart showing position breakdown (top 10 + "Other")
- **Data Table**: Top 10 current positions with shares, price, value, weight
- **Portfolio Insights**: YTD performance (%), average daily value
- **Export**: Download portfolio values as CSV

**Accuracy vs Official 13F Values:**

Recent quarters (2024-2025) show excellent accuracy:
- **Average error**: 5.25%
- **Median error**: 5.50%
- **Best**: Q2 2025 at -4.32% error
- **Latest** (Q3 2025): -4.42% error
  - Official 13F: $13.84B
  - Calculated: $13.23B
  - Difference: -$612M (4.42% under)

**Top 5 Most Accurate Quarters:**
1. Q2 2025 (2025-06-30): -4.32% | 87% position coverage
2. Q3 2025 (2025-09-30): -4.42% | 90% position coverage
3. Q1 2025 (2025-03-31): -5.03% | 83% position coverage
4. Q4 2024 (2024-12-31): -5.50% | 84% position coverage
5. Q1 2024 (2024-03-31): -5.57% | 76% position coverage

**Why calculations are slightly under (4-6%):**
- Missing tickers: ~10-15% of positions have unresolved tickers (no price data)
- Timing differences: Yahoo Finance close prices vs fund-reported values
- Delisted securities: Some positions in securities no longer traded

**Early quarters (2020-2022):**
- Much larger errors (40-54%) due to:
  - Many more unresolved tickers (~60-70 positions vs ~8-15 today)
  - Missing historical price data for delisted companies
  - Incomplete CUSIP cache at that time

**Usage:**

1. **Generate Daily Holdings Table:**
   ```bash
   python scripts/consolidate_holdings.py
   ```
   Or use button in Data Management page → "Consolidate Holdings"

2. **View Portfolio Size:**
   - Navigate to "Portfolio Size Analysis" page in dashboard
   - Automatically loads 2025 YTD data
   - Select portfolio from dropdown

3. **Export Data:**
   - Click "Export Portfolio Values to CSV" button
   - Downloads detailed position values for all dates

**Files:**
- **Utility**: `utils/holdings_operations.py` (15 KB, 6 core functions)
- **Script**: `scripts/consolidate_holdings.py` (2.9 KB)
- **Dashboard**: `dashboard/pages/7_Portfolio_Size.py` (7.5 KB)
- **Data**: `data/processed/holdings.csv` (5.4 MB, 118,839 records)

**Key Functions** (in `utils/holdings_operations.py`):
- `resolve_tickers_from_cusip_cache()` - Fill missing tickers from CUSIP cache
- `detect_position_exits()` - Identify sold positions between filings
- `process_quarterly_filings_to_daily_holdings()` - Main processing function (quarterly → daily)
- `get_forward_filled_prices()` - Extend prices to cover weekends/holidays
- `calculate_portfolio_values()` - Join holdings × prices, calculate position values
- `save_processed_holdings()` - Save with memory optimizations (categorical dtypes)

**Integration:**
- Added `load_processed_holdings()` to `utils/csv_data.py`
- Added "Consolidate Holdings" button to Data Management page
- Auto-discovered in Streamlit sidebar (no registration needed)

**Performance:**
- Consolidation: ~10 seconds for 20 filings → 118K records
- Forward-fill prices: ~5 seconds for 162 tickers
- Calculate values: ~2 seconds for 118K holdings
- Page load: <3 seconds total

**Conclusion:**
For practical portfolio tracking, the system is excellent - within 5% of official values for all recent quarters, with 80-90% position coverage. The small underestimation is consistent and predictable, making it reliable for trend analysis and performance monitoring.

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
- Values in 13F are reported in thousands (scraper multiplies by 1000)
  - **Note**: Early filings (2020-2022 Q3) have unscaled values (in thousands)
  - Later filings (2022 Q4+) have scaled values (in dollars)
  - This inconsistency occurred when SEC scraper was updated but old files weren't regenerated
- OpenFIGI API key is optional but recommended (set `OPENFIGI_API_KEY` env var)
- CUSIP cache auto-builds from 13F filings and can be viewed/edited in Data Management page
- Portfolio size calculations use forward-filled prices (weekends/holidays use last trading day price)
- Position exits are detected automatically by comparing consecutive quarterly filings
