"""
Portfolio Size Analysis

This page displays portfolio value over time by joining daily holdings with price data.
Shows 2025 YTD total portfolio value and position breakdown.
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.holdings_operations import (
    get_forward_filled_prices,
    calculate_portfolio_values
)
from utils.csv_data import load_portfolios
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

st.title("Portfolio Size Analysis")

# Portfolio selector
portfolios = load_portfolios(portfolio_type='fund').to_dict('records')
if not portfolios:
    st.warning("No portfolios found.")
    st.stop()

portfolio_options = {p['name']: p['id'] for p in portfolios}
selected_name = st.selectbox("Select Portfolio", list(portfolio_options.keys()))
portfolio_id = portfolio_options[selected_name]

# Load processed holdings
holdings_file = project_root / "data" / "processed" / "holdings.csv"

if not holdings_file.exists():
    st.error("Holdings data not found. Please run the consolidation script first.")
    st.info("Go to Data Management page and click 'Consolidate Holdings to Daily Table'")
    st.stop()

# Load and filter holdings
@st.cache_data
def load_holdings(portfolio_id: str, start_date: str):
    """Load holdings and filter to date range."""
    df = pd.read_csv(holdings_file)
    df = df[df['portfolio'] == portfolio_id]
    df = df[df['eod_date'] >= start_date]
    return df

# Load and forward-fill prices
@st.cache_data
def load_prices(start_date: str):
    """Load and forward-fill prices."""
    return get_forward_filled_prices(start_date=start_date)

# Date range: 2025 YTD
ytd_start = '2025-01-01'

with st.spinner("Loading holdings data..."):
    holdings_df = load_holdings(portfolio_id, ytd_start)

if holdings_df.empty:
    st.warning(f"No holdings data found for {selected_name} in 2025 YTD.")
    st.stop()

with st.spinner("Loading and forward-filling prices..."):
    prices_df = load_prices(ytd_start)

with st.spinner("Calculating position values..."):
    portfolio_values = calculate_portfolio_values(holdings_df, prices_df)

if portfolio_values.empty:
    st.warning("No position values could be calculated. Check if price data is available.")
    st.stop()

# Metrics row
st.markdown("---")
col1, col2, col3 = st.columns(3)

# Calculate latest values
latest_date = portfolio_values['eod_date'].max()
latest_values = portfolio_values[portfolio_values['eod_date'] == latest_date]
total_value = latest_values['position_value'].sum()
num_positions = len(latest_values[latest_values['shares'] > 0])

with col1:
    st.metric("Total Portfolio Value", f"${total_value:,.0f}")

with col2:
    st.metric("Number of Positions", f"{num_positions}")

with col3:
    date_range = f"{portfolio_values['eod_date'].min()} to {latest_date}"
    st.metric("Date Range", date_range)

st.markdown("---")

# Chart 1: Total Portfolio Value Over Time
st.subheader("Total Portfolio Value - 2025 YTD")

# Aggregate by date
daily_totals = portfolio_values.groupby('eod_date')['position_value'].sum().reset_index()
daily_totals.columns = ['Date', 'Total Value']

fig1 = px.line(
    daily_totals,
    x='Date',
    y='Total Value',
    title='Daily Portfolio Value',
    labels={'Total Value': 'Total Portfolio Value ($)'}
)

fig1.update_layout(
    hovermode='x unified',
    yaxis_tickformat='$,.0f',
    xaxis_title='Date',
    yaxis_title='Total Portfolio Value ($)',
    showlegend=False
)

fig1.update_traces(line_color='#1f77b4', line_width=2)

st.plotly_chart(fig1, use_container_width=True)

# Chart 2: Portfolio Composition by Position (Stacked Area)
st.subheader("Portfolio Composition by Position - 2025 YTD")

# Get top 10 holdings by average value
top_tickers = (
    portfolio_values.groupby('ticker')['position_value']
    .mean()
    .nlargest(10)
    .index.tolist()
)

# Create "Other" category
portfolio_values_display = portfolio_values.copy()
portfolio_values_display['display_ticker'] = portfolio_values_display['ticker'].apply(
    lambda x: x if x in top_tickers else 'Other'
)

# Aggregate by date and ticker
composition = (
    portfolio_values_display
    .groupby(['eod_date', 'display_ticker'])['position_value']
    .sum()
    .reset_index()
)

# Sort to put "Other" last in the legend
ticker_order = top_tickers + ['Other']
composition['display_ticker'] = pd.Categorical(
    composition['display_ticker'],
    categories=ticker_order,
    ordered=True
)
composition = composition.sort_values(['eod_date', 'display_ticker'])

fig2 = px.area(
    composition,
    x='eod_date',
    y='position_value',
    color='display_ticker',
    title='Position Values Stacked by Ticker',
    labels={
        'eod_date': 'Date',
        'position_value': 'Position Value ($)',
        'display_ticker': 'Position'
    }
)

fig2.update_layout(
    hovermode='x unified',
    yaxis_tickformat='$,.0f',
    xaxis_title='Date',
    yaxis_title='Position Value ($)',
    legend=dict(
        title='Position',
        orientation='v',
        yanchor='top',
        y=1,
        xanchor='left',
        x=1.02
    )
)

st.plotly_chart(fig2, use_container_width=True)

# Data table: Top 10 positions by current value
st.subheader("Top 10 Positions (Current)")

latest_positions = latest_values[latest_values['shares'] > 0].copy()
latest_positions = latest_positions.sort_values('position_value', ascending=False).head(10)

# Calculate percentage
latest_positions['weight'] = (latest_positions['position_value'] / total_value * 100).round(2)

display_df = latest_positions[['ticker', 'shares', 'close', 'position_value', 'weight']].copy()
display_df.columns = ['Ticker', 'Shares', 'Price', 'Position Value', 'Weight (%)']

# Format columns
display_df['Shares'] = display_df['Shares'].apply(lambda x: f"{x:,.0f}")
display_df['Price'] = display_df['Price'].apply(lambda x: f"${x:,.2f}")
display_df['Position Value'] = display_df['Position Value'].apply(lambda x: f"${x:,.0f}")
display_df['Weight (%)'] = display_df['Weight (%)'].apply(lambda x: f"{x:.2f}%")

st.dataframe(display_df, use_container_width=True, hide_index=True)

# Additional insights
st.markdown("---")
st.subheader("Portfolio Insights")

col1, col2 = st.columns(2)

with col1:
    # Portfolio change since start of year
    first_date = daily_totals['Date'].min()
    last_date = daily_totals['Date'].max()

    first_value = daily_totals[daily_totals['Date'] == first_date]['Total Value'].iloc[0]
    last_value = daily_totals[daily_totals['Date'] == last_date]['Total Value'].iloc[0]

    pct_change = ((last_value - first_value) / first_value * 100)
    dollar_change = last_value - first_value

    st.metric(
        "YTD Performance",
        f"{pct_change:+.2f}%",
        delta=f"${dollar_change:+,.0f}"
    )

with col2:
    # Average daily value
    avg_value = daily_totals['Total Value'].mean()
    st.metric("Average Daily Value", f"${avg_value:,.0f}")

# Export data option
st.markdown("---")
st.subheader("Export Data")

if st.button("Export Portfolio Values to CSV"):
    # Prepare export DataFrame
    export_df = portfolio_values[['eod_date', 'ticker', 'shares', 'close', 'position_value']].copy()
    export_df.columns = ['Date', 'Ticker', 'Shares', 'Close Price', 'Position Value']

    # Convert to CSV
    csv = export_df.to_csv(index=False)

    st.download_button(
        label="Download CSV",
        data=csv,
        file_name=f"{portfolio_id}_portfolio_values_2025_ytd.csv",
        mime="text/csv"
    )
