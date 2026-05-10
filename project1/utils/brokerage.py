import pandas as pd
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
BROKERAGE_HOLDINGS_FILE = RAW_DATA_DIR / "brokerage_holdings.csv"
STAGED_TRADES_FILE = RAW_DATA_DIR / "staged_trades.csv"
TRADE_LOG_FILE = RAW_DATA_DIR / "trade_log.csv"

HOLDINGS_COLS = ["ticker", "shares", "last_updated"]
STAGED_COLS = ["ticker", "action", "suggested_shares", "actual_shares", "exec_price", "notes"]
LOG_COLS = ["executed_at", "strategy", "ticker", "action", "suggested_shares", "actual_shares", "exec_price", "total_value", "notes"]


def load_brokerage_holdings() -> pd.DataFrame:
    if not BROKERAGE_HOLDINGS_FILE.exists():
        return pd.DataFrame({
            "ticker": pd.Series(dtype="str"),
            "shares": pd.Series(dtype="float64"),
            "last_updated": pd.Series(dtype="str"),
        })
    return pd.read_csv(BROKERAGE_HOLDINGS_FILE)


def save_brokerage_holdings(df: pd.DataFrame) -> None:
    df = df.copy()
    df["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    df[HOLDINGS_COLS].to_csv(BROKERAGE_HOLDINGS_FILE, index=False)


def load_staged_trades() -> pd.DataFrame:
    if not STAGED_TRADES_FILE.exists():
        return pd.DataFrame(columns=STAGED_COLS)
    return pd.read_csv(STAGED_TRADES_FILE)


def save_staged_trades(df: pd.DataFrame) -> None:
    df[STAGED_COLS].to_csv(STAGED_TRADES_FILE, index=False)


def clear_staged_trades() -> None:
    pd.DataFrame(columns=STAGED_COLS).to_csv(STAGED_TRADES_FILE, index=False)


def load_trade_log() -> pd.DataFrame:
    if not TRADE_LOG_FILE.exists():
        return pd.DataFrame(columns=LOG_COLS)
    return pd.read_csv(TRADE_LOG_FILE)


def save_trade_log(df: pd.DataFrame) -> None:
    """Overwrite the trade log with an edited DataFrame. Recomputes total_value."""
    df = df.copy()
    df["total_value"] = (df["actual_shares"].abs() * df["exec_price"]).round(2)
    df["notes"] = df["notes"].fillna("").astype(str)
    df[LOG_COLS].to_csv(TRADE_LOG_FILE, index=False)


def confirm_execution(staged_df: pd.DataFrame, strategy_name: str, notes: str = "") -> None:
    """Append staged trades to trade log, update holdings, clear staging area.

    Note: not atomic — if save_brokerage_holdings() fails, staging is already cleared
    and the partial update cannot be replayed. Acceptable limitation of CSV-only storage.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_rows = []
    for _, row in staged_df.iterrows():
        actual = float(row.get("actual_shares") if pd.notna(row.get("actual_shares")) else row["suggested_shares"])
        price = float(row.get("exec_price") if pd.notna(row.get("exec_price")) else 0)
        row_notes = str(row.get("notes") or "") or notes
        log_rows.append({
            "executed_at": now,
            "strategy": strategy_name,
            "ticker": row["ticker"],
            "action": row["action"],
            "suggested_shares": float(row["suggested_shares"]),
            "actual_shares": actual,
            "exec_price": price,
            "total_value": round(abs(actual) * price, 2),
            "notes": row_notes,
        })

    new_log = pd.DataFrame(log_rows, columns=LOG_COLS)
    if TRADE_LOG_FILE.exists():
        existing = pd.read_csv(TRADE_LOG_FILE)
        new_log = pd.concat([existing, new_log], ignore_index=True)
    new_log.to_csv(TRADE_LOG_FILE, index=False)

    # Update brokerage holdings
    holdings = load_brokerage_holdings()
    for _, row in staged_df.iterrows():
        actual = float(row.get("actual_shares") if pd.notna(row.get("actual_shares")) else row["suggested_shares"])
        ticker = str(row["ticker"])
        if row["action"] == "BUY":
            delta = actual
        elif row["action"] == "SELL":
            delta = -actual
        else:
            raise ValueError(f"Unknown action '{row['action']}' for ticker {row['ticker']}")
        if ticker in holdings["ticker"].values:
            holdings.loc[holdings["ticker"] == ticker, "shares"] += delta
        else:
            holdings = pd.concat(
                [holdings, pd.DataFrame([{"ticker": ticker, "shares": delta, "last_updated": now}])],
                ignore_index=True,
            )

    save_brokerage_holdings(holdings)
    clear_staged_trades()
