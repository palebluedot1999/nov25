# Hedge Fund Portfolio Tracker

A Python-based dashboard for tracking and analyzing hedge fund portfolios using SEC 13F filings.

## Features

- **SEC EDGAR Integration**: Scrape 13F filings directly from SEC EDGAR
- **Yahoo Finance Integration**: Fetch real-time and historical price data with smart incremental updates
- **Security Metadata Enrichment**: 31 fundamental data fields (sector, industry, financials, ratios)
- **Background Price Fetching**: Parallel processing (10x faster) with real-time progress tracking
- **Interactive Dashboard**: Streamlit-based UI viewable in browser
- **CSV-Only Storage**: Simplified architecture with no database dependencies
- **Analysis Tools**:
  - Portfolio positions and concentration metrics
  - Top 10 holdings weight over time visualization
  - P&L calculations
  - Tracking error vs benchmark
  - Filing calendar with 5-year historical data
  - Manual trade entry and tracking

## Project Structure

```
project1/
├── config/                       # Configuration files
│   └── settings.py              # App settings and SEC User-Agent
├── scrapers/                     # Data scraping modules
│   ├── sec_edgar.py             # SEC EDGAR 13F scraper
│   └── yahoo_finance.py         # Yahoo Finance price fetcher
├── data/                         # CSV-based data storage
│   ├── portfolios.csv           # Portfolio metadata
│   ├── strategies.csv           # Strategy definitions
│   ├── tags.csv                 # Custom tags for categorization
│   ├── transactions.csv         # Manual trade entries
│   ├── raw/                     # Raw data from external sources
│   │   ├── cusip_cache.csv      # CUSIP↔Ticker mappings (162 entries)
│   │   ├── security_metadata.csv # Fundamental data (161 securities, 31 fields)
│   │   ├── price_fetch_status.json # Background price fetch status tracking
│   │   ├── metadata_fetch_status.json # Background metadata fetch status tracking
│   │   ├── 13f_filings/         # SEC 13F quarterly holdings (one CSV per filing)
│   │   └── yahoo_prices/        # Yahoo Finance price data (one CSV per ticker)
│   └── processed/               # Processed/consolidated data
│       ├── prices.csv           # Master price table (188K+ records, 162 tickers)
│       └── securities.csv       # Master securities table (162 entries, CUSIP + metadata)
├── scripts/                      # Initialization and backfill scripts
│   ├── initialize_csv_files.py  # Create CSV data files
│   ├── backfill_historical_holdings.py # Fetch historical 13F filings
│   ├── background_price_fetch.py # Background price fetching with status tracking
│   ├── background_metadata_fetch.py # Background metadata fetching with status tracking
│   ├── fetch_all_prices.py      # Bulk fetch 5yr prices for all holdings
│   ├── fetch_security_metadata.py # Fetch fundamental data from Yahoo Finance
│   ├── consolidate_prices.py    # Merge individual price files into master table
│   └── consolidate_securities.py # Merge CUSIP cache + metadata into securities.csv
├── dashboard/                    # Streamlit dashboard
│   ├── app.py                   # Main dashboard app
│   ├── pages/                   # Dashboard pages
│   │   ├── 1_📊_Overview.py     # Portfolio summary with top holdings chart
│   │   ├── 2_📈_Positions.py    # Current holdings with trade entry form
│   │   ├── 3_💰_P&L_Analysis.py
│   │   ├── 4_📉_Tracking_Error.py
│   │   ├── 5_📅_Calendar.py
│   │   └── 6_⚙️_Data_Management.py # Smart price pull, security addition, fund batch processing
│   └── components/              # Reusable UI components
├── utils/                        # Utilities
│   ├── csv_data.py              # CSV data layer (replaces database)
│   ├── data_processing.py       # Data transformations
│   ├── price_operations.py      # Smart incremental price fetching with parallel processing
│   ├── security_operations.py   # Security addition with OpenFIGI CUSIP/ticker lookup
│   ├── metadata_operations.py   # Fetch and manage security fundamental data with background processing
│   ├── security_consolidation.py # Merge CUSIP cache with metadata into master securities table
│   └── fund_operations.py       # Batch CIK processing and portfolio creation
├── tests/                        # Unit tests
│   └── test_security_operations.py # Security operations tests (11 tests)
├── requirements.txt              # Dependencies
└── README.md
```

## Tech Stack

- **Python**: 3.12.10
- **Dashboard**: Streamlit
- **Storage**: CSV-only (no database)
- **Data Sources**:
  - SEC EDGAR (13F filings)
  - Yahoo Finance (price data and fundamental metadata)
  - OpenFIGI API (CUSIP-to-ticker mapping, optional)

## Setup

### 1. Install Python 3.12

```bash
py install 3.12
```

### 2. Create and activate virtual environment

```bash
python -m venv .venv
source .venv/Scripts/activate  # Windows Git Bash
# OR
.venv\Scripts\activate         # Windows CMD
# OR
source .venv/bin/activate      # Linux/macOS
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Update SEC User Agent

Edit `config/settings.py` and update `SEC_USER_AGENT` with your contact email (required by SEC).

### 5. Initialize CSV data files

```bash
python scripts/initialize_csv_files.py
```

This creates the necessary CSV files:
- `data/portfolios.csv` - Portfolio definitions
- `data/strategies.csv` - Strategy categories
- `data/tags.csv` - Custom tags
- `data/transactions.csv` - Manual trades

### 6. Backfill historical data (optional)

To fetch 5 years of historical 13F filings for Baker Bros:

```bash
python scripts/backfill_historical_holdings.py
```

This downloads 20 quarterly filings (2021-2025) to `data/raw/13f_filings/`.

### 7. Fetch security metadata (optional)

To enrich securities with fundamental data (sector, industry, financials):

```bash
python scripts/fetch_security_metadata.py
```

This fetches 31 fundamental fields for all 161 securities and saves to `data/raw/security_metadata.csv`.

## Usage

### Running the Dashboard

```bash
streamlit run dashboard/app.py
```

The dashboard will open in your browser at `http://localhost:8501`.

### Dashboard Pages

1. **Overview**: Portfolio summary, key metrics, and top 10 holdings weight over time chart
2. **Positions**: Current holdings with manual trade entry form
3. **P&L Analysis**: Performance calculations
4. **Tracking Error**: Benchmark comparison vs XBI
5. **Calendar**: SEC filing calendar and history
6. **Data Management**:
   - Smart Price Pull: Background fetching with parallel processing and progress tracking
   - Add New Security: Ticker/CUSIP resolution via OpenFIGI API with Securities view
   - Add Fund Portfolio: Batch CIK processing with auto-name fetching
   - Fetch Security Metadata: Background fetch of 31 fundamental fields with progress tracking
   - Process Raw Data: Consolidate securities and price files into master tables

### Fetching New Data

From the **Data Management** page:

1. **Smart Price Pull**: Automatically fetches missing price data for all 162 securities using parallel processing (10x faster). Runs in background with real-time progress tracking.
2. **Add New Security**: Add securities by ticker or CUSIP. CUSIP→ticker auto-resolved via OpenFIGI API. View all securities in the Securities expander.
3. **Add Fund Portfolio**: Batch add multiple funds by CIK with automatic SEC name lookup and holdings download.
4. **Fetch Security Metadata**: Background fetch of 31 fundamental fields (sector, industry, financials) for all securities. Takes ~1-2 minutes with rate limiting.
5. **Consolidate Securities**: Merge CUSIP cache with metadata into master `securities.csv` table (162 entries, 32 columns).
6. **Consolidate Prices**: Merge individual ticker price files into master `prices.csv` table.

### Manual Trade Entry

From the **Positions** page, use the trade entry form to log manual trades:
- Date and time
- Ticker symbol
- Direction (Buy/Sell)
- Quantity
- Price and total cost
- Strategy assignment

Trades are saved to `data/transactions.csv`.

### Command Line Usage

```python
# Fetch latest filing
from scrapers.sec_edgar import scrape_13f_filing
scrape_13f_filing(cik='1263508', portfolio_id='baker-bros')

# Get portfolio holdings
from utils.csv_data import get_latest_holdings
holdings = get_latest_holdings('baker-bros')

# Fetch price data
from scrapers.yahoo_finance import fetch_price_data
prices = fetch_price_data('AAPL', start_date='2024-01-01')
```

## Default Fund

The project is pre-configured to track:

- **Baker Bros. Advisors LP** (CIK: 1263508)
- **Benchmark**: XBI (SPDR S&P Biotech ETF)
- **Historical Data**: 20 quarterly filings (Q1 2021 - Q3 2025)
- **Securities**: 162 total (161 holdings + XBI benchmark)
  - 160 with full metadata (31 fields)
  - 2 without metadata (newly added)
- **Price Data**: 188K+ records across 162 tickers
- **Master Tables**:
  - `securities.csv`: 162 rows × 32 columns (CUSIP + ticker + metadata)
  - `prices.csv`: 188K+ rows × 10 columns (price history)

## Adding More Funds

Edit `data/portfolios.csv` to add additional funds:

```csv
portfolio_id,name,cik,benchmark,active
new-fund,New Fund Name,0001234567,SPY,true
```

Then use the Data Management page or run the scraper manually:

```python
from scrapers.sec_edgar import scrape_13f_filing
scrape_13f_filing(cik='0001234567', portfolio_id='new-fund')
```

## Data Format

### Holdings CSVs

Each quarterly filing is stored as a separate CSV in `data/raw/13f_filings/`:

```
baker-bros_2025-11-14_holdings.csv
```

Columns:
- `portfolio_id`: Fund identifier
- `filing_date`: Date filing was submitted
- `period_end_date`: Quarter end date
- `cusip`: Security CUSIP
- `ticker`: Stock ticker (mapped via OpenFIGI)
- `company_name`: Issuer name
- `shares`: Number of shares held
- `value`: Market value (in dollars, not thousands)
- `percent_of_portfolio`: Position weight

### Portfolio CSV

`data/portfolios.csv` defines tracked funds:

```csv
portfolio_id,name,cik,benchmark,active
baker-bros,Baker Bros. Advisors LP,1263508,XBI,true
```

## Data Sources

- **SEC EDGAR**: 13F-HR filings (quarterly institutional holdings)
- **Yahoo Finance**: Stock prices, benchmark data, and fundamental metadata (31 fields)
- **OpenFIGI**: CUSIP-to-ticker symbol mapping (optional, API key recommended)
- **Future**: Whale Wisdom, DataRoma

## Current Data Coverage

- **Securities**: 162 total from Baker Bros portfolio + benchmark
  - Holdings: 161 securities
  - Benchmark: XBI (SPDR S&P Biotech ETF)
  - With metadata: 160 securities
  - Without metadata: 2 securities (newly added)
- **Price Records**: 188K+ historical price records (5 years)
- **Metadata Fields**: 31 fundamental data points per security
  - Company info, market data, valuation ratios, financials, balance sheet, institutional holdings
- **Historical Period**: 5 years (2021-2025, 20 quarterly filings)
- **Master Tables**:
  - `securities.csv`: Complete security reference with CUSIP, ticker, and metadata
  - `prices.csv`: All historical price data consolidated

## Important Notes

- **13F Filings**: Reported quarterly, approximately 45 days after quarter end
- **Position Values**: SEC reports values in thousands; scraper converts to actual dollars
- **SEC Rate Limit**: 10 requests per second (enforced by User-Agent header)
- **CUSIP Mapping**: Cached in `data/raw/cusip_cache.csv` to minimize OpenFIGI API calls
- **Data Updates**: Dashboard fetches data on page load (no background scheduler)

## Development

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_security_operations.py -v

# With coverage
pytest tests/ --cov=utils --cov=scrapers
```

Current test coverage:
- `tests/test_security_operations.py` - 11 tests for CUSIP/ticker resolution (all passing)

### Code Structure

- **Scrapers**: Fetch raw data from external sources
- **Utils**: Data layer (`csv_data.py`) and transformations
- **Dashboard**: Streamlit UI and visualization
- **Scripts**: One-time setup and backfill operations

## Future Enhancements

- [ ] Implement P&L and tracking error analysis (currently placeholders in dashboard)
- [ ] Add Whale Wisdom scraper
- [ ] Add DataRoma scraper
- [ ] Historical position change visualization (QoQ analysis)
- [ ] Multi-fund comparison view
- [ ] More interactive Plotly charts
- [ ] More unit tests for scrapers and analysis modules
- [x] ~~CUSIP-to-ticker mapping~~ (✓ Implemented via OpenFIGI API)
- [x] ~~CSV-only storage migration~~ (✓ Complete - database removed)
- [x] ~~Background price fetching~~ (✓ Parallel processing with status tracking)
- [x] ~~Security metadata enrichment~~ (✓ 31 fundamental fields from Yahoo Finance)
- [x] ~~Securities master table~~ (✓ Consolidated CUSIP + ticker + metadata)
- [x] ~~Background metadata fetching~~ (✓ Real-time progress tracking)
- [x] ~~Unit tests for security operations~~ (✓ 11 tests passing)

## License

MIT
