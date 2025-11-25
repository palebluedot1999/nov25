"""
Filing Calendar page showing filing dates and events.
"""

import streamlit as st
import sys
from pathlib import Path
import pandas as pd
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.data_processing import get_historical_filings_dataframe
from utils.csv_data import load_portfolios
from config.settings import DATA_DIR

st.title("📅 Filing Calendar")

# Load SEC 13F filing calendar
calendar_file = DATA_DIR / "processed" / "calendar.csv"
if calendar_file.exists():
    calendar_df = pd.read_csv(calendar_file)

    st.subheader("13F Filing Calendar")
    st.caption("Standard quarterly filing periods and deadlines")

    # Extract years from the Quarter column
    calendar_df['Year'] = calendar_df['Quarter'].str.extract(r'(\d{4})')[0].astype(int)
    years = sorted(calendar_df['Year'].unique())

    # Year selector
    selected_year = st.selectbox("Select Year", years, index=0)

    # Filter by selected year
    year_df = calendar_df[calendar_df['Year'] == selected_year].copy()

    # Display quarters in a grid
    quarters = year_df.to_dict('records')

    # Create 4 columns for each quarter
    cols = st.columns(4)

    for idx, quarter_data in enumerate(quarters):
        with cols[idx]:
            st.markdown(f"### {quarter_data['Quarter']}")
            st.markdown(f"**Period:**")
            st.markdown(f"{quarter_data['Start Date']} - {quarter_data['End Date']}")
            st.markdown(f"**Filing Deadline:**")
            st.markdown(f"📌 {quarter_data['Filing Deadline']}")

    st.divider()

# Portfolio filing history
st.subheader("Portfolio Filing History")

# Portfolio selector
portfolios = load_portfolios(portfolio_type='fund').to_dict('records')
if not portfolios:
    st.warning("No fund portfolios found.")
    st.stop()

portfolio_options = {p['name']: p['id'] for p in portfolios}
selected_name = st.selectbox("Select Portfolio", list(portfolio_options.keys()))
portfolio_id = portfolio_options[selected_name]

df = get_historical_filings_dataframe(portfolio_id)

if df.empty:
    st.warning("No filing data available for this portfolio.")
else:
    # Display filings table
    display_cols = ['filing_date', 'period_end_date', 'total_value', 'num_positions']
    available_cols = [col for col in display_cols if col in df.columns]
    display_df = df[available_cols].copy()

    # Format values
    if 'total_value' in display_df.columns:
        display_df['total_value'] = (display_df['total_value'] / 1e9).round(2)

    col_names = {
        'filing_date': 'Filing Date',
        'period_end_date': 'Period End',
        'total_value': 'Total Value ($B)',
        'num_positions': 'Positions'
    }
    display_df.columns = [col_names.get(col, col) for col in available_cols]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )
