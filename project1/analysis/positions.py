"""
Position analysis for portfolio holdings.
"""

import pandas as pd
from typing import Optional

# NOTE: This module needs updating to use CSV storage (utils.csv_data)
# Database imports removed - module not currently used by dashboard
# TODO: Update to use load_latest_holdings, get_all_filings, load_holdings_by_date from utils.csv_data


class PositionAnalyzer:
    """Analyze portfolio positions and changes."""

    def __init__(self, fund_id: str):
        self.fund_id = fund_id

    def get_current_positions(self) -> pd.DataFrame:
        """Get current positions from latest filing."""
        latest_filing = get_latest_filing(self.fund_id)

        if not latest_filing:
            return pd.DataFrame()

        holdings = get_holdings_for_filing(latest_filing['id'])
        df = pd.DataFrame([dict(h) for h in holdings])

        if df.empty:
            return df

        # Calculate derived metrics
        total_value = df['value'].sum()
        df['weight'] = (df['value'] / total_value * 100).round(2)
        df['value_millions'] = (df['value'] / 1_000_000).round(2)

        return df.sort_values('value', ascending=False)

    def get_position_changes(
        self,
        filing_id_1: int,
        filing_id_2: int
    ) -> pd.DataFrame:
        """
        Compare positions between two filings.

        Args:
            filing_id_1: Earlier filing ID
            filing_id_2: Later filing ID

        Returns:
            DataFrame with position changes
        """
        holdings_1 = get_holdings_for_filing(filing_id_1)
        holdings_2 = get_holdings_for_filing(filing_id_2)

        df1 = pd.DataFrame([dict(h) for h in holdings_1])
        df2 = pd.DataFrame([dict(h) for h in holdings_2])

        if df1.empty or df2.empty:
            return pd.DataFrame()

        # Merge on company name (since CUSIPs can change)
        merged = pd.merge(
            df1[['company_name', 'shares', 'value']],
            df2[['company_name', 'shares', 'value']],
            on='company_name',
            how='outer',
            suffixes=('_old', '_new')
        )

        merged = merged.fillna(0)

        # Calculate changes
        merged['shares_change'] = merged['shares_new'] - merged['shares_old']
        merged['value_change'] = merged['value_new'] - merged['value_old']
        merged['shares_change_pct'] = (
            merged['shares_change'] / merged['shares_old'] * 100
        ).replace([float('inf'), float('-inf')], 100)

        # Categorize changes
        def categorize(row):
            if row['shares_old'] == 0:
                return 'NEW'
            elif row['shares_new'] == 0:
                return 'CLOSED'
            elif row['shares_change'] > 0:
                return 'INCREASED'
            elif row['shares_change'] < 0:
                return 'DECREASED'
            else:
                return 'UNCHANGED'

        merged['change_type'] = merged.apply(categorize, axis=1)

        return merged.sort_values('value_change', ascending=False)

    def get_quarter_over_quarter_changes(self) -> pd.DataFrame:
        """Get position changes from most recent two filings."""
        filings = get_all_filings(self.fund_id)

        if len(filings) < 2:
            return pd.DataFrame()

        return self.get_position_changes(filings[1]['id'], filings[0]['id'])

    def get_concentration_metrics(self) -> dict:
        """Calculate portfolio concentration metrics."""
        df = self.get_current_positions()

        if df.empty:
            return {}

        # Sort by weight
        df = df.sort_values('weight', ascending=False)

        # Top N concentration
        top_5_weight = df.head(5)['weight'].sum()
        top_10_weight = df.head(10)['weight'].sum()
        top_20_weight = df.head(20)['weight'].sum()

        # Herfindahl-Hirschman Index
        hhi = (df['weight'] ** 2).sum()

        # Number of positions by size
        large_positions = len(df[df['weight'] >= 5])
        medium_positions = len(df[(df['weight'] >= 1) & (df['weight'] < 5)])
        small_positions = len(df[df['weight'] < 1])

        return {
            'total_positions': len(df),
            'top_5_concentration': top_5_weight,
            'top_10_concentration': top_10_weight,
            'top_20_concentration': top_20_weight,
            'herfindahl_index': hhi,
            'large_positions': large_positions,
            'medium_positions': medium_positions,
            'small_positions': small_positions
        }

    def get_new_positions(self) -> pd.DataFrame:
        """Get positions that are new since last filing."""
        changes = self.get_quarter_over_quarter_changes()

        if changes.empty:
            return pd.DataFrame()

        return changes[changes['change_type'] == 'NEW']

    def get_closed_positions(self) -> pd.DataFrame:
        """Get positions that were closed since last filing."""
        changes = self.get_quarter_over_quarter_changes()

        if changes.empty:
            return pd.DataFrame()

        return changes[changes['change_type'] == 'CLOSED']

    def get_significant_changes(self, threshold_pct: float = 25) -> pd.DataFrame:
        """Get positions with significant changes (>threshold%)."""
        changes = self.get_quarter_over_quarter_changes()

        if changes.empty:
            return pd.DataFrame()

        return changes[abs(changes['shares_change_pct']) >= threshold_pct]


if __name__ == "__main__":
    analyzer = PositionAnalyzer('baker-bros')

    print("Current positions:")
    df = analyzer.get_current_positions()
    print(df.head(10)[['company_name', 'shares', 'value_millions', 'weight']])

    print("\nConcentration metrics:")
    metrics = analyzer.get_concentration_metrics()
    for key, value in metrics.items():
        print(f"  {key}: {value}")
