import sqlite3
import os

db_path = "data/karnataka_solar.db"
if not os.path.exists(db_path):
    print(f"Database NOT found at {db_path}")
else:
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cur.fetchall()
        print(f"Tables: {tables}")
        
        for table in ["default_readings", "ncep_readings", "stategen_readings"]:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                print(f"Table {table}: {count} records")
            except Exception as e:
                print(f"Error checking {table}: {e}")
        conn.close()
    except Exception as e:
        print(f"Connection error: {e}")
