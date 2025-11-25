"""
Yahoo Finance data fetcher for stock prices and benchmarks.
Updated to work with new database schema (securities, prices, benchmark_prices).
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict

from config.settings import DEFAULT_BENCHMARK
# Database functions removed - now using CSV storage via utils.csv_data


class YahooFinanceFetcher:
    """Fetcher for Yahoo Finance data."""

    def __init__(self):
        pass

    def get_stock_prices(
        self,
        ticker: str,
        start_date: str = None,
        end_date: str = None,
        period: str = "1y"
    ) -> pd.DataFrame:
        """
        Fetch historical prices for a stock.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            period: Period to fetch if dates not specified (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)

        Returns:
            DataFrame with OHLCV data
        """
        try:
            stock = yf.Ticker(ticker)

            if start_date and end_date:
                df = stock.history(start=start_date, end=end_date)
            else:
                df = stock.history(period=period)

            if df.empty:
                print(f"No data found for {ticker}")
                return pd.DataFrame()

            # Reset index to get date as column
            df = df.reset_index()
            df['ticker'] = ticker

            # Rename columns to match our schema
            df = df.rename(columns={
                'Date': 'date',
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })

            # Handle adjusted close if available
            if 'Adj Close' in df.columns:
                df = df.rename(columns={'Adj Close': 'adj_close'})
            else:
                df['adj_close'] = df['close']

            # Convert date to string format
            df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')

            return df[['ticker', 'date', 'open', 'high', 'low', 'close', 'adj_close', 'volume']]

        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")
            return pd.DataFrame()

    def get_multiple_stocks(
        self,
        tickers: list,
        start_date: str = None,
        end_date: str = None,
        period: str = "1y"
    ) -> pd.DataFrame:
        """Fetch prices for multiple stocks."""
        all_data = []

        for ticker in tickers:
            print(f"Fetching {ticker}...")
            df = self.get_stock_prices(ticker, start_date, end_date, period)
            if not df.empty:
                all_data.append(df)

        if all_data:
            return pd.concat(all_data, ignore_index=True)
        return pd.DataFrame()

    def get_current_price(self, ticker: str) -> Optional[float]:
        """Get the current/latest price for a stock."""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            return info.get('regularMarketPrice') or info.get('currentPrice')
        except Exception as e:
            print(f"Error getting current price for {ticker}: {e}")
            return None

    def get_current_prices(self, tickers: list) -> dict:
        """Get current prices for multiple stocks."""
        prices = {}
        for ticker in tickers:
            price = self.get_current_price(ticker)
            if price:
                prices[ticker] = price
        return prices

    def get_benchmark_data(
        self,
        benchmark: str = None,
        start_date: str = None,
        end_date: str = None,
        period: str = "1y"
    ) -> pd.DataFrame:
        """Fetch benchmark index data."""
        benchmark = benchmark or DEFAULT_BENCHMARK
        return self.get_stock_prices(benchmark, start_date, end_date, period)

    def save_prices_to_db(self, df: pd.DataFrame):
        """Save price data to database."""
        if df.empty:
            return

        # Add security_id if available
        prices = []
        for record in df.to_dict('records'):
            security = get_security_by_ticker(record['ticker'])
            record['security_id'] = security['id'] if security else None
            prices.append(record)

        insert_prices(prices)
        print(f"Saved {len(prices)} price records to database")

    def save_benchmark_prices_to_db(self, df: pd.DataFrame, portfolio_id: str):
        """
        Save benchmark price data to database.

        Args:
            df: DataFrame with price data
            portfolio_id: Portfolio ID (should be a benchmark portfolio)
        """
        if df.empty:
            return

        benchmark_prices = []
        for record in df.to_dict('records'):
            benchmark_prices.append({
                'portfolio_id': portfolio_id,
                'ticker': record['ticker'],
                'date': record['date'],
                'close': record['close'],
                'adj_close': record['adj_close']
            })

        insert_benchmark_prices(benchmark_prices)
        print(f"Saved {len(benchmark_prices)} benchmark price records to database")

    def get_stock_info(self, ticker: str) -> dict:
        """Get company info for a ticker."""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            return {
                'ticker': ticker,
                'name': info.get('longName') or info.get('shortName'),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'market_cap': info.get('marketCap'),
                'currency': info.get('currency', 'USD'),
                'exchange': info.get('exchange')
            }
        except Exception as e:
            print(f"Error getting info for {ticker}: {e}")
            return {'ticker': ticker}

    def enrich_security(self, ticker: str) -> bool:
        """
        Enrich an existing security with Yahoo Finance data (sector, industry, etc.).

        Args:
            ticker: Stock ticker to enrich

        Returns:
            True if successful, False otherwise
        """
        try:
            security = get_security_by_ticker(ticker)
            if not security:
                print(f"Security {ticker} not found in database")
                return False

            # Fetch info from Yahoo Finance
            info = self.get_stock_info(ticker)

            # Update security with enriched data
            security_data = {
                'cusip': security['cusip'],
                'ticker': ticker,
                'company_name': info.get('name') or security['company_name'],
                'share_class': security['share_class'],
                'asset_class': security['asset_class'] or 'stock',
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'exchange': info.get('exchange'),
                'is_active': security['is_active']
            }

            insert_security(security_data)
            print(f"Enriched security {ticker} with Yahoo Finance data")
            return True

        except Exception as e:
            print(f"Error enriching security {ticker}: {e}")
            return False

    def bulk_enrich_securities(self, tickers: List[str]):
        """
        Enrich multiple securities with Yahoo Finance data.

        Args:
            tickers: List of tickers to enrich
        """
        print(f"Enriching {len(tickers)} securities with Yahoo Finance data...")
        success_count = 0

        for ticker in tickers:
            if self.enrich_security(ticker):
                success_count += 1

        print(f"Successfully enriched {success_count}/{len(tickers)} securities")


def fetch_prices_for_holdings(tickers: list, period: str = "1y"):
    """Convenience function to fetch and save prices for holdings."""
    fetcher = YahooFinanceFetcher()
    df = fetcher.get_multiple_stocks(tickers, period=period)
    fetcher.save_prices_to_db(df)
    return df


def fetch_benchmark(benchmark: str = None, period: str = "1y"):
    """Convenience function to fetch and save benchmark data."""
    fetcher = YahooFinanceFetcher()
    df = fetcher.get_benchmark_data(benchmark, period=period)
    fetcher.save_prices_to_db(df)
    return df


if __name__ == "__main__":
    # Test fetching some biotech stocks and XBI benchmark
    fetcher = YahooFinanceFetcher()

    # Fetch benchmark
    print("Fetching XBI benchmark...")
    df = fetcher.get_benchmark_data(period="3mo")
    print(df.head())

    # Fetch a sample stock
    print("\nFetching SGEN (example biotech)...")
    df = fetcher.get_stock_prices("SGEN", period="3mo")
    print(df.head())

    # Get current price
    print("\nCurrent XBI price:", fetcher.get_current_price("XBI"))
