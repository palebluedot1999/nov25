"""
Profit and Loss (P&L) calculations for portfolio analysis.
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

# NOTE: This module needs updating to use CSV storage (utils.csv_data)
# Database imports removed - module not currently used by dashboard
# TODO: Update to use load_latest_holdings, get_all_filings, load_prices from utils.csv_data
from scrapers.yahoo_finance import YahooFinanceFetcher


class PnLCalculator:
    """Calculate profit and loss for portfolio positions."""

    def __init__(self, fund_id: str):
        self.fund_id = fund_id
        self.yahoo = YahooFinanceFetcher()

    def get_position_pnl(
        self,
        ticker: str,
        shares: float,
        cost_basis: float,
        current_price: float = None
    ) -> dict:
        """
        Calculate P&L for a single position.

        Args:
            ticker: Stock ticker
            shares: Number of shares
            cost_basis: Original cost basis (total value at purchase)
            current_price: Current price (fetched if not provided)

        Returns:
            Dictionary with P&L metrics
        """
        if current_price is None:
            current_price = self.yahoo.get_current_price(ticker)

        if current_price is None:
            return {
                'ticker': ticker,
                'shares': shares,
                'cost_basis': cost_basis,
                'current_value': None,
                'pnl': None,
                'pnl_percent': None,
                'error': 'Could not fetch current price'
            }

        current_value = shares * current_price
        pnl = current_value - cost_basis
        pnl_percent = (pnl / cost_basis * 100) if cost_basis > 0 else 0

        return {
            'ticker': ticker,
            'shares': shares,
            'cost_basis': cost_basis,
            'current_price': current_price,
            'current_value': current_value,
            'pnl': pnl,
            'pnl_percent': pnl_percent
        }

    def calculate_portfolio_pnl(
        self,
        reference_filing_id: int = None,
        current_prices: dict = None
    ) -> pd.DataFrame:
        """
        Calculate P&L for all positions.

        Uses a reference filing as the cost basis (e.g., previous quarter)
        and current prices for current value.

        Args:
            reference_filing_id: Filing ID to use as cost basis
            current_prices: Dict of ticker -> current price

        Returns:
            DataFrame with P&L for each position
        """
        # Get latest filing if no reference provided
        latest_filing = get_latest_filing(self.fund_id)
        if not latest_filing:
            return pd.DataFrame()

        holdings = get_holdings_for_filing(latest_filing['id'])

        if not holdings:
            return pd.DataFrame()

        # Fetch current prices for all tickers
        tickers = [h['ticker'] for h in holdings if h['ticker']]

        if current_prices is None and tickers:
            current_prices = self.yahoo.get_current_prices(tickers)

        results = []
        for holding in holdings:
            ticker = holding['ticker']
            shares = holding['shares']
            cost_basis = holding['value']  # Use reported value as cost basis

            if ticker and ticker in current_prices:
                current_price = current_prices[ticker]
                pnl_data = self.get_position_pnl(ticker, shares, cost_basis, current_price)
            else:
                # No ticker or price available
                pnl_data = {
                    'ticker': ticker or 'N/A',
                    'company_name': holding['company_name'],
                    'shares': shares,
                    'cost_basis': cost_basis,
                    'current_price': None,
                    'current_value': None,
                    'pnl': None,
                    'pnl_percent': None
                }

            pnl_data['company_name'] = holding['company_name']
            pnl_data['cusip'] = holding['cusip']
            results.append(pnl_data)

        df = pd.DataFrame(results)

        # Calculate totals
        if 'current_value' in df.columns:
            df['current_value'] = pd.to_numeric(df['current_value'], errors='coerce')
            df['pnl'] = pd.to_numeric(df['pnl'], errors='coerce')

        return df

    def calculate_period_pnl(
        self,
        start_date: str,
        end_date: str = None
    ) -> dict:
        """
        Calculate portfolio P&L over a time period.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (defaults to today)

        Returns:
            Dictionary with period P&L metrics
        """
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')

        # Get filings within the period
        all_filings = get_all_filings(self.fund_id)

        if not all_filings:
            return {}

        # Find start and end filings
        start_filing = None
        end_filing = None

        for filing in all_filings:
            if filing['report_date'] <= start_date:
                start_filing = filing
                break

        for filing in reversed(all_filings):
            if filing['report_date'] <= end_date:
                end_filing = filing
                break

        if not start_filing or not end_filing:
            return {}

        start_value = start_filing['total_value']
        end_value = end_filing['total_value']
        pnl = end_value - start_value
        pnl_percent = (pnl / start_value * 100) if start_value > 0 else 0

        return {
            'start_date': start_filing['report_date'],
            'end_date': end_filing['report_date'],
            'start_value': start_value,
            'end_value': end_value,
            'pnl': pnl,
            'pnl_percent': pnl_percent
        }

    def get_pnl_summary(self) -> dict:
        """Get summary P&L metrics for the portfolio."""
        df = self.calculate_portfolio_pnl()

        if df.empty:
            return {}

        total_cost = df['cost_basis'].sum()
        total_current = df['current_value'].sum()
        total_pnl = df['pnl'].sum()

        winners = df[df['pnl'] > 0]
        losers = df[df['pnl'] < 0]

        return {
            'total_cost_basis': total_cost,
            'total_current_value': total_current,
            'total_pnl': total_pnl,
            'total_pnl_percent': (total_pnl / total_cost * 100) if total_cost > 0 else 0,
            'num_winners': len(winners),
            'num_losers': len(losers),
            'biggest_winner': winners.nlargest(1, 'pnl').to_dict('records')[0] if len(winners) > 0 else None,
            'biggest_loser': losers.nsmallest(1, 'pnl').to_dict('records')[0] if len(losers) > 0 else None
        }


def calculate_simple_return(start_value: float, end_value: float) -> float:
    """Calculate simple return percentage."""
    if start_value == 0:
        return 0
    return (end_value - start_value) / start_value * 100


def calculate_holding_period_return(
    cash_flows: list,
    ending_value: float
) -> float:
    """
    Calculate holding period return with cash flows.

    Args:
        cash_flows: List of (date, amount) tuples (negative for contributions)
        ending_value: Ending portfolio value

    Returns:
        Holding period return as percentage
    """
    # Simple implementation - just sum cash flows
    total_invested = sum(-cf[1] for cf in cash_flows if cf[1] < 0)

    if total_invested == 0:
        return 0

    return (ending_value - total_invested) / total_invested * 100


if __name__ == "__main__":
    # Test P&L calculations
    calculator = PnLCalculator('baker-bros')

    print("Calculating portfolio P&L...")
    df = calculator.calculate_portfolio_pnl()

    if not df.empty:
        print(f"\nTop 5 positions by P&L:")
        print(df.nlargest(5, 'pnl')[['company_name', 'pnl', 'pnl_percent']])

        summary = calculator.get_pnl_summary()
        print(f"\nP&L Summary:")
        print(f"  Total P&L: ${summary.get('total_pnl', 0):,.0f}")
        print(f"  Return: {summary.get('total_pnl_percent', 0):.2f}%")
