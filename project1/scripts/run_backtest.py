"""
CLI entry point for the Strategy 1 backtest.

Usage:
    python scripts/run_backtest.py
    python scripts/run_backtest.py --contribution 500 --trade-day 2
    python scripts/run_backtest.py --hard-stop -0.35 --min-hold 6
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.strategy_engine import StrategyConfig, run_simulation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Strategy 1 (Top-10 Equal-Weight) backtest")
    parser.add_argument("--contribution", type=float, default=1000.0,
                        help="Monthly capital contribution in dollars (default: 1000)")
    parser.add_argument("--positions", type=int, default=10,
                        help="Max portfolio positions (default: 10)")
    parser.add_argument("--min-hold", type=int, default=3,
                        help="Minimum hold period in months before selling (default: 3)")
    parser.add_argument("--trade-day", type=int, default=1,
                        help="Nth trading day of month to execute trades (default: 1)")
    parser.add_argument("--hard-stop", type=float, default=-0.40,
                        help="Hard stop loss threshold, e.g. -0.40 for -40%% (default: -0.40)")
    parser.add_argument("--relative-bleed", type=float, default=-0.25,
                        help="Relative bleed absolute return threshold (default: -0.25)")
    parser.add_argument("--relative-bleed-xbi", type=float, default=-0.15,
                        help="Relative bleed XBI underperformance threshold (default: -0.15)")
    parser.add_argument("--freeze-threshold", type=float, default=-0.10,
                        help="Freeze threshold return, e.g. -0.10 for -10%% (default: -0.10)")
    parser.add_argument("--portfolio", type=str, default="baker-bros",
                        help="Portfolio ID (default: baker-bros)")
    args = parser.parse_args()

    config = StrategyConfig(
        monthly_contribution=args.contribution,
        max_positions=args.positions,
        min_hold_months=args.min_hold,
        trade_day=args.trade_day,
        hard_stop_return=args.hard_stop,
        relative_bleed_return=args.relative_bleed,
        relative_bleed_xbi_underperformance=args.relative_bleed_xbi,
        freeze_return_threshold=args.freeze_threshold,
        portfolio_id=args.portfolio,
    )

    print("=" * 60)
    print("Strategy 1: Baker Bros Top-10 Equal-Weight Backtest")
    print("=" * 60)
    print(f"Config: ${config.monthly_contribution:,.0f}/month | "
          f"max {config.max_positions} positions | "
          f"min hold {config.min_hold_months}mo | "
          f"trade day {config.trade_day}")
    print(f"        hard stop {config.hard_stop_return*100:.0f}% | "
          f"rel bleed {config.relative_bleed_return*100:.0f}% + XBI {config.relative_bleed_xbi_underperformance*100:.0f}pp | "
          f"freeze {config.freeze_return_threshold*100:.0f}%")
    print()

    positions_df, transactions_df, performance_df = run_simulation(config)

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    if not performance_df.empty:
        first = performance_df[performance_df["cumulative_invested"] > 0].iloc[0]
        last = performance_df.iloc[-1]
        print(f"Backtest period:    {first['date']} to {last['date']}")
        print(f"Cumulative invested: ${last['cumulative_invested']:>10,.2f}")
        print(f"Portfolio value:     ${last['portfolio_value']:>10,.2f}")
        print(f"Portfolio return:    {last['portfolio_return']*100:>+.1f}%")
        print(f"XBI return:          {last['xbi_return']*100:>+.1f}%")
        print(f"vs XBI:              {(last['portfolio_return'] - last['xbi_return'])*100:>+.1f}pp")

    if not positions_df.empty:
        active = positions_df[positions_df["status"] == "active"]
        frozen = positions_df[positions_df["status"] == "frozen"]
        sold = positions_df[positions_df["status"] == "sold"]
        print(f"\nPositions: {len(active)} active | {len(frozen)} frozen | {len(sold)} sold")

    if not transactions_df.empty:
        buys = transactions_df[transactions_df["action"] == "buy"]
        sells = transactions_df[transactions_df["action"] == "sell"]
        freezes = transactions_df[transactions_df["action"] == "freeze"]
        print(f"Transactions: {len(buys)} buys | {len(sells)} sells | {len(freezes)} freezes")


if __name__ == "__main__":
    main()
