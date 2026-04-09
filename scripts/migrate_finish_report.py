import sqlite3
import os

def migrate():
    db_path = "data/bot_database.db"
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Add report_type column
        cursor.execute("ALTER TABLE report_submissions ADD COLUMN report_type VARCHAR DEFAULT 'start'")
        print("Added column 'report_type' to 'report_submissions'")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("Column 'report_type' already exists")
        else:
            print(f"Error adding 'report_type': {e}")

    try:
        # Add end_time column
        cursor.execute("ALTER TABLE report_submissions ADD COLUMN end_time VARCHAR")
        print("Added column 'end_time' to 'report_submissions'")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("Column 'end_time' already exists")
        else:
            print(f"Error adding 'end_time': {e}")

    conn.commit()
    conn.close()
    print("Migration finished")

if __name__ == "__main__":
    migrate()
