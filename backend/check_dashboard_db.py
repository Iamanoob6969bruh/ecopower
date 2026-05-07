import sqlite3
import os

db_path = "dashboard.db"
if not os.path.exists(db_path):
    print(f"Database NOT found at {db_path}")
else:
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cur.fetchall()
        print(f"Tables: {tables}")
        
        for table_tuple in tables:
            table = table_tuple[0]
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"Table {table}: {count} records")
        conn.close()
    except Exception as e:
        print(f"Error: {e}")
