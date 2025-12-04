"""
Portfolio Size Analysis

This page displays portfolio value over time by joining daily holdings with price data.
Shows total portfolio value and position breakdown for any selected date range.
"""

import streamlit as st
import sys
from pathlib import Path
from datetime import datetime, timedelta

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

# Get available date range from holdings
@st.cache_data
def get_date_range(portfolio_id: str):
    """Get min and max dates available in holdings."""
    df = pd.read_csv(holdings_file)
    df = df[df['portfolio'] == portfolio_id]
    if df.empty:
        return None, None
    return df['eod_date'].min(), df['eod_date'].max()

min_date_str, max_date_str = get_date_range(portfolio_id)

if min_date_str is None:
    st.error(f"No holdings data found for {selected_name}")
    st.stop()

min_date = pd.to_datetime(min_date_str).date()
max_date = pd.to_datetime(max_date_str).date()

# Date range selector
st.markdown("---")
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    # Preset options
    today = datetime.now().date()
    current_year_start = datetime(today.year, 1, 1).date()

    preset_options = {
        "Year to Date": (current_year_start, max_date),
        "Last 3 Months": (max_date - timedelta(days=90), max_date),
        "Last 6 Months": (max_date - timedelta(days=180), max_date),
        "Last Year": (max_date - timedelta(days=365), max_date),
        "All Time": (min_date, max_date),
        "Custom": None
    }

    preset = st.selectbox("Date Range", list(preset_options.keys()), index=0)

if preset == "Custom":
    with col2:
        start_date = st.date_input("Start Date", value=current_year_start, min_value=min_date, max_value=max_date)
    with col3:
        end_date = st.date_input("End Date", value=max_date, min_value=min_date, max_value=max_date)
else:
    start_date, end_date = preset_options[preset]
    with col2:
        st.date_input("Start Date", value=start_date, min_value=min_date, max_value=max_date, disabled=True)
    with col3:
        st.date_input("End Date", value=end_date, min_value=min_date, max_value=max_date, disabled=True)

# Convert dates to strings
start_date_str = start_date.strftime('%Y-%m-%d')
end_date_str = end_date.strftime('%Y-%m-%d')

# Validate date range
if start_date > end_date:
    st.error("Start date must be before end date")
    st.stop()

st.markdown("---")

# Load and filter holdings
@st.cache_data
def load_holdings(portfolio_id: str, start_date: str, end_date: str):
    """Load holdings and filter to date range."""
    df = pd.read_csv(holdings_file)
    df = df[df['portfolio'] == portfolio_id]
    df = df[(df['eod_date'] >= start_date) & (df['eod_date'] <= end_date)]
    return df

# Load and forward-fill prices
@st.cache_data
def load_prices(start_date: str, end_date: str):
    """Load and forward-fill prices."""
    return get_forward_filled_prices(start_date=start_date, end_date=end_date)

with st.spinner("Loading holdings data..."):
    holdings_df = load_holdings(portfolio_id, start_date_str, end_date_str)

if holdings_df.empty:
    st.warning(f"No holdings data found for {selected_name} in selected date range.")
    st.stop()

with st.spinner("Loading and forward-filling prices..."):
    prices_df = load_prices(start_date_str, end_date_str)

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
st.subheader(f"Total Portfolio Value - {preset}")

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
st.subheader(f"Portfolio Composition by Position - {preset}")

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

    # Dynamic label based on preset
    if preset == "Year to Date":
        perf_label = "YTD Performance"
    elif preset == "Custom":
        perf_label = "Period Performance"
    else:
        perf_label = f"{preset} Performance"

    st.metric(
        perf_label,
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

    # Dynamic filename
    date_suffix = f"{start_date_str}_to_{end_date_str}".replace('-', '')

    st.download_button(
        label="Download CSV",
        data=csv,
        file_name=f"{portfolio_id}_portfolio_values_{date_suffix}.csv",
        mime="text/csv"
    )
