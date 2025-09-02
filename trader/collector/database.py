# collector/database.py
import sqlite3
import logging
from pathlib import Path

# Place the database in a 'data' directory at the project root.
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "trading_data.db"
DB_PATH.parent.mkdir(exist_ok=True) # Ensure the 'data' directory exists

def get_db_connection():
    """Establishes and returns a database connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """
    Creates the necessary database tables if they don't already exist.
    This function should be run once when setting up the collector.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Table for historical item data (value, rap, demand, etc.)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS item_market_history (
            timestamp INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            value INTEGER,
            rap INTEGER,
            demand INTEGER,
            trend INTEGER,
            projected INTEGER,
            hyped INTEGER,
            rare INTEGER,
            PRIMARY KEY (timestamp, item_id)
        )
    ''')

    # Table to log completed/inactive trades for training data
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trade_history (
            trade_id INTEGER PRIMARY KEY,
            partner_id INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('Completed', 'Inactive')),
            created_timestamp INTEGER NOT NULL,
            last_updated_timestamp INTEGER NOT NULL,
            profit_rap INTEGER,
            trade_type TEXT
        )
    ''')

    # Table to store the assets involved in each trade
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trade_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER NOT NULL,
            asset_id INTEGER NOT NULL,
            asset_name TEXT NOT NULL,
            is_giving INTEGER NOT NULL, -- 1 if giving, 0 if receiving
            value INTEGER,
            rap INTEGER,
            FOREIGN KEY (trade_id) REFERENCES trade_history (trade_id)
        )
    ''')
    
    conn.commit()
    conn.close()
    logging.info(f"📚 Database initialized successfully at {DB_PATH}")

if __name__ == '__main__':
    # This allows you to set up the database by running: python -m collector.database
    initialize_database()
