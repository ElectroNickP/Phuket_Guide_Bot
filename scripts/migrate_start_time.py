"""
Migration: add start_time column to report_submissions table.
Run once: python scripts/migrate_start_time.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "bot_database.db")

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(report_submissions)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if "start_time" not in columns:
        cursor.execute("ALTER TABLE report_submissions ADD COLUMN start_time TEXT")
        print("✅ Added 'start_time' column to report_submissions.")
    else:
        print("ℹ️ Column 'start_time' already exists.")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
