# Project Context for Claude

## Overview
Hedge fund portfolio tracker that scrapes SEC 13F filings and displays analysis in a Streamlit dashboard.

## Current State
- **Phase 1 Complete**: Foundation built
- **Target Fund**: Baker Bros. Advisors LP (CIK 1263508)
- **Benchmark**: XBI (SPDR S&P Biotech ETF)
- **Python**: 3.12.10 (installed via `py install 3.12`)

## Setup Instructions
```bash
# Activate virtual environment
source .venv/Scripts/activate

# Initialize database (creates tables)
python -c "from utils.database import init_database; init_database()"

# Run dashboard
streamlit run dashboard/app.py
```

## Known Issues (To Debug)
- **Positions page KeyError**: `get_holdings_dataframe()` in `utils/data_processing.py` has edge case when database returns empty holdings but with a filing record. Need to trace the exact data flow.

## Tech Stack
- **Backend**: Python
- **Dashboard**: Streamlit
- **Storage**: SQLite + JSON/CSV hybrid
- **Data Sources**: SEC EDGAR, Yahoo Finance

## Key Files
- `dashboard/app.py` - Main Streamlit app (run with `streamlit run dashboard/app.py`)
- `scrapers/sec_edgar.py` - 13F filing scraper
- `scrapers/yahoo_finance.py` - Price data fetcher
- `utils/database.py` - SQLite schema and operations
- `config/funds.json` - Fund definitions

## Design Decisions
- SQLite for structured data (holdings, filings, prices)
- Raw JSON/CSV in `data/raw/` for scraper output before processing
- Quarterly filing data used as cost basis for P&L
- Data fetched on-demand when dashboard loads (no background scheduler)

## What's Working
- SEC EDGAR scraper for 13F filings
- Yahoo Finance price fetcher
- Database schema with all tables (funds, filings, holdings, prices, benchmarks, trades)
- Dashboard with Overview, Positions, Calendar, Data Management pages
- **Trade entry form** on Positions page (date, time, ticker, direction, quantity, price, cost, strategy)
- P&L and tracking error analysis modules (need price data to function)

## Next Steps / Future Enhancements
- [ ] Add Whale Wisdom scraper
- [ ] Add DataRoma scraper
- [ ] Implement CUSIP-to-ticker mapping (for accurate price lookups)
- [ ] Add more interactive Plotly charts
- [ ] Historical position change visualization
- [ ] Multi-fund comparison view
- [ ] Caching layer for performance
- [ ] Unit tests for scrapers and analysis

## User Preferences
- Wants flexibility to add more funds later
- Prefers data to load fresh on page open
- Interested in comprehensive analysis (P&L, tracking error, positions, calendar, benchmarks)

## Notes
- SEC requires User-Agent with contact email (configured in settings.py)
- 13F filings are quarterly, ~45 days after quarter end
- Values in 13F are reported in thousands (scraper multiplies by 1000)
