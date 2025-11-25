"""
Tracking error analysis comparing portfolio returns to benchmark.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

from config.settings import DEFAULT_BENCHMARK
# NOTE: This module needs updating to use CSV storage (utils.csv_data)
# Database imports removed - module not currently used by dashboard
# TODO: Update to use load_prices, get_all_filings from utils.csv_data
from scrapers.yahoo_finance import YahooFinanceFetcher


class TrackingErrorAnalyzer:
    """Analyze tracking error vs benchmark."""

    def __init__(self, fund_id: str, benchmark: str = None):
        self.fund_id = fund_id
        self.benchmark = benchmark or DEFAULT_BENCHMARK
        self.yahoo = YahooFinanceFetcher()

    def get_benchmark_returns(
        self,
        start_date: str = None,
        end_date: str = None,
        period: str = "1y"
    ) -> pd.DataFrame:
        """Get benchmark daily returns."""
        df = self.yahoo.get_stock_prices(
            self.benchmark,
            start_date=start_date,
            end_date=end_date,
            period=period
        )

        if df.empty:
            return pd.DataFrame()

        df = df.sort_values('date')
        df['return'] = df['adj_close'].pct_change() * 100
        df['cumulative_return'] = (1 + df['return'] / 100).cumprod() - 1
        df['cumulative_return'] = df['cumulative_return'] * 100

        return df

    def get_portfolio_returns(self) -> pd.DataFrame:
        """
        Get portfolio returns based on filing values.

        Note: Since 13F filings are quarterly, this gives quarterly returns.
        """
        filings = get_all_filings(self.fund_id)

        if not filings:
            return pd.DataFrame()

        df = pd.DataFrame([dict(f) for f in filings])
        df = df.sort_values('report_date')

        # Calculate returns
        df['return'] = df['total_value'].pct_change() * 100
        df['cumulative_return'] = (1 + df['return'] / 100).cumprod() - 1
        df['cumulative_return'] = df['cumulative_return'] * 100

        return df

    def calculate_tracking_error(
        self,
        portfolio_returns: pd.Series,
        benchmark_returns: pd.Series
    ) -> float:
        """
        Calculate tracking error (standard deviation of return differences).

        Args:
            portfolio_returns: Series of portfolio returns
            benchmark_returns: Series of benchmark returns

        Returns:
            Annualized tracking error percentage
        """
        if len(portfolio_returns) != len(benchmark_returns):
            # Align returns
            min_len = min(len(portfolio_returns), len(benchmark_returns))
            portfolio_returns = portfolio_returns.tail(min_len)
            benchmark_returns = benchmark_returns.tail(min_len)

        return_diff = portfolio_returns.values - benchmark_returns.values
        tracking_error = np.std(return_diff)

        # Annualize (assuming quarterly returns for 13F)
        annualized_te = tracking_error * np.sqrt(4)

        return annualized_te

    def calculate_information_ratio(
        self,
        portfolio_returns: pd.Series,
        benchmark_returns: pd.Series
    ) -> float:
        """
        Calculate information ratio.

        IR = Active Return / Tracking Error
        """
        if len(portfolio_returns) < 2:
            return 0

        active_return = portfolio_returns.mean() - benchmark_returns.mean()
        tracking_error = self.calculate_tracking_error(portfolio_returns, benchmark_returns)

        if tracking_error == 0:
            return 0

        return active_return / tracking_error

    def calculate_beta(
        self,
        portfolio_returns: pd.Series,
        benchmark_returns: pd.Series
    ) -> float:
        """Calculate portfolio beta vs benchmark."""
        if len(portfolio_returns) < 2:
            return 1

        covariance = np.cov(portfolio_returns, benchmark_returns)[0, 1]
        variance = np.var(benchmark_returns)

        if variance == 0:
            return 1

        return covariance / variance

    def calculate_alpha(
        self,
        portfolio_returns: pd.Series,
        benchmark_returns: pd.Series,
        risk_free_rate: float = 0
    ) -> float:
        """
        Calculate Jensen's alpha.

        Alpha = Rp - [Rf + Beta * (Rm - Rf)]
        """
        beta = self.calculate_beta(portfolio_returns, benchmark_returns)

        portfolio_mean = portfolio_returns.mean()
        benchmark_mean = benchmark_returns.mean()

        expected_return = risk_free_rate + beta * (benchmark_mean - risk_free_rate)
        alpha = portfolio_mean - expected_return

        return alpha

    def get_risk_metrics(self) -> dict:
        """Get comprehensive risk metrics vs benchmark."""
        portfolio_df = self.get_portfolio_returns()
        benchmark_df = self.get_benchmark_returns(period="2y")

        if portfolio_df.empty or benchmark_df.empty:
            return {}

        # Get quarterly benchmark returns to match filing frequency
        benchmark_df['date'] = pd.to_datetime(benchmark_df['date'])
        benchmark_quarterly = benchmark_df.resample('Q', on='date').last()

        portfolio_returns = portfolio_df['return'].dropna()
        benchmark_returns = benchmark_quarterly['return'].dropna()

        # Align by taking minimum length
        min_periods = min(len(portfolio_returns), len(benchmark_returns))

        if min_periods < 2:
            return {
                'error': 'Insufficient data for risk metrics'
            }

        portfolio_returns = portfolio_returns.tail(min_periods)
        benchmark_returns = benchmark_returns.tail(min_periods)

        return {
            'benchmark': self.benchmark,
            'periods': min_periods,
            'portfolio_mean_return': portfolio_returns.mean(),
            'benchmark_mean_return': benchmark_returns.mean(),
            'portfolio_volatility': portfolio_returns.std() * np.sqrt(4),
            'benchmark_volatility': benchmark_returns.std() * np.sqrt(4),
            'tracking_error': self.calculate_tracking_error(portfolio_returns, benchmark_returns),
            'information_ratio': self.calculate_information_ratio(portfolio_returns, benchmark_returns),
            'beta': self.calculate_beta(portfolio_returns, benchmark_returns),
            'alpha': self.calculate_alpha(portfolio_returns, benchmark_returns),
            'correlation': np.corrcoef(portfolio_returns, benchmark_returns)[0, 1]
        }

    def get_return_comparison_df(self) -> pd.DataFrame:
        """Get DataFrame comparing portfolio and benchmark returns over time."""
        portfolio_df = self.get_portfolio_returns()
        benchmark_df = self.get_benchmark_returns(period="2y")

        if portfolio_df.empty or benchmark_df.empty:
            return pd.DataFrame()

        # Resample benchmark to quarterly
        benchmark_df['date'] = pd.to_datetime(benchmark_df['date'])
        benchmark_quarterly = benchmark_df.resample('Q', on='date').agg({
            'close': 'last',
            'return': lambda x: ((1 + x / 100).prod() - 1) * 100,
            'cumulative_return': 'last'
        }).reset_index()

        comparison = pd.merge(
            portfolio_df[['report_date', 'return', 'cumulative_return']].rename(
                columns={'return': 'portfolio_return', 'cumulative_return': 'portfolio_cumulative'}
            ),
            benchmark_quarterly[['date', 'return', 'cumulative_return']].rename(
                columns={'date': 'report_date', 'return': 'benchmark_return', 'cumulative_return': 'benchmark_cumulative'}
            ),
            on='report_date',
            how='outer'
        )

        comparison['active_return'] = comparison['portfolio_return'] - comparison['benchmark_return']

        return comparison.sort_values('report_date')


if __name__ == "__main__":
    analyzer = TrackingErrorAnalyzer('baker-bros')

    print(f"Risk metrics vs {analyzer.benchmark}:")
    metrics = analyzer.get_risk_metrics()

    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")
