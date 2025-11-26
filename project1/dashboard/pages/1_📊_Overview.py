"""
Portfolio Overview page.
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.data_processing import get_portfolio_summary, get_top_holdings_over_time
from utils.csv_data import load_portfolios

st.title("Portfolio Overview")

# Portfolio selector
portfolios = load_portfolios(portfolio_type='fund').to_dict('records')
if not portfolios:
    st.warning("No portfolios found. Please initialize data files from Data Management page.")
    st.stop()

portfolio_options = {p['name']: p['id'] for p in portfolios}
selected_name = st.selectbox("Select Portfolio", list(portfolio_options.keys()))
portfolio_id = portfolio_options[selected_name]

summary = get_portfolio_summary(portfolio_id)

if not summary:
    st.warning("No portfolio data available. Please fetch data first from the Data Management page.")
    st.stop()

# Key metrics
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "Total Value",
        f"${summary['total_value'] / 1e9:.2f}B" if summary['total_value'] > 1e9
        else f"${summary['total_value'] / 1e6:.2f}M"
    )

with col2:
    st.metric(
        "Positions",
        summary['num_positions']
    )

with col3:
    st.metric(
        "Report Date",
        summary['report_date']
    )

with col4:
    st.metric(
        "Filing Date",
        summary['filing_date']
    )

st.divider()

# Top holdings
st.subheader("Top 10 Holdings")

if summary['top_holdings']:
    import pandas as pd

    df = pd.DataFrame(summary['top_holdings'])

    display_df = df[['company_name', 'ticker', 'shares', 'value_millions', 'weight']].copy()
    display_df.columns = ['Company', 'Ticker', 'Shares', 'Value ($M)', 'Weight (%)']

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )

    # Pie chart of top holdings
    import plotly.express as px

    fig = px.pie(
        df,
        values='value',
        names='company_name',
        title='Portfolio Composition (Top 10)'
    )
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # Historical weight chart for top 10 holdings
    st.subheader("Top 10 Holdings Weight Over Time")

    historical_df = get_top_holdings_over_time(portfolio_id, top_n=10)

    if not historical_df.empty:
        # Create line chart
        fig_line = px.line(
            historical_df,
            x='filing_date',
            y='weight',
            color='ticker',
            labels={
                'filing_date': 'Filing Date',
                'weight': 'Portfolio Weight (%)',
                'ticker': 'Ticker'
            },
            title='Top 10 Holdings Weight Over Time',
            hover_data=['company_name']
        )

        # Update layout for better visibility
        fig_line.update_layout(
            hovermode='x unified',
            legend=dict(
                title='Ticker',
                orientation='v',
                yanchor='top',
                y=1,
                xanchor='left',
                x=1.02
            )
        )

        st.plotly_chart(fig_line, use_container_width=True)
    else:
        st.info("No historical data available for weight tracking.")
