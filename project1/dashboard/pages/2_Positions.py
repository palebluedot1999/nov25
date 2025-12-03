"""
Portfolio Positions page - shows all current holdings and trade entry.
"""

import streamlit as st
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.data_processing import get_holdings_dataframe
from utils.csv_data import (
    load_portfolios,
    add_transaction,
    load_transactions,
    delete_transaction,
    get_all_strategies
)
import pandas as pd
from datetime import date, datetime

st.title("Portfolio Positions")

# Portfolio selector
portfolios = load_portfolios().to_dict('records')
if not portfolios:
    st.warning("No portfolios found.")
    st.stop()

# Separate by type
fund_portfolios = [p for p in portfolios if p['portfolio_type'] == 'fund']
user_portfolios = [p for p in portfolios if p['portfolio_type'] == 'user']

portfolio_options = {}
if fund_portfolios:
    portfolio_options.update({f"[Fund] {p['name']}": p['id'] for p in fund_portfolios})
if user_portfolios:
    portfolio_options.update({f"[User] {p['name']}": p['id'] for p in user_portfolios})

if not portfolio_options:
    st.warning("No active portfolios found.")
    st.stop()

selected_name = st.selectbox("Select Portfolio", list(portfolio_options.keys()))
portfolio_id = portfolio_options[selected_name]

# Holdings display
df = get_holdings_dataframe(portfolio_id)

if not df.empty:
    # Filters
    col1, col2 = st.columns(2)
    with col1:
        min_weight = st.slider("Minimum Weight (%)", 0.0, 10.0, 0.0, 0.1)
    with col2:
        search = st.text_input("Search Company")

    # Apply filters
    filtered_df = df[df['weight'] >= min_weight]
    if search:
        filtered_df = filtered_df[
            filtered_df['company_name'].str.contains(search, case=False, na=False)
        ]

    # Display
    display_cols = ['company_name', 'ticker', 'cusip', 'shares', 'value_millions', 'weight']
    available_cols = [col for col in display_cols if col in filtered_df.columns]
    display_df = filtered_df[available_cols].copy()

    col_names = {
        'company_name': 'Company',
        'ticker': 'Ticker',
        'cusip': 'CUSIP',
        'shares': 'Shares',
        'value_millions': 'Value ($M)',
        'weight': 'Weight (%)'
    }
    display_df.columns = [col_names.get(col, col) for col in available_cols]

    st.dataframe(
        display_df.sort_values('Value ($M)', ascending=False) if 'Value ($M)' in display_df.columns else display_df,
        use_container_width=True,
        hide_index=True
    )

    st.info(f"Showing {len(filtered_df)} of {len(df)} positions")
else:
    st.warning("No position data available for this portfolio.")

st.divider()

# Trade Entry Section
st.subheader("Trade Entry")

with st.form("trade_form"):
    col1, col2, col3 = st.columns(3)

    with col1:
        trade_date = st.date_input("Date", value=date.today())
        trade_time = st.time_input("Time", value=datetime.now().time())
        ticker = st.text_input("Ticker", placeholder="e.g., AAPL")

    with col2:
        direction = st.selectbox("Direction", ["BUY", "SELL"])
        quantity = st.number_input("Quantity", min_value=0.0, step=1.0)
        price = st.number_input("Price", min_value=0.0, step=0.01)

    with col3:
        cost = st.number_input("Cost/Commission", min_value=0.0, step=0.01)

        # Strategy dropdown
        strategies = get_all_strategies()
        strategy_options = [""] + [s['name'] for s in strategies]
        strategy_name = st.selectbox("Strategy", strategy_options)

        notes = st.text_input("Notes", placeholder="Optional notes")

    submitted = st.form_submit_button("Add Trade")

    if submitted:
        if ticker and quantity > 0 and price > 0:
            # Calculate total value
            total_value = quantity * price
            if direction == "SELL":
                total_value = -total_value

            transaction_data = {
                'portfolio_id': portfolio_id,
                'ticker': ticker.upper(),
                'cusip': '',
                'transaction_date': trade_date.isoformat(),
                'transaction_time': trade_time.strftime('%H:%M:%S'),
                'transaction_type': direction,
                'quantity': quantity if direction == "BUY" else -quantity,
                'price': price,
                'fees': cost,
                'total_value': total_value,
                'strategy': strategy_name if strategy_name else '',
                'source': 'MANUAL',
                'filing_date': '',
                'notes': notes
            }
            add_transaction(transaction_data)
            st.success(f"Transaction added: {direction} {quantity} {ticker.upper()} @ ${price}")
            st.rerun()
        else:
            st.error("Please fill in ticker, quantity, and price.")

# Display transactions table
st.subheader("Transaction History")

trans_df = load_transactions(portfolio_id)

if not trans_df.empty:
    display_cols = ['id', 'transaction_date', 'transaction_time', 'ticker', 'transaction_type',
                   'quantity', 'price', 'fees', 'strategy', 'source']
    available_cols = [col for col in display_cols if col in trans_df.columns]
    display_trans = trans_df[available_cols].copy()

    col_names = {
        'id': 'ID',
        'transaction_date': 'Date',
        'transaction_time': 'Time',
        'ticker': 'Ticker',
        'transaction_type': 'Type',
        'quantity': 'Qty',
        'price': 'Price',
        'fees': 'Fees',
        'strategy': 'Strategy',
        'source': 'Source'
    }
    display_trans.columns = [col_names.get(col, col) for col in available_cols]

    st.dataframe(
        display_trans,
        use_container_width=True,
        hide_index=True
    )

    # Delete transaction option
    col1, col2 = st.columns([3, 1])
    with col1:
        trans_to_delete = st.number_input("Transaction ID to delete", min_value=1, step=1)
    with col2:
        if st.button("Delete Transaction"):
            delete_transaction(int(trans_to_delete))
            st.success(f"Transaction {trans_to_delete} deleted")
            st.rerun()
else:
    st.info("No transactions recorded yet for this portfolio.")
