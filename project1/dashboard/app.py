"""
Main Streamlit dashboard application.
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import DASHBOARD_TITLE, DASHBOARD_PAGE_ICON

# Page configuration
st.set_page_config(
    page_title=DASHBOARD_TITLE,
    page_icon=DASHBOARD_PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
    }
    .stMetric {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Landing page
st.title("Hedge Fund Portfolio Tracker")

st.markdown("""
Welcome to the Hedge Fund Portfolio Tracker dashboard. This application helps you track and analyze hedge fund portfolios using SEC 13F filings.

### Features

- **📊 Overview**: Portfolio summary with key metrics and top holdings
- **📈 Positions**: Detailed holdings view with trade entry functionality
- **💰 P&L Analysis**: Profit/loss analysis (coming soon)
- **📉 Tracking Error**: Benchmark comparison and performance metrics (coming soon)
- **📅 Calendar**: Historical filing dates and portfolio snapshots
- **⚙️ Data Management**: Fetch and manage SEC filings and price data

### Getting Started

Use the sidebar to navigate to different pages. If you're setting up for the first time:

1. Go to **⚙️ Data Management** to initialize the database
2. Fetch SEC 13F filings for your target fund
3. Process the raw filings to populate the database
4. Explore the **📊 Overview** and **📈 Positions** pages to see your data

### Current Focus

**Target Fund**: Baker Bros. Advisors LP (CIK 1263508)
**Benchmark**: XBI (SPDR S&P Biotech ETF)
""")
