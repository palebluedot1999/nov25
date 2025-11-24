"""
Filing Calendar page showing filing dates and events.
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.data_processing import get_historical_filings_dataframe
from utils.database import get_all_portfolios

st.title("Filing Calendar")

# Portfolio selector
portfolios = get_all_portfolios(portfolio_type='fund')
if not portfolios:
    st.warning("No fund portfolios found.")
    st.stop()

portfolio_options = {p['name']: p['id'] for p in portfolios}
selected_name = st.selectbox("Select Portfolio", list(portfolio_options.keys()))
portfolio_id = portfolio_options[selected_name]

df = get_historical_filings_dataframe(portfolio_id)

if df.empty:
    st.warning("No filing data available for this portfolio.")
    st.stop()

# Display filings table
display_cols = ['form_type', 'filing_date', 'report_date', 'total_value', 'num_positions']
available_cols = [col for col in display_cols if col in df.columns]
display_df = df[available_cols].copy()

# Format values
if 'total_value' in display_df.columns:
    display_df['total_value'] = (display_df['total_value'] / 1e9).round(2)

col_names = {
    'form_type': 'Form',
    'filing_date': 'Filing Date',
    'report_date': 'Report Date',
    'total_value': 'Total Value ($B)',
    'num_positions': 'Positions'
}
display_df.columns = [col_names.get(col, col) for col in available_cols]

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True
)
