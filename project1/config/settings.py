"""
Application settings and configuration.
"""

from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
DATABASE_PATH = DATA_DIR / "portfolio.db"

# SEC EDGAR settings
SEC_EDGAR_BASE_URL = "https://www.sec.gov"
SEC_EDGAR_API_URL = "https://data.sec.gov"
SEC_USER_AGENT = "Portfolio Tracker (thomaspwiig@gmail.com)"  # SEC requires user agent with contact info

# Yahoo Finance settings
YAHOO_FINANCE_ENABLED = True

# Data refresh settings
CACHE_EXPIRY_HOURS = 24  # How long to cache data before refreshing

# Dashboard settings
DASHBOARD_TITLE = "Hedge Fund Portfolio Tracker"
DASHBOARD_PAGE_ICON = "📊"

# Default benchmark for tracking error
DEFAULT_BENCHMARK = "XBI"  # SPDR S&P Biotech ETF (relevant for Baker Bros)
