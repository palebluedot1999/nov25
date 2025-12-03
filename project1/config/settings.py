"""
Application settings and configuration.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent

# Load environment variables from .env file
load_dotenv(PROJECT_ROOT / '.env')
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# SEC EDGAR settings
SEC_EDGAR_BASE_URL = "https://www.sec.gov"
SEC_EDGAR_API_URL = "https://data.sec.gov"
SEC_USER_AGENT = "Portfolio Tracker (thomaspwiig@gmail.com)"  # SEC requires user agent with contact info

# Yahoo Finance settings
YAHOO_FINANCE_ENABLED = True

# OpenFIGI API settings (for CUSIP-to-ticker mapping)
# Tries environment variable first, falls back to hardcoded value
# Sign up for free API key at: https://www.openfigi.com/api
OPENFIGI_API_KEY = os.getenv('OPENFIGI_API_KEY', None)  # Set to None or your key here

# Data refresh settings
CACHE_EXPIRY_HOURS = 24  # How long to cache data before refreshing

# Dashboard settings
DASHBOARD_TITLE = "Hedge Fund Portfolio Tracker"
DASHBOARD_PAGE_ICON = "chart"

# Default benchmark for tracking error
DEFAULT_BENCHMARK = "XBI"  # SPDR S&P Biotech ETF (relevant for Baker Bros)
