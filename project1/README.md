# Hedge Fund Portfolio Tracker

A Python-based dashboard for tracking and analyzing hedge fund portfolios using SEC 13F filings.

## Features

- **SEC EDGAR Integration**: Scrape 13F filings directly from SEC EDGAR
- **Yahoo Finance Integration**: Fetch real-time and historical price data
- **Interactive Dashboard**: Streamlit-based UI viewable in browser
- **CSV-Only Storage**: Simplified architecture with no database dependencies
- **Analysis Tools**:
  - Portfolio positions and concentration metrics
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
│   ├── raw/
│   │   ├── cusip_cache.csv      # CUSIP-to-ticker mappings (OpenFIGI)
│   │   ├── 13f_filings/         # Quarterly holdings CSVs (one per filing)
│   │   └── sec_13f_filing_periods_*.csv  # Filing calendar data
│   ├── prices/                  # Price data CSVs (one per ticker)
│   └── processed/
│       └── calendar.csv         # Processed filing calendar
├── scripts/                      # Initialization and backfill scripts
│   ├── initialize_csv_files.py  # Create CSV data files
│   └── backfill_historical_holdings.py  # Fetch historical 13F data
├── analysis/                     # Analysis modules
│   ├── pnl.py                   # P&L calculations
│   ├── positions.py             # Position analysis
│   └── tracking_error.py        # Benchmark comparison
├── dashboard/                    # Streamlit dashboard
│   ├── app.py                   # Main dashboard app
│   ├── pages/                   # Dashboard pages
│   │   ├── 1_📊_Overview.py
│   │   ├── 2_📈_Positions.py    # Includes trade entry form
│   │   ├── 3_💰_P&L_Analysis.py
│   │   ├── 4_📉_Tracking_Error.py
│   │   ├── 5_📅_Calendar.py
│   │   └── 6_⚙️_Data_Management.py
│   └── components/              # Reusable UI components
├── utils/                        # Utilities
│   ├── csv_data.py              # CSV data layer (replaces database)
│   └── data_processing.py       # Data transformations
├── requirements.txt              # Dependencies
└── README.md
```

## Tech Stack

- **Python**: 3.12.10
- **Dashboard**: Streamlit
- **Storage**: CSV-only (no database)
- **Data Sources**:
  - SEC EDGAR (13F filings)
  - Yahoo Finance (price data)
  - OpenFIGI API (CUSIP-to-ticker mapping)

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

## Usage

### Running the Dashboard

```bash
streamlit run dashboard/app.py
```

The dashboard will open in your browser at `http://localhost:8501`.

### Dashboard Pages

1. **Overview**: Portfolio summary and key metrics
2. **Positions**: Current holdings with trade entry form
3. **P&L Analysis**: Performance calculations
4. **Tracking Error**: Benchmark comparison vs XBI
5. **Calendar**: SEC filing calendar and history
6. **Data Management**: Fetch new filings and manage data

### Fetching New Data

From the **Data Management** page:

1. **Fetch Latest 13F Filing**: Download most recent filing from SEC EDGAR
2. **Fetch Filing Calendar**: Update 13F filing due dates
3. **Fetch Benchmark Prices**: Get XBI price data for comparison

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
- **Yahoo Finance**: Stock prices and benchmark data
- **OpenFIGI**: CUSIP-to-ticker symbol mapping
- **Future**: Whale Wisdom, DataRoma

## Important Notes

- **13F Filings**: Reported quarterly, approximately 45 days after quarter end
- **Position Values**: SEC reports values in thousands; scraper converts to actual dollars
- **SEC Rate Limit**: 10 requests per second (enforced by User-Agent header)
- **CUSIP Mapping**: Cached in `data/raw/cusip_cache.csv` to minimize OpenFIGI API calls
- **Data Updates**: Dashboard fetches data on page load (no background scheduler)

## Development

### Running Tests

```bash
pytest tests/
```

### Code Structure

- **Scrapers**: Fetch raw data from external sources
- **Utils**: Data layer (`csv_data.py`) and transformations
- **Analysis**: Portfolio calculations and metrics
- **Dashboard**: Streamlit UI and visualization
- **Scripts**: One-time setup and backfill operations

## Future Enhancements

- [ ] Complete P&L and tracking error analysis modules for CSV storage
- [ ] Add Whale Wisdom scraper
- [ ] Add DataRoma scraper
- [ ] Historical position change visualization (QoQ analysis)
- [ ] Multi-fund comparison view
- [ ] Interactive Plotly charts
- [ ] Unit tests for scrapers and analysis modules

## License

MIT
