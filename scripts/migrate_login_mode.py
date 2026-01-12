
import sqlite3
import os

DB_PATH = "data/app.db"

def add_login_mode_col():
    if not os.path.exists(DB_PATH):
        print(f"DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT login_mode FROM accounts LIMIT 1")
        print("Column 'login_mode' already exists.")
    except sqlite3.OperationalError:
        print("Adding 'login_mode' column...")
        cursor.execute("ALTER TABLE accounts ADD COLUMN login_mode TEXT DEFAULT 'auto'")
        conn.commit()
    
    conn.close()

if __name__ == "__main__":
    add_login_mode_col()
