"""
Run portfolio strategy backtesting engine.

Simulates all 8 strategy streams (4 strategies × 2 variants) using Baker Bros
13F data and daily price history. Outputs three CSV files to data/processed/.

Usage:
    python scripts/run_backtest.py
    python scripts/run_backtest.py --contribution 500
    python scripts/run_backtest.py --streams 1.0 1.1
"""

import sys
import argparse
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.strategy_config import StrategyConfig, STREAM_IDS
from utils.strategy_engine import run_backtest
from utils.csv_data import PROCESSED_DATA_DIR


def main():
    parser = argparse.ArgumentParser(description="Run strategy backtest")
    parser.add_argument(
        "--contribution", type=float, default=1000.0,
        help="Monthly capital contribution (default: $1,000)",
    )
    parser.add_argument(
        "--streams", nargs="+", default=None,
        help="Stream IDs to run (default: all 8)",
    )
    args = parser.parse_args()

    config = StrategyConfig(monthly_contribution=args.contribution)
    streams = args.streams or STREAM_IDS

    print("=" * 60)
    print("Portfolio Strategy Backtest")
    print("=" * 60)
    print(f"  Monthly contribution: ${config.monthly_contribution:,.0f}")
    print(f"  Streams: {', '.join(streams)}")
    print(f"  Benchmark: {config.benchmark_ticker}")
    print(f"  Portfolio: {config.portfolio_id}")
    print()

    positions_df, transactions_df, performance_df = run_backtest(config, streams)

    if positions_df.empty:
        print("ERROR: Backtest produced no output.")
        return

    # Save outputs
    print()
    print("Saving output CSVs...")
    pos_path = PROCESSED_DATA_DIR / "strategy_positions.csv"
    txn_path = PROCESSED_DATA_DIR / "strategy_transactions.csv"
    perf_path = PROCESSED_DATA_DIR / "strategy_performance.csv"

    positions_df.to_csv(pos_path, index=False)
    transactions_df.to_csv(txn_path, index=False)
    performance_df.to_csv(perf_path, index=False)

    print(f"  {pos_path.name}: {len(positions_df):,} rows")
    print(f"  {txn_path.name}: {len(transactions_df):,} rows")
    print(f"  {perf_path.name}: {len(performance_df):,} rows")

    # Summary stats
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)

    for sid in streams:
        stream_pos = positions_df[positions_df["stream_id"] == sid]
        active = len(stream_pos[stream_pos["status"] == "active"])
        frozen = len(stream_pos[stream_pos["status"] == "frozen"])
        sold = len(stream_pos[stream_pos["status"] == "sold"])

        stream_perf = performance_df[performance_df["stream_id"] == sid]
        if not stream_perf.empty:
            latest = stream_perf.iloc[-1]
            port_ret = latest["portfolio_return"] * 100
            xbi_ret = latest["xbi_return"] * 100
            invested = latest["cumulative_invested"]
        else:
            port_ret = xbi_ret = invested = 0

        print(f"  {sid}: active={active}, frozen={frozen}, sold={sold} | "
              f"return={port_ret:+.1f}% vs XBI {xbi_ret:+.1f}% | "
              f"invested=${invested:,.0f}")

    print()
    print("Done.")


if __name__ == "__main__":
    main()
