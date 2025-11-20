"""
Database utilities for SQLite operations.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from config.settings import DATABASE_PATH


def get_connection():
    """Get a database connection."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_cursor():
    """Context manager for database cursor."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    finally:
        conn.close()


def init_database():
    """Initialize the database with required tables."""
    with get_cursor() as cursor:
        # Funds table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS funds (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                cik TEXT NOT NULL UNIQUE,
                description TEXT,
                benchmark TEXT,
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Filings table (13F submissions)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS filings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fund_id TEXT NOT NULL,
                accession_number TEXT NOT NULL UNIQUE,
                filing_date DATE NOT NULL,
                report_date DATE NOT NULL,
                form_type TEXT DEFAULT '13F-HR',
                total_value REAL,
                num_holdings INTEGER,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (fund_id) REFERENCES funds(id)
            )
        """)

        # Holdings table (positions from each filing)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filing_id INTEGER NOT NULL,
                cusip TEXT,
                ticker TEXT,
                company_name TEXT NOT NULL,
                share_class TEXT,
                shares REAL NOT NULL,
                value REAL NOT NULL,
                option_type TEXT,
                investment_discretion TEXT,
                voting_authority_sole REAL,
                voting_authority_shared REAL,
                voting_authority_none REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (filing_id) REFERENCES filings(id)
            )
        """)

        # Prices table (historical stock prices)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                date DATE NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                adj_close REAL,
                volume INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, date)
            )
        """)

        # Benchmarks table (benchmark index data)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS benchmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                date DATE NOT NULL,
                close REAL NOT NULL,
                adj_close REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(ticker, date)
            )
        """)

        # Create indexes for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_holdings_filing ON holdings(filing_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_holdings_ticker ON holdings(ticker)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_filings_fund ON filings(fund_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_filings_date ON filings(report_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON prices(ticker, date)")

    print(f"Database initialized at {DATABASE_PATH}")


def insert_fund(fund_data: dict):
    """Insert or update a fund."""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT OR REPLACE INTO funds (id, name, cik, description, benchmark, active)
            VALUES (:id, :name, :cik, :description, :benchmark, :active)
        """, fund_data)


def insert_filing(filing_data: dict) -> int:
    """Insert a filing and return its ID."""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT OR IGNORE INTO filings
            (fund_id, accession_number, filing_date, report_date, form_type, total_value, num_holdings, source)
            VALUES (:fund_id, :accession_number, :filing_date, :report_date, :form_type, :total_value, :num_holdings, :source)
        """, filing_data)

        # Get the filing ID
        cursor.execute("SELECT id FROM filings WHERE accession_number = ?", (filing_data['accession_number'],))
        result = cursor.fetchone()
        return result['id'] if result else None


def insert_holdings(holdings: list, filing_id: int):
    """Insert holdings for a filing."""
    with get_cursor() as cursor:
        for holding in holdings:
            holding['filing_id'] = filing_id
            cursor.execute("""
                INSERT INTO holdings
                (filing_id, cusip, ticker, company_name, share_class, shares, value,
                 option_type, investment_discretion, voting_authority_sole,
                 voting_authority_shared, voting_authority_none)
                VALUES (:filing_id, :cusip, :ticker, :company_name, :share_class, :shares, :value,
                        :option_type, :investment_discretion, :voting_authority_sole,
                        :voting_authority_shared, :voting_authority_none)
            """, holding)


def insert_prices(prices: list):
    """Insert price data."""
    with get_cursor() as cursor:
        for price in prices:
            cursor.execute("""
                INSERT OR REPLACE INTO prices
                (ticker, date, open, high, low, close, adj_close, volume)
                VALUES (:ticker, :date, :open, :high, :low, :close, :adj_close, :volume)
            """, price)


def get_latest_filing(fund_id: str):
    """Get the most recent filing for a fund."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT * FROM filings
            WHERE fund_id = ?
            ORDER BY report_date DESC
            LIMIT 1
        """, (fund_id,))
        return cursor.fetchone()


def get_holdings_for_filing(filing_id: int):
    """Get all holdings for a specific filing."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT * FROM holdings
            WHERE filing_id = ?
            ORDER BY value DESC
        """, (filing_id,))
        return cursor.fetchall()


def get_all_filings(fund_id: str):
    """Get all filings for a fund."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT * FROM filings
            WHERE fund_id = ?
            ORDER BY report_date DESC
        """, (fund_id,))
        return cursor.fetchall()


def get_price_history(ticker: str, start_date: str = None, end_date: str = None):
    """Get price history for a ticker."""
    with get_cursor() as cursor:
        query = "SELECT * FROM prices WHERE ticker = ?"
        params = [ticker]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        query += " ORDER BY date"
        cursor.execute(query, params)
        return cursor.fetchall()


if __name__ == "__main__":
    init_database()
