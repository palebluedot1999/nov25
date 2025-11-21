"""
Database utilities for SQLite operations.
Redesigned schema for multi-portfolio support with proper security master table.
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime
from config.settings import DATABASE_PATH


def get_connection():
    """Get a database connection."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
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
        # 1. Securities Master Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS securities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cusip TEXT UNIQUE,
                ticker TEXT,
                company_name TEXT NOT NULL,
                share_class TEXT,
                asset_class TEXT,
                sector TEXT,
                industry TEXT,
                exchange TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. Portfolios (replaces funds, includes benchmarks and user portfolios)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolios (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                portfolio_type TEXT NOT NULL,
                cik TEXT,
                description TEXT,
                benchmark_id TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (benchmark_id) REFERENCES portfolios(id)
            )
        """)

        # 3. Strategies
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                description TEXT,
                category TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 4. Tags
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                tag_type TEXT,
                color TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 5. Filings (13F filing metadata)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS filings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id TEXT NOT NULL,
                accession_number TEXT NOT NULL UNIQUE,
                filing_date DATE NOT NULL,
                report_date DATE NOT NULL,
                form_type TEXT DEFAULT '13F-HR',
                total_value REAL,
                num_positions INTEGER,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id)
            )
        """)

        # 6. Transactions (all trade activity)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id TEXT NOT NULL,
                security_id INTEGER NOT NULL,
                transaction_date DATE NOT NULL,
                transaction_time TIME,
                transaction_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL,
                fees REAL DEFAULT 0,
                total_value REAL,
                strategy_id INTEGER,
                source TEXT,
                filing_id INTEGER,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
                FOREIGN KEY (security_id) REFERENCES securities(id),
                FOREIGN KEY (strategy_id) REFERENCES strategies(id),
                FOREIGN KEY (filing_id) REFERENCES filings(id)
            )
        """)

        # 7. Holdings (position snapshots per portfolio)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id TEXT NOT NULL,
                security_id INTEGER NOT NULL,
                as_of_date DATE NOT NULL,
                shares REAL NOT NULL,
                cost_basis REAL,
                market_value REAL,
                filing_id INTEGER,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
                FOREIGN KEY (security_id) REFERENCES securities(id),
                FOREIGN KEY (filing_id) REFERENCES filings(id),
                UNIQUE(portfolio_id, security_id, as_of_date)
            )
        """)

        # 8. Prices (historical OHLCV data)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                security_id INTEGER,
                ticker TEXT NOT NULL,
                date DATE NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                adj_close REAL,
                volume INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (security_id) REFERENCES securities(id),
                UNIQUE(ticker, date)
            )
        """)

        # 9. Benchmark Prices
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS benchmark_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                date DATE NOT NULL,
                close REAL NOT NULL,
                adj_close REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
                UNIQUE(portfolio_id, date)
            )
        """)

        # 10. Transaction Tags (many-to-many)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transaction_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
                UNIQUE(transaction_id, tag_id)
            )
        """)

        # 11. Holding Tags (many-to-many)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS holding_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                holding_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (holding_id) REFERENCES holdings(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
                UNIQUE(holding_id, tag_id)
            )
        """)

        # 12. Security CUSIP History (track ticker changes)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS security_cusip_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                security_id INTEGER NOT NULL,
                cusip TEXT,
                ticker TEXT,
                company_name TEXT,
                effective_date DATE NOT NULL,
                end_date DATE,
                change_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (security_id) REFERENCES securities(id)
            )
        """)

        # 13. Statistics (flexible stats storage)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id TEXT,
                security_id INTEGER,
                stat_type TEXT NOT NULL,
                stat_name TEXT NOT NULL,
                stat_value REAL,
                stat_text TEXT,
                calculation_date DATE NOT NULL,
                as_of_date DATE NOT NULL,
                period TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id),
                FOREIGN KEY (security_id) REFERENCES securities(id)
            )
        """)

        # Create indexes for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_securities_cusip ON securities(cusip)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_securities_ticker ON securities(ticker)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_portfolios_type ON portfolios(portfolio_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_filings_portfolio ON filings(portfolio_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_filings_date ON filings(report_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_portfolio ON transactions(portfolio_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_security ON transactions(security_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_holdings_portfolio ON holdings(portfolio_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_holdings_security ON holdings(security_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_holdings_date ON holdings(as_of_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_prices_security ON prices(security_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_prices_ticker_date ON prices(ticker, date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_benchmark_prices_portfolio ON benchmark_prices(portfolio_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_statistics_portfolio ON statistics(portfolio_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_statistics_security ON statistics(security_id)")

    print(f"Database initialized at {DATABASE_PATH}")


# ============================================================================
# SECURITIES
# ============================================================================

def insert_security(security_data: dict) -> int:
    """Insert or update a security and return its ID."""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO securities (cusip, ticker, company_name, share_class, asset_class,
                                   sector, industry, exchange, is_active, updated_at)
            VALUES (:cusip, :ticker, :company_name, :share_class, :asset_class,
                    :sector, :industry, :exchange, :is_active, CURRENT_TIMESTAMP)
            ON CONFLICT(cusip) DO UPDATE SET
                ticker = EXCLUDED.ticker,
                company_name = EXCLUDED.company_name,
                share_class = EXCLUDED.share_class,
                asset_class = EXCLUDED.asset_class,
                sector = EXCLUDED.sector,
                industry = EXCLUDED.industry,
                exchange = EXCLUDED.exchange,
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP
        """, security_data)

        # Get the security ID
        cursor.execute("SELECT id FROM securities WHERE cusip = ?", (security_data.get('cusip'),))
        result = cursor.fetchone()
        return result['id'] if result else cursor.lastrowid


def get_security_by_cusip(cusip: str) -> Optional[sqlite3.Row]:
    """Get security by CUSIP."""
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM securities WHERE cusip = ?", (cusip,))
        return cursor.fetchone()


def get_security_by_ticker(ticker: str) -> Optional[sqlite3.Row]:
    """Get security by ticker."""
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM securities WHERE ticker = ? AND is_active = 1", (ticker,))
        return cursor.fetchone()


def get_security_by_id(security_id: int) -> Optional[sqlite3.Row]:
    """Get security by ID."""
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM securities WHERE id = ?", (security_id,))
        return cursor.fetchone()


# ============================================================================
# PORTFOLIOS
# ============================================================================

def insert_portfolio(portfolio_data: dict):
    """Insert or update a portfolio."""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT OR REPLACE INTO portfolios
            (id, name, portfolio_type, cik, description, benchmark_id, is_active, updated_at)
            VALUES (:id, :name, :portfolio_type, :cik, :description, :benchmark_id, :is_active, CURRENT_TIMESTAMP)
        """, portfolio_data)


def get_portfolio(portfolio_id: str) -> Optional[sqlite3.Row]:
    """Get portfolio by ID."""
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM portfolios WHERE id = ?", (portfolio_id,))
        return cursor.fetchone()


def get_all_portfolios(portfolio_type: Optional[str] = None) -> List[sqlite3.Row]:
    """Get all portfolios, optionally filtered by type."""
    with get_cursor() as cursor:
        if portfolio_type:
            cursor.execute("SELECT * FROM portfolios WHERE portfolio_type = ? AND is_active = 1", (portfolio_type,))
        else:
            cursor.execute("SELECT * FROM portfolios WHERE is_active = 1")
        return cursor.fetchall()


# ============================================================================
# STRATEGIES
# ============================================================================

def insert_strategy(strategy_data: dict) -> int:
    """Insert a strategy and return its ID."""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT OR IGNORE INTO strategies (code, name, description, category, is_active)
            VALUES (:code, :name, :description, :category, :is_active)
        """, strategy_data)

        cursor.execute("SELECT id FROM strategies WHERE code = ?", (strategy_data['code'],))
        result = cursor.fetchone()
        return result['id'] if result else cursor.lastrowid


def get_all_strategies() -> List[sqlite3.Row]:
    """Get all active strategies."""
    with get_cursor() as cursor:
        cursor.execute("SELECT * FROM strategies WHERE is_active = 1 ORDER BY category, name")
        return cursor.fetchall()


# ============================================================================
# TAGS
# ============================================================================

def insert_tag(tag_data: dict) -> int:
    """Insert a tag and return its ID."""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT OR IGNORE INTO tags (name, tag_type, color, description)
            VALUES (:name, :tag_type, :color, :description)
        """, tag_data)

        cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_data['name'],))
        result = cursor.fetchone()
        return result['id'] if result else cursor.lastrowid


def get_all_tags(tag_type: Optional[str] = None) -> List[sqlite3.Row]:
    """Get all tags, optionally filtered by type."""
    with get_cursor() as cursor:
        if tag_type:
            cursor.execute("SELECT * FROM tags WHERE tag_type = ? ORDER BY name", (tag_type,))
        else:
            cursor.execute("SELECT * FROM tags ORDER BY tag_type, name")
        return cursor.fetchall()


# ============================================================================
# FILINGS
# ============================================================================

def insert_filing(filing_data: dict) -> int:
    """Insert a filing and return its ID."""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT OR IGNORE INTO filings
            (portfolio_id, accession_number, filing_date, report_date, form_type,
             total_value, num_positions, source)
            VALUES (:portfolio_id, :accession_number, :filing_date, :report_date, :form_type,
                    :total_value, :num_positions, :source)
        """, filing_data)

        cursor.execute("SELECT id FROM filings WHERE accession_number = ?",
                      (filing_data['accession_number'],))
        result = cursor.fetchone()
        return result['id'] if result else None


def get_latest_filing(portfolio_id: str) -> Optional[sqlite3.Row]:
    """Get the most recent filing for a portfolio."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT * FROM filings
            WHERE portfolio_id = ?
            ORDER BY report_date DESC
            LIMIT 1
        """, (portfolio_id,))
        return cursor.fetchone()


def get_all_filings(portfolio_id: str) -> List[sqlite3.Row]:
    """Get all filings for a portfolio."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT * FROM filings
            WHERE portfolio_id = ?
            ORDER BY report_date DESC
        """, (portfolio_id,))
        return cursor.fetchall()


# ============================================================================
# TRANSACTIONS
# ============================================================================

def insert_transaction(transaction_data: dict) -> int:
    """Insert a transaction and return its ID."""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO transactions
            (portfolio_id, security_id, transaction_date, transaction_time, transaction_type,
             quantity, price, fees, total_value, strategy_id, source, filing_id, notes, updated_at)
            VALUES (:portfolio_id, :security_id, :transaction_date, :transaction_time, :transaction_type,
                    :quantity, :price, :fees, :total_value, :strategy_id, :source, :filing_id, :notes,
                    CURRENT_TIMESTAMP)
        """, transaction_data)
        return cursor.lastrowid


def get_transactions(portfolio_id: str, start_date: Optional[str] = None,
                     end_date: Optional[str] = None) -> List[sqlite3.Row]:
    """Get transactions for a portfolio, optionally filtered by date range."""
    with get_cursor() as cursor:
        query = """
            SELECT t.*, s.ticker, s.company_name, st.name as strategy_name
            FROM transactions t
            JOIN securities s ON t.security_id = s.id
            LEFT JOIN strategies st ON t.strategy_id = st.id
            WHERE t.portfolio_id = ?
        """
        params = [portfolio_id]

        if start_date:
            query += " AND t.transaction_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND t.transaction_date <= ?"
            params.append(end_date)

        query += " ORDER BY t.transaction_date DESC, t.transaction_time DESC"
        cursor.execute(query, params)
        return cursor.fetchall()


def delete_transaction(transaction_id: int):
    """Delete a transaction by ID."""
    with get_cursor() as cursor:
        cursor.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))


# ============================================================================
# HOLDINGS
# ============================================================================

def insert_holding(holding_data: dict) -> int:
    """Insert or update a holding and return its ID."""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO holdings
            (portfolio_id, security_id, as_of_date, shares, cost_basis, market_value,
             filing_id, source, updated_at)
            VALUES (:portfolio_id, :security_id, :as_of_date, :shares, :cost_basis, :market_value,
                    :filing_id, :source, CURRENT_TIMESTAMP)
            ON CONFLICT(portfolio_id, security_id, as_of_date) DO UPDATE SET
                shares = EXCLUDED.shares,
                cost_basis = EXCLUDED.cost_basis,
                market_value = EXCLUDED.market_value,
                filing_id = EXCLUDED.filing_id,
                source = EXCLUDED.source,
                updated_at = CURRENT_TIMESTAMP
        """, holding_data)
        return cursor.lastrowid


def get_holdings(portfolio_id: str, as_of_date: Optional[str] = None) -> List[sqlite3.Row]:
    """Get holdings for a portfolio, optionally as of a specific date."""
    with get_cursor() as cursor:
        if as_of_date:
            cursor.execute("""
                SELECT h.*, s.ticker, s.company_name, s.cusip, s.sector, s.industry
                FROM holdings h
                JOIN securities s ON h.security_id = s.id
                WHERE h.portfolio_id = ? AND h.as_of_date = ?
                ORDER BY h.market_value DESC
            """, (portfolio_id, as_of_date))
        else:
            # Get most recent holdings for each security
            cursor.execute("""
                SELECT h.*, s.ticker, s.company_name, s.cusip, s.sector, s.industry
                FROM holdings h
                JOIN securities s ON h.security_id = s.id
                WHERE h.portfolio_id = ?
                AND h.as_of_date = (
                    SELECT MAX(as_of_date) FROM holdings
                    WHERE portfolio_id = h.portfolio_id AND security_id = h.security_id
                )
                ORDER BY h.market_value DESC
            """, (portfolio_id,))
        return cursor.fetchall()


def get_holdings_for_filing(filing_id: int) -> List[sqlite3.Row]:
    """Get all holdings for a specific filing."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT h.*, s.ticker, s.company_name, s.cusip, s.sector, s.industry
            FROM holdings h
            JOIN securities s ON h.security_id = s.id
            WHERE h.filing_id = ?
            ORDER BY h.market_value DESC
        """, (filing_id,))
        return cursor.fetchall()


# ============================================================================
# PRICES
# ============================================================================

def insert_prices(prices: List[dict]):
    """Insert price data."""
    with get_cursor() as cursor:
        for price in prices:
            cursor.execute("""
                INSERT OR REPLACE INTO prices
                (security_id, ticker, date, open, high, low, close, adj_close, volume)
                VALUES (:security_id, :ticker, :date, :open, :high, :low, :close, :adj_close, :volume)
            """, price)


def get_price_history(ticker: str, start_date: Optional[str] = None,
                      end_date: Optional[str] = None) -> List[sqlite3.Row]:
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


# ============================================================================
# BENCHMARK PRICES
# ============================================================================

def insert_benchmark_prices(benchmark_prices: List[dict]):
    """Insert benchmark price data."""
    with get_cursor() as cursor:
        for price in benchmark_prices:
            cursor.execute("""
                INSERT OR REPLACE INTO benchmark_prices
                (portfolio_id, ticker, date, close, adj_close)
                VALUES (:portfolio_id, :ticker, :date, :close, :adj_close)
            """, price)


def get_benchmark_price_history(portfolio_id: str, start_date: Optional[str] = None,
                                end_date: Optional[str] = None) -> List[sqlite3.Row]:
    """Get benchmark price history for a portfolio."""
    with get_cursor() as cursor:
        query = "SELECT * FROM benchmark_prices WHERE portfolio_id = ?"
        params = [portfolio_id]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        query += " ORDER BY date"
        cursor.execute(query, params)
        return cursor.fetchall()


# ============================================================================
# STATISTICS
# ============================================================================

def insert_statistic(stat_data: dict) -> int:
    """Insert a statistic and return its ID."""
    with get_cursor() as cursor:
        cursor.execute("""
            INSERT INTO statistics
            (portfolio_id, security_id, stat_type, stat_name, stat_value, stat_text,
             calculation_date, as_of_date, period, metadata)
            VALUES (:portfolio_id, :security_id, :stat_type, :stat_name, :stat_value, :stat_text,
                    :calculation_date, :as_of_date, :period, :metadata)
        """, stat_data)
        return cursor.lastrowid


def get_statistics(portfolio_id: Optional[str] = None, stat_type: Optional[str] = None) -> List[sqlite3.Row]:
    """Get statistics, optionally filtered by portfolio and/or type."""
    with get_cursor() as cursor:
        query = "SELECT * FROM statistics WHERE 1=1"
        params = []

        if portfolio_id:
            query += " AND portfolio_id = ?"
            params.append(portfolio_id)
        if stat_type:
            query += " AND stat_type = ?"
            params.append(stat_type)

        query += " ORDER BY calculation_date DESC"
        cursor.execute(query, params)
        return cursor.fetchall()


if __name__ == "__main__":
    init_database()
